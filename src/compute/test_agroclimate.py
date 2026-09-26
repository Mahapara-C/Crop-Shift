"""
Unit tests for src/compute/agroclimate.py
Run from src/compute with: pytest test_agroclimate.py -v
"""

import numpy as np
import pandas as pd
import pytest
from agroclimate import (rain_onset, build_feature_table, nearest_analog_year,
                         dry_spell_length, eto_penman_monteith, backtest_rotation)


def make_series(values, start_date="2019-01-01"):
    """Helper: build a daily rainfall Series from a plain list of values."""
    dates = pd.date_range(start=start_date, periods=len(values), freq="D")
    return pd.Series(values, index=dates)


# ---------------- rain_onset ----------------

def test_detects_clear_monsoon_onset():
    """A single realistic wet season should be detected near its start."""
    values = [0.0] * 100 + [25.0] * 60 + [0.0] * 100
    result = rain_onset(make_series(values), 2019)
    assert result["onset_doy"] is not None
    assert 100 <= result["onset_doy"] <= 108


def test_rejects_isolated_wet_week():
    """A single wet week with no sustained rain after it is not onset —
    the exact false-start bug found on real 2019 data."""
    values = [0.0] * 50 + [25.0] * 7 + [0.0] * 300
    result = rain_onset(make_series(values), 2019)
    assert result["onset_doy"] is None


def test_no_rain_all_year_returns_none():
    """A year with no rainfall at all should return None, not crash."""
    result = rain_onset(make_series([0.0] * 365), 2020)
    assert result["onset_doy"] is None
    assert result["onset_amount_mm"] is None


def test_handles_short_year_gracefully():
    """A partial year shouldn't crash even without a full confirm window."""
    result = rain_onset(make_series([0.0] * 10 + [30.0] * 7), 2025)
    assert "onset_doy" in result


# ---------------- dry_spell_length ----------------

