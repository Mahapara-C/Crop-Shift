"""
src/compute/agroclimate.py

Deterministic agroclimate functions — pure Python, no AI involvement.
Consumed by nearest_analog_year() and the agent's tool layer, but never
touched by any model at runtime.
"""

import pandas as pd
import numpy as np

def rain_onset(daily_rainfall, year, min_week_mm=20.0, dry_spell_days=7,
               dry_day_threshold=1.0, confirm_window_days=30, min_confirm_total_mm=450.0):
    """
    Finds the monsoon onset date for a single year, per the definition:
    "the first 7-day window with >=20mm rainfall not followed by a dry
    spell longer than 7 days" — extended with a sustained-rainfall check
    (>=450mm over the following 30 days) to reject pre-monsoon nor'wester
    bursts that pass the dry-spell test but aren't real monsoon onset.

    Threshold of 450mm was chosen empirically against 2001-2025 Cumilla
    POWER data: it keeps 23/25 years matched with average onset ~May 16
    (consistent with regional monsoon climatology), just before higher
    thresholds start rejecting years structurally rather than improving
    accuracy. Years with no valid onset (e.g. 2005, 2012) had normal
    total rainfall but no single 30-day window meeting the confirm
    threshold — a real gradual-onset pattern, not a data gap. Such years
    are simply excluded from nearest_analog_year()'s candidate pool.

    Parameters
    ----------
    daily_rainfall : pd.Series
        Daily rainfall (mm), indexed by date, filtered to one year.
    year : int
        The year being analyzed (for labeling the result).

    Returns
    -------
    dict with onset_doy (day of year), onset_date, onset_amount_mm —
    or None values if no valid onset was found that year.
    """
    rolling_7day = daily_rainfall.rolling(window=7).sum()
    is_dry_day = (daily_rainfall < dry_day_threshold)

    for i in range(6, len(daily_rainfall)):
        window_total = rolling_7day.iloc[i]
        if window_total >= min_week_mm:
            check_start = i + 1
            check_end = min(i + 1 + confirm_window_days, len(daily_rainfall))
            follow_period = daily_rainfall.iloc[check_start:check_end]
            follow_dry = is_dry_day.iloc[check_start:check_end]

            if len(follow_period) < dry_spell_days:
                is_false_start = False
            else:
                longest_dry_run = (
                    follow_dry.groupby((~follow_dry).cumsum()).cumsum().max()
                    if follow_dry.any() else 0
                )
                no_long_dry_gap = longest_dry_run < dry_spell_days
                sustained_rain = follow_period.sum() >= min_confirm_total_mm
                is_false_start = not (no_long_dry_gap and sustained_rain)

            if not is_false_start:
                onset_date = daily_rainfall.index[i]
                return {
                    "year": year,
                    "onset_doy": onset_date.dayofyear,
                    "onset_date": str(onset_date.date()),
                    "onset_amount_mm": round(window_total, 1)
                }
    return {"year": year, "onset_doy": None, "onset_date": None, "onset_amount_mm": None}




def dry_spell_length(daily_rainfall, dry_day_threshold=1.0):
    """Longest consecutive run of dry days across the WHOLE year — used as
    a matching feature (distinct from the onset false-start check inside
    rain_onset())."""
    is_dry = (daily_rainfall < dry_day_threshold)
    if not is_dry.any():
        return 0
    return int(is_dry.groupby((~is_dry).cumsum()).cumsum().max())


def build_feature_table(df, years=range(2001, 2026)):
    """One row per year: onset_doy, onset_amount_mm, dry_spell_days,
    mean_t2m_c — the four features nearest_analog_year() matches on.
    Years with no valid monsoon onset (per rain_onset()) are excluded
    entirely, since they have no onset_doy/onset_amount_mm to match on.

    Parameters
    ----------
    df : pd.DataFrame
        Daily data indexed by date, with 'rainfall_mm' and 'temp_c' columns
        (as produced by the NASA POWER pull).
    years : iterable of int
        Which years to include, if present in df.

    Returns
    -------
    pd.DataFrame indexed by year, with the four feature columns.
    """
    rows = []
    for yr in years:
        year_data = df[df.index.year == yr]
        if len(year_data) < 300:
            continue
        onset = rain_onset(year_data["rainfall_mm"], yr)
        if onset["onset_doy"] is None:
            continue
        rows.append({
            "year": yr,
            "onset_doy": onset["onset_doy"],
            "onset_amount_mm": onset["onset_amount_mm"],
            "dry_spell_days": dry_spell_length(year_data["rainfall_mm"]),
            "mean_t2m_c": year_data["temp_c"].mean()
        })
    return pd.DataFrame(rows).set_index("year")


FEATURES = ["onset_doy", "onset_amount_mm", "dry_spell_days", "mean_t2m_c"]


