"""
scripts/run_hindcast.py

Task 5b/5c/5d: leave-one-year-out hindcast of rabi outcomes, the El Nino
lens, onset sensitivity and trends, for the five districts. Rain comes from
NASA GPM IMERG (load_weather() in src/compute/weather.py; task 5d): NASA
POWER rain has step changes around 1997 and 2014-15 (see
docs/results/rain_source_check.md). The primary window is seasons 2001-2024
(IMERG Final Run ends 2025-09-30, so season 2025 is not complete). The full
1981-2025 NASA POWER record is run too, but shown only in the appendix
data-consistency check. Writes docs/results/hindcast.md.

Run from the repo root (takes about 12 minutes):
    python scripts/run_hindcast.py
"""

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "compute"))
from agroclimate import build_feature_table  # noqa: E402
from enso import season_enso_labels  # noqa: E402
from hindcast import (seasonal_series, loo_hindcast, skill_table, compare_groups,  # noqa: E402
                      trend, onset_sensitivity, onset_shift_summary, unconfirmed_onset)
from water_balance import (load_crop_params, load_soil_params, weather_table,  # noqa: E402
                           crop_season_all_years, total_available_water)
from weather import load_weather, RAIN_CITATIONS  # noqa: E402

DATA = os.path.join(ROOT, "data", "processed")
ONI_PATH = os.path.join(ROOT, "data", "reference", "oni.csv")
OUT_PATH = os.path.join(ROOT, "docs", "results", "hindcast.md")

RAIN_SOURCE = "imerg"             # main analysis; the POWER run feeds the appendix only
YEARS = list(range(1981, 2026))   # full POWER record (appendix); season Y = Nov 1 of Y to Apr 30 of Y+1
EARLY = (1981, 2000)              # the part of the record added in task 5a
RECENT = (2001, 2024)             # primary window: IMERG starts 2001, its last season is 2024
WB_FIRST_YEAR = 1984              # POWER solar radiation (so ET0) starts 1984-01-01
DECISION_DATE = "10-31"
SOWING = "11-15"
CROPS = ("mustard", "wheat")
K = 5
SHARED_CELL = "noakhali"          # same POWER cell as Feni (temperature etc.): reported, never pooled
METHODS = ["analog_1", f"analog_{K}", "enso_phase"]
METHOD_NAMES = {"analog_1": "1 nearest analog", f"analog_{K}": f"mean of {K} nearest analogs",
                "enso_phase": "ENSO-phase average"}

# key: (label, unit, decimals)
OUTCOMES = {
    "rabi_rain": ("Rabi rain, Nov-Apr", "mm", 0),
    "mustard_irrigation": ("Mustard net irrigation", "mm", 0),
    "mustard_stress": ("Mustard rainfed water-stress days", "days", 1),
    "wheat_irrigation": ("Wheat net irrigation", "mm", 0),
    "wheat_stress": ("Wheat rainfed water-stress days", "days", 1),
}
LENS = {**OUTCOMES,
        "next_monsoon_rain": ("Next monsoon rain, Jun-Sep of Y+1", "mm", 0),
        "next_premonsoon_tmax": ("Next pre-monsoon mean Tmax, Mar-May of Y+1", "°C", 2)}
# key: (label, short name, unit, decimals)
TRENDS = {
    "rabi_rain": ("Rabi rain, Nov-Apr (season Y)", "rabi rain", "mm", 1),
    "jjas_rain": ("Jun-Sep rain (year Y)", "Jun-Sep rain", "mm", 1),
    "mam_tmax": ("Mar-May mean Tmax (year Y)", "Mar-May mean Tmax", "°C", 2),
    "mustard_irrigation": ("Mustard net irrigation (season Y)", "mustard irrigation", "mm", 1),
}


# ---------------- compute ----------------

def district_outcomes(daily, lat, elev, soil, crop_params, kc_table, years):
    """One row per season year Y with every outcome used in the report."""
    rain, tmax = daily["rainfall_mm"], daily["temp_max_c"]
    out = pd.DataFrame(index=years)
    out["rabi_rain"] = seasonal_series(rain, years, "11-01", "04-30", 0, 1)
    out["next_monsoon_rain"] = seasonal_series(rain, years, "06-01", "09-30", 1, 1)
    out["next_premonsoon_tmax"] = seasonal_series(tmax, years, "03-01", "05-31", 1, 1, how="mean")
    out["jjas_rain"] = seasonal_series(rain, years, "06-01", "09-30", 0, 0)
    out["mam_tmax"] = seasonal_series(tmax, years, "03-01", "05-31", 0, 0, how="mean")
    first = max(WB_FIRST_YEAR, daily.index.min().year)
    weather = weather_table(daily.loc[f"{first}-01-01":], lat, elev)
    for crop in CROPS:
        seasons = crop_season_all_years(crop, SOWING, weather, kc_table, crop_params, soil,
                                        years=range(first, years[-1] + 1))
        seasons = seasons.set_index("year")
        out[f"{crop}_irrigation"] = seasons["net_irrigation_mm"]
        out[f"{crop}_stress"] = seasons["water_stress_days"].astype(float)
    return out


