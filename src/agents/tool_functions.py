"""
src/agents/tool_functions.py

Maps tool names (from tools.json) to real, callable Python functions.
This is the ONLY place the agent layer touches actual data — it loads
each district's pre-processed CSVs and calls the deterministic Layer 1
functions in src/compute/agroclimate.py. No AI involvement here.

Weather comes from load_weather() in src/compute/weather.py: NASA GPM IMERG
rain with NASA POWER temperature, humidity, wind and radiation (task 5d).
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compute"))
from agroclimate import (build_feature_table,
                         nearest_analog_year as _nearest_analog_year,
                         backtest_rotation as _backtest_rotation)
from weather import load_weather, RAIN_CITATIONS

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")

# Elevations are the values NASA POWER itself reports for each point.
DISTRICT_META = {
    "cumilla":      {"lat": 23.4607, "lon": 91.1809, "elevation_m": 28.08},
    "noakhali":     {"lat": 22.8696, "lon": 91.0995, "elevation_m": 10.66},
    "feni":         {"lat": 23.0159, "lon": 91.3976, "elevation_m": 10.66},
    "brahmanbaria": {"lat": 23.9571, "lon": 91.1119, "elevation_m": 25.16},
    "sylhet":       {"lat": 24.8949, "lon": 91.8687, "elevation_m": 103.47},
}

SMAP_FIRST_YEAR = 2015  # NASA SMAP L4 record starts 2015-03-31

POWER_SOURCE = {"dataset": "NASA POWER Daily Point API (AG community): temperature, humidity, "
                           "wind, solar radiation",
                "url": "https://power.larc.nasa.gov/"}
RAIN_SOURCE = RAIN_CITATIONS["imerg"]
FIRST_YEAR = 2001  # IMERG rain starts 2001
SMAP_SOURCE = {"dataset": "NASA SMAP L4 root-zone soil moisture (SPL4SMGP.008), via AppEEARS",
               "url": "https://appeears.earthdatacloud.nasa.gov/"}
KC_SOURCE = {"dataset": "FAO-56 crop coefficients (Allen et al., 1998)",
             "url": "https://www.fao.org/4/x0490e/x0490e00.htm"}

_weather_cache = {}
_smap_cache = {}
_kc_table = None


def _load_weather(district):
    if district not in _weather_cache:
        _weather_cache[district] = load_weather(district, data_dir=DATA_DIR)
    return _weather_cache[district]


def candidate_years(weather, decision_date):
    """Years from FIRST_YEAR whose data reaches decision_date, so a year cut
    off by the end of the record (e.g. IMERG ending 30 Sep) is never matched
    on a truncated season."""
    last = weather.index.max()
    return [y for y in range(FIRST_YEAR, last.year + 1)
            if pd.Timestamp(f"{y}-{decision_date}") <= last]


def _load_smap(district):
    if district not in _smap_cache:
        path = os.path.join(DATA_DIR, f"smap_{district}_2015_2026.csv")
        _smap_cache[district] = pd.read_csv(path, index_col="date", parse_dates=True)["sm_rootzone"]
    return _smap_cache[district]


def _load_kc_table():
    global _kc_table
    if _kc_table is None:
        _kc_table = pd.read_csv(os.path.join(DATA_DIR, "kc_table.csv"))
    return _kc_table


def tool_nearest_analog_year(district, current_season, decision_date="10-31"):
    """Returns TWO matches: the closest year overall (every year from 2001
    with complete data, per prompt-2.md's matching decision), and the closest
    year that also has SMAP soil-moisture records, which is the one to backtest.

    decision_date restricts every candidate year's features to data from
    Jan 1 through that MM-DD, so matching never uses data that wouldn't
    yet be available on the day the recommendation is made."""
    weather = _load_weather(district)
    years = candidate_years(weather, decision_date)
    feature_table = build_feature_table(weather, years=years, decision_date=decision_date)
    covered_years = [y for y in feature_table.index if y >= SMAP_FIRST_YEAR]

    overall = _nearest_analog_year(current_season, feature_table)
    covered = _nearest_analog_year(current_season, feature_table,
                                   candidate_years=covered_years)
    return {
        "best_match_overall": overall,
        "best_match_with_soil_moisture": covered,
        "year_to_backtest": covered["analog_year"],
        "years_compared": len(feature_table),
        "years_compared_with_soil_moisture": len(covered_years),
        "note": (f"Matching searched every year from {years[0]} to {years[-1]} with a "
                 "valid monsoon onset. Soil-moisture records start in 2015, so "
                 "rotation backtests use the closest match from 2015 onward."),
        "source": RAIN_SOURCE,
        "sources": [RAIN_SOURCE, POWER_SOURCE],
    }


def tool_backtest_rotation(district, analog_year, rotation_plan):
    """Runs backtest_rotation() on real district data. Refuses pre-2015
    years with a clear message instead of returning a hollow 0-of-0, and
    flags any backtest where part of the rotation had no data."""
    if analog_year < SMAP_FIRST_YEAR:
        raise ValueError(
            f"No SMAP soil-moisture data for {analog_year} (records start "
            f"2015-03-31). Use year_to_backtest from nearest_analog_year."
        )
    meta = DISTRICT_META[district]
    result = _backtest_rotation(
        rotation_plan=rotation_plan,
        analog_year=analog_year,
        power_df=_load_weather(district),
        smap_series=_load_smap(district),
        kc_table=_load_kc_table(),
        latitude_deg=meta["lat"],
        elevation_m=meta["elevation_m"],
    )

    # The day-by-day table is kept out of the model's context (too large);
    # the interface's provenance drawer can request it separately later.
    complete = result["total_days"] == result["planned_days"]
    output = {
        "analog_year": result["analog_year"],
        "planned_days": result["planned_days"],
        "evaluated_days": result["total_days"],
        "coverage_complete": complete,
        "usable_moisture_days": result["usable_moisture_days"],
        "by_crop": result["by_crop"],
        "sources": [SMAP_SOURCE, RAIN_SOURCE, POWER_SOURCE, KC_SOURCE],
    }
    if not complete:
        output["coverage_note"] = (
            f"Only {result['total_days']} of {result['planned_days']} planned days "
            f"had data. Usable-day counts cover the evaluated days only and must "
            f"not be compared directly with a fully covered rotation."
        )
    return output


# Maps tool name (as it appears in tools.json) -> real Python function.
# cite_check is deliberately NOT here: it is not a model-callable tool,
# it runs inside guard() on every final answer.
TOOL_FUNCTIONS = {
    "nearest_analog_year": tool_nearest_analog_year,
    "backtest_rotation": tool_backtest_rotation,
}