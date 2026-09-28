"""
src/compute/post_flood.py

Task 7a: how long after a flood is a plot ready to sow again, and what does
that do to the crop choice?

Two independent signals, both NASA:
  - smap_days_to_normal(): SMAP root-zone soil moisture recovers to a normal,
    non-flooded level (a calendar-window percentile from every OTHER year),
    held for several days so a single dry reading doesn't count.
  - water_persistence(): OPERA DSWx-S1 says when standing water was last
    seen near the point.
  - flood_recession() (Task 7a-2): over a 20 km x 20 km DSWx-S1 area, the
    flood-water peak and when it fell below 10% of that peak.

earliest_sowing_date() takes the later of the two (soil dry AND water gone).
crops_still_possible() then checks that date against data/reference/
crop_calendar.csv; a crop with no cited sowing window there is skipped with
a "research pending" notice rather than guessing one (CLAUDE.md: no source,
no row) -- this is the flood -> late-sowing -> risk cascade CLAUDE.md asks
for, minus the risk_calendar.py re-ranking step (Task 6, not built yet).

Rain everywhere else in CropShift is NASA GPM IMERG (src/compute/weather.py);
this module uses SMAP root-zone soil moisture and DSWx-S1 water fraction,
which are independent of that choice.
"""

import os

import numpy as np
import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CROP_CALENDAR_PATH = os.path.join(REPO_ROOT, "data", "reference", "crop_calendar.csv")

REFERENCE_YEAR = 2001  # any non-leap year, used only to map (month, day) -> day-of-year


def _doy(month, day):
    """Day-of-year in a fixed non-leap reference year, so Feb 29 maps to Feb 28."""
    if month == 2 and day == 29:
        day = 28
    return pd.Timestamp(REFERENCE_YEAR, month, day).dayofyear


def _circular_distance(doy_a, doy_b, year_len=365):
    """Distance between two day-of-year values, wrapping across the year boundary."""
    diff = abs(doy_a - doy_b)
    return min(diff, year_len - diff)


def _calendar_window_percentile(series, target_date, pct, window_days, other_years_only=True):
    """pct percentile of `series` values whose date falls within window_days of
    target_date's (month, day) in any year (other_years_only=True: every year
    except target_date's own). None if no values fall in the window."""
    target_doy = _doy(target_date.month, target_date.day)
    doys = np.array([_doy(d.month, d.day) for d in series.index])
    dist = np.array([_circular_distance(target_doy, d) for d in doys])
    mask = dist <= window_days
    if other_years_only:
        mask &= series.index.year != target_date.year
    values = series[mask]
    if len(values) == 0:
        return None
    return float(np.percentile(values, pct))


def _days_to_normal(series, flood_date, pct, window_days, hold_days):
    """First run of hold_days consecutive days, on or after flood_date, each at
    or below that day's calendar-window percentile threshold. Returns
    {"days", "date"} with both None if the series never recovers."""
    after = series[series.index >= flood_date]
    is_below = []
    for d in after.index:
        threshold = _calendar_window_percentile(series, d, pct, window_days)
        is_below.append(threshold is not None and series.loc[d] <= threshold)
    below = pd.Series(is_below, index=after.index)
    run = 0
    for i, is_below in enumerate(below):
        run = run + 1 if is_below else 0
        if run >= hold_days:
            normal_date = below.index[i - hold_days + 1]
            return {"days": int((normal_date - flood_date).days), "date": str(normal_date.date())}
    return {"days": None, "date": None}


