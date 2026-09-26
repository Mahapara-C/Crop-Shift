"""
src/acquire/fetch_soilgrids.py

Builds data/reference/soil_params.csv: field capacity and wilting point
for each district, for the FAO-56 root-zone water balance
(src/compute/water_balance.py).

How each value is found (nothing is typed in by hand):
1. Clay / silt / sand % come from ISRIC SoilGrids 2.0 (free REST API),
   averaged over 0-100 cm (thickness-weighted) at a few points ~11 km
   around the district point. The district point itself is usually a
   town, which SoilGrids masks out (it returns no value there).
2. Those fractions are classified into a USDA texture class (the standard
   USDA texture-triangle rules).
3. theta_FC and theta_WP are the midpoints of that texture's range in
   FAO-56 Table 19. If the texture is not a Table 19 row, the script stops
   instead of guessing.

SoilGrids asks for at most 5 requests per minute, so this takes a few
minutes. Run from the repo root:
    python src/acquire/fetch_soilgrids.py
"""

import csv
import json
import os
import time
import requests

# "directions" = where to sample around the district point, in order of
# preference. Cumilla, Feni and Brahmanbaria are only ~5-10 km from the
# India (Tripura) border to the east, so they are sampled westward only:
# a point across the border would not describe the district's soil.
WEST_ONLY = ["N", "W", "S", "NW", "SW"]
DISTRICTS = {
    "cumilla":      {"lat": 23.4607, "lon": 91.1809, "directions": WEST_ONLY},
    "noakhali":     {"lat": 22.8696, "lon": 91.0995,
                     "directions": ["N", "W", "E", "NW", "NE", "S", "SW", "SE"]},
    "feni":         {"lat": 23.0159, "lon": 91.3976, "directions": WEST_ONLY},
    "brahmanbaria": {"lat": 23.9571, "lon": 91.1119, "directions": WEST_ONLY},
    "sylhet":       {"lat": 24.8949, "lon": 91.8687,
                     "directions": ["N", "E", "S", "W", "NE", "SE", "SW", "NW"]},
}
STEPS = {"N": (1, 0), "E": (0, 1), "S": (-1, 0), "W": (0, -1),
         "NE": (1, 1), "SE": (-1, 1), "SW": (-1, -1), "NW": (1, -1)}

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
DEPTHS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15, "30-60cm": 30, "60-100cm": 40}
RING_DEG = 0.1           # ~11 km: far enough to leave the town and its rivers
POINTS_WANTED = 4        # valid points averaged per district
SECONDS_BETWEEN_CALLS = 13  # stays under SoilGrids' 5 requests/minute

# FAO-56 (Allen et al., 1998) Chapter 7, Table 19: (theta_FC range, theta_WP range,
# (theta_FC - theta_WP) range), m3/m3. Copied from the FAO HTML edition. The source
# prints silty clay theta_FC as "0-30 - 0.42", a typo for 0.30 - 0.42.
TABLE_19 = {
    "sand":            ((0.07, 0.17), (0.02, 0.07), (0.05, 0.11)),
    "loamy sand":      ((0.11, 0.19), (0.03, 0.10), (0.06, 0.12)),
    "sandy loam":      ((0.18, 0.28), (0.06, 0.16), (0.11, 0.15)),
    "loam":            ((0.20, 0.30), (0.07, 0.17), (0.13, 0.18)),
    "silt loam":       ((0.22, 0.36), (0.09, 0.21), (0.13, 0.19)),
    "silt":            ((0.28, 0.36), (0.12, 0.22), (0.16, 0.20)),
    "silty clay loam": ((0.30, 0.37), (0.17, 0.24), (0.13, 0.18)),
    "silty clay":      ((0.30, 0.42), (0.17, 0.29), (0.13, 0.19)),
    "clay":            ((0.32, 0.40), (0.20, 0.24), (0.12, 0.20)),
}
# USDA classes missing from Table 19 (clay loam, sandy clay loam, sandy clay).
# A district whose SoilGrids texture is one of these uses the Table 19 class
# named here, and the reason is written into its CSV notes. Keyed by district
# AND expected texture, so a fallback never applies silently to new data.
TEXTURE_FALLBACK = {
    "brahmanbaria": {
        "texture": "clay loam", "use": "clay",
        "reason": ("{texture} has no Table 19 row. Its clay content ({clay:.1f}%) is "
                   "just under the 40% clay boundary of USDA clay, so the nearest Table 19 "
                   "class, clay, is used. The other neighbour, silty clay loam, gives almost "
                   "the same theta_FC - theta_WP (0.13 vs 0.14 m3/m3)."),
    },
    "sylhet": {
        "texture": "sandy clay loam", "use": "loam",
        "reason": ("{texture} has no Table 19 row. The nearest Table 19 class in the USDA "
                   "texture triangle is loam (this mean has clay {clay:.1f}% vs loam's upper "
                   "limit of 27%, and silt {silt:.1f}% vs loam's lower limit of 28%), so loam "
                   "is used. The other Table 19 neighbour, sandy loam, gives almost the same "
                   "theta_FC - theta_WP (0.12 vs 0.13 m3/m3)."),
    },
}
FAO56_TITLE = ("FAO Irrigation and Drainage Paper 56 (Allen, Pereira, Raes, Smith): "
               "Table 19, Typical soil water characteristics for different soil types")