def compute(rain_source, years):
    """Every result for one rain source over season years `years`. res["loo"]
    covers all of `years`; res["loo_recent"] only the primary window RECENT."""
    meta = pd.read_csv(os.path.join(DATA, "district_metadata.csv"))
    soil = load_soil_params()
    crop_params = load_crop_params()
    kc_table = pd.read_csv(os.path.join(DATA, "kc_table.csv"))
    oni = pd.read_csv(ONI_PATH)
    labels = season_enso_labels(oni, "ASO").reindex(years)
    labels_jas = season_enso_labels(oni, "JAS").reindex(years)
    only_recent = years[0] == RECENT[0] and years[-1] == RECENT[1]

    res = {"districts": list(meta["district"]), "labels": labels, "labels_jas": labels_jas,
           "outcomes": {}, "features": {}, "loo": {}, "loo_recent": {}, "onsets": [],
           "raw_mm": {}, "years": years, "rain_source": rain_source}
    for _, d in meta.iterrows():
        name = d["district"]
        print(f"{name} ({rain_source} rain): outcomes ...", flush=True)
        daily = load_weather(name, rain_source)
        outcomes = district_outcomes(daily, d["latitude"], d["elevation_m"],
                                     soil[name], crop_params, kc_table, years)
        feats = build_feature_table(daily, years=years, decision_date=DECISION_DATE)
        res["outcomes"][name], res["features"][name] = outcomes, feats
        print(f"{name} ({rain_source} rain): hindcast ...", flush=True)
        recent_feats = feats[(feats.index >= RECENT[0]) & (feats.index <= RECENT[1])]
        for key in OUTCOMES:
            res["loo_recent"][(name, key)] = loo_hindcast(
                outcomes[key].loc[RECENT[0]:RECENT[1]], recent_feats, labels["phase"], k=K)
            res["loo"][(name, key)] = (res["loo_recent"][(name, key)] if only_recent else
                                       loo_hindcast(outcomes[key], feats, labels["phase"], k=K))
        onsets = onset_sensitivity(daily["rainfall_mm"], years, decision_date=DECISION_DATE)
        onsets["district"] = name
        res["onsets"].append(onsets)
        # Irrigated run refills the root zone once depletion passes RAW (Zr = zr_min).
        for crop in CROPS:
            taw = total_available_water(soil[name]["theta_fc_m3m3"], soil[name]["theta_wp_m3m3"],
                                        crop_params[crop]["zr_min_m"])
            res["raw_mm"][(name, crop)] = crop_params[crop]["p"] * taw
    res["onsets"] = pd.concat(res["onsets"], ignore_index=True)
    return res


# ---------------- helpers ----------------

def pooled_districts(res):
    return [d for d in res["districts"] if d != SHARED_CELL]


def dname(d):
    return d.capitalize()


def row_name(d):
    return f"{dname(d)} (Feni's POWER cell; not pooled)" if d == SHARED_CELL else dname(d)


def fmt(x, decimals=0, sign=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:+.{decimals}f}" if sign else f"{x:.{decimals}f}"


def p_eq(p):
    """'p=0.03', 'p=0.004' or 'p<0.001'."""
    if p is None or np.isnan(p):
        return "p=n/a"
    if p < 0.001:
        return "p<0.001"
    return f"p={p:.3f}" if p < 0.01 else f"p={p:.2f}"


def significant(p):
    return p is not None and not np.isnan(p) and p < 0.05


def bold_if(text, p):
    return f"**{text}**" if significant(p) else text


def lower_first(text):
    return text[:1].lower() + text[1:]


def season_name(y):
    return f"{y}-{str(y + 1)[2:]}"


def skill_cell(row):
    text = f"{fmt(row['skill'], 2, sign=True)} ({int(row['wins'])}/{int(row['n'])}, {p_eq(row['sign_p'])})"
    return bold_if(text, row["sign_p"])


def pooled_skill(res, key, recent=True):
    """recent=True (default): primary window, 2001-2025. recent=False:
    full 1981-2025 record, appendix only."""
    source = res["loo_recent"] if recent else res["loo"]
    table = pd.concat([source[(d, key)] for d in pooled_districts(res)])
    return skill_table(table, METHODS)


def pooled_mean(res, key):
    """Mean over the pooled districts per season (NaN if any is missing)."""
    return pd.concat([res["outcomes"][d][key] for d in pooled_districts(res)],
                     axis=1).mean(axis=1, skipna=False)


def trend_series(s, key, period):
    first = max(period[0], WB_FIRST_YEAR) if key.startswith(CROPS) else period[0]
    return s.loc[first:period[1]]


def trend_results(res, period):
    out = {}
    for d in res["districts"]:
        for k in TRENDS:
            out[(d, k)] = trend(trend_series(res["outcomes"][d][k], k, period))
    for k in TRENDS:
        out[("pooled", k)] = trend(trend_series(pooled_mean(res, k), k, period))
    return out


def no_confirmed_onset(res, d, period):
    """Years in period whose analog features have no onset, or only an
    unconfirmed Oct 25-31 one."""
    feats = res["features"][d]
    years = range(period[0], period[1] + 1)
    return [y for y in years if y not in feats.index
            or unconfirmed_onset(feats.loc[y, "onset_doy"], y, DECISION_DATE)]


def unconfirmed_feature_years(res, d):
    feats = res["features"][d]
    return [y for y in feats.index if unconfirmed_onset(feats.loc[y, "onset_doy"], y, DECISION_DATE)]


def enso_lists(res, years):
    lab = res["labels"]
    el = [y for y in years if lab.loc[y, "phase"] == "el_nino"]
    strong = [y for y in years if lab.loc[y, "label"] == "strong_el_nino"]
    return el, strong, lab.loc[years, "phase"].value_counts()


def lens_rows(res, years):
    el, _, _ = enso_lists(res, years)
    out = []
    for key, (label, unit, dec) in LENS.items():
        s = pooled_mean(res, key).loc[years[0]:years[-1]]
        is_el = s.index.isin(el)
        out.append((key, label, unit, dec, compare_groups(s[is_el], s[~is_el])))
    return out


# ---------------- report sections ----------------

def section_glance(res, recent=True):
    lines = ["| Outcome | " + " | ".join(METHOD_NAMES[m] for m in METHODS) + " |",
             "|---|" + "---|" * len(METHODS)]
    for key, (label, unit, _) in OUTCOMES.items():
        sk = pooled_skill(res, key, recent)
        lines.append(f"| {label} ({unit}) | " +
                     " | ".join(skill_cell(sk.loc[m]) for m in METHODS) + " |")
    return "\n".join(lines)


def section_skill(res, recent=True):
    """recent=True (default): primary window, 2001-2025. recent=False:
    full 1981-2025 record, appendix only."""
    source = res["loo_recent"] if recent else res["loo"]
    parts = []
    for key, (label, unit, dec) in OUTCOMES.items():
        rows = [f"#### {label} ({unit})", "",
                "| District | seasons scored | MAE, long-term average | " +
                " | ".join(METHOD_NAMES[m] for m in METHODS) + " |",
                "|---|---|---|" + "---|" * len(METHODS)]

        def add(name, sk):
            rows.append(f"| {name} | {sk['n'].iloc[0]} | {fmt(sk['mae_reference'].iloc[0], dec)} | " +
                        " | ".join(skill_cell(sk.loc[m]) for m in METHODS) + " |")
        for d in pooled_districts(res):
            add(dname(d), skill_table(source[(d, key)], METHODS))
        add("**Pooled (4 districts)**", pooled_skill(res, key, recent))
        add(row_name(SHARED_CELL), skill_table(source[(SHARED_CELL, key)], METHODS))
        parts.append("\n".join(rows))
    return "\n\n".join(parts)


def section_consistency(res):
    heads = ["District", f"Jun-Sep rain, {EARLY[0]}-{EARLY[1]} (mm)",
             f"Jun-Sep rain, {RECENT[0]}-{RECENT[1]} (mm)",
             f"Rabi rain, {EARLY[0]}-{EARLY[1]} (mm)", f"Rabi rain, {RECENT[0]}-{RECENT[1]} (mm)",
             f"Mar-May Tmax, {EARLY[0]}-{EARLY[1]} (°C)", f"Mar-May Tmax, {RECENT[0]}-{RECENT[1]} (°C)",
             f"years without a confirmed onset, {EARLY[0]}-{EARLY[1]}",
             f"years without a confirmed onset, {RECENT[0]}-{RECENT[1]}"]
    rows = ["| " + " | ".join(heads) + " |", "|" + "---|" * len(heads)]
    n_early, n_recent = EARLY[1] - EARLY[0] + 1, RECENT[1] - RECENT[0] + 1

    def means(s, dec):
        return [fmt(s.loc[EARLY[0]:EARLY[1]].mean(), dec), fmt(s.loc[RECENT[0]:RECENT[1]].mean(), dec)]

    for d in pooled_districts(res) + ["pooled", SHARED_CELL]:
        if d == "pooled":
            o = {k: pooled_mean(res, k) for k in ("jjas_rain", "rabi_rain", "mam_tmax")}
            onset = ["", ""]
            name = "**Mean of 4 districts**"
        else:
            o = res["outcomes"][d]
            onset = [f"{len(no_confirmed_onset(res, d, EARLY))} of {n_early}",
                     f"{len(no_confirmed_onset(res, d, RECENT))} of {n_recent}"]
            name = row_name(d)
        cells = means(o["jjas_rain"], 0) + means(o["rabi_rain"], 0) + means(o["mam_tmax"], 2) + onset
        rows.append(f"| {name} | " + " | ".join(cells) + " |")
    table = "\n".join(rows)
    unconfirmed = "; ".join(f"{dname(d)}: {', '.join(map(str, unconfirmed_feature_years(res, d))) or 'none'}"
                            for d in res["districts"])
    missing = "; ".join(f"{dname(d)}: {', '.join(map(str, sorted(set(res['years']) - set(res['features'][d].index)))) or 'none'}"
                        for d in res["districts"])
    return table, unconfirmed, missing


