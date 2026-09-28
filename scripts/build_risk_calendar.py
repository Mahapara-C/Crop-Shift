"""
scripts/build_risk_calendar.py

Builds the sowing-date risk calendar (src/compute/risk_calendar.py) for the
5 districts, seasons 2001-2024, and writes:
  data/processed/risk_calendar.csv   one row per district x crop x sowing date
  docs/results/risk_calendar.md      rotation options after an aman harvest on
                                     Nov 15 and Dec 5, sanity checks,
                                     assumptions, sensitivity and DATA GAPS

Run from the repo root:
    python scripts/build_risk_calendar.py
"""

import os
import sys
import time

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "compute"))
from risk_calendar import (ASSUMPTIONS, skipped_note, DISTRICT_METADATA_PATH, HORIZON_DAYS,  # noqa: E402
                           REFERENCE_FILES, RISK_CALENDAR_PATH, SEASONS, build_calendar,
                           build_crop_specs, crop_calendar, district_area,
                           load_reference_for_calendar, paddy_percolation, prepare_weather,
                           resolve_paddy, rotation_options, threshold_value)
from water_balance import load_soil_params  # noqa: E402
from weather import RAIN_CITATIONS  # noqa: E402

OUT_MD = os.path.join(ROOT, "docs", "results", "risk_calendar.md")
HARVESTS = ("2024-11-15", "2024-12-05")      # aman harvest dates for the rotation tables
PLANNED_NEXT = "boro_rice"                   # the fit check: does the rabi crop clear boro's window?
WHEAT_SANITY = [(11, 15), (12, 15), (12, 22), (12, 29)]
BORO_SANITY = [(12, 5), (1, 15)]


def fmt(x, digits=0):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "–"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        return f"{x:.{digits}f}" if digits else f"{round(x):d}"
    return str(x)


def table(rows, columns):
    """Markdown table from a list of dicts; columns = [(header, key or fn)]."""
    lines = ["| " + " | ".join(h for h, _ in columns) + " |",
             "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        cells = [(key(row) if callable(key) else fmt(row.get(key))) for _, key in columns]
        lines.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ")
                                       for c in cells) + " |")
    return "\n".join(lines)


def day_label(date_str):
    return pd.Timestamp(date_str).strftime("%b %d") if date_str else "–"


def short_source(citations):
    titles = []
    for c in citations:
        t = c["source_title"].split("(")[0].split(",")[0].strip()[:40]
        if t not in titles:
            titles.append(t)
    return "; ".join(titles)


def crop_status_rows(specs):
    rows = []
    for crop, spec in specs.items():
        w = spec["window"]
        stages = ", ".join(
            f"{k} {v['value']:.0f} d" + (f" ({v['low']:.0f}-{v['high']:.0f})" if v["low"] != v["high"]
                                          and not k.startswith("tuber") else "")
            for k, v in spec["stage_days"].items()) or "none cited"
        live = "; ".join(
            f"{h['hazard']} ({h['op'] if 'op' in h else '>='}"
            f"{threshold_value(h, 'onset'):g}"
            + (f", severe {threshold_value(h, 'severe'):g}" if h["threshold"]["low"] != h["threshold"]["high"] else "")
            + (" C" if h["kind"] == "temp" else " saturated days") + f"; {short_source(h['threshold']['citations'])})"
            for h in spec["hazards"]) or "none"
        missing = "; ".join(m["hazard"] for m in spec["missing"]) or "none"
        base = spec["base_temp"]
        rows.append({
            "crop": crop,
            "window": f"{w['start'][0]:02d}-{w['start'][1]:02d} to {w['end'][0]:02d}-{w['end'][1]:02d} ({w['method']})" if w else "none",
            "method": spec["stage_method"] + (f" (base {base['value']:g} C)" if spec["stage_method"] == "gdd" else ""),
            "stages": stages, "live": live, "missing": missing})
    return rows


def problem_cell(r):
    return r["problem_line"]


def coverage_cell(r):
    if not r["hazards_checked"]:
        return "–"
    if r["coverage"] == "full":
        return "full"
    return f"partial — {r['coverage_notice']}"


def rotation_rows(result, areas):
    rows = []
    for o in result["options"]:
        rows.append({**o, "area": areas.get(o["crop"], {}).get("ha")})
    return rows