def smap_days_to_normal(smap_df, flood_date, pct=80, window_days=15, hold_days=7,
                        value_col="sm_rootzone"):
    """
    Days from flood_date until SMAP root-zone soil moisture is back to a
    normal (non-flooded) level.

    "Normal" for a given day = at or below the `pct` percentile of that
    calendar day (+/- window_days) taken over every OTHER year in smap_df,
    held for hold_days days in a row so one dry reading doesn't count.

    smap_df : DataFrame with a DatetimeIndex (or one with a "date" column)
        and a `value_col` column, covering several years so the "other
        years" percentile is meaningful.
    flood_date : the date to count recovery from (e.g. flood peak).

    Returns {"days_to_normal", "normal_date", "pct", "sensitivity"} where
    sensitivity also reports pct 70 and 90 as {"pct_70": {...}, "pct_90": {...}}
    (days/date None if the series never recovers in the data).
    """
    if isinstance(smap_df, pd.DataFrame):
        series = smap_df[value_col]
    else:
        series = smap_df
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError("smap_df must have (or be indexed by) dates")
    series = series.sort_index().dropna()
    flood_date = pd.Timestamp(flood_date)
    if flood_date not in series.index and flood_date > series.index.max():
        raise ValueError(f"No SMAP data on or after flood_date {flood_date.date()}")

    sensitivity = {p: _days_to_normal(series, flood_date, p, window_days, hold_days)
                   for p in sorted({70, 80, 90, pct})}
    primary = sensitivity[pct]
    return {
        "days_to_normal": primary["days"],
        "normal_date": primary["date"],
        "pct": pct,
        "window_days": window_days,
        "hold_days": hold_days,
        "sensitivity": {f"pct_{p}": sensitivity[p] for p in sorted(sensitivity)},
    }


def water_persistence(dswx_df, water_threshold=0.1, valid_threshold=0.5,
                      date_col="date", water_col="water_fraction", valid_col="valid_fraction"):
    """
    From OPERA DSWx-S1 observations near a point (as saved by
    scripts/fetch_dswx.py: date, water_fraction, valid_fraction), the last
    date open water was seen and how many cloud-free-enough observations
    there were to look at.

    Only observations with valid_fraction >= valid_threshold are used (a
    scene mostly cloud/no-data is not trusted either way). "Open water" =
    water_fraction >= water_threshold among those.

    Returns {"last_water_date" (None if water was never seen),
    "cloud_free_observations"}.
    """
    df = dswx_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    usable = df[df[valid_col] >= valid_threshold]
    water_rows = usable[usable[water_col] >= water_threshold]
    last_water_date = water_rows[date_col].max() if len(water_rows) else None
    return {
        "last_water_date": str(last_water_date.date()) if last_water_date is not None else None,
        "cloud_free_observations": int(len(usable)),
    }


def flood_recession(dswx_area_df, fraction_of_peak=0.10, hold_scenes=2, valid_threshold=0.5,
                    baseline=0.0, value_col="flood_km2", date_col="date",
                    valid_col="valid_fraction"):
    """
    Task 7a-2: when did FLOOD water over an area (scripts/fetch_dswx.py
    --area: date, flood_km2, flood_fraction, valid_fraction, n_scenes) drain?

    Only scenes with valid_fraction >= valid_threshold are used. The peak is
    the largest `value_col`; "mostly gone" is the first scene after the peak
    below fraction_of_peak x peak, staying below it for hold_scenes scenes in
    a row (so one low reading between passes doesn't count).

    baseline (default 0): the level of "flood" water the method reports with
    no flood at all (e.g. the median over dry-season reference scenes: wet
    paddies, radar speckle). With a baseline the threshold becomes
    baseline + fraction_of_peak x (peak - baseline), i.e. 90% of the water
    ABOVE that floor has gone. baseline=0 is the plain 10%-of-peak rule.

    Returns {"peak_date", "peak_value", "threshold", "water_gone_date",
    "days_peak_to_gone", "scenes_used"}; water_gone_date and
    days_peak_to_gone are None if the flood never receded in the data.
    """
    df = dswx_area_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df[df[valid_col] >= valid_threshold].sort_values(date_col).reset_index(drop=True)
    if df.empty:
        raise ValueError("no scenes with valid_fraction >= valid_threshold")
    peak_idx = int(df[value_col].idxmax())
    peak_date, peak_value = df.loc[peak_idx, date_col], float(df.loc[peak_idx, value_col])
    threshold = baseline + fraction_of_peak * (peak_value - baseline)

    gone_date, run = None, 0
    after = df.iloc[peak_idx + 1:]
    for i, value in enumerate(after[value_col]):
        run = run + 1 if value < threshold else 0
        if run >= hold_scenes:
            gone_date = after.iloc[i - hold_scenes + 1][date_col]
            break
    return {
        "peak_date": str(peak_date.date()),
        "peak_value": peak_value,
        "threshold": threshold,
        "water_gone_date": str(gone_date.date()) if gone_date is not None else None,
        "days_peak_to_gone": int((gone_date - peak_date).days) if gone_date is not None else None,
        "scenes_used": int(len(df)),
    }