def section_lens(res, years):
    """years: contiguous list of season years to restrict the lens to
    (RECENT for the primary window, res["years"] for the full-record appendix)."""
    el, strong, counts = enso_lists(res, years)
    lab = res["labels"]
    lines = ["| Outcome | n El Niño seasons | n other seasons | median, El Niño | median, other | "
             "difference (El Niño - other) | Mann-Whitney p |",
             "|---|---|---|---|---|---|---|"]
    for _, label, unit, dec, c in lens_rows(res, years):
        lines.append(f"| {label} ({unit}) | {c['n_group']} | {c['n_rest']} | "
                     f"{fmt(c['median_group'], dec)} | {fmt(c['median_rest'], dec)} | "
                     f"{bold_if(fmt(c['difference'], dec, sign=True), c['p'])} | "
                     f"{p_eq(c['p']).replace('p=', '').replace('p<', '<')} |")
    main = "\n".join(lines)

    heads = ["Season", "ONI ASO"] + [f"{LENS[k][0]} ({LENS[k][1]})" for k in LENS]
    rows = ["| " + " | ".join(heads) + " |", "|" + "---|" * len(heads)]
    means = {k: pooled_mean(res, k).loc[years[0]:years[-1]] for k in LENS}
    for y in strong:
        rows.append(f"| {season_name(y)} | {lab.loc[y, 'oni']:+.2f} | " +
                    " | ".join(fmt(means[k].get(y), LENS[k][2]) for k in LENS) + " |")
    rows.append("| Median, all seasons | | " +
                " | ".join(fmt(means[k].median(), LENS[k][2]) for k in LENS) + " |")
    strong_table = "\n".join(rows)

    heads = ["District"] + [f"{LENS[k][0]} ({LENS[k][1]})" for k in LENS]
    rows = ["| " + " | ".join(heads) + " |", "|" + "---|" * len(heads)]
    for d in pooled_districts(res) + [SHARED_CELL]:
        cells = []
        for k, (_, _, dec) in LENS.items():
            s = res["outcomes"][d][k].loc[years[0]:years[-1]]
            is_el = s.index.isin(el)
            c = compare_groups(s[is_el], s[~is_el])
            cells.append(bold_if(f"{fmt(c['difference'], dec, sign=True)} ({p_eq(c['p'])})", c["p"]))
        rows.append(f"| {row_name(d)} | " + " | ".join(cells) + " |")
    district_table = "\n".join(rows)

    changed = [y for y in years if res["labels_jas"].loc[y, "phase"] != lab.loc[y, "phase"]]
    changed_text = (", ".join(f"{season_name(y)} ({res['labels_jas'].loc[y, 'phase']} on JAS, "
                              f"{lab.loc[y, 'phase']} on ASO)" for y in changed) if changed else "none")
    others = [y for y in years if y not in el]
    near = [y for y in el if 1.4 <= lab.loc[y, "oni"] < 1.5]
    near_text = ("; ".join(f"{season_name(y)} (ASO {lab.loc[y, 'oni']:+.2f})" for y in near)
                 if near else "none")
    return {"main": main, "strong": strong_table, "districts": district_table, "near": near_text,
            "el_text": ", ".join(season_name(y) for y in el), "counts": counts,
            "changed_text": changed_text, "n_strong": len(strong),
            "median_year_el": float(np.median(el)), "median_year_other": float(np.median(others))}


def section_rain_jump(res):
    """Small year-by-year table showing the pre-1997 vs post-1997 rain
    jump in NASA POWER (task 5c finding: a data-consistency break, not
    climate). Calendar years, not season years, but they coincide for
    Jun-Sep rain (offset 0)."""
    years = list(range(1993, 2001))
    jj_pooled = pooled_mean(res, "jjas_rain")
    jj_cumilla = res["outcomes"]["cumilla"]["jjas_rain"]
    lines = ["| Year | Jun-Sep rain, mean of 4 districts (mm) | Jun-Sep rain, Cumilla (mm) |",
             "|---|---|---|"]
    for y in years:
        lines.append(f"| {y} | {fmt(jj_pooled.get(y), 0)} | {fmt(jj_cumilla.get(y), 0)} |")
    return "\n".join(lines)


def section_onset(res):
    raw = res["onsets"][res["onsets"]["district"] != SHARED_CELL]
    confirmed = raw.copy()
    confirmed.loc[confirmed["unconfirmed"], "onset_doy"] = np.nan
    summ = onset_shift_summary(confirmed, default=(20.0, 450.0))
    n_unconf = raw.groupby(["min_week_mm", "confirm_mm"])["unconfirmed"].sum()
    lines = ["| 7-day total (mm) | 30-day total (mm) | confirmed onsets found | "
             "unconfirmed 25-31 Oct onsets | median onset | median shift vs default (days) | "
             "mean absolute shift (days) | largest absolute shift (days) |",
             "|---|---|---|---|---|---|---|---|"]
    for _, r in summ.iterrows():
        default = r["min_week_mm"] == 20.0 and r["confirm_mm"] == 450.0
        median_date = (pd.Timestamp("2001-01-01") + pd.Timedelta(days=r["median_doy"] - 1)).strftime("%d %b")
        first = f"**{r['min_week_mm']:.0f}**" if default else f"{r['min_week_mm']:.0f}"
        second = f"**{r['confirm_mm']:.0f}** (default)" if default else f"{r['confirm_mm']:.0f}"
        lines.append(f"| {first} | {second} | {int(r['found'])} of {int(r['rows'])} | "
                     f"{int(n_unconf[(r['min_week_mm'], r['confirm_mm'])])} | {median_date} | "
                     f"{fmt(r['median_shift'], 0, sign=True)} | {fmt(r['mean_abs_shift'], 1)} | "
                     f"{fmt(r['max_abs_shift'], 0)} |")
    non_default = summ[~((summ["min_week_mm"] == 20.0) & (summ["confirm_mm"] == 450.0))]
    return {"table": "\n".join(lines), "min_shift": non_default["mean_abs_shift"].min(),
            "max_shift": non_default["mean_abs_shift"].max()}


