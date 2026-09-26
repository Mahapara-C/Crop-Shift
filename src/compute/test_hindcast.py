"""
Unit tests for src/compute/hindcast.py
Run from the repo root with: python -m pytest src -q
"""

import numpy as np
import pandas as pd
import pytest
from agroclimate import FEATURES
from hindcast import (window_stat, seasonal_series, rank_analogs, loo_hindcast,
                      sign_test_p, skill_table, compare_groups, trend,
                      onset_sensitivity, onset_shift_summary, unconfirmed_onset)


def features_from(values):
    """Feature table where every feature of a year equals that year's
    value in `values` ({year: number})."""
    return pd.DataFrame({f: values for f in FEATURES}).rename_axis("year")


# ---------------- seasonal totals ----------------

def test_rabi_window_sums_nov_to_apr():
    """1 mm every day: Nov 1 2023 - Apr 30 2024 is 182 days (2024 is a leap year)."""
    days = pd.date_range("2023-01-01", "2024-12-31")
    rain = pd.Series(1.0, index=days)
    out = seasonal_series(rain, [2023], "11-01", "04-30", 0, 1)
    assert out[2023] == pytest.approx(182.0)


def test_window_with_a_missing_day_is_nan():
    days = pd.date_range("2023-01-01", "2023-12-31")
    rain = pd.Series(1.0, index=days)
    assert np.isnan(window_stat(rain.drop(pd.Timestamp("2023-06-10")), "2023-06-01", "2023-06-30"))
    rain["2023-06-10"] = np.nan
    assert np.isnan(window_stat(rain, "2023-06-01", "2023-06-30"))


def test_window_beyond_the_data_is_nan():
    days = pd.date_range("2023-01-01", "2023-12-31")
    rain = pd.Series(1.0, index=days)
    out = seasonal_series(rain, [2023], "06-01", "09-30", 1, 1)
    assert np.isnan(out[2023])


def test_window_mean():
    days = pd.date_range("2023-03-01", "2023-05-31")
    tmax = pd.Series(np.where(days.month == 3, 30.0, 33.0), index=days)
    expected = (31 * 30.0 + 61 * 33.0) / 92
    assert window_stat(tmax, "2023-03-01", "2023-05-31", how="mean") == pytest.approx(expected)


# ---------------- analogs ----------------

def test_rank_analogs_orders_by_distance():
    table = features_from({2001: 0.0, 2002: 1.0, 2003: 3.0, 2004: 6.0})
    current = {f: 0.9 for f in FEATURES}
    assert rank_analogs(current, table, [2001, 2002, 2003, 2004], k=3) == [2002, 2001, 2003]


def test_rank_analogs_only_uses_candidates():
    table = features_from({2001: 0.0, 2002: 1.0, 2003: 3.0, 2004: 6.0})
    current = {f: 0.9 for f in FEATURES}
    assert rank_analogs(current, table, [2003, 2004], k=5) == [2003, 2004]


# ---------------- leave-one-year-out ----------------

def two_regime_data():
    """Years 2001-2004 look alike (feature 0) and all had outcome 10;
    years 2005-2008 look alike (feature 5) and all had outcome 20."""
    years = range(2001, 2009)
    feats = features_from({y: (0.0 if y <= 2004 else 5.0) for y in years})
    outcome = pd.Series({y: (10.0 if y <= 2004 else 20.0) for y in years})
    return outcome, feats


def test_perfect_analog_gives_skill_one():
    outcome, feats = two_regime_data()
    table = loo_hindcast(outcome, feats, k=3)
    skill = skill_table(table, ["analog_1", "analog_3"])
    assert skill.loc["analog_1", "skill"] == pytest.approx(1.0)
    assert skill.loc["analog_3", "skill"] == pytest.approx(1.0)
    assert skill.loc["analog_1", "wins"] == 8
    # Climatology for 2001 is the mean of the other 7 years.
    assert table.loc[2001, "climatology"] == pytest.approx((3 * 10 + 4 * 20) / 7)


