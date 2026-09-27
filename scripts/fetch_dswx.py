"""
scripts/fetch_dswx.py

Downloads OPERA DSWx-S1 (Dynamic Surface Water Extent from Sentinel-1) water
classification for a small window around each district point and saves:

    data/processed/dswx_<district>.csv   (date, water_fraction, valid_fraction, granule_id)

Access: NASA CMR granule search via earthaccess, authenticated with
EARTHDATA_TOKEN from .env, then a 300 m x 300 m windowed read of just the
granule's WTR band (Cloud-Optimized GeoTIFF range request) -- never the
whole scene, and the raster is never written to disk or committed.

WTR band codes (OPERA DSWx-S1 Product Spec v1.0.0, D-108761 Rev A):
  0 = not water, 1 = open water, 3 = inundated vegetation,
  250 = HAND-masked (topographically too high to ever be water),
  251 = layover/shadow-masked (radar geometry, no reliable reading here),
  255 = fill (outside the observed swath for this pass).
water_fraction = share of VALID window pixels (0, 1 or 3) classified as
water (1 or 3). valid_fraction = share of ALL window pixels that are valid
(excludes 250/251/255). A granule whose window is 100% masked/fill is
skipped (there is nothing to report for that pass).

Coverage: DSWx-S1 exists from 2023-12-01 globally, but CLAUDE.md notes it
only exists over this area (Feni/Cumilla, and in practice the neighbouring
Noakhali/Brahmanbaria points) from 21 Aug 2024 -- not Sylhet, whose flood
(June 2022) predates the mission entirely.

Resumable: granule IDs already saved are skipped, so re-running only spends
time on new scenes; progress is saved to disk every 10 new granules.

AREA MODE (--area, Task 7a-2). The district points are town centres, so a
300 m window sees buildings, not farmland. Area mode instead reads a
20 km x 20 km window centred on the point from every DSWx-S1 granule that
touches it -- the flood period (2024-08-21 to 2024-12-31) and a dry-season
reference (2025-01-01 to 2025-03-31) -- reprojected (nearest neighbour) onto
one fixed 30 m UTM grid per district so neighbouring tiles line up. Each
granule's window is cached as a small compressed array in
cache/dswx_area/<district>/ (gitignored; never the raw tile, never in git).
Then --build merges same-day granules, marks "permanent water" (water in
most valid reference scenes) and saves:

    data/processed/dswx_area_<district>.csv
        (date, flood_km2, flood_fraction, valid_fraction, n_scenes;
         2024-08-21 to 2025-03-31, i.e. flood period + reference rows)
    docs/results/img/dswx_flood_<district>_<date>.png   (feni, noakhali)

Run from the repo root:
    python scripts/fetch_dswx.py                          # 4 districts, Aug 2024 to today
    python scripts/fetch_dswx.py feni                      # one district
    python scripts/fetch_dswx.py feni --end 2024-12-31      # a shorter window (faster)
    python scripts/fetch_dswx.py --area --limit 5           # time 5 area reads
    python scripts/fetch_dswx.py --area                     # fetch all area windows
    python scripts/fetch_dswx.py --area --build             # CSVs + PNGs from cache
"""

import argparse
import os
import sys
import time

import earthaccess
import numpy as np
import pandas as pd
import rasterio
from dotenv import load_dotenv
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform
from rasterio.windows import from_bounds

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "acquire"))
sys.path.insert(0, os.path.join(ROOT, "src", "compute"))
from fetch_power import DISTRICTS  # noqa: E402
from flood_area import (combine_scenes, flood_mask, flood_stats,  # noqa: E402
                        permanent_water_mask)

SHORT_NAME = "OPERA_L3_DSWX-S1_V1"
SOURCE_URL = "https://podaac.jpl.nasa.gov/OPERA"
START_DATE = "2024-08-01"
WINDOW_M = 300.0  # metres square, centred on the point
VALID_CODES = {0, 1, 3}
WATER_CODES = {1, 3}
OUT_DIR = os.path.join(ROOT, "data", "processed")