def sanity_checks(specs, weather, districts):
    wheat = specs["wheat"]
    heat = [h["hazard"] for h in wheat["hazards"] if h["hazard"].startswith("heat")]
    wheat_rows = []
    for d in districts:
        cal = {r["sowing_mmdd"]: r for r in crop_calendar(d, wheat, weather[d], SEASONS,
                                                            sow_dates=WHEAT_SANITY,
                                                            sensitivity=False)}
        years = {k: r["problem_years"] for k, r in cal.items()}  # any heat hazard
        per = {k: "/".join(str(r[f"problem_years_{h}"]) for h in heat) for k, r in cal.items()}
        ok = all(years[k] >= years["11-15"] for k in ("12-15", "12-22", "12-29"))
        wheat_rows.append({"district": d, **{k: f"{years[k]} ({per[k]})" for k in years},
                           "result": "PASS" if ok else "FAIL"})
    boro = specs["boro_rice"]
    boro_live = any(h["hazard"] == "cold_booting" for h in boro["hazards"])
    boro_rows = []
    if boro_live:
        for d in districts:
            cal = {r["sowing_mmdd"]: r for r in crop_calendar(d, boro, weather[d], SEASONS,
                                                                sow_dates=BORO_SANITY,
                                                                sensitivity=False)}
            a, b = cal["12-05"]["problem_years_cold_booting"], cal["01-15"]["problem_years_cold_booting"]
            boro_rows.append({"district": d, "12-05": a, "01-15": b,
                              "result": "PASS" if a >= b else "FAIL"})
    boro_reason = "; ".join(m["reason"] for m in boro["missing"] if m["hazard"] == "cold_booting")
    return heat, wheat_rows, boro_live, boro_rows, boro_reason


def zoning_conflicts(ref, districts):
    """Skipped CZIS zoning rows that say 'Not Suitable' where BBS reports area."""
    zoning = ref.skipped[ref.skipped["item"].str.startswith("zoning.")]
    rows = []
    for _, z in zoning.iterrows():
        _, district, crop = z["item"].split(".", 2)
        area = district_area(ref, district).get(crop, {}).get("ha")
        if z["value"].strip().lower() == "not suitable" and area:
            rows.append({"district": district, "crop": crop, "czis": z["value"], "bbs_ha": area})
    return zoning, rows