def test_constant_series_makes_climatology_exact():
    years = range(2001, 2009)
    outcome = pd.Series(5.0, index=list(years))
    feats = features_from({y: float(y) for y in years})
    table = loo_hindcast(outcome, feats, k=3)
    assert (table["climatology"] == 5.0).all()
    skill = skill_table(table, ["analog_1"])
    assert skill.loc["analog_1", "mae_reference"] == 0.0
    assert np.isnan(skill.loc["analog_1", "skill"])  # nothing to beat
    assert skill.loc["analog_1", "ties"] == 8
    assert np.isnan(skill.loc["analog_1", "sign_p"])


def test_held_out_value_never_used_for_itself():
    outcome, feats = two_regime_data()
    before = loo_hindcast(outcome, feats, k=3)
    changed = outcome.copy()
    changed[2003] = 999.0
    after = loo_hindcast(changed, feats, k=3)
    cols = ["climatology", "analog_1", "analog_3", "analog_year"]
    pd.testing.assert_series_equal(before.loc[2003, cols], after.loc[2003, cols])
    assert after.loc[2003, "observed"] == 999.0


def test_k_analog_mean():
    years = [2001, 2002, 2003, 2004, 2005]
    feats = features_from({2001: 0.0, 2002: 1.0, 2003: 2.0, 2004: 3.0, 2005: 10.0})
    outcome = pd.Series({2001: 1.0, 2002: 2.0, 2003: 4.0, 2004: 8.0, 2005: 16.0})
    table = loo_hindcast(outcome, feats, k=2)
    # 2001's nearest two are 2002 (value 2) and 2003 (value 4).
    assert table.loc[2001, "analog_year"] == 2002
    assert table.loc[2001, "analog_1"] == 2.0
    assert table.loc[2001, "analog_2"] == pytest.approx(3.0)
    assert set(table.index) == set(years)


def test_year_without_features_has_no_analog():
    outcome, feats = two_regime_data()
    table = loo_hindcast(outcome, feats.drop(index=2002), k=3)
    assert np.isnan(table.loc[2002, "analog_1"])
    assert not np.isnan(table.loc[2002, "climatology"])
    # skill_table scores every method on the same seasons, so 2002 drops out.
    assert skill_table(table, ["analog_1"]).loc["analog_1", "n"] == 7


def test_enso_phase_climatology_uses_same_phase_only():
    outcome = pd.Series({2001: 1.0, 2002: 3.0, 2003: 10.0, 2004: 20.0, 2005: 7.0})
    phases = pd.Series({2001: "el_nino", 2002: "el_nino", 2003: "la_nina",
                        2004: "la_nina", 2005: "neutral"})
    table = loo_hindcast(outcome, phases=phases)
    assert table.loc[2001, "enso_phase"] == 3.0
    assert table.loc[2003, "enso_phase"] == 20.0
    # 2005 is the only neutral year: falls back to climatology, and says so.
    assert table.loc[2005, "enso_phase"] == pytest.approx(table.loc[2005, "climatology"])
    assert table.loc[2005, "enso_fallback"]
    assert not table.loc[2001, "enso_fallback"]


# ---------------- skill and sign test ----------------

def test_skill_table_counts():
    table = pd.DataFrame({"observed": [10.0, 10.0, 10.0, 10.0],
                          "climatology": [12.0, 12.0, 12.0, 12.0],
                          "m": [11.0, 11.0, 14.0, 12.0]})
    row = skill_table(table, ["m"]).loc["m"]
    assert row["mae_reference"] == pytest.approx(2.0)
    assert row["mae"] == pytest.approx(2.0)
    assert row["skill"] == pytest.approx(0.0)
    assert (row["wins"], row["losses"], row["ties"]) == (2, 1, 1)


def test_sign_test():
    assert sign_test_p(10, 0) == pytest.approx(2 * 0.5 ** 10)
    assert sign_test_p(5, 5) == pytest.approx(1.0)
    assert np.isnan(sign_test_p(0, 0))


# ---------------- group comparison ----------------

def test_compare_groups_separated():
    result = compare_groups([10, 11, 12, 13, 14, 15], [1, 2, 3, 4, 5, 6, np.nan])
    assert result["n_group"] == 6 and result["n_rest"] == 6
    assert result["median_group"] == 12.5
    assert result["median_rest"] == 3.5
    assert result["difference"] == 9.0
    assert result["p"] < 0.01