# CLAUDE.md: "OPERA DSWx-S1 exists over Feni/Cumilla from 21 Aug 2024 only."
# Noakhali and Brahmanbaria points are close enough to share that coverage;
# Sylhet's flood predates the DSWx-S1 mission (data starts 2023-12-01), so
# its post-flood analysis uses SMAP alone (docs/results/post_flood.md).
DSWX_DISTRICTS = ("feni", "cumilla", "noakhali", "brahmanbaria")

CSV_COLUMNS = ["date", "water_fraction", "valid_fraction", "granule_id"]


def window_stats(fs, wtr_url, lon, lat, window_m=WINDOW_M):
    """Reads only a window_m x window_m metre window of one WTR GeoTIFF band
    around (lon, lat) via an HTTPS range request (no full-scene download).
    Returns (water_fraction, valid_fraction), or (None, None) if every pixel
    in the window is masked or fill."""
    half = window_m / 2
    with rasterio.open(fs.open(wtr_url)) as ds:
        cx, cy = transform("EPSG:4326", ds.crs, [lon], [lat])
        cx, cy = cx[0], cy[0]
        window = from_bounds(cx - half, cy - half, cx + half, cy + half, ds.transform)
        data = ds.read(1, window=window)
    valid = np.isin(data, list(VALID_CODES))
    if not valid.any():
        return None, None
    water = np.isin(data, list(WATER_CODES))
    return float(water[valid].sum() / valid.sum()), float(valid.sum() / data.size)


def load_saved(path):
    if not os.path.exists(path):
        return pd.DataFrame(columns=CSV_COLUMNS)
    return pd.read_csv(path)


