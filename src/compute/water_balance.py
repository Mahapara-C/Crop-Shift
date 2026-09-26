"""
FAO-56 Chapter 8 daily root-zone soil water balance (Allen et al., 1998,
FAO Irrigation and Drainage Paper 56, https://www.fao.org/4/x0490e/x0490e0e.htm).

For one crop, sowing date and year it answers two questions from NASA
POWER weather for the area around a field:
  1. Rainfed: on how many days was the root zone drier than the crop can
     use without stress (water_stress_days)?
  2. Irrigated: how much net irrigation (mm) keeps it out of stress?

Equations (FAO-56 numbering):
  TAW = 1000 (theta_FC - theta_WP) Zr                            (Eq. 82)
  RAW = p TAW                                                    (Eq. 83)
  Ks  = (TAW - Dr) / ((1 - p) TAW) when Dr > RAW, else 1         (Eq. 84)
  ETc_adj = Ks Kc ET0                                            (Eq. 81)
  Dr,i = Dr,i-1 - (P - RO)i - Ii - CRi + ETc,i + DPi             (Eq. 85)
  0 <= Dr,i <= TAW                                               (Eq. 86)
  DPi = (P - RO)i + Ii - ETc,i - Dr,i-1 >= 0                     (Eq. 88)
  Kc between stages: linear (Eq. 66, the Fig. 25 Kc curve)

Assumptions (each one is also in the docstring where it is applied):
  - RO = 0. No runoff method is cited yet, so all water above field
    capacity leaves as DP; deep_percolation_mm therefore includes runoff.
  - CR = 0 (FAO-56: fine when the water table is > ~1 m below the roots;
    NOT true for shallow monsoon water tables, which makes stress an upper
    bound in those months).
  - Rain below 0.2 ET0 on a day is ignored (FAO-56 Ch. 8: it "is normally
    entirely evaporated").
  - Zr is constant through the season. Following Table 22 footnote 1, the
    rainfed (stress) run uses the larger Zr and the irrigation run uses the
    smaller Zr.
  - Ks for day i uses the depletion at the end of day i-1 (FAO-56 Example 36).
  - A day counts as a water-stress day when its end-of-day Dr > RAW.

Crop Zr and p: data/reference/crop_params.csv (FAO-56 Table 22).
Soil theta_FC and theta_WP: data/reference/soil_params.csv (FAO-56 Table 19,
texture from ISRIC SoilGrids 2.0).
"""

import os

import numpy as np
import pandas as pd

from agroclimate import eto_penman_monteith

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CROP_PARAMS_PATH = os.path.join(REPO_ROOT, "data", "reference", "crop_params.csv")
SOIL_PARAMS_PATH = os.path.join(REPO_ROOT, "data", "reference", "soil_params.csv")

SMALL_RAIN_FRACTION = 0.2  # rain < 0.2 ET0 is ignored (FAO-56 Ch. 8)


# ---------------- reference values ----------------

def _load_reference(path):
    """Reads a data/reference CSV whose items are named '<name>.<key>'
    into {name: {key: value}}."""
    table = pd.read_csv(path)
    out = {}
    for item, value in zip(table["item"], table["value"]):
        name, key = item.split(".", 1)
        out.setdefault(name, {})[key] = float(value)
    return out


def load_crop_params(path=CROP_PARAMS_PATH):
    """{crop: {"zr_min_m", "zr_max_m", "p"}} from FAO-56 Table 22."""
    return _load_reference(path)


def load_soil_params(path=SOIL_PARAMS_PATH):
    """{district: {"theta_fc_m3m3", "theta_wp_m3m3", "clay_pct", ...}}
    from FAO-56 Table 19 by SoilGrids texture."""
    return _load_reference(path)


# ---------------- building blocks ----------------

def total_available_water(theta_fc, theta_wp, zr_m):
    """TAW in mm (FAO-56 Eq. 82)."""
    if theta_fc <= theta_wp:
        raise ValueError(f"theta_FC ({theta_fc}) must be above theta_WP ({theta_wp})")
    if zr_m <= 0:
        raise ValueError(f"Root depth must be positive, got {zr_m}")
    return 1000.0 * (theta_fc - theta_wp) * zr_m


def adjusted_p(p_table, etc_mm):
    """p corrected for the day's ETc (FAO-56 Table 22 footnote 2):
    p = p_table + 0.04 (5 - ETc), limited to 0.1 <= p <= 0.8."""
    return min(0.8, max(0.1, p_table + 0.04 * (5.0 - etc_mm)))