def nearest_analog_year(current_season, feature_table, features=FEATURES):
    """
    Finds the historical year whose climate signature is closest to
    current_season, using z-normalized Euclidean distance. Matches ONLY
    on POWER-derived features (never SMAP — SMAP only goes back to 2015,
    so using it here would shrink the candidate pool from ~25 years to
    ~10; SMAP is used only inside backtest_rotation() on whichever year
    gets picked here).

    current_season : dict
        Same feature keys as `features`, describing the season to match
        (e.g. this year's observed onset so far).
    feature_table : pd.DataFrame
        From build_feature_table() — one row per historical year.

    Z-normalization uses the MEAN and STD DEVIATION of each feature
    across all years in feature_table, applied identically to
    current_season, so no single feature dominates the distance purely
    due to its raw units (e.g. onset_doy spans ~100 days while
    mean_t2m_c spans ~1 degree).

    Returns the matched year, its raw distance, and each feature's
    individual normalized contribution — so the interface can explain
    WHY this year was chosen.
    """
    means = feature_table[features].mean()
    stds = feature_table[features].std()

    normalized_table = (feature_table[features] - means) / stds
    cur_normalized = {f: (current_season[f] - means[f]) / stds[f] for f in features}
    cur_vec = np.array([cur_normalized[f] for f in features])

    best_year, best_dist, best_contrib = None, np.inf, None
    for year, row in normalized_table.iterrows():
        vec = row[features].values.astype(float)
        diffs = np.abs(cur_vec - vec)
        dist = float(np.linalg.norm(diffs))
        if dist < best_dist:
            best_year, best_dist = year, dist
            best_contrib = dict(zip(features, diffs.tolist()))

    return {
        "analog_year": int(best_year),
        "distance": round(best_dist, 3),
        "feature_contributions": {k: round(v, 3) for k, v in best_contrib.items()}
    }
def eto_penman_monteith(row, day_of_year, latitude_deg, elevation_m):
    """
    FAO-56 Penman-Monteith reference evapotranspiration (Equation 6),
    for a single day. Validated against Cumilla (2001-2025 POWER data):
    monthly averages show the expected seasonal curve — low in Dec/Jan
    (~2.1-2.4 mm/day), pre-monsoon peak in April (~5.2 mm/day), easing
    through monsoon months (~3.4-3.5 mm/day) — consistent with known
    Bangladesh climatology.

    row : a row with temp_max_c, temp_min_c, temp_mean_c, rh_pct,
          wind_speed_ms, solar_rad_kwh_m2.
          NOTE: despite its name, solar_rad_kwh_m2 is in MJ/m2/day when
          pulled under POWER's "AG" (agroclimatology) community — no
          unit conversion is applied here. (RE-community pulls would be
          in kWh/m2/day and WOULD need *3.6 conversion — the two
          communities differ in units for this same parameter, which
          is the bug this function's validation caught.)
    day_of_year : 1-365/366, for extraterrestrial radiation.
    latitude_deg, elevation_m : site location, varies per district.

    Returns ET0 in mm/day.
    """
    T_max, T_min, T_mean = row["temp_max_c"], row["temp_min_c"], row["temp_mean_c"]
    RH = row["rh_pct"]
    u2 = row["wind_speed_ms"]
    Rs = row["solar_rad_kwh_m2"]  # already MJ/m2/day under AG community

    P = 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26
    gamma = 0.000665 * P

    def e_sat(T):
        return 0.6108 * np.exp((17.27 * T) / (T + 237.3))
    es = (e_sat(T_max) + e_sat(T_min)) / 2
    ea = es * (RH / 100.0)
    delta = (4098 * e_sat(T_mean)) / ((T_mean + 237.3) ** 2)

    lat_rad = np.radians(latitude_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * day_of_year / 365)
    decl = 0.409 * np.sin(2 * np.pi * day_of_year / 365 - 1.39)
    ws = np.arccos(-np.tan(lat_rad) * np.tan(decl))
    Ra = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(lat_rad) * np.sin(decl) + np.cos(lat_rad) * np.cos(decl) * np.sin(ws)
    )
    Rso = (0.75 + 2e-5 * elevation_m) * Ra
    Rns = (1 - 0.23) * Rs
    sigma = 4.903e-9
    T_max_k, T_min_k = T_max + 273.16, T_min + 273.16
    ratio = min(Rs / Rso, 1.0) if Rso > 0 else 0.0
    Rnl = sigma * ((T_max_k**4 + T_min_k**4) / 2) * (0.34 - 0.14 * np.sqrt(ea)) * (1.35 * ratio - 0.35)
    Rn = Rns - Rnl
    G = 0

    numerator = 0.408 * delta * (Rn - G) + gamma * (900 / (T_mean + 273)) * u2 * (es - ea)
    denominator = delta + gamma * (1 + 0.34 * u2)
    return round(float(numerator / denominator), 2)

