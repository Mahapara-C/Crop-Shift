"""
src/acquire/fetch_power.py

Downloads NASA POWER daily data (AG community, 2001 to END_DATE) for one district
and saves it to data/processed/ with CropShift's standard column names.

Run from the repo root, e.g.:
    python src/acquire/fetch_power.py sylhet
"""

import os
import sys
import requests
import pandas as pd

DISTRICTS = {
    "cumilla":      {"lat": 23.4607, "lon": 91.1809},
    "noakhali":     {"lat": 22.8696, "lon": 91.0995},
    "feni":         {"lat": 23.0159, "lon": 91.3976},
    "brahmanbaria": {"lat": 23.9571, "lon": 91.1119},
    "sylhet":       {"lat": 24.8949, "lon": 91.8687},
}

# POWER parameter name -> CropShift column name. This order is also the
# column order in the saved file, so every district's file is identical in shape.
COLUMNS = {
    "PRECTOTCORR": "rainfall_mm",
    "T2M": "temp_mean_c",
    "T2M_MAX": "temp_max_c",
    "T2M_MIN": "temp_min_c",
    "RH2M": "rh_pct",
    "WS2M": "wind_speed_ms",
    "ALLSKY_SFC_SW_DWN": "solar_rad_mj_m2",  # MJ/m2/day under the AG community
}

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
END_DATE = "20260831"  # latest month safely available; SMAP runs to 2026-09-20
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")


def fetch(district):
    coords = DISTRICTS[district]
    params = {
        "parameters": ",".join(COLUMNS.keys()),
        "community": "AG",
        "longitude": coords["lon"],
        "latitude": coords["lat"],
        "start": "20010101",
        "end": END_DATE,
        "format": "JSON",
    }
    response = requests.get(URL, params=params, timeout=120)
    response.raise_for_status()
    data = response.json()

    df = pd.DataFrame(data["properties"]["parameter"])
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    df = df.rename(columns=COLUMNS)[list(COLUMNS.values())]

    missing = int((df == -999).sum().sum())
    elevation = data["geometry"]["coordinates"][2]

    out_path = os.path.abspath(os.path.join(OUT_DIR, f"power_{district}_daily.csv"))
    df.to_csv(out_path)
    print(f"{district}: {len(df)} rows, {missing} missing values, "
          f"elevation {elevation} m -> {out_path}")


if __name__ == "__main__":
    fetch(sys.argv[1])