FAO56_URL = "https://www.fao.org/4/x0490e/x0490e0c.htm"
SOILGRIDS_TITLE = ("ISRIC SoilGrids 2.0 (Poggio et al. 2021, SOIL 7:217-240), "
                   "mean {prop} content")

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                        "data", "reference", "soil_params.csv")
# Raw per-point answers, so a re-run does not hit the slow API again
# (data/raw/ is git-ignored). Delete the file to fetch everything fresh.
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                          "data", "raw", "soilgrids_points.json")


def usda_texture(sand, silt, clay):
    """USDA soil texture class from sand/silt/clay percentages (the standard
    texture-triangle rules, as in the NRCS texture calculator)."""
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 2 * clay < 30:
        return "loamy sand"
    if (7 <= clay < 20 and sand > 52) or (clay < 7 and silt < 50):
        return "sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "silt loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "clay loam"
    if 27 <= clay < 40 and sand <= 20:
        return "silty clay loam"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 40 and silt >= 40:
        return "silty clay"
    return "clay"


def query_point(lat, lon):
    """0-100 cm thickness-weighted clay/silt/sand % at one point, or None
    if SoilGrids has no value at any depth there."""
    params = [("lon", lon), ("lat", lat), ("value", "mean")]
    params += [("property", p) for p in ("clay", "silt", "sand")]
    params += [("depth", d) for d in DEPTHS]
    for attempt in range(6):  # the free API often answers 503 or stalls for a while
        try:
            response = requests.get(URL, params=params, timeout=180)
            if response.status_code not in (429, 502, 503, 504):
                break
            problem = f"HTTP {response.status_code}"
        except (requests.Timeout, requests.ConnectionError) as err:
            problem = type(err).__name__
        wait = 30 * (attempt + 1)
        print(f"  SoilGrids busy ({problem}), retrying in {wait} s")
        time.sleep(wait)
    else:
        raise RuntimeError("SoilGrids did not answer after 6 attempts; try again later")
    response.raise_for_status()
    result = {}
    for layer in response.json()["properties"]["layers"]:
        d_factor = layer["unit_measure"]["d_factor"]  # g/kg / 10 = %
        total = 0.0
        for depth in layer["depths"]:
            value = depth["values"]["mean"]
            if value is None:
                return None
            total += (value / d_factor) * DEPTHS[depth["label"]]
        result[layer["name"]] = total / sum(DEPTHS.values())
    return result


def ring_points(lat, lon, directions):
    """Points RING_DEG away from (lat, lon) in the given compass directions."""
    return [(round(lat + STEPS[d][0] * RING_DEG, 4), round(lon + STEPS[d][1] * RING_DEG, 4))
            for d in directions]


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1)


