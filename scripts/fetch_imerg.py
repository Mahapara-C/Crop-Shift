"""
scripts/fetch_imerg.py

Downloads NASA GPM IMERG V07 Final Run daily precipitation (GES DISC product
GPM_3IMERGDF, version 07) for the five district points in src/acquire/fetch_power.py,
from 2001-01-01 to the latest day available, and saves one small file per district:

    data/processed/imerg_<district>_daily.csv   (columns: date,rainfall_mm)

Access: the NASA Giovanni time-series API (one request per point per calendar year).
Giovanni returns the value of the 0.1 degree IMERG cell that contains the point,
which is also the nearest cell centre; the script checks that and records the cell
centre in data/processed/imerg_cells.csv.

Resumable: days already saved are skipped; a year is only requested again if some
of its days are missing. The Earthdata token is read from .env (EARTHDATA_TOKEN)
and is never printed.

Run from the repo root:
    python scripts/fetch_imerg.py            # all five districts
    python scripts/fetch_imerg.py feni       # one district
"""

import datetime as dt
import io
import os
import sys
import time

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "acquire"))
from fetch_power import DISTRICTS  # noqa: E402

URL = "https://api.giovanni.earthdata.nasa.gov/timeseries"
DATA_ID = "GPM_3IMERGDF_07_precipitation"
PRODUCT = "GPM_3IMERGDF.07"
DOI = "10.5067/GPM/IMERGDF/DAY/07"
SOURCE_URL = "https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDF_07/summary"
START_DATE = dt.date(2001, 1, 1)
UNDEF = -9999.9
OUT_DIR = os.path.join(ROOT, "data", "processed")
CELLS_PATH = os.path.join(OUT_DIR, "imerg_cells.csv")


def nearest_cell_centre(value):
    """Centre of the 0.1 degree IMERG cell containing `value` (cells run x.x0 to x.x0+0.1)."""
    return round(np.floor(value * 10) / 10 + 0.05, 2)


def parse_giovanni_csv(text):
    """Split Giovanni's time-series CSV into (header dict, Series of daily mm)."""
    head_text, _, table_text = text.partition("\n\n")
    header = {}
    for line in head_text.strip().splitlines():
        key, _, value = line.partition(",")
        header[key.strip()] = value.strip()
    table = pd.read_csv(io.StringIO(table_text.strip()))
    dates = pd.to_datetime(table.iloc[:, 0]).dt.normalize()
    rain = pd.to_numeric(table.iloc[:, 1], errors="coerce")
    rain = rain.where(rain > UNDEF + 1)  # -9999.9 = no data
    return header, pd.Series(rain.values, index=dates, name="rainfall_mm")


def fetch_year(token, lat, lon, year, end_date):
    """One Giovanni request for one point and one calendar year (clipped to end_date).
    Returns (header, series) or (None, None) if Giovanni has no data in that range."""
    last = min(dt.date(year, 12, 31), end_date)
    params = {"data": DATA_ID, "location": f"[{lat},{lon}]",
              "time": f"{year}-01-01T00:00:00/{last.isoformat()}T23:59:59"}
    for attempt in range(3):
        try:
            r = requests.get(URL, params=params, timeout=300,
                             headers={"Authorization": f"Bearer {token}"})
        except requests.RequestException as err:
            print(f"    {year}: network error ({type(err).__name__}), retry {attempt + 1}")
            time.sleep(5)
            continue
        if r.status_code == 404 and "not found" in r.text.lower():
            return None, None
        if r.status_code == 200:
            return parse_giovanni_csv(r.text)
        print(f"    {year}: HTTP {r.status_code}, retry {attempt + 1}")
        time.sleep(5)
    raise RuntimeError(f"Giovanni request failed 3 times for {year} at [{lat},{lon}]")


def load_saved(path):
    if not os.path.exists(path):
        return pd.Series(dtype=float, name="rainfall_mm")
    saved = pd.read_csv(path, index_col="date", parse_dates=True)["rainfall_mm"]
    return saved.dropna()


def fetch_district(district, token, end_date):
    lat, lon = DISTRICTS[district]["lat"], DISTRICTS[district]["lon"]
    path = os.path.join(OUT_DIR, f"imerg_{district}_daily.csv")
    rain = load_saved(path)
    header = None
    t0 = time.time()
    for year in range(START_DATE.year, end_date.year + 1):
        days = pd.date_range(f"{year}-01-01", min(dt.date(year, 12, 31), end_date))
        if days.isin(rain.index).all():
            continue
        header, new = fetch_year(token, lat, lon, year, end_date)
        if new is None:
            print(f"  {district} {year}: no IMERG data on Giovanni; stopping here")
            break
        rain = pd.concat([rain[~rain.index.isin(new.index)], new.dropna()]).sort_index()
        rain.round(2).rename_axis("date").to_csv(path, header=True)
        print(f"  {district} {year}: {new.notna().sum()} days, "
              f"{time.time() - t0:.0f} s so far")
        if len(new) < len(days):
            break  # reached the end of the available record
    return rain, header


def record_cell(district, header, rain):
    lat, lon = DISTRICTS[district]["lat"], DISTRICTS[district]["lon"]
    cell_lat, cell_lon = nearest_cell_centre(lat), nearest_cell_centre(lon)
    if header is not None:
        g_lat, g_lon = float(header["lat"]), float(header["lon"])
        if abs(g_lat - cell_lat) > 1e-6 or abs(g_lon - cell_lon) > 1e-6:
            raise ValueError(f"{district}: Giovanni cell ({g_lat}, {g_lon}) is not the "
                             f"nearest 0.1 degree cell ({cell_lat}, {cell_lon})")
    cells = (pd.read_csv(CELLS_PATH, index_col="district") if os.path.exists(CELLS_PATH)
             else pd.DataFrame())
    cells.loc[district, ["point_lat", "point_lon", "cell_lat", "cell_lon"]] = [lat, lon, cell_lat, cell_lon]
    cells.loc[district, ["first_date", "last_date", "days"]] = [
        str(rain.index.min().date()), str(rain.index.max().date()), len(rain)]
    cells.loc[district, ["product", "doi", "access", "source_url"]] = [
        PRODUCT, DOI, URL, SOURCE_URL]
    cells["days"] = cells["days"].astype(int)
    cells.index.name = "district"
    cells.sort_index().to_csv(CELLS_PATH)


def main(districts):
    load_dotenv(os.path.join(ROOT, ".env"))
    token = os.environ.get("EARTHDATA_TOKEN")
    if not token:
        sys.exit("EARTHDATA_TOKEN is not set in .env")
    end_date = dt.date.today() - dt.timedelta(days=1)
    for district in districts:
        print(f"{district}:")
        rain, header = fetch_district(district, token, end_date)
        if len(rain):
            record_cell(district, header, rain)
            print(f"  saved {len(rain)} days, {rain.index.min().date()} to {rain.index.max().date()}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(DISTRICTS))