def section_trends(res, tr, period):
    heads = ["District"] + [f"{TRENDS[k][0]}, {TRENDS[k][2]}/decade" for k in TRENDS]
    rows = ["| " + " | ".join(heads) + " |", "|" + "---|" * len(heads)]
    for d in pooled_districts(res) + ["pooled", SHARED_CELL]:
        cells = []
        for k, (_, _, _, dec) in TRENDS.items():
            t = tr[(d, k)]
            text = (f"{fmt(t['slope_per_decade'], dec, sign=True)} "
                    f"[{fmt(t['slope_lo'], dec, sign=True)}, {fmt(t['slope_hi'], dec, sign=True)}], "
                    f"tau={t['tau']:+.2f}, {p_eq(t['p'])}")
            cells.append(bold_if(text, t["p"]))
        name = "**Mean of 4 districts**" if d == "pooled" else row_name(d)
        rows.append(f"| {name} | " + " | ".join(cells) + " |")
    spans = []
    for k in TRENDS:
        s = trend_series(pooled_mean(res, k), k, period).dropna()
        spans.append(f"{len(s)} ({s.index.min()}-{s.index.max()})")
    rows.append("| n (years) | " + " | ".join(spans) + " |")
    return "\n".join(rows)


def irrigation_step_text(res):
    parts = []
    for crop in CROPS:
        vals = [res["raw_mm"][(d, crop)] for d in pooled_districts(res)]
        parts.append(f"{crop} {min(vals):.0f}-{max(vals):.0f} mm")
    return ", ".join(parts)


# ---------------- plain-English summary ----------------

def meaning(res, tr_recent, lens):
    """All numbers here are over the primary window, {RECENT[0]}-{RECENT[1]},
    with IMERG rain only. The full 1981-2025 POWER record is appendix-only
    (see the data-consistency check) and is never quoted here."""
    lines = []
    wins = []
    for key, (label, _, _) in OUTCOMES.items():
        sk = pooled_skill(res, key)
        for m in METHODS:
            r = sk.loc[m]
            if r["skill"] > 0 and significant(r["sign_p"]):
                wins.append(f"{METHOD_NAMES[m]} for {lower_first(label)}: skill {r['skill']:+.2f} "
                            f"({p_eq(r['sign_p'])})")
    best = max(pooled_skill(res, k)["skill"].max() for k in OUTCOMES)
    if not wins:
        lines.append(f"- **Nothing tested beats the long-term average.** Pooled over the four "
                     f"districts, {RECENT[0]}-{RECENT[1]}, no method is closer in a significant "
                     f"majority of seasons; the best pooled skill is {best:+.2f} (1 = perfect, "
                     f"0 = no better than the long-term average).")
    else:
        lines.append(f"- **Nothing tested reliably beats the long-term average**, {RECENT[0]}-"
                     f"{RECENT[1]}, except: " + "; ".join(wins) + ". Every other method-outcome "
                     f"pair is within chance of the long-term average or worse. With "
                     f"{len(OUTCOMES) * len(METHODS)} method-outcome pairs tested, one p < 0.05 "
                     f"could appear by chance, and the pooled p is optimistic (neighbouring "
                     f"districts are not independent); a skill this small is not a reason to use "
                     f"that method.")

    analog = [pooled_skill(res, k).loc["analog_1", "skill"] for k in OUTCOMES]
    analog_k = [pooled_skill(res, k).loc[f"analog_{K}", "skill"] for k in OUTCOMES]
    worse = [lower_first(OUTCOMES[k][0]) for k in OUTCOMES
             if pooled_skill(res, k).loc["analog_1", "skill"] < 0
             and significant(pooled_skill(res, k).loc["analog_1", "sign_p"])]
    worse_text = (f" It is significantly worse than the long-term average for "
                  f"{'; '.join(sorted(set(worse)))}." if worse else "")
    headline = (f"is worse than the long-term average** for every outcome, {RECENT[0]}-{RECENT[1]}"
                if max(analog) < 0 else f"does not beat the long-term average** over {RECENT[0]}-{RECENT[1]}")
    lines.append(f"- **The single nearest analog year (the \"field twin\") {headline} "
                 f"(pooled skill {min(analog):+.2f} to {max(analog):+.2f})."
                 f"{worse_text} The mean of {K} analogs scores {min(analog_k):+.2f} to "
                 f"{max(analog_k):+.2f}. This backs CropShift's rule: the field twin is shown as an **example** of "
                 f"a past season, never as a guide to this one, and is not used in the ranking.")

    lines.append(f"- **Keep ranking on the spread of past years** (\"problems in X of N years\", average "
                 f"and worst 20%), not on one analog year or an ENSO average: the long-term average "
                 f"is the benchmark nothing here reliably beats. Rankings, skill and trends use only "
                 f"{RECENT[0]}-{RECENT[1]} with NASA GPM IMERG rain: NASA POWER rain has step "
                 f"changes around 1997 and 2014-15 (see `docs/results/rain_source_check.md` and the "
                 f"appendix), so POWER rain is not used in any recommendation.")

    sig = [(label, unit, c) for _, label, unit, _, c in lens if significant(c["p"])]
    if sig:
        lines.append(f"- **El Niño lens (context, not forecast, {RECENT[0]}-{RECENT[1]}):** "
                     "differences with p < 0.05 in the 4-district mean: " +
                     "; ".join(f"{lower_first(label)} {c['difference']:+.0f} {unit} (difference of "
                               f"medians, {p_eq(c['p'])}, "
                               f"n = {c['n_group']} El Niño vs {c['n_rest']} other seasons)"
                               for label, unit, c in sig) +
                     f". With {len(lens)} outcomes tested, one p < 0.05 could appear by chance. "
                     f"Show it only with n and the label \"context, not forecast\"; do not use it in "
                     f"the ranking.")
    else:
        lines.append(f"- **El Niño lens (context, not forecast, {RECENT[0]}-{RECENT[1]}):** no El "
                     "Niño vs other-season difference reaches p < 0.05 in the 4-district mean.")

    def listing(t):
        items = [f"{TRENDS[k][1]} {t[('pooled', k)]['slope_per_decade']:+.1f} {TRENDS[k][2]}/decade "
                 f"({p_eq(t[('pooled', k)]['p'])})" for k in TRENDS if significant(t[("pooled", k)]["p"])]
        return "; ".join(items) if items else "none"
    lines.append(f"- **Trends (4-district mean, p < 0.05, {RECENT[0]}-{RECENT[1]}, IMERG rain):** "
                 f"{listing(tr_recent)}. The earlier NASA POWER Jun-Sep rain trend (task 5c) came from "
                 f"POWER's 2014-15 step change, not from the climate, and must not be quoted. POWER "
                 f"trends appear only in the appendix.")
    return "\n".join(lines)