def earliest_sowing_date(days_to_normal_result, water_persistence_result):
    """
    The later of: soil back to normal (days_to_normal_result["normal_date"])
    and water gone. Water gone is either flood_recession()'s
    "water_gone_date" (area mode: flood water mostly gone), or else the day
    after water_persistence()'s "last_water_date" (the last day water was
    confirmed present) -- no other buffer is added, per CLAUDE.md: no extra
    buffer unless it is sourced from data/reference/.

    If water was never observed, soil moisture is the only constraint. None
    if soil moisture never reached normal in the data.
    """
    normal_date = days_to_normal_result.get("normal_date")
    if normal_date is None:
        return None
    soil_date = pd.Timestamp(normal_date)
    if "water_gone_date" in water_persistence_result:
        gone = water_persistence_result["water_gone_date"]
        if gone is None:
            return None  # flood water never receded in the data: no date to give
        return str(max(soil_date, pd.Timestamp(gone)).date())
    last_water = water_persistence_result.get("last_water_date")
    if last_water is None:
        return str(soil_date.date())
    water_gone_date = pd.Timestamp(last_water) + pd.Timedelta(days=1)
    return str(max(soil_date, water_gone_date).date())


def crops_still_possible(earliest_date, district, crops=None, path=CROP_CALENDAR_PATH):
    """
    For each crop, compares earliest_date to that crop's cited sow.window_end
    for `district` in data/reference/crop_calendar.csv (expected columns:
    crop, district, sow_window_start, sow_window_end, plus the usual
    source_title/source_url/... columns).

    crops=None checks every crop with a row for this district. A crop with
    no row -- because the file doesn't exist yet, or this crop/district
    combination isn't in it -- is never given an invented window: it is
    returned under "pending" with a "research pending" notice instead.

    Returns {"possible": [{"crop", "still_possible", "sow_window_end"}, ...],
    "pending": [{"crop", "notice"}, ...]}.
    """
    if earliest_date is None:
        raise ValueError("earliest_date is None: soil moisture never reached normal in the data")
    earliest = pd.Timestamp(earliest_date)

    if not os.path.exists(path):
        pending = [{"crop": c, "notice": "research pending: data/reference/crop_calendar.csv "
                                          "does not exist yet"} for c in (crops or [])]
        return {"possible": [], "pending": pending}

    calendar = pd.read_csv(path)
    if not {"crop", "district", "sow_window_end"} <= set(calendar.columns):
        # The researched file uses the item,value reference format; windows
        # from it are read by risk_calendar.rotation_options() instead.
        pending = [{"crop": c, "notice": "crop_calendar.csv is in item/value format: use "
                                          "risk_calendar.rotation_options() for sowing windows"}
                   for c in (crops or [])]
        return {"possible": [], "pending": pending}
    calendar = calendar[calendar["district"] == district]
    check_crops = crops if crops is not None else sorted(calendar["crop"].unique())

    possible, pending = [], []
    for crop in check_crops:
        rows = calendar[calendar["crop"] == crop]
        if rows.empty:
            pending.append({"crop": crop, "notice": f"research pending: no crop_calendar.csv "
                                                     f"row for {crop} in {district}"})
            continue
        window_end = pd.Timestamp(rows.iloc[0]["sow_window_end"])
        possible.append({
            "crop": crop,
            "still_possible": bool(earliest <= window_end),
            "sow_window_end": str(window_end.date()),
        })
    return {"possible": possible, "pending": pending}