def fetch_district(district, fs, start_date, end_date):
    lat, lon = DISTRICTS[district]["lat"], DISTRICTS[district]["lon"]
    path = os.path.join(OUT_DIR, f"dswx_{district}.csv")
    saved = load_saved(path)
    seen = set(saved["granule_id"])

    granules = earthaccess.search_data(short_name=SHORT_NAME, point=(lon, lat),
                                       temporal=(start_date, end_date))
    granules.sort(key=lambda g: g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"])
    todo = [g for g in granules if g["meta"]["native-id"] not in seen]
    print(f"  {district}: {len(granules)} granules found, {len(seen)} already saved, "
          f"{len(todo)} to fetch")

    rows = saved.to_dict("records")
    t0 = time.time()
    for i, granule in enumerate(todo, start=1):
        granule_id = granule["meta"]["native-id"]
        wtr_url = next(u for u in granule.data_links() if u.endswith("_B01_WTR.tif"))
        begin = granule["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
        date = pd.Timestamp(begin).normalize()
        try:
            water_frac, valid_frac = window_stats(fs, wtr_url, lon, lat)
        except Exception as err:
            print(f"    {date.date()}: read failed ({type(err).__name__}: {err}), skipped")
            continue
        if water_frac is None:
            print(f"    {date.date()}: window fully masked/fill, skipped")
            continue
        rows.append({"date": str(date.date()), "water_fraction": round(water_frac, 4),
                    "valid_fraction": round(valid_frac, 4), "granule_id": granule_id})
        if i % 10 == 0 or i == len(todo):
            elapsed = time.time() - t0
            print(f"    {i}/{len(todo)} fetched, {elapsed:.0f}s elapsed, "
                  f"~{elapsed / i:.1f}s/granule")
            pd.DataFrame(rows, columns=CSV_COLUMNS).sort_values("date").to_csv(path, index=False)
    pd.DataFrame(rows, columns=CSV_COLUMNS).sort_values("date").to_csv(path, index=False)
    return len(rows)


# ---------------- area mode (Task 7a-2) ----------------

AREA_SIZE_M = 20000.0
AREA_RES_M = 30.0
AREA_CACHE = os.path.join(ROOT, "cache", "dswx_area")
FLOOD_PERIOD = ("2024-08-21", "2024-12-31")
REFERENCE_PERIOD = ("2025-01-01", "2025-03-31")  # dry season: permanent-water baseline
IMG_DIR = os.path.join(ROOT, "docs", "results", "img")
MAP_DISTRICTS = ("feni", "noakhali")
MAP_TARGET_DATES = ("2024-08-21", "2024-09-05", "2024-09-25", "2024-10-15")
AREA_CSV_COLUMNS = ["date", "flood_km2", "flood_fraction", "valid_fraction", "n_scenes"]


def area_grid(lat, lon, size_m=AREA_SIZE_M, res=AREA_RES_M):
    """A fixed size_m x size_m grid of res-metre pixels in the point's UTM zone
    (north), snapped to multiples of res so it lines up with the DSWx-S1 MGRS
    tile grids. Returns (crs, affine, n_pixels_per_side)."""
    zone = int((lon + 180) // 6) + 1
    crs = CRS.from_epsg(32600 + zone)
    xs, ys = transform("EPSG:4326", crs, [lon], [lat])
    n = int(round(size_m / res))
    left = round((xs[0] - size_m / 2) / res) * res
    top = round((ys[0] + size_m / 2) / res) * res
    return crs, Affine(res, 0, left, 0, -res, top), n


def grid_bbox_lonlat(grid):
    """(west, south, east, north) in degrees covering the grid, for CMR search."""
    crs, aff, n = grid
    x0, x1 = aff.c, aff.c + n * aff.a
    y0, y1 = aff.f, aff.f + n * aff.e
    lons, lats = transform(crs, "EPSG:4326", [x0, x1, x0, x1], [y0, y0, y1, y1])
    return min(lons), min(lats), max(lons), max(lats)


def read_area(fs, wtr_url, grid):
    """The grid's window of one WTR band, read via HTTPS range requests
    (WarpedVRT only pulls the blocks it needs), nearest-neighbour, 255 outside."""
    crs, aff, n = grid
    with rasterio.open(fs.open(wtr_url)) as ds:
        with WarpedVRT(ds, crs=crs, transform=aff, width=n, height=n,
                       resampling=Resampling.nearest, src_nodata=255, nodata=255) as vrt:
            return vrt.read(1)


def parse_granule_id(granule_id):
    """OPERA_L3_DSWx-S1_T46QCL_20240821T120455Z_20251107T032635Z_S1A_30_v1.0
    -> (tile, sensing time, production time, UTC date "YYYY-MM-DD")."""
    parts = granule_id.split("_")
    tile, sensing, production = parts[3], parts[4], parts[5]
    return tile, sensing, production, f"{sensing[:4]}-{sensing[4:6]}-{sensing[6:8]}"


def dedupe_granules(granules):
    """Keeps only the latest production of each (tile, sensing time)."""
    best = {}
    for g in granules:
        tile, sensing, production, _ = parse_granule_id(g["meta"]["native-id"])
        kept = best.get((tile, sensing))
        if kept is None or production > parse_granule_id(kept["meta"]["native-id"])[2]:
            best[(tile, sensing)] = g
    return sorted(best.values(), key=lambda g: parse_granule_id(g["meta"]["native-id"])[1])


def fetch_area(district, fs, periods, limit=None):
    """Caches every granule's window for `district` over `periods`.
    Returns (n_read, seconds, n_still_to_read_before_limit)."""
    grid = area_grid(DISTRICTS[district]["lat"], DISTRICTS[district]["lon"])
    cache_dir = os.path.join(AREA_CACHE, district)
    os.makedirs(cache_dir, exist_ok=True)
    granules = []
    for start, end in periods:
        granules += earthaccess.search_data(short_name=SHORT_NAME,
                                            bounding_box=grid_bbox_lonlat(grid),
                                            temporal=(start, end))
    granules = dedupe_granules(granules)
    todo = [g for g in granules
            if not os.path.exists(os.path.join(cache_dir, g["meta"]["native-id"] + ".npz"))]
    n_todo = len(todo)
    print(f"  {district}: {len(granules)} granules touch the 20 km window, "
          f"{len(granules) - n_todo} cached, {n_todo} to read")
    if limit is not None:
        todo = todo[:limit]
    t0, n_read = time.time(), 0
    for i, granule in enumerate(todo, start=1):
        gid = granule["meta"]["native-id"]
        wtr_url = next(u for u in granule.data_links() if u.endswith("_B01_WTR.tif"))
        try:
            arr = read_area(fs, wtr_url, grid)
        except Exception as err:
            print(f"    {gid}: read failed ({type(err).__name__}: {err}), skipped")
            continue
        np.savez_compressed(os.path.join(cache_dir, gid + ".npz"), wtr=arr)
        n_read += 1
        if i % 10 == 0 or i == len(todo):
            elapsed = time.time() - t0
            print(f"    {i}/{len(todo)} read, {elapsed:.0f}s elapsed, ~{elapsed / i:.1f}s/granule")
    return n_read, time.time() - t0, n_todo


def load_cached_by_date(district, start, end):
    """{UTC date: [wtr arrays]} for the district's cached granules in [start, end]."""
    cache_dir = os.path.join(AREA_CACHE, district)
    by_date = {}
    for name in sorted(os.listdir(cache_dir)):
        if not name.endswith(".npz"):
            continue
        date = parse_granule_id(name[:-4])[3]
        if start <= date <= end:
            by_date.setdefault(date, []).append(np.load(os.path.join(cache_dir, name))["wtr"])
    return by_date


def save_flood_map(district, date, wtr, permanent, known, stats, path):
    """Small 2x-downsampled PNG: flood water, permanent water, land, no reading."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    valid = np.isin(wtr, (0, 1, 3)) & known
    classes = np.zeros(wtr.shape, dtype=np.uint8)            # 0 = no reading
    classes[valid] = 1                                        # 1 = land
    classes[wtr == 250] = 2                                   # 2 = high ground (HAND-masked)
    classes[valid & permanent & np.isin(wtr, (1, 3))] = 3     # 3 = permanent water
    classes[flood_mask(wtr, permanent, known)] = 4            # 4 = flood water
    small = classes[::2, ::2]
    colors = ["#c8c8c8", "#efe9dc", "#d9cbb0", "#0b3a6e", "#1f9bd6"]
    labels = ["no reading", "land", "high ground (HAND-masked)", "permanent water",
              "flood water"]
    fig, ax = plt.subplots(figsize=(3.6, 4.4), dpi=100)
    ax.imshow(small, cmap=ListedColormap(colors), vmin=0, vmax=4, interpolation="nearest")
    centre = small.shape[0] / 2
    ax.plot(centre, centre, marker="+", color="black", markersize=9, mew=1.2)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"{district.title()}, {date}\nflood water {stats['flood_km2']:.1f} km² "
                 f"({stats['flood_fraction'] * 100:.0f}% of valid area)", fontsize=8)
    ax.legend(handles=[Patch(color=c, label=l) for c, l in zip(colors, labels)],
              loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=2, fontsize=6,
              frameon=False)
    fig.text(0.5, 0.005, "NASA OPERA DSWx-S1, 20 km x 20 km around the town point (+)",
             ha="center", fontsize=5.5)
    fig.subplots_adjust(left=0.03, right=0.97, top=0.88, bottom=0.17)
    fig.savefig(path)
    plt.close(fig)


def build_area(district):
    """Cache -> data/processed/dswx_area_<district>.csv (+ PNG maps for MAP_DISTRICTS)."""
    grid = area_grid(DISTRICTS[district]["lat"], DISTRICTS[district]["lon"])
    pixel_km2 = (grid[1].a / 1000) ** 2
    reference = load_cached_by_date(district, *REFERENCE_PERIOD)
    ref_maps = [combine_scenes(arrs) for _, arrs in sorted(reference.items())]
    permanent, known = permanent_water_mask(ref_maps)
    print(f"  {district}: {len(ref_maps)} reference dates, permanent water "
          f"{permanent.sum() * pixel_km2:.1f} km2, {known.mean() * 100:.0f}% of pixels known")

    rows, maps = [], {}
    # rows cover the flood period AND the dry-season reference: the reference
    # rows show the method's own floor of non-permanent water (wet paddies,
    # radar speckle) when there is no flood
    scenes = load_cached_by_date(district, FLOOD_PERIOD[0], REFERENCE_PERIOD[1])
    for date, arrs in sorted(scenes.items()):
        wtr = combine_scenes(arrs)
        stats = flood_stats(wtr, permanent, known, pixel_km2)
        if stats["valid_fraction"] == 0:
            continue
        rows.append({"date": date, "flood_km2": round(stats["flood_km2"], 3),
                     "flood_fraction": round(stats["flood_fraction"], 4),
                     "valid_fraction": round(stats["valid_fraction"], 4),
                     "n_scenes": len(arrs)})
        maps[date] = (wtr, stats)
    df = pd.DataFrame(rows, columns=AREA_CSV_COLUMNS)
    path = os.path.join(OUT_DIR, f"dswx_area_{district}.csv")
    df.to_csv(path, index=False)
    print(f"  saved {path} ({len(df)} dates)")

    if district in MAP_DISTRICTS and len(df):
        os.makedirs(IMG_DIR, exist_ok=True)
        good = df[df["valid_fraction"] >= 0.5].reset_index(drop=True)
        offsets = pd.to_datetime(good["date"])
        for target in MAP_TARGET_DATES:
            date = good.loc[(offsets - pd.Timestamp(target)).abs().idxmin(), "date"]
            wtr, stats = maps[date]
            img = os.path.join(IMG_DIR, f"dswx_flood_{district}_{date}.png")
            save_flood_map(district, date, wtr, permanent, known, stats, img)
            print(f"  map {img} ({os.path.getsize(img) / 1024:.0f} KB)")
    return df


def main_area(districts, limit, build):
    if build:
        for district in districts:
            build_area(district)
        return
    fs = login()
    total_read, total_s, total_todo = 0, 0.0, 0
    for district in districts:
        n, secs, n_todo = fetch_area(district, fs, (FLOOD_PERIOD, REFERENCE_PERIOD), limit)
        total_read, total_s, total_todo = total_read + n, total_s + secs, total_todo + n_todo
    if total_read:
        per = total_s / total_read
        print(f"read {total_read} granule windows in {total_s:.0f}s (~{per:.1f}s/granule); "
              f"{total_todo} were outstanding -> ~{total_todo * per / 60:.0f} min for all")


def login():
    load_dotenv(os.path.join(ROOT, ".env"))
    if not os.environ.get("EARTHDATA_TOKEN"):
        sys.exit("EARTHDATA_TOKEN is not set in .env")
    auth = earthaccess.login(strategy="environment")
    if not auth.authenticated:
        sys.exit("earthaccess could not authenticate with EARTHDATA_TOKEN")
    return earthaccess.get_fsspec_https_session()


def main(districts, end_date):
    fs = login()
    for district in districts:
        if district not in DSWX_DISTRICTS:
            print(f"{district}: skipped -- no OPERA DSWx-S1 coverage here before its flood "
                  f"date (CLAUDE.md: DSWx-S1 exists over Feni/Cumilla from 21 Aug 2024 only)")
            continue
        print(f"{district}:")
        n = fetch_district(district, fs, START_DATE, end_date)
        print(f"  saved {n} observations total")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("districts", nargs="*", default=list(DSWX_DISTRICTS),
                        help="district names (default: all 4 with DSWx-S1 coverage)")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"),
                        help="last date to search (default: today)")
    parser.add_argument("--area", action="store_true",
                        help="20 km x 20 km flood-area mode (Task 7a-2)")
    parser.add_argument("--build", action="store_true",
                        help="with --area: build CSVs and PNG maps from the cache")
    parser.add_argument("--limit", type=int, default=None,
                        help="with --area: read at most this many granules per district")
    args = parser.parse_args()
    if args.area:
        main_area(args.districts, args.limit, args.build)
    else:
        main(args.districts, args.end)
