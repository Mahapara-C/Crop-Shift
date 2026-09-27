"""
scripts/fetch_dswx.py

Downloads OPERA DSWx-S1 (Dynamic Surface Water Extent from Sentinel-1) water
classification for a small window around each district point and saves:

    data/processed/dswx_<district>.csv   (date, water_fraction, valid_fraction, granule_id)

Access: NASA CMR granule search via earthaccess, authenticated with
EARTHDATA_TOKEN from .env, then a 300 m x 300 m windowed read of just the
granule's WTR band (Cloud-Optimized GeoTIFF range request) -- never the
whole scene, and the raster is never written to disk or committed.

WTR band codes (OPERA DSWx-S1 Product Spec v1.0.0, D-108761 Rev A):
  0 = not water, 1 = open water, 3 = inundated vegetation,
  250 = HAND-masked (topographically too high to ever be water),
  251 = layover/shadow-masked (radar geometry, no reliable reading here),
  255 = fill (outside the observed swath for this pass).
water_fraction = share of VALID window pixels (0, 1 or 3) classified as
water (1 or 3). valid_fraction = share of ALL window pixels that are valid
(excludes 250/251/255). A granule whose window is 100% masked/fill is
skipped (there is nothing to report for that pass).

Coverage: DSWx-S1 exists from 2023-12-01 globally, but CLAUDE.md notes it
only exists over this area (Feni/Cumilla, and in practice the neighbouring
Noakhali/Brahmanbaria points) from 21 Aug 2024 -- not Sylhet, whose flood
(June 2022) predates the mission entirely.

Resumable: granule IDs already saved are skipped, so re-running only spends
time on new scenes; progress is saved to disk every 10 new granules.

Run from the repo root:
    python scripts/fetch_dswx.py                          # 4 districts, Aug 2024 to today
    python scripts/fetch_dswx.py feni                      # one district
    python scripts/fetch_dswx.py feni --end 2024-12-31      # a shorter window (faster)
"""

import argparse
import os
import sys
import time

import earthaccess
import numpy as np
import pandas as pd
import rasterio
from dotenv import load_dotenv
from rasterio.warp import transform
from rasterio.windows import from_bounds

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "acquire"))
from fetch_power import DISTRICTS  # noqa: E402

SHORT_NAME = "OPERA_L3_DSWX-S1_V1"
SOURCE_URL = "https://podaac.jpl.nasa.gov/OPERA"
START_DATE = "2024-08-01"
WINDOW_M = 300.0  # metres square, centred on the point
VALID_CODES = {0, 1, 3}
WATER_CODES = {1, 3}
OUT_DIR = os.path.join(ROOT, "data", "processed")

# CLAUDE.md: "OPERA DSWx-S1 exists over Feni/Cumilla from 21 Aug 2024 only."
# Noakhali and Brahmanbaria points are close enough to share that coverage;
# Sylhet's flood predates the DSWx-S1 mission (data starts 2023-12-01), so
# its post-flood analysis uses SMAP alone (docs/results/post_flood.md).
DSWX_DISTRICTS = ("feni", "cumilla", "noakhali", "brahmanbaria")

CSV_COLUMNS = ["date", "water_fraction", "valid_fraction", "granule_id"]


def window_stats(fs, wtr_url, lon, lat, window_m=WINDOW_M):
    """Reads only a window_m x window_m metre window of one WTR GeoTIFF band
    around (lon, lat) via an HTTPS range request (no full-scene download).
    Returns (water_fraction, valid_fraction), or (None, None) if every pixel
    in the window is masked or fill."""
    half = window_m / 2
    with rasterio.open(fs.open(wtr_url)) as ds:
        cx, cy = transform("EPSG:4326", ds.crs, [lon], [lat])
        cx, cy = cx[0], cy[0]
        window = from_bounds(cx - half, cy - half, cx + half, cy + half, ds.transform)
        data = ds.read(1, window=window)
    valid = np.isin(data, list(VALID_CODES))
    if not valid.any():
        return None, None
    water = np.isin(data, list(WATER_CODES))
    return float(water[valid].sum() / valid.sum()), float(valid.sum() / data.size)


def load_saved(path):
    if not os.path.exists(path):
        return pd.DataFrame(columns=CSV_COLUMNS)
    return pd.read_csv(path)


def fetch_district(district, fs, start_date, end_date):
    lat, lon = DISTRICTS[district]["lat"], DISTRICTS[district]["lon"]
    path = os.path.join(OUT_DIR, f"dswx_{district}.csv")
    saved = load_saved(path)
    seen = set(saved["granule_id"])

    granules = earthaccess.search_data(short_name=SHORT_NAME, point=(lon, lat),
                                       temporal=(start_date, end_date))
    granules.sort(key=lambda g: g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"])
    todo = [g for g in granules if g["meta"]["native-id"] not in seen]
    print(f"  {district}: {len(granules)} granules found, {len(seen)} already saved, "
          f"{len(todo)} to fetch")

    rows = saved.to_dict("records")
    t0 = time.time()
    for i, granule in enumerate(todo, start=1):
        granule_id = granule["meta"]["native-id"]
        wtr_url = next(u for u in granule.data_links() if u.endswith("_B01_WTR.tif"))
        begin = granule["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
        date = pd.Timestamp(begin).normalize()
        try:
            water_frac, valid_frac = window_stats(fs, wtr_url, lon, lat)
        except Exception as err:
            print(f"    {date.date()}: read failed ({type(err).__name__}: {err}), skipped")
            continue
        if water_frac is None:
            print(f"    {date.date()}: window fully masked/fill, skipped")
            continue
        rows.append({"date": str(date.date()), "water_fraction": round(water_frac, 4),
                    "valid_fraction": round(valid_frac, 4), "granule_id": granule_id})
        if i % 10 == 0 or i == len(todo):
            elapsed = time.time() - t0
            print(f"    {i}/{len(todo)} fetched, {elapsed:.0f}s elapsed, "
                  f"~{elapsed / i:.1f}s/granule")
            pd.DataFrame(rows, columns=CSV_COLUMNS).sort_values("date").to_csv(path, index=False)
    pd.DataFrame(rows, columns=CSV_COLUMNS).sort_values("date").to_csv(path, index=False)
    return len(rows)


def main(districts, end_date):
    load_dotenv(os.path.join(ROOT, ".env"))
    if not os.environ.get("EARTHDATA_TOKEN"):
        sys.exit("EARTHDATA_TOKEN is not set in .env")
    auth = earthaccess.login(strategy="environment")
    if not auth.authenticated:
        sys.exit("earthaccess could not authenticate with EARTHDATA_TOKEN")
    fs = earthaccess.get_fsspec_https_session()
    for district in districts:
        if district not in DSWX_DISTRICTS:
            print(f"{district}: skipped -- no OPERA DSWx-S1 coverage here before its flood "
                  f"date (CLAUDE.md: DSWx-S1 exists over Feni/Cumilla from 21 Aug 2024 only)")
            continue
        print(f"{district}:")
        n = fetch_district(district, fs, START_DATE, end_date)
        print(f"  saved {n} observations total")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("districts", nargs="*", default=list(DSWX_DISTRICTS),
                        help="district names (default: all 4 with DSWx-S1 coverage)")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"),
                        help="last date to search (default: today)")
    args = parser.parse_args()
    main(args.districts, args.end)