def main():
    t0 = time.time()
    metadata = pd.read_csv(DISTRICT_METADATA_PATH).set_index("district")
    districts = list(metadata.index)
    ref = load_reference_for_calendar()
    specs = build_crop_specs(ref)
    weather = {d: prepare_weather(d, metadata) for d in districts}
    calendar = build_calendar(districts, specs, ref, weather_by_district=weather)
    calendar.to_csv(RISK_CALENDAR_PATH, index=False, float_format="%.3f")
    print(f"wrote {RISK_CALENDAR_PATH} ({len(calendar)} rows)")

    soils, paddy = load_soil_params(), resolve_paddy(ref)
    heat, wheat_rows, boro_live, boro_rows, boro_reason = sanity_checks(specs, weather, districts)
    zoning, conflicts = zoning_conflicts(ref, districts)

    md = []
    md.append("# Sowing-date risk calendar (task 6)\n")
    md.append(
        "For each district, crop and weekly sowing date, the table in `data/processed/risk_calendar.csv` "
        f"counts in how many of the {len(SEASONS)} seasons {SEASONS[0]}-{SEASONS[-1]} NASA data for the "
        "area around a field showed a problem: a **sourced** hazard threshold crossed at a sensitive "
        "crop stage. Net irrigation and water-stress days come from the FAO-56 root-zone balance "
        "(`water_balance.py`). This is a record of past seasons for comparing options, **not a forecast** "
        "of the coming season.\n")
    md.append(f"- Rain: {RAIN_CITATIONS['imerg']['dataset']} ({RAIN_CITATIONS['imerg']['url']}). "
              "Temperature, humidity, wind, solar: NASA POWER daily (https://power.larc.nasa.gov/), "
              "via `load_weather()`. ET0: FAO-56 Penman-Monteith.")
    md.append("- Researched values: `data/reference/` "
              f"({', '.join(REFERENCE_FILES)}), read by the strict loader `src/compute/reference.py`. "
              "Files in `data/reference/` were not edited; bad rows are skipped and listed under DATA GAPS.")
    md.append(f"- A season counts in `n_years` only if the weather covers {HORIZON_DAYS} days after sowing. "
              "Season Y = 1 Aug Y to 31 Jul Y+1. `worst20` = mean of the worst 20% of seasons.")
    md.append("- A crop with **no evaluable sourced hazard** has no problem-year share. It is listed "
              "but not ranked, because 'no hazard assessed' is not the same as 'no risk'.")
    md.append("- Feni and Noakhali share one NASA POWER cell, so their temperature-based results "
              "are the same; only their IMERG rain (and so the water numbers) differ.\n")

    md.append("## Which crops and hazards are live\n")
    md.append(table(crop_status_rows(specs), [
        ("crop", "crop"), ("sowing window", "window"), ("stage timing", "method"),
        ("cited stage days (mean climate, mid-window)", "stages"),
        ("live hazards (threshold; source)", "live"), ("not evaluable", "missing")]))
    md.append("\nWater stress days and net irrigation (FAO-56) are computed for wheat, mustard, "
              "lentil and potato. Boro rice gets a ponded-paddy water need instead (below). "
              "Water numbers are reported alongside the risk; they do not count as 'problems', "
              "because no source gives a stress-day threshold.\n")

    for harvest in HARVESTS:
        md.append(f"## Options after an aman harvest on {day_label(harvest)}\n")
        md.append(f"Earliest sowing = harvest + {ASSUMPTIONS['turnaround_days']['value']} days "
                  "turnaround (CropShift assumption), then the first weekly calendar date on or after "
                  "it. Ranked by problem-year share, then by worst-20% net irrigation. "
                  f"'fits before boro' = median maturity is on or before boro's transplanting "
                  "window end (Jan 30), for an aman - rabi crop - boro rotation. "
                  "Area = BBS district area, information only (not a filter).\n")
        for d in districts:
            result = rotation_options(d, harvest, planned_next_crop=PLANNED_NEXT, calendar=calendar)
            md.append(f"### {d.capitalize()} (earliest sowing {day_label(result['earliest_sowing_date'])})\n")
            md.append(table(rotation_rows(result, district_area(ref, d)), [
                ("rank", "rank"), ("crop", "crop"), ("sow", lambda r: day_label(r["sowing_date"])),
                ("window", "window"),
                ("window passed", "window_passed"),
                ("outside window", "outside_recommended_window"),
                ("problem years", problem_cell),
                ("hazards assessed", lambda r: r["hazards_assessed"] or "none"),
                ("coverage", coverage_cell),
                ("net irrigation mm (mean / worst20)",
                 lambda r: f"{fmt(r['irrigation_mm_mean'])} / {fmt(r['irrigation_mm_worst20'])}"),
                ("stress days (mean)", "stress_days_mean"),
                ("maturity", lambda r: day_label(r["maturity_date"])),
                ("fits before boro", "fits_before_next_crop"),
                ("BBS area ha", "area")]))
            md.append("")

    md.append("## Sanity checks (real data, thresholds not tuned)\n")
    md.append("**Wheat sown late (Dec 15-31) should have at least as many heat problem years as "
              f"wheat sown mid-November.** Cells: seasons (of {len(SEASONS)}) with any wheat heat "
              f"problem; in brackets the count per hazard ({' / '.join(heat)}), and a season "
              "can have both.\n")
    md.append(table(wheat_rows, [("district", "district")]
                    + [(f"{m:02d}-{d:02d}", f"{m:02d}-{d:02d}") for m, d in WHEAT_SANITY]
                    + [("result", "result")]))
    md.append("")
    md.append("**Boro transplanted in early December should have at least as many cold problem "
              "years as mid-January.**\n")
    if boro_live:
        md.append(table(boro_rows, [("district", "district"), ("12-05", "12-05"),
                                    ("01-15", "01-15"), ("result", "result")]))
    else:
        md.append(f"CANNOT RUN: boro cold at booting is not evaluable. Reason: {boro_reason}. "
                  "The BRRI rows that cite boro durations (140 d for BRRI dhan28, 160 d for "
                  "BRRI dhan29) and the 12-13 C booting cold threshold were skipped because their "
                  "source_url is a PDF file name, not an http(s) link. Adding the public BRRI URL "
                  "to those rows would unblock this check. The pytest for it is skipped, not passed.")
    md.append("")

    md.append("## Sensitivity of problem years to the CropShift assumptions\n")
    md.append("At each crop's sowing date after a Nov 15 aman harvest (as in the first rotation "
              "tables). `hot N` = at least N hot/cold days "
              "in the stage make a problem year (default 3). `severe` = the severe end of a cited "
              "threshold range. `window 15` = 15-day flowering window instead of 7.\n")
    sens = []
    for d in districts:
        for o in rotation_options(d, HARVESTS[0], calendar=calendar)["options"]:
            if o["sowing_date"] is None or not o["hazards_assessed"]:
                continue
            key = pd.Timestamp(o["sowing_date"]).strftime("%m-%d")
            hit = calendar[(calendar["district"] == d) & (calendar["crop"] == o["crop"])
                           & (calendar["sowing_mmdd"] == key)]
            sens.append({**hit.iloc[0].to_dict(), "sow": day_label(o["sowing_date"])})
    md.append(table(sens, [
        ("district", "district"), ("crop", "crop"), ("sow", "sow"),
        ("default (hot 3)", "problem_years"),
        ("hot 1", "problem_years_hot1"), ("hot 5", "problem_years_hot5"),
        ("severe", "problem_years_severe"), ("window 15", "problem_years_window15"),
        ("n", "n_years")]))
    md.append("")

    if paddy is not None:
        md.append("## Boro rice: ponded-paddy water need\n")
        md.append(f"Land preparation {paddy['land_prep_water']['value']:g} mm + daily ETc (FAO-56 rice Kc "
                  "from kc_table, 150 days from transplanting) + percolation - rain, keeping a "
                  f"{paddy['ponding_depth']['value']:g} mm water layer "
                  f"({short_source(paddy['land_prep_water']['citations'])}; percolation: "
                  f"clay {paddy['percolation_clay']['value']:g} mm/d, "
                  f"{short_source(paddy['percolation_clay']['citations'])}; loam "
                  f"{paddy['percolation_loam']['value']:g} mm/d, "
                  f"{short_source(paddy['percolation_loam']['citations'])}). "
                  "Totals in mm per season (mean / worst20). No boro hazard is evaluable, so these rows "
                  "carry water need only.\n")
        boro = calendar[calendar["crop"] == "boro_rice"]
        dates = ["12-05", "12-19", "01-02", "01-16", "01-30"]
        prow = []
        for d in districts:
            perc, cls = paddy_percolation(soils[d], paddy)
            r = {"district": d, "soil": f"{cls} ({perc:g} mm/d)"}
            for md_ in dates:
                x = boro[(boro["district"] == d) & (boro["sowing_mmdd"] == md_)]
                r[md_] = (f"{fmt(x.iloc[0]['irrigation_mm_mean'])} / {fmt(x.iloc[0]['irrigation_mm_worst20'])}"
                          if len(x) else "–")
            prow.append(r)
        md.append(table(prow, [("district", "district"), ("percolation class", "soil")]
                        + [(f"transplant {m}", m) for m in dates]))
        md.append("")

    md.append("## CropShift assumptions (not from a source)\n")
    md.append(table([{"name": k, **v} for k, v in ASSUMPTIONS.items()], [
        ("name", "name"), ("value", lambda r: fmt(r["value"])),
        ("sensitivity run", lambda r: ", ".join(str(s) for s in r["sensitivity"]) or "–"),
        ("what it means", "text")]))
    md.append("")

    md.append("## District crop area (information only)\n")
    crops_area = ["boro_rice", "aman_rice", "wheat", "potato"]
    md.append(table([{"district": d, **{c: district_area(ref, d).get(c, {}).get("ha") for c in crops_area}}
                     for d in districts],
                    [("district", "district")] + [(f"{c} ha", c) for c in crops_area]))
    md.append("\nSource: BBS crop estimates (rows in `crop_area_by_district.csv`). No BBS area rows "
              "exist for mustard or lentil. Area never filters or ranks crops.\n")
    md.append(f"**Zoning rows are not used as a filter.** The {len(zoning)} CZIS suitability rows "
              "were skipped by the loader (their source_url `czis.cropzoning.gov.bd` has no http(s) "
              "scheme), and they also conflict with BBS: CZIS says 'Not Suitable' where BBS "
              "reports substantial planted area:\n")
    md.append(table(conflicts, [("district", "district"), ("crop", "crop"), ("CZIS class", "czis"),
                                ("BBS area ha", "bbs_ha")]))
    md.append("")

    md.append("## DATA GAPS\n")
    counts = ref.skipped["reason"].value_counts()
    md.append("Skipped reference rows by reason: "
              + ", ".join(f"{r} {n}" for r, n in counts.items()) + f" (total {len(ref.skipped)}).\n")
    md.append("### Crops and hazards with no evaluable sourced threshold or stage\n")
    gaps = [m for spec in specs.values() for m in spec["missing"]]
    for crop, spec in specs.items():
        if "maturity" not in spec["stage_days"]:
            item = f"{crop}.stage.days_to_maturity"
            gaps.append({"crop": crop, "hazard": "(maturity date)",
                         "reason": f"no kept {item} row{skipped_note(ref, item)}; the "
                                   "'fits before next crop' check shows –"})
    md.append(table(gaps, [("crop", "crop"), ("hazard / item", "hazard"), ("reason", "reason")]))
    md.append("")
    md.append("### Every skipped reference row\n")
    md.append(table(ref.skipped.to_dict("records"), [
        ("file", "file"), ("line", "line"), ("item", "item"), ("reason", "reason"),
        ("detail", "detail")]))
    md.append("")

    with open(OUT_MD, "w", encoding="utf-8") as handle:
        handle.write("\n".join(md))
    print(f"wrote {OUT_MD} in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
