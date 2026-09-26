"""
Diagnostic: is a low backtest score a genuinely dry year, or a drift in
the SMAP record? For each year it compares the average SEASONAL soil-
moisture percentile (June-November, same method as backtest_rotation)
with total June-November rainfall (NASA GPM IMERG via load_weather()). Not
fully independent: SMAP L4's rain forcing is corrected to IMERG.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "agents"))
from tool_functions import _load_smap, _load_weather


def seasonal_percentiles(smap, window=15):
    """Mirrors backtest_rotation(): each day ranked against other years
    within +/- window days of the same day of year."""
    s = smap.dropna()
    doy, yr, v = s.index.dayofyear.values, s.index.year.values, s.values
    out = np.empty(len(s))
    for i in range(len(s)):
        gap = np.abs(doy - doy[i])
        gap = np.minimum(gap, 366 - gap)
        ref = v[(gap <= window) & (yr != yr[i])]
        out[i] = 100.0 * np.sum(ref <= v[i]) / len(ref)
    return pd.Series(out, index=s.index)


for district in ["cumilla", "brahmanbaria", "noakhali"]:
    pct = seasonal_percentiles(_load_smap(district))
    pct = pct[(pct.index.month >= 6) & (pct.index.month <= 11)]
    rain = _load_weather(district)["rainfall_mm"]
    rain = rain[(rain.index.month >= 6) & (rain.index.month <= 11)]

    table = pd.DataFrame({
        "smap_seasonal_pctl": pct.groupby(pct.index.year).mean().round(1),
        "rain_jun_nov_mm": rain.groupby(rain.index.year).sum().round(0),
    }).loc[2015:2025]

    print(f"\n=== {district} ===")
    print(table.to_string())
    print(f"correlation between the two columns: "
          f"{table['smap_seasonal_pctl'].corr(table['rain_jun_nov_mm']):.2f}")