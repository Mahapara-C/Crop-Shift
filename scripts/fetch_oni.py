"""
scripts/fetch_oni.py

Downloads NOAA CPC's Oceanic Nino Index (ONI) ascii table and saves it to
data/reference/oni.csv in CropShift's reference format: one row per
overlapping 3-month season, with the season's SST anomaly plus source
columns so every value is cited.

Run from the repo root:
    python scripts/fetch_oni.py
"""

import os
import requests
import pandas as pd

URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
SOURCE_TITLE = "NOAA CPC Oceanic Nino Index (ONI), 3-month running mean of ERSSTv5 SST anomalies, Nino 3.4 region"
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "reference", "oni.csv")


def fetch():
    response = requests.get(URL, timeout=60)
    response.raise_for_status()

    rows = []
    lines = response.text.strip().splitlines()
    for line in lines[1:]:  # skip header row
        parts = line.split()
        if len(parts) != 4:
            continue
        season, year, total, anom = parts
        rows.append({
            "season": season,
            "year": int(year),
            "total": float(total),
            "anom": float(anom),
            "source_title": SOURCE_TITLE,
            "source_url": URL,
        })

    df = pd.DataFrame(rows)
    out_path = os.path.abspath(OUT_PATH)
    df.to_csv(out_path, index=False)
    print(f"oni.csv: {len(df)} rows, years {df['year'].min()}-{df['year'].max()} -> {out_path}")
    return df


if __name__ == "__main__":
    fetch()