# ---------------- report ----------------

def write_report(res, res_power):
    """res: IMERG rain, primary window (every main section).
    res_power: NASA POWER rain, full 1981-2025 record (appendix only)."""
    recent_years = list(range(RECENT[0], RECENT[1] + 1))
    tr_recent = trend_results(res, RECENT)
    lens_recent = lens_rows(res, recent_years)
    ls_recent = section_lens(res, recent_years)
    on = section_onset(res)
    unconfirmed_main = "; ".join(
        f"{dname(d)}: {', '.join(map(str, unconfirmed_feature_years(res, d))) or 'none'}"
        for d in res["districts"])
    missing_main = "; ".join(
        f"{dname(d)}: {', '.join(map(str, sorted(set(recent_years) - set(res['features'][d].index)))) or 'none'}"
        for d in res["districts"])
    pooled_names = ", ".join(dname(d) for d in pooled_districts(res))
    n_trend_tests_recent = len(TRENDS) * (len(res["districts"]) + 1)
    last_monsoon_missing = np.isnan(pooled_mean(res, "next_monsoon_rain").get(RECENT[1], np.nan))
    monsoon_note = (f"The next monsoon of season {RECENT[1]} is not complete in the data yet."
                    if last_monsoon_missing else
                    f"The next monsoon of season {RECENT[1]} (Jun-Sep {RECENT[1] + 1}) is included.")

    # appendix-only, NASA POWER rain
    years_full = res_power["years"]
    cons_table, unconfirmed_years, missing_years = section_consistency(res_power)
    tr_full = trend_results(res_power, (years_full[0], years_full[-1]))
    ls_full = section_lens(res_power, years_full)
    n_trend_tests_full = len(TRENDS) * (len(res_power["districts"]) + 1)

    text = f"""# Hindcast, El Niño lens and trends (Task 5b/5c/5d)

Generated by `scripts/run_hindcast.py`. Do not edit by hand; re-run the script.

This page checks how well simple ways of using past seasons match a rabi season they
were not allowed to see, measured as **skill vs the long-term average** of the other
seasons. It tests methods; it says nothing about any future season. All numbers are
for NASA data for the area around each district point, not for a particular field.

**Rain: NASA GPM IMERG V07 Final Run daily** (0.1 degree cell; `load_weather()` in
`src/compute/weather.py`). Temperature, humidity, wind and solar radiation: NASA POWER.
NASA POWER rain has step changes around 1997 and 2014-15 that IMERG does not show
(`docs/results/rain_source_check.md`), so POWER rain is used only in the appendix.

**Primary analysis window: seasons {RECENT[0]}-{RECENT[1]}.** IMERG starts in 2001 and its
Final Run currently ends on 30 Sep 2025, so season 2025 (Nov 2025-Apr 2026) is not complete.
The full {years_full[0]}-{years_full[-1]} NASA POWER record appears only in the appendix,
"Data-consistency check (not used for recommendations)".

## At a glance: pooled skill vs the long-term average

Pooled over {pooled_names} (Noakhali excluded; see Setup). Each cell: skill (seasons
closer than the long-term average / seasons scored, two-sided sign test). Skill =
1 - MAE(method) / MAE(long-term average): 1 is perfect, 0 is no better than the long-term
average, below 0 is worse. **Bold** = p < 0.05, in either direction. Seasons
{RECENT[0]}-{RECENT[1]}; analogs, averages and scaling use only these seasons.

{section_glance(res)}

## What this means for CropShift

{meaning(res, tr_recent, lens_recent)}

## Setup

- **Season Y** = rabi season from 1 Nov of Y to 30 Apr of Y+1. **Primary window:**
  Y = {RECENT[0]}-{RECENT[1]}. **Decision date** = 31 Oct of Y: nothing after it is used to
  choose analogs or the ENSO label.
- **Outcomes** per district and season:
  - rabi rain (mm), NASA GPM IMERG daily rain;
  - net irrigation (mm) and rainfed water-stress days for **mustard** and **wheat** sown on
    15 Nov, from the FAO-56 root-zone balance in `src/compute/water_balance.py`
    (`crop_season_all_years`, default spin-up from 1 Aug at field capacity, soil from
    `data/reference/soil_params.csv`, Zr and p from `data/reference/crop_params.csv`).
    The irrigated run refills the root zone to field capacity each
    time depletion passes RAW, so net irrigation moves in steps of about one refill
    (RAW: {irrigation_step_text(res)}) and behaves like a count of irrigations.
- **Four ways to estimate a held-out season**, leave-one-year-out (the season being checked
  is removed from every average and from the analog pool):
  1. *long-term average*: mean of all other seasons (the benchmark);
  2. *1 nearest analog*: `nearest_analog_year()` on the four `build_feature_table()` features
     (onset day, onset amount, longest dry spell, mean temperature) computed with
     `decision_date="{DECISION_DATE}"`;
  3. *mean of {K} nearest analogs*: the same ranking, first {K} years averaged;
  4. *ENSO-phase average*: mean of the other seasons in the same ENSO phase (El Niño, neutral
     or La Niña; strong El Niño counted as El Niño). Fallbacks to the long-term average
     because a phase had no other season: {int(sum(t['enso_fallback'].sum() for t in res['loo_recent'].values()))}.
- Analog candidates are all other seasons with an outcome, earlier **and** later (a standard
  hindcast, not a real-time replay). A season whose year has no onset (no feature row) is
  left out for **every** method in that district, so all methods are scored on the same seasons.
- **Pooled** = {pooled_names} together. Neighbouring districts share much of their weather,
  so pooled district-seasons are not independent and the pooled sign-test p is optimistic.
- **Feni and Noakhali share one NASA POWER weather cell** (identical temperature, humidity,
  wind). With IMERG their rain comes from different 0.1 degree cells, but Noakhali is only
  about 1-4% wetter (`docs/results/rain_source_check.md`). Noakhali is reported in every
  table but **excluded from all pooled statistics**, so the shared cell is not counted twice.
  Do not read a Feni-Noakhali contrast into any number here.

## 1. Skill vs the long-term average, per district

Cells as in "At a glance". MAE of the long-term average is in the outcome's unit.
Seasons {RECENT[0]}-{RECENT[1]}.

{section_skill(res)}

## 2. El Niño lens: context, not forecast

**Label, known on 31 Oct:** the NOAA CPC ONI value for **ASO** (Aug-Sep-Oct) of year Y, from
`data/reference/oni.csv`: El Niño >= +0.5, strong El Niño >= +1.5, La Niña <= -0.5, otherwise
neutral. ASO sea-surface temperatures are all observed by 31 Oct, but CPC publishes the ASO
value in early November. Using the previous value (JAS), which is published by then, would
change these seasons: {ls_recent['changed_text']}.

Seasons {RECENT[0]}-{RECENT[1]}: {ls_recent['counts'].get('el_nino', 0)} El Niño (of which {ls_recent['n_strong']} strong),
{ls_recent['counts'].get('neutral', 0)} neutral, {ls_recent['counts'].get('la_nina', 0)} La Niña.
El Niño seasons: {ls_recent['el_text']}.

### El Niño seasons vs all other seasons (mean of {pooled_names})

Context, not forecast. The next monsoon (Jun-Sep of Y+1) and next pre-monsoon (Mar-May of Y+1)
come months after the rabi season. **Bold** = p < 0.05. {monsoon_note}

{ls_recent['main']}

### Strong El Niño seasons one by one (mean of {pooled_names})

Context, not forecast. Only the ASO value counts, so seasons that became strong later in the
winter are not listed; just under +1.5 on 31 Oct: {ls_recent['near']}.

{ls_recent['strong']}

### El Niño minus other seasons, per district (difference of medians, Mann-Whitney p)

Context, not forecast.

{ls_recent['districts']}

## 3. Onset sensitivity (kharif monsoon onset)

`rain_onset()` thresholds varied: the 7-day total that starts the monsoon (15 / 20 / 25 mm) and
the 30-day total that confirms it (350 / 450 / 550 mm). Each year uses 1 Jan to 31 Oct only
(as `build_feature_table()` does). District-years pooled over {pooled_names},
{RECENT[0]}-{RECENT[1]}, IMERG rain. Shift = onset with these thresholds minus onset with
the default (20 mm, 450 mm), for years where both give a confirmed onset (+ = later).

{on['table']}

- Across the eight non-default settings the mean absolute shift is {on['min_shift']:.1f} to
  {on['max_shift']:.1f} days. The 7-day threshold barely matters; the 30-day confirmation
  total moves onset by weeks. Onset day is one of the four analog features, so this choice
  changes which years are picked as analogs.
- **Edge case in `rain_onset()`, now fixed:** a wet week with fewer than 7 days after it,
  i.e. a week ending 25-31 Oct with a 31 Oct cutoff, used to be accepted as the onset
  **without** the dry-spell and 30-day checks. It is now rejected (not an onset), so the
  "unconfirmed 25-31 Oct onsets" column is kept only as a check and should be 0 in every row.
- Years with **no onset at all** by 31 Oct, IMERG rain (left out of the analog methods):
  {missing_main}. Years resting on an unconfirmed 25-31 Oct onset (should be none):
  {unconfirmed_main}.

## 4. Trends

Theil-Sen slope per decade [95% interval], Mann-Kendall tau and p (`scipy.stats.theilslopes`,
`scipy.stats.kendalltau` against the year). **Bold** = p < 0.05. Seasons {RECENT[0]}-{RECENT[1]}.

{section_trends(res, tr_recent, RECENT)}

- **Autocorrelation is not corrected** (no pre-whitening or variance correction), so p-values
  may be too small if neighbouring years are alike.
- {n_trend_tests_recent} tests are shown; at p < 0.05 a few could come out "significant" by chance.
- Trends in gridded data can reflect changes in the observations feeding them, not only the
  climate. IMERG shows no significant step change (`docs/results/rain_source_check.md`), but
  its satellite inputs did change (TRMM era to 2014, GPM era after). The NASA POWER Jun-Sep
  trend in the previous version of this page came from POWER's 2014-15 step change and must
  not be quoted.

## Caveats

- These scores compare methods on cell averages (IMERG rain 0.1 degree, POWER temperature
  about 0.5 degree), not on a field.
- Irrigation and stress come from a model (FAO-56 bucket, runoff and capillary rise set to
  zero, one soil per district); see `docs/results/water_balance_validation.md` for how its
  soil water compares with SMAP.
- Leave-one-year-out uses later years as candidates too. A real-time replay (earlier years
  only) would have fewer candidates, especially for the early seasons.

## Appendix: Data-consistency check (not used for recommendations)

Everything in this appendix uses the full {years_full[0]}-{years_full[-1]} NASA POWER record,
**rain included**. It is kept only to show why POWER rain was replaced; none of these numbers
feed the ranking, ENSO lens or trend statements used by CropShift.

### Skill with POWER rain over the primary window (for comparison only)

Same method and seasons as "At a glance" ({RECENT[0]}-{RECENT[1]}), but with NASA POWER rain.
Seasons scored can differ slightly because onset years differ between the two rain records.

{section_glance(res_power)}

### The rain jump

Mean Jun-Sep rain jumps sharply around 1997, well before any plausible change in the local
monsoon:

{section_rain_jump(res_power)}

### {EARLY[0]}-{EARLY[1]} vs {RECENT[0]}-{RECENT[1]}

{cons_table}

"Confirmed onset" = `rain_onset()` found an onset that passed its dry-spell and 30-day
checks. Years with **no onset at all** by 31 Oct (left out of the analog methods):
{missing_years}. Years whose analog features rest on an **unconfirmed 25-31 Oct onset**
(a wet week too close to the 31 Oct cutoff for `rain_onset()` to check; it now rejects these,
so this is a check that should read "none"; see section 3): {unconfirmed_years}.

Most {EARLY[0]}-{EARLY[1]} years never reach 450 mm in 30 days in POWER rain. Either the early
monsoons really were much weaker or, more likely, the rain record is not consistent over
time (a reanalysis's inputs change over the decades). IMERG starts in 2001, so it cannot
check 1981-2000 directly, but it shows that POWER rain also jumps a second time, around
2014-15 (`docs/results/rain_source_check.md`). POWER rain is therefore appendix-only.

### Full-record ({years_full[0]}-{years_full[-1]}) skill, El Niño lens and trends, POWER rain

Shown for reference only, not used for recommendations.

{section_skill(res_power, recent=False)}

{ls_full['main']}

{section_trends(res_power, tr_full, (years_full[0], years_full[-1]))}

- {n_trend_tests_full} tests shown here. Mean Jun-Sep POWER rain is far higher in
  {RECENT[0]}-{RECENT[1]} than in {EARLY[0]}-{EARLY[1]} (see the rain jump table above) and jumps
  again around 2014-15; changes that large are not a plausible climate signal, so these
  POWER trends must **not** be quoted as climate change, or at all outside this appendix.

## Sources

- Rain: {RAIN_CITATIONS["imerg"]["dataset"]}, {RAIN_CITATIONS["imerg"]["url"]}
  (doi:10.5067/GPM/IMERGDF/DAY/07)
- NASA POWER daily, AG community (temperature, humidity, wind, solar radiation; rain in the
  appendix only): https://power.larc.nasa.gov/
- NOAA CPC Oceanic Niño Index (ONI): https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
  (`data/reference/oni.csv`)
- FAO-56: Allen, Pereira, Raes, Smith (1998), *Crop evapotranspiration*, FAO Irrigation and
  Drainage Paper 56, https://www.fao.org/4/x0490e/x0490e0e.htm
- Soil and crop parameters: `data/reference/soil_params.csv`, `data/reference/crop_params.csv`
- Statistics: SciPy (`scipy.stats.kendalltau`, `theilslopes`, `mannwhitneyu`, `binomtest`),
  https://docs.scipy.org/doc/scipy/reference/stats.html
"""
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    res = compute(RAIN_SOURCE, list(range(RECENT[0], RECENT[1] + 1)))
    res_power = compute("power", YEARS)
    write_report(res, res_power)
    print(f"Wrote {os.path.relpath(OUT_PATH, ROOT)}")


if __name__ == "__main__":
    main()
