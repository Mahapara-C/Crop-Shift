"""
src/compute/weather.py

One loader for a district's daily weather table, so every script and tool uses the
same rain source.

load_weather(district, rain_source="imerg") returns the NASA POWER daily table
(temperature, humidity, wind, solar radiation from POWER) with rainfall_mm taken
from NASA GPM IMERG V07 Final Run daily (GPM_3IMERGDF.07), plus a rain_source column.

Why: NASA POWER rain has step changes (around 1997 and again around 2015-16) that
are data artifacts, not climate; see docs/results/rain_source_check.md.

With rain_source="imerg" the table is cut to the days IMERG covers (2001-01-01 to
its last saved day). POWER rain is never used to fill the gaps, so one table never
mixes two rain records.
"""

import os

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")
RAIN_SOURCES = ("imerg", "power")
DEFAULT_RAIN_SOURCE = "imerg"

# Citation for the rain column, for any tool result that reports rain.
RAIN_CITATIONS = {
    "imerg": {"dataset": "NASA GPM IMERG V07 Final Run daily (GPM_3IMERGDF.07), 0.1 degree",
              "url": "https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDF_07/summary"},
    "power": {"dataset": "NASA POWER daily, AG community (PRECTOTCORR)",
              "url": "https://power.larc.nasa.gov/"},
}


def load_weather(district, rain_source=DEFAULT_RAIN_SOURCE, data_dir=DATA_DIR):
    """Daily weather for one district, indexed by date.

    Columns: the POWER columns (rainfall_mm, temp_mean_c, ...) plus rain_source.
    rain_source="imerg": rainfall_mm replaced by IMERG, rows limited to IMERG's dates.
    rain_source="power": the POWER table unchanged.
    Raises ValueError for an unknown source or if IMERG has a missing day inside
    its range (no silent gaps).
    """
    if rain_source not in RAIN_SOURCES:
        raise ValueError(f"rain_source must be one of {RAIN_SOURCES}, got {rain_source!r}")
    power = pd.read_csv(os.path.join(data_dir, f"power_{district}_daily.csv"),
                        index_col="date", parse_dates=True)
    if rain_source == "power":
        return power.assign(rain_source="power")

    imerg = pd.read_csv(os.path.join(data_dir, f"imerg_{district}_daily.csv"),
                        index_col="date", parse_dates=True)["rainfall_mm"]
    days = pd.date_range(imerg.index.min(), imerg.index.max(), freq="D")
    imerg = imerg.reindex(days)
    if imerg.isna().any():
        first_gap = imerg.index[imerg.isna()][0].date()
        raise ValueError(f"IMERG rain for {district} has missing days (first: {first_gap})")

    weather = power.loc[power.index.isin(days)].copy()
    weather["rainfall_mm"] = imerg.reindex(weather.index).values
    weather["rain_source"] = "imerg"
    return weather
