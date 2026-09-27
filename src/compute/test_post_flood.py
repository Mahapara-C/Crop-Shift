"""
Unit tests for src/compute/post_flood.py
Run from the repo root with: python -m pytest src -q
"""

import os

import numpy as np
import pandas as pd
import pytest
from post_flood import (smap_days_to_normal, water_persistence, earliest_sowing_date,
                        crops_still_possible, CROP_CALENDAR_PATH)


# ---------------- smap_days_to_normal ----------------

def _synthetic_smap(flood_year=2024, n_other_years=4, dry_value=0.20, wet_value=0.45,
                    recovery_day=10):
    """Several years of a flat dry-season baseline (dry_value) around the flood
    date's calendar window, so the pct percentile threshold ~= dry_value. The
    flood year starts wet and linearly recovers to dry_value by recovery_day,
    then stays dry."""
    dates, values = [], []
    for year in range(flood_year - n_other_years, flood_year):
        for day_offset in range(-30, 31):
            dates.append(pd.Timestamp(year, 8, 15) + pd.Timedelta(days=day_offset))
            values.append(dry_value)
    flood_start = pd.Timestamp(flood_year, 8, 15)
    for day_offset in range(0, 40):
        dates.append(flood_start + pd.Timedelta(days=day_offset))
        if day_offset <= recovery_day:
            frac = day_offset / recovery_day
            values.append(wet_value - frac * (wet_value - dry_value))
        else:
            values.append(dry_value)
    series = pd.Series(values, index=pd.DatetimeIndex(dates), name="sm_rootzone")
    return series.groupby(series.index).first().sort_index(), flood_start


def test_recovers_after_expected_day():
    series, flood_date = _synthetic_smap()
    result = smap_days_to_normal(series, flood_date, pct=80, window_days=15, hold_days=5)
    # threshold ~= dry baseline value (80th pct of a flat series = that value);
    # the series is <= dry_value from recovery_day (10) onward.
    assert result["days_to_normal"] == 10
    assert result["normal_date"] == str((flood_date + pd.Timedelta(days=10)).date())


def test_higher_percentile_recovers_sooner_or_same():
    series, flood_date = _synthetic_smap()
    result = smap_days_to_normal(series, flood_date, pct=80, window_days=15, hold_days=5)
    assert result["sensitivity"]["pct_90"]["days"] <= result["sensitivity"]["pct_70"]["days"]


def test_reports_70_80_90_sensitivity():
    series, flood_date = _synthetic_smap()
    result = smap_days_to_normal(series, flood_date, pct=80, window_days=15, hold_days=5)
    assert set(result["sensitivity"]) == {"pct_70", "pct_80", "pct_90"}


def test_never_recovers_returns_none():
    series, flood_date = _synthetic_smap(dry_value=0.20, wet_value=0.45, recovery_day=1000)
    # truncate so the series ends before recovery
    series = series[series.index <= flood_date + pd.Timedelta(days=5)]
    result = smap_days_to_normal(series, flood_date, pct=80, window_days=15, hold_days=5)
    assert result["days_to_normal"] is None
    assert result["normal_date"] is None


def test_hold_days_requires_a_consecutive_run():
    dates = pd.date_range("2024-08-15", periods=20, freq="D")
    # dips below threshold on day 2 only, otherwise wet; baseline years all flat at 0.40
    other_years = []
    other_dates = []
    for year in (2020, 2021, 2022, 2023):
        for offset in range(-15, 16):
            other_dates.append(pd.Timestamp(year, 8, 15) + pd.Timedelta(days=offset))
            other_years.append(0.40)
    values = [0.50] * 20
    values[2] = 0.10  # single-day dip, should not count as recovery
    values[10] = 0.10
    values[11] = 0.10
    values[12] = 0.10  # 3-day run, still short of hold_days=3... make it exactly 3
    all_dates = list(dates) + other_dates
    all_values = values + other_years
    series = pd.Series(all_values, index=pd.DatetimeIndex(all_dates)).sort_index()
    series = series[~series.index.duplicated()]
    result = smap_days_to_normal(series, dates[0], pct=80, window_days=15, hold_days=3)
    assert result["days_to_normal"] == 10


def test_raises_when_no_data_after_flood_date():
    series, flood_date = _synthetic_smap()
    with pytest.raises(ValueError):
        smap_days_to_normal(series, flood_date + pd.Timedelta(days=10000))


def test_accepts_dataframe_with_value_column():
    series, flood_date = _synthetic_smap()
    df = series.rename("sm_rootzone").to_frame()
    result = smap_days_to_normal(df, flood_date, pct=80, window_days=15, hold_days=5)
    assert result["days_to_normal"] == 10