def test_compare_groups_identical_is_not_significant():
    result = compare_groups([1, 2, 3, 4], [1, 2, 3, 4])
    assert result["difference"] == 0.0
    assert result["p"] == pytest.approx(1.0)


# ---------------- trends ----------------

def test_trend_perfect_line():
    s = pd.Series(np.arange(20) * 2.0, index=range(1981, 2001))  # +2 per year
    result = trend(s)
    assert result["tau"] == pytest.approx(1.0)
    assert result["slope_per_decade"] == pytest.approx(20.0)
    assert result["p"] < 0.001
    assert result["n"] == 20


def test_trend_constant_series():
    s = pd.Series(7.0, index=range(1981, 2001))
    result = trend(s)
    assert result["slope_per_decade"] == 0.0
    assert result["tau"] == 0.0 and result["p"] == 1.0


def test_trend_needs_three_years():
    with pytest.raises(ValueError):
        trend(pd.Series([1.0, 2.0], index=[2000, 2001]))


# ---------------- onset sensitivity ----------------

def steady_monsoon(start_doy, mm_per_day, years=(2001, 2002), length_days=366):
    """No rain until start_doy, then mm_per_day every day for length_days,
    each year."""
    days = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-31")
    doy = days.dayofyear
    wet = (doy >= start_doy) & (doy < start_doy + length_days)
    return pd.Series(np.where(wet, mm_per_day, 0.0), index=days)


def test_onset_moves_with_the_7_day_threshold():
    # 20 mm/day from day 150: the 7-day total reaches 20 mm on day 150 and
    # 40 mm on day 151, and the next 30 days hold 600 mm.
    table = onset_sensitivity(steady_monsoon(150, 20.0), [2001, 2002])
    summary = onset_shift_summary(table).set_index(["min_week_mm", "confirm_mm"])
    assert summary.loc[(20.0, 450.0), "median_shift"] == 0.0
    assert summary.loc[(15.0, 450.0), "median_shift"] == 0.0
    assert summary.loc[(25.0, 450.0), "median_shift"] == 1.0
    assert summary.loc[(25.0, 450.0), "median_doy"] == 151.0
    assert summary.loc[(20.0, 450.0), "found"] == 2


def test_onset_not_found_when_confirm_total_too_high():
    # 12 mm/day gives 360 mm in 30 days: passes 350, fails 450 and 550.
    # The rain stops after 60 days so no wet week sits in the last 7 days
    # before the cutoff (rain_onset() accepts such a week unconfirmed).
    rain = steady_monsoon(150, 12.0, years=(2001,), length_days=60)
    table = onset_sensitivity(rain, [2001])
    found = table.set_index("confirm_mm")["onset_doy"]
    assert found.loc[350.0].notna().all()
    assert found.loc[450.0].isna().all() and found.loc[550.0].isna().all()
    summary = onset_shift_summary(table).set_index(["min_week_mm", "confirm_mm"])
    assert summary.loc[(20.0, 350.0), "n_compared"] == 0


def test_onset_uses_data_up_to_decision_date_only():
    rain = steady_monsoon(320, 20.0, years=(2001,))  # monsoon only after Oct 31
    table = onset_sensitivity(rain, [2001])
    assert table["onset_doy"].isna().all()
    assert not table["unconfirmed"].any()


def test_unconfirmed_onset_is_the_last_week_before_the_cutoff():
    # 2001: Oct 24 = day 297, Oct 25 = day 298, Oct 31 = day 304.
    assert not unconfirmed_onset(297, 2001)
    assert unconfirmed_onset(298, 2001)
    assert unconfirmed_onset(304, 2001)
    assert unconfirmed_onset(299, 2004)       # leap year: Oct 25 = day 299
    assert not unconfirmed_onset(298, 2004)
    assert not unconfirmed_onset(None, 2001)
    assert not unconfirmed_onset(np.nan, 2001)


def test_late_october_wet_week_is_flagged_unconfirmed():
    # A single wet week at the very end of the window: rain_onset() accepts
    # it without the 30-day check, and the table flags it.
    rain = steady_monsoon(298, 20.0, years=(2001,), length_days=7)
    table = onset_sensitivity(rain, [2001], week_mm=(20.0,), confirm_mm=(450.0,))
    assert table.loc[0, "onset_doy"] == 298.0
    assert table.loc[0, "unconfirmed"]