def district_texture(name, lat, lon, directions, cache):
    found = []
    for plat, plon in ring_points(lat, lon, directions):
        key = f"{plat:.4f},{plon:.4f}"
        if key not in cache:
            cache[key] = query_point(plat, plon)
            save_cache(cache)
            time.sleep(SECONDS_BETWEEN_CALLS)
        point = cache[key]
        if point is not None:
            found.append(((plat, plon), point))
            print(f"  {name} ({plat}, {plon}): {point}")
        if len(found) == POINTS_WANTED:
            break
    if not found:
        raise RuntimeError(f"SoilGrids returned no data around {name}")
    mean = {p: sum(pt[p] for _, pt in found) / len(found) for p in ("clay", "silt", "sand")}
    scale = 100.0 / sum(mean.values())  # SoilGrids fractions can sum to 99-101
    mean = {p: v * scale for p, v in mean.items()}
    per_point = [usda_texture(pt["sand"], pt["silt"], pt["clay"]) for _, pt in found]
    return mean, [xy for xy, _ in found], per_point


def rows_for_district(name, mean, points, per_point):
    texture = usda_texture(mean["sand"], mean["silt"], mean["clay"])
    table_class, fallback_note = texture, ""
    if texture not in TABLE_19:
        fallback = TEXTURE_FALLBACK.get(name)
        if fallback is None or fallback["texture"] != texture:
            raise RuntimeError(f"{name}: texture '{texture}' has no FAO-56 Table 19 row "
                               "and no reviewed TEXTURE_FALLBACK; not writing a guessed value")
        table_class = fallback["use"]
        fallback_note = " " + fallback["reason"].format(texture=texture, **mean)
    fc_range, wp_range, taw_range = TABLE_19[table_class]
    fc = round(sum(fc_range) / 2, 3)
    wp = round(sum(wp_range) / 2, 3)
    where = "; ".join(f"({lat}, {lon})" for lat, lon in points)
    grid_note = (f"Thickness-weighted 0-100 cm mean of {len(points)} SoilGrids points ~11 km "
                 f"around the district point: {where}. Per-point USDA classes: "
                 f"{', '.join(per_point)}. Sampled around, not at, the district point, "
                 f"which is a town (SoilGrids masks urban areas).")
    texture_note = (f"Texture assumption: USDA {texture}, classified from this district's "
                    f"SoilGrids 0-100 cm mean (clay {mean['clay']:.1f}%, silt "
                    f"{mean['silt']:.1f}%, sand {mean['sand']:.1f}%; see the *_pct rows)."
                    f"{fallback_note}")
    rows = []
    for prop in ("clay", "silt", "sand"):
        rows.append({
            "item": f"{name}.{prop}_pct", "value": round(mean[prop], 1), "unit": "%",
            "source_title": SOILGRIDS_TITLE.format(prop=prop),
            "source_url": URL, "page": "REST API v2.0 properties/query, depths 0-100 cm",
            "year": 2021, "notes": grid_note,
        })
    rows.append({
        "item": f"{name}.theta_fc_m3m3", "value": fc, "unit": "m3/m3",
        "source_title": FAO56_TITLE, "source_url": FAO56_URL,
        "page": "Chapter 7, Table 19", "year": 1998,
        "notes": f"{texture_note} Value = midpoint of the Table 19 {table_class} theta_FC "
                 f"range {fc_range[0]}-{fc_range[1]}.",
    })
    rows.append({
        "item": f"{name}.theta_wp_m3m3", "value": wp, "unit": "m3/m3",
        "source_title": FAO56_TITLE, "source_url": FAO56_URL,
        "page": "Chapter 7, Table 19", "year": 1998,
        "notes": f"{texture_note} Value = midpoint of the Table 19 {table_class} theta_WP "
                 f"range {wp_range[0]}-{wp_range[1]}. theta_FC - theta_WP = "
                 f"{fc - wp:.3f}, inside Table 19's {taw_range[0]}-{taw_range[1]}.",
    })
    return rows


def main():
    rows = []
    cache = load_cache()
    for name, loc in DISTRICTS.items():
        print(f"Fetching {name} ...")
        mean, points, per_point = district_texture(name, loc["lat"], loc["lon"],
                                                   loc["directions"], cache)
        rows += rows_for_district(name, mean, points, per_point)
    columns = ["item", "value", "unit", "source_title", "source_url", "page", "year", "notes"]
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {os.path.normpath(OUT_PATH)}")


if __name__ == "__main__":
    main()
