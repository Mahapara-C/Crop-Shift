"""
src/compute/agroclimate.py

Deterministic agroclimate functions — pure Python, no AI involvement.
Consumed by nearest_analog_year() and the agent's tool layer, but never
touched by any model at runtime.
"""

import pandas as pd


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