def test_dry_spell_length_finds_longest_run():
    values = [0.0, 5.0, 0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert dry_spell_length(make_series(values)) == 5


# ---------------- build_feature_table: decision_date ----------------

def _monsoon_df(n_days=365, start="2019-01-01"):
    """A year with a clear, valid monsoon onset around day 100, so
    build_feature_table() actually produces a row (not excluded for lack
    of onset)."""
    values = [0.0] * 100 + [25.0] * 60 + [0.0] * (n_days - 160)
    temps = [25.0] * n_days
    return pd.DataFrame({"rainfall_mm": values, "temp_mean_c": temps},
                        index=pd.date_range(start, periods=n_days, freq="D"))


def test_decision_date_ignores_data_after_cutoff():
    """Rainfall/temp changes made only AFTER decision_date must not move
    the computed features at all."""
    df = _monsoon_df()
    table_before = build_feature_table(df, years=[2019], decision_date="10-31")
    assert not table_before.empty  # sanity: onset was actually found

    # Mutate only the data strictly after Oct 31 with wildly different
    # values; the decision_date cutoff should make this invisible.
    df_after = df.copy()
    after_cutoff = df_after.index > pd.Timestamp("2019-10-31")
    df_after.loc[after_cutoff, "rainfall_mm"] = 500.0
    df_after.loc[after_cutoff, "temp_mean_c"] = 45.0
    table_after = build_feature_table(df_after, years=[2019], decision_date="10-31")

    pd.testing.assert_frame_equal(table_before, table_after)


def test_different_decision_date_changes_features():
    """An earlier decision_date that excludes the monsoon onset (or part
    of the growing season) must change the computed features."""
    values = [0.0] * 100 + [25.0] * 60 + [0.0] * 205  # onset ~day 100
    df = pd.DataFrame({
        "rainfall_mm": values,
        "temp_mean_c": [25.0] * 200 + [30.0] * 165,
    }, index=pd.date_range("2019-01-01", periods=365, freq="D"))

    table_full = build_feature_table(df, years=[2019], decision_date="10-31")
    table_early = build_feature_table(df, years=[2019], decision_date="06-30")

    assert not table_full.equals(table_early)
    # Full-season mean temp includes the later, hotter days; the early
    # cutoff must not.
    assert table_full.loc[2019, "mean_t2m_c"] != table_early.loc[2019, "mean_t2m_c"]


def test_build_feature_table_exact_values_on_synthetic_data():
    """Direct check of every output column against hand-computed values,
    not just that decision_date changes them. Constant 15mm/day rain all
    year: the first 7-day window (day 7) sums to 105mm (>=20 threshold);
    the following 30 days sum to exactly 450mm (>=450 confirm threshold,
    boundary case) with zero dry days, so onset is detected at day 7 with
    no false-start rejection. No day is ever dry, so dry_spell_days=0.
    Constant 25C gives mean_t2m_c=25.0 exactly."""
    dates = pd.date_range("2020-01-01", periods=365, freq="D")
    df = pd.DataFrame({"rainfall_mm": [15.0] * 365, "temp_mean_c": [25.0] * 365},
                      index=dates)
    table = build_feature_table(df, years=[2020])

    assert list(table.index) == [2020]
    assert table.loc[2020, "onset_doy"] == 7
    assert table.loc[2020, "onset_amount_mm"] == 105.0
    assert table.loc[2020, "dry_spell_days"] == 0
    assert table.loc[2020, "mean_t2m_c"] == 25.0


def test_build_feature_table_excludes_years_with_no_onset():
    """A year with no valid monsoon onset must not appear in the table at
    all (it has no onset_doy/onset_amount_mm to build a row from), while a
    year in the same call that DOES have an onset still gets a row.
    (Two years, not one, because an all-excluded call hits a separate,
    pre-existing empty-DataFrame edge case in build_feature_table's
    set_index("year") — out of scope for this test pass.)"""
    onset_dates = pd.date_range("2020-01-01", periods=365, freq="D")
    onset_df = pd.DataFrame({"rainfall_mm": [15.0] * 365, "temp_mean_c": [25.0] * 365},
                            index=onset_dates)
    no_onset_dates = pd.date_range("2021-01-01", periods=365, freq="D")
    no_onset_df = pd.DataFrame({"rainfall_mm": [0.0] * 365, "temp_mean_c": [25.0] * 365},
                               index=no_onset_dates)
    df = pd.concat([onset_df, no_onset_df])

    table = build_feature_table(df, years=[2020, 2021])
    assert list(table.index) == [2020]


# ---------------- nearest_analog_year ----------------

def _three_year_table(onsets, amounts, spells, temps):
    return pd.DataFrame({
        "onset_doy": onsets, "onset_amount_mm": amounts,
        "dry_spell_days": spells, "mean_t2m_c": temps,
    }, index=pd.Index([2001, 2002, 2003], name="year"))


def test_analog_year_self_match_is_zero_distance():
    """A season identical to a table year must match itself at distance 0."""
    table = _three_year_table([120, 140, 160], [30.0, 50.0, 70.0],
                              [40, 50, 60], [24.5, 25.0, 25.5])
    result = nearest_analog_year(table.loc[2002].to_dict(), table)
    assert result["analog_year"] == 2002
    assert result["distance"] == 0.0


def test_analog_year_picks_closest_not_furthest():
    table = _three_year_table([100, 150, 200], [20.0, 50.0, 80.0],
                              [30, 50, 70], [24.0, 25.0, 26.0])
    season = {"onset_doy": 105, "onset_amount_mm": 22.0,
              "dry_spell_days": 32, "mean_t2m_c": 24.1}
    assert nearest_analog_year(season, table)["analog_year"] == 2001


def test_analog_year_candidate_restriction_picks_next_closest():
    """Excluding the exact match must return the next-closest allowed year."""
    table = _three_year_table([120, 140, 160], [30.0, 50.0, 70.0],
                              [40, 50, 60], [24.5, 25.0, 25.5])
    result = nearest_analog_year(table.loc[2001].to_dict(), table,
                                 candidate_years=[2002, 2003])
    assert result["analog_year"] == 2002


# ---------------- eto_penman_monteith ----------------

def test_eto_matches_fao56_example_18_with_rh_extremes():
    """FAO-56 (Allen et al., 1998), Chapter 4, Example 18, p.72: reference
    ET0 for Uccle, Belgium, 6 July (day 187), lat 50.8N, elevation 100m.
    Inputs: Tmax=21.5C, Tmin=12.3C, RHmax=84%, RHmin=63%, wind at 10m =
    10 km/h -> u2=2.078 m/s (already converted to 2m height, as our
    function requires), sunshine n=9.25h -> Rs=22.07 MJ/m2/day (FAO-56's
    own intermediate Angstrom-formula result, since eto_penman_monteith
    takes Rs directly and has no sunshine-hours-to-Rs step).
    FAO-56's published answer is ET0=3.9 mm/day.

    With rh_max_pct/rh_min_pct supplied, ea is computed per FAO-56 Eq.17
    (RHmax/RHmin separately) instead of the RH-mean approximation, closing
    the gap that the mean-RH approximation used to leave against the
    published value.
    """
    row = pd.Series({
        "temp_max_c": 21.5, "temp_min_c": 12.3, "temp_mean_c": 16.9,
        "rh_max_pct": 84, "rh_min_pct": 63, "wind_speed_ms": 2.078,
        "solar_rad_mj_m2": 22.07
    })
    result = eto_penman_monteith(row, day_of_year=187, latitude_deg=50.8,
                                 elevation_m=100)
    assert abs(result - 3.9) <= 0.1


def test_eto_falls_back_to_rh_mean_method_without_rh_extremes():
    """When only a single mean RH is available (as with NASA POWER's
    RH2M — no separate RHmax/RHmin), eto_penman_monteith falls back to
    FAO-56 Eq.19: ea = es * (RHmean / 100). Same inputs as Example 18,
    but with RH=(84+63)/2=73.5% fed as a single rh_pct.

    This approximation alone shifts ea enough to move the result to
    3.79 mm/day — a 0.11 mm/day gap from FAO-56's published 3.9, just
    outside +/-0.1 of the true answer. So this test documents and
    validates the Eq.19 path's own arithmetic (checked by hand against
    the FAO-56 worked steps for delta, gamma, Ra, Rso, Rns, Rnl, Rn —
    all matched to within rounding) against 3.79, not against the
    published 3.9.
    """
    row = pd.Series({
        "temp_max_c": 21.5, "temp_min_c": 12.3, "temp_mean_c": 16.9,
        "rh_pct": (84 + 63) / 2, "wind_speed_ms": 2.078,
        "solar_rad_mj_m2": 22.07
    })
    result = eto_penman_monteith(row, day_of_year=187, latitude_deg=50.8,
                                 elevation_m=100)
    assert abs(result - 3.79) <= 0.05


def test_eto_seasonal_pattern_is_sane():
    """ET0 should be lower in winter than in the pre-monsoon season."""
    winter_row = pd.Series({
        "temp_max_c": 24.0, "temp_min_c": 11.0, "temp_mean_c": 17.0,
        "rh_pct": 70.0, "wind_speed_ms": 1.5, "solar_rad_mj_m2": 16.0
    })
    premonsoon_row = pd.Series({
        "temp_max_c": 34.0, "temp_min_c": 24.0, "temp_mean_c": 29.0,
        "rh_pct": 65.0, "wind_speed_ms": 2.0, "solar_rad_mj_m2": 20.0
    })
    winter_eto = eto_penman_monteith(winter_row, day_of_year=15,
                                     latitude_deg=23.4607, elevation_m=28.08)
    premonsoon_eto = eto_penman_monteith(premonsoon_row, day_of_year=105,
                                         latitude_deg=23.4607, elevation_m=28.08)
    assert premonsoon_eto > winter_eto
    assert 1.5 <= winter_eto <= 4.0
    assert 3.5 <= premonsoon_eto <= 7.0


# ---------------- backtest_rotation ----------------

KC_TEST_TABLE = pd.DataFrame({
    "crop": ["rice"] * 4 + ["potato"] * 4,
    "stage": ["initial", "development", "mid", "late"] * 2,
    "length_days": [30, 30, 60, 30, 25, 30, 45, 30],
    "kc": [1.05, 1.05, 1.20, 0.60, 0.50, 0.50, 1.15, 0.75],
})


def _weather(start, end):
    """Constant weather for start..end — these tests are about soil moisture."""
    dates = pd.date_range(start, end, freq="D")
    return pd.DataFrame({
        "temp_max_c": 30.0, "temp_min_c": 20.0, "temp_mean_c": 25.0,
        "rh_pct": 70.0, "wind_speed_ms": 1.5, "solar_rad_mj_m2": 18.0
    }, index=dates)


def _flat_inputs(start, end):
    """Weather plus soil moisture for start..end, AND a 2010-2012 history
    so every time of year has other-year reference data. These tests
    check dates and counts, not which days are usable."""
    history_dates = pd.date_range("2010-01-01", "2012-12-31", freq="D")
    history = pd.Series(np.linspace(0.10, 0.40, len(history_dates)), index=history_dates)
    window_dates = pd.date_range(start, end, freq="D")
    window = pd.Series(np.linspace(0.10, 0.40, len(window_dates)), index=window_dates)
    return _weather(start, end), pd.concat([history, window])


def _run(rotation, analog_year, power_df, smap_series):
    return backtest_rotation(rotation, analog_year, power_df, smap_series,
                             KC_TEST_TABLE, latitude_deg=23.46, elevation_m=28.0)


def test_backtest_rotation_all_wet_days_are_usable():
    """Wetter than every other year at that time of year -> every day usable."""
    history_dates = pd.date_range("2010-01-01", periods=1000, freq="D")
    history = pd.Series(np.linspace(0.05, 0.19, 1000), index=history_dates)
    rotation_dates = pd.date_range("2019-01-01", periods=150, freq="D")
    smap = pd.concat([history, pd.Series([0.50] * 150, index=rotation_dates)])

    result = _run([{"crop": "rice", "start_date": "2019-01-01"}], 2019,
                  _weather("2019-01-01", "2019-05-30"), smap)
    assert result["total_days"] == 150
    assert result["usable_moisture_days"] == 150


def test_backtest_rotation_all_dry_days_are_unusable():
    """Drier than every other year at that time of year -> no day usable."""
    history_dates = pd.date_range("2010-01-01", periods=1000, freq="D")
    history = pd.Series(np.linspace(0.30, 0.44, 1000), index=history_dates)
    rotation_dates = pd.date_range("2019-01-01", periods=150, freq="D")
    smap = pd.concat([history, pd.Series([0.05] * 150, index=rotation_dates)])

    result = _run([{"crop": "rice", "start_date": "2019-01-01"}], 2019,
                  _weather("2019-01-01", "2019-05-30"), smap)
    assert result["usable_moisture_days"] == 0


def test_backtest_rotation_missing_dates_are_skipped_not_crashed():
    """Only the 10 days with data are evaluated; the other 140 are skipped."""
    power_df, smap = _flat_inputs("2019-01-01", "2019-01-10")
    result = _run([{"crop": "rice", "start_date": "2019-01-01"}], 2019, power_df, smap)
    assert result["total_days"] == 10
    assert result["planned_days"] == 150


def test_backtest_replays_analog_year_not_plan_year():
    """A plan dated 2024, replayed as 2019, must use 2019's data."""
    power_df, smap = _flat_inputs("2019-01-01", "2019-12-31")
    result = _run([{"crop": "rice", "start_date": "2024-01-01"}], 2019, power_df, smap)
    assert result["total_days"] == 150
    assert result["detail"]["date"].dt.year.unique().tolist() == [2019]


def test_backtest_keeps_cross_year_rotation_order():
    """July rice then January potato, replayed as 2016: the potato must
    start in January 2017, after the rice, not in January 2016."""
    power_df, smap = _flat_inputs("2016-06-01", "2017-12-31")
    rotation = [{"crop": "rice", "start_date": "2019-07-01"},
                {"crop": "potato", "start_date": "2020-01-15"}]
    result = _run(rotation, 2016, power_df, smap)
    detail = result["detail"]
    assert detail[detail["crop"] == "rice"]["date"].min() == pd.Timestamp("2016-07-01")
    assert detail[detail["crop"] == "potato"]["date"].min() == pd.Timestamp("2017-01-15")
    assert result["planned_days"] == 150 + 130


def test_backtest_unknown_crop_raises():
    """A misspelled crop must raise an error, not silently vanish."""
    power_df, smap = _flat_inputs("2019-01-01", "2019-12-31")
    with pytest.raises(ValueError):
        _run([{"crop": "Rice", "start_date": "2019-05-01"}], 2019, power_df, smap)


def test_backtest_judges_dry_season_against_its_own_season():
    """A January wetter than every past January must count as usable,
    even though January is the driest part of the year. Ranked against
    the whole year (the old method), it would have failed."""
    history_dates = pd.date_range("2015-01-01", "2018-12-31", freq="D")
    month = history_dates.month
    history_values = np.where(month <= 3, 0.11,          # dry season
                     np.where((month >= 6) & (month <= 9), 0.38, 0.25))
    history = pd.Series(history_values, index=history_dates)
    jan_2019 = pd.date_range("2019-01-01", "2019-01-25", freq="D")
    smap = pd.concat([history, pd.Series([0.13] * 25, index=jan_2019)])

    result = _run([{"crop": "potato", "start_date": "2019-01-01"}], 2019,
                  _weather("2019-01-01", "2019-01-25"), smap)
    assert result["total_days"] == 25
    assert result["usable_moisture_days"] == 25