def backtest_rotation(rotation_plan, analog_year, power_df, smap_series, kc_table,
                       latitude_deg, elevation_m,
                       kc_low=0.3, kc_high=1.2, pctl_low=20, pctl_high=60):
    """
    Replays a candidate crop rotation against the REAL observed SMAP and
    POWER data from analog_year, and counts "usable soil moisture days" —
    days where soil moisture was adequate for that day's crop water demand.

    SIMPLIFIED METHOD (documented placeholder — see NOTE below):
    Since field capacity/wilting point data isn't yet available per
    district, adequacy is judged by ranking each day's SMAP root-zone
    moisture against that SAME location's own historical percentile
    distribution (computed from its full SMAP record), rather than an
    absolute soil-physics threshold. The required percentile scales
    linearly with that day's crop coefficient (Kc): a low-Kc day
    (e.g. early growth, kc_low=0.3) only needs the 20th percentile
    (pctl_low) or better; a peak-Kc day (kc_high=1.2, mid-season) needs
    the 60th percentile (pctl_high) or better. This avoids needing soil
    survey data we don't have yet, at the cost of being a proxy rather
    than a true water-balance calculation.

    NOTE: This is the pre-October-1 simplified version. A fuller
    FAO-56 Chapter 8 style day-by-day root-zone depletion model
    (using actual field capacity / wilting point / management allowable
    depletion) is planned as a post-Oct-1 upgrade once ISRIC SoilGrids
    data is incorporated — see prompt-2.md's data inventory.

    Parameters
    ----------
    rotation_plan : list of dicts, e.g.
        [{"crop": "rice", "start_date": "2019-05-15"},
         {"crop": "mung_bean", "start_date": "2019-09-20"}]
    analog_year : int — the year whose real data we're replaying.
    power_df : DataFrame — that district's full POWER data (needs
               temp_max_c, temp_min_c, temp_mean_c, rh_pct, wind_speed_ms,
               solar_rad_kwh_m2), indexed by date.
    smap_series : Series of daily sm_rootzone values, indexed by date,
                  for that district's FULL history (used both to look up
                  the analog year's values AND to compute the historical
                  percentile distribution).
    kc_table : DataFrame from the kc_table.csv (crop, stage, length_days, kc).
    latitude_deg, elevation_m : for ET0 calculation.

    Returns
    -------
    dict with per-crop day counts, usable_moisture_days, and the daily
    detail table (for the provenance drawer / debugging).
    """
    smap_sorted = smap_series.dropna().sort_values().values

    def moisture_percentile(value):
        idx = np.searchsorted(smap_sorted, value, side='right')
        return 100.0 * idx / len(smap_sorted)

    def required_percentile(kc):
        kc_clamped = max(kc_low, min(kc_high, kc))
        frac = (kc_clamped - kc_low) / (kc_high - kc_low)
        return pctl_low + frac * (pctl_high - pctl_low)

    daily_rows = []

    for entry in rotation_plan:
        crop = entry["crop"]
        start = pd.Timestamp(entry["start_date"])
        crop_stages = kc_table[kc_table["crop"] == crop].reset_index(drop=True)

        day_offset = 0
        for _, stage_row in crop_stages.iterrows():
            stage_name = stage_row["stage"]
            kc = stage_row["kc"]
            length = int(stage_row["length_days"])

            for d in range(length):
                current_date = start + pd.Timedelta(days=day_offset)
                day_offset += 1

                if current_date not in power_df.index or current_date not in smap_series.index:
                    continue

                row = power_df.loc[current_date]
                doy = current_date.dayofyear
                eto = eto_penman_monteith(row, doy, latitude_deg, elevation_m)
                demand_mm = kc * eto

                sm_value = smap_series.loc[current_date]
                pctl = moisture_percentile(sm_value)
                req_pctl = required_percentile(kc)
                usable = pctl >= req_pctl

                daily_rows.append({
                    "date": current_date, "crop": crop, "stage": stage_name,
                    "kc": kc, "eto_mm": eto, "demand_mm": round(demand_mm, 2),
                    "sm_rootzone": sm_value, "sm_percentile": round(pctl, 1),
                    "required_percentile": round(req_pctl, 1), "usable": usable
                })

    detail_df = pd.DataFrame(daily_rows)
    if detail_df.empty:
        return {"usable_moisture_days": 0, "total_days": 0, "detail": detail_df}

    return {
        "usable_moisture_days": int(detail_df["usable"].sum()),
        "total_days": len(detail_df),
        "by_crop": detail_df.groupby("crop")["usable"].agg(["sum", "count"]).to_dict("index"),
        "detail": detail_df
    }