def kc_daily(kc_table, crop):
    """Daily Kc for a whole season, built as FAO-56 Fig. 25: constant
    Kc_ini, then a straight line up to Kc_mid through the development
    stage, constant Kc_mid, then a straight line down to Kc_end through
    the late stage (Eq. 66). Not stepwise.

    kc_table rows per crop: initial (kc = Kc_ini), development (its kc
    column is not used; it only gives the stage length), mid (Kc_mid),
    late (kc = Kc_end, reached on the last day).
    """
    rows = kc_table[kc_table["crop"] == crop].set_index("stage")
    if rows.empty:
        raise ValueError(f"No Kc stages for crop '{crop}' in kc_table — "
                         f"known crops: {sorted(kc_table['crop'].unique())}")
    length = {s: int(rows.loc[s, "length_days"]) for s in
              ("initial", "development", "mid", "late")}
    kc_ini = float(rows.loc["initial", "kc"])
    kc_mid = float(rows.loc["mid", "kc"])
    kc_end = float(rows.loc["late", "kc"])

    dev = np.arange(1, length["development"] + 1) / length["development"]
    late = np.arange(1, length["late"] + 1) / length["late"]
    return np.concatenate([
        np.full(length["initial"], kc_ini),
        kc_ini + dev * (kc_mid - kc_ini),
        np.full(length["mid"], kc_mid),
        kc_mid + late * (kc_end - kc_mid),
    ])


def weather_table(power_df, latitude_deg, elevation_m):
    """Daily rainfall_mm and et0_mm (FAO-56 Penman-Monteith) from a POWER
    dataframe with a DatetimeIndex."""
    et0 = [eto_penman_monteith(row, date.dayofyear, latitude_deg, elevation_m)
           for date, row in power_df.iterrows()]
    return pd.DataFrame({"rainfall_mm": power_df["rainfall_mm"].astype(float),
                         "et0_mm": et0}, index=power_df.index)


# ---------------- the daily balance ----------------

def simulate_balance(rain_mm, et0_mm, kc, taw_mm, p, initial_depletion_mm=0.0,
                     irrigate=False, adjust_p=False):
    """
    Runs the FAO-56 root-zone depletion balance (Eq. 85) day by day.

    rain_mm, et0_mm, kc : equal-length sequences (a Series index is kept).
    taw_mm : total available water of the root zone (Eq. 82).
    p : Table 22 depletion fraction; adjust_p=True corrects it daily for
        ETc (footnote 2). Otherwise one constant p is used, which FAO-56
        says is often done for a growing period.
    initial_depletion_mm : Dr at the end of the day before day 1 (0 = field
        capacity, which FAO-56 allows after heavy rain).
    irrigate : when True, any day that ends with Dr > RAW gets net
        irrigation I = Dr, refilling the root zone to field capacity (so
        I <= Dr and irrigation never drains, as FAO-56 advises).

    Returns a daily DataFrame. Each row satisfies Eq. 85 exactly:
        depletion_mm = depletion_start_mm - eff_rain_mm - irrigation_mm
                       + etc_adj_mm + deep_percolation_mm
    """
    index = rain_mm.index if isinstance(rain_mm, pd.Series) else None
    rain = np.asarray(rain_mm, dtype=float)
    et0 = np.asarray(et0_mm, dtype=float)
    kc = np.asarray(kc, dtype=float)
    if not (len(rain) == len(et0) == len(kc)):
        raise ValueError("rain_mm, et0_mm and kc must have the same length")
    if np.isnan(rain).any() or np.isnan(et0).any():
        raise ValueError("rain_mm and et0_mm must not contain missing values")
    if taw_mm <= 0:
        raise ValueError(f"TAW must be positive, got {taw_mm}")
    if not 0 < p < 1:
        raise ValueError(f"p must be between 0 and 1, got {p}")
    if not 0 <= initial_depletion_mm <= taw_mm:
        raise ValueError(f"Initial depletion {initial_depletion_mm} must be within 0..TAW")

    rows = []
    dr_prev = float(initial_depletion_mm)
    for i in range(len(rain)):
        etc = kc[i] * et0[i]
        p_day = adjusted_p(p, etc) if adjust_p else p
        raw = p_day * taw_mm

        # Eq. 84, using the depletion at the start of the day.
        ks = 1.0 if dr_prev <= raw else (taw_mm - dr_prev) / ((1 - p_day) * taw_mm)
        ks = min(1.0, max(0.0, ks))
        etc_adj = ks * etc  # Eq. 81

        eff_rain = rain[i] if rain[i] >= SMALL_RAIN_FRACTION * et0[i] else 0.0

        dr = dr_prev - eff_rain + etc_adj
        deep_perc = 0.0
        if dr < 0:              # above field capacity: the excess drains (Eq. 88)
            deep_perc = -dr
            dr = 0.0
        elif dr > taw_mm:       # Eq. 86 upper limit: the soil cannot give more than TAW
            etc_adj -= dr - taw_mm
            dr = taw_mm

        irrigation = 0.0
        if irrigate and dr > raw:
            irrigation = dr
            dr = 0.0

        rows.append({
            "rain_mm": rain[i], "eff_rain_mm": eff_rain, "et0_mm": et0[i],
            "kc": kc[i], "etc_mm": etc, "ks": ks, "etc_adj_mm": etc_adj,
            "p": p_day, "raw_mm": raw, "irrigation_mm": irrigation,
            "deep_percolation_mm": deep_perc, "depletion_start_mm": dr_prev,
            "depletion_mm": dr, "water_stress": dr > raw,
        })
        dr_prev = dr

    daily = pd.DataFrame(rows, index=index)
    daily["relative_soil_water"] = 1.0 - daily["depletion_mm"] / taw_mm
    return daily


# ---------------- crop seasons ----------------

def _covered(weather, dates):
    return dates.isin(weather.index).all()


def _spinup_depletion(weather, sow, kc_ini, taw_mm, p, spinup_start, adjust_p):
    """Depletion (mm) on the eve of sowing. The balance starts at field
    capacity (Dr = 0) on the most recent spinup_start date (default 1 August,
    monsoon peak, when FAO-56's "near field capacity after heavy rain" is a
    fair assumption) and runs rainfed with the crop's Kc_ini, which mainly
    reflects bare-soil evaporation, until the day before sowing.
    Returns None when the weather does not cover the spin-up."""
    month, day = (int(x) for x in spinup_start.split("-"))
    start = pd.Timestamp(year=sow.year, month=month, day=day)
    if start > sow:
        start = pd.Timestamp(year=sow.year - 1, month=month, day=day)
    if start == sow:
        return 0.0
    dates = pd.date_range(start, sow - pd.Timedelta(days=1), freq="D")
    if not _covered(weather, dates):
        return None
    w = weather.loc[dates]
    run = simulate_balance(w["rainfall_mm"], w["et0_mm"], np.full(len(dates), kc_ini),
                           taw_mm, p, 0.0, irrigate=False, adjust_p=adjust_p)
    return float(run["depletion_mm"].iloc[-1])


def crop_season(crop, sowing_date, weather, kc_table, crop_params, soil,
                initial_depletion_frac=None, spinup_start="08-01", adjust_p=False):
    """
    Rainfed and irrigated FAO-56 balance for one crop sown on one date.

    weather : DataFrame with DatetimeIndex and rainfall_mm, et0_mm
              (see weather_table()).
    crop_params : load_crop_params() output; soil : one district's entry of
              load_soil_params().
    initial_depletion_frac : Dr at sowing as a fraction of TAW (0 = field
              capacity). None (default) spins up from spinup_start instead.

    The rainfed run uses zr_max_m and the irrigated run zr_min_m (FAO-56
    Table 22 footnote 1: larger Zr for modelling stress or rainfed
    conditions, smaller Zr for irrigation scheduling).

    Returns a dict of season totals plus "daily" (rainfed) and
    "daily_irrigated" tables. Raises ValueError if the weather does not
    cover the spin-up and the season.
    """
    if crop not in crop_params:
        raise ValueError(f"No Zr/p for crop '{crop}' in crop_params — "
                         f"known: {sorted(crop_params)}")
    kc = kc_daily(kc_table, crop)
    sow = pd.Timestamp(sowing_date)
    dates = pd.date_range(sow, periods=len(kc), freq="D")
    if not _covered(weather, dates):
        raise ValueError(f"Weather does not cover {crop} sown {sow.date()} "
                         f"to {dates[-1].date()}")
    season = weather.loc[dates]
    params = crop_params[crop]
    theta_fc, theta_wp = soil["theta_fc_m3m3"], soil["theta_wp_m3m3"]

    runs = {}
    for scenario, zr, irrigate in (("rainfed", params["zr_max_m"], False),
                                   ("irrigated", params["zr_min_m"], True)):
        taw = total_available_water(theta_fc, theta_wp, zr)
        if initial_depletion_frac is None:
            dr0 = _spinup_depletion(weather, sow, kc[0], taw, params["p"],
                                    spinup_start, adjust_p)
            if dr0 is None:
                raise ValueError(f"Weather does not cover the spin-up before {sow.date()}")
        else:
            dr0 = initial_depletion_frac * taw
        daily = simulate_balance(season["rainfall_mm"], season["et0_mm"], kc, taw,
                                 params["p"], dr0, irrigate=irrigate, adjust_p=adjust_p)
        runs[scenario] = (daily, taw, zr, dr0)

    rainfed, taw, zr_rainfed, dr0 = runs["rainfed"]
    irrigated, _, zr_irrigated, _ = runs["irrigated"]
    return {
        "crop": crop,
        "sowing_date": str(sow.date()),
        "harvest_date": str(dates[-1].date()),
        "season_days": len(dates),
        "water_stress_days": int(rainfed["water_stress"].sum()),
        "net_irrigation_mm": round(float(irrigated["irrigation_mm"].sum()), 1),
        "irrigation_events": int((irrigated["irrigation_mm"] > 0).sum()),
        "deep_percolation_mm": round(float(rainfed["deep_percolation_mm"].sum()), 1),
        "rain_mm": round(float(rainfed["rain_mm"].sum()), 1),
        "effective_rain_mm": round(float(rainfed["eff_rain_mm"].sum()), 1),
        "etc_mm": round(float(rainfed["etc_mm"].sum()), 1),
        "etc_adj_mm": round(float(rainfed["etc_adj_mm"].sum()), 1),
        "taw_mm": round(taw, 1),
        "raw_mm": round(params["p"] * taw, 1),
        "initial_depletion_mm": round(dr0, 1),
        "zr_rainfed_m": zr_rainfed,
        "zr_irrigated_m": zr_irrigated,
        "daily": rainfed,
        "daily_irrigated": irrigated,
    }


def crop_season_all_years(crop, sowing_mmdd, weather, kc_table, crop_params, soil,
                          years=None, **kwargs):
    """
    crop_season() for the same sowing day ("MM-DD") in every year the
    weather covers (spin-up included). "year" is the sowing year; a
    November sowing's season runs into the next year. Feb 29 becomes
    Feb 28 in non-leap years. Returns one row per year, without the daily
    tables.
    """
    month, day = (int(x) for x in sowing_mmdd.split("-"))
    if years is None:
        years = range(weather.index.min().year, weather.index.max().year + 1)
    rows = []
    for year in years:
        try:
            sow = pd.Timestamp(year=year, month=month, day=day)
        except ValueError:
            sow = pd.Timestamp(year=year, month=month, day=28)
        try:
            result = crop_season(crop, sow, weather, kc_table, crop_params, soil, **kwargs)
        except ValueError as err:
            if "does not cover" in str(err):
                continue
            raise
        result.pop("daily")
        result.pop("daily_irrigated")
        rows.append({"year": year, **result})
    return pd.DataFrame(rows)


# ---------------- validation against SMAP ----------------

def reference_grass_balance(weather, soil, zr_m, p, start, end):
    """Continuous rainfed balance for the reference grass (Kc = 1.0, by the
    definition of ET0) from start (at field capacity) to end."""
    w = weather.loc[start:end]
    taw = total_available_water(soil["theta_fc_m3m3"], soil["theta_wp_m3m3"], zr_m)
    return simulate_balance(w["rainfall_mm"], w["et0_mm"], np.ones(len(w)), taw, p, 0.0)


def weekly_anomaly_correlation(model, observed, months=None):
    """
    Pearson r between weekly anomalies of two daily series.

    Only weeks with all 7 days present in both series are used. A week's
    anomaly is its mean minus the mean of that ISO week number over all
    years (week 53 is folded into 52), so the shared seasonal cycle is
    removed and r measures whether wetter- and drier-than-usual weeks
    line up. months (e.g. [11, 12, 1, 2, 3, 4]) limits r to weeks ending
    in those months; the climatology still uses every week.

    Returns r (anomalies), r_raw (weekly values, seasonal cycle included,
    for context) and n_weeks.
    """
    both = pd.concat({"model": model, "obs": observed}, axis=1).dropna()
    grouped = both.resample("W")
    weekly = grouped.mean()[grouped.count().min(axis=1) == 7]
    week_no = weekly.index.isocalendar().week.clip(upper=52).to_numpy()
    anomaly = weekly - weekly.groupby(week_no).transform("mean")
    if months is not None:
        keep = weekly.index.month.isin(months)
        weekly, anomaly = weekly[keep], anomaly[keep]
    if len(weekly) < 3:
        raise ValueError("Fewer than 3 complete weeks to correlate")
    return {
        "r": float(np.corrcoef(anomaly["model"], anomaly["obs"])[0, 1]),
        "r_raw": float(np.corrcoef(weekly["model"], weekly["obs"])[0, 1]),
        "n_weeks": int(len(weekly)),
    }