# ---------------- water_persistence ----------------

def test_last_water_date_from_cloud_free_observations():
    dswx = pd.DataFrame({
        "date": ["2024-08-01", "2024-08-05", "2024-08-10", "2024-08-15", "2024-08-20"],
        "water_fraction": [0.9, 0.6, 0.05, 0.02, 0.0],
        "valid_fraction": [0.9, 0.8, 0.7, 0.9, 0.9],
    })
    result = water_persistence(dswx)
    assert result["last_water_date"] == "2024-08-05"
    assert result["cloud_free_observations"] == 5


def test_ignores_low_validity_scenes():
    dswx = pd.DataFrame({
        "date": ["2024-08-01", "2024-08-20"],
        "water_fraction": [0.9, 0.9],   # the later scene looks flooded...
        "valid_fraction": [0.9, 0.1],   # ...but is mostly cloud/no-data
    })
    result = water_persistence(dswx, valid_threshold=0.5)
    assert result["last_water_date"] == "2024-08-01"
    assert result["cloud_free_observations"] == 1


def test_no_water_ever_seen_returns_none():
    dswx = pd.DataFrame({
        "date": ["2024-08-01", "2024-08-05"],
        "water_fraction": [0.01, 0.0],
        "valid_fraction": [0.9, 0.9],
    })
    result = water_persistence(dswx)
    assert result["last_water_date"] is None
    assert result["cloud_free_observations"] == 2


# ---------------- earliest_sowing_date ----------------

def test_earliest_date_is_the_later_of_soil_and_water():
    soil = {"normal_date": "2024-08-20"}
    water_later = {"last_water_date": "2024-08-25"}  # gone on the 26th, later than soil
    assert earliest_sowing_date(soil, water_later) == "2024-08-26"

    water_earlier = {"last_water_date": "2024-08-01"}  # gone on the 2nd, earlier than soil
    assert earliest_sowing_date(soil, water_earlier) == "2024-08-20"


def test_earliest_date_uses_soil_only_when_water_never_seen():
    soil = {"normal_date": "2024-08-20"}
    water_never = {"last_water_date": None}
    assert earliest_sowing_date(soil, water_never) == "2024-08-20"


def test_earliest_date_none_when_soil_never_normal():
    soil = {"normal_date": None}
    water = {"last_water_date": "2024-08-01"}
    assert earliest_sowing_date(soil, water) is None


# ---------------- crops_still_possible ----------------

def test_crop_calendar_file_missing_returns_research_pending(tmp_path):
    missing_path = tmp_path / "crop_calendar.csv"
    result = crops_still_possible("2024-08-20", "feni", crops=["rice", "wheat"], path=str(missing_path))
    assert result["possible"] == []
    assert {p["crop"] for p in result["pending"]} == {"rice", "wheat"}
    assert all("research pending" in p["notice"] for p in result["pending"])


def test_crop_row_missing_is_skipped_not_invented(tmp_path):
    path = tmp_path / "crop_calendar.csv"
    pd.DataFrame([
        {"crop": "rice", "district": "feni", "sow_window_start": "2024-08-01",
         "sow_window_end": "2024-09-15"},
    ]).to_csv(path, index=False)
    result = crops_still_possible("2024-08-20", "feni", crops=["rice", "wheat"], path=str(path))
    assert result["possible"] == [{"crop": "rice", "still_possible": True,
                                   "sow_window_end": "2024-09-15"}]
    assert result["pending"] == [{"crop": "wheat", "notice": "research pending: no "
                                  "crop_calendar.csv row for wheat in feni"}]


def test_still_possible_is_false_when_earliest_date_past_window():
    path_df = pd.DataFrame([
        {"crop": "rice", "district": "feni", "sow_window_start": "2024-08-01",
         "sow_window_end": "2024-08-10"},
    ])
    tmp = os.path.join(os.path.dirname(__file__), "_tmp_crop_calendar_test.csv")
    path_df.to_csv(tmp, index=False)
    try:
        result = crops_still_possible("2024-08-20", "feni", crops=["rice"], path=tmp)
        assert result["possible"] == [{"crop": "rice", "still_possible": False,
                                       "sow_window_end": "2024-08-10"}]
    finally:
        os.remove(tmp)


def test_raises_on_none_earliest_date():
    with pytest.raises(ValueError):
        crops_still_possible(None, "feni")


def test_real_crop_calendar_path_is_missing_for_now():
    # data/reference/crop_calendar.csv has not been researched/added yet
    # (CLAUDE.md: no source, no row) -- this documents that state rather
    # than assuming it exists.
    assert not os.path.exists(CROP_CALENDAR_PATH)
