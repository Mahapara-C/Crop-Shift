"""
Unit tests for src/compute/agroclimate.py
Run with: pytest src/compute/test_agroclimate.py
"""

import pandas as pd
from agroclimate import rain_onset, build_feature_table, nearest_analog_year, dry_spell_length

def make_series(values, start_date="2019-01-01"):
    """Helper: build a daily rainfall Series from a plain list of values."""
    dates = pd.date_range(start=start_date, periods=len(values), freq="D")
    return pd.Series(values, index=dates)


def test_detects_clear_monsoon_onset():
    """A single realistic wet season should be detected near its start."""
    # 100 dry days, then ~60 days of sustained heavy rain (a clean monsoon)
    values = [0.0] * 100 + [25.0] * 60 + [0.0] * 100
    series = make_series(values)
    result = rain_onset(series, 2019)
    assert result["onset_doy"] is not None
    # Onset should land within the first few days of the wet season starting
    assert 100 <= result["onset_doy"] <= 108


def test_rejects_isolated_wet_week():
    """A single wet week with no sustained rain after it should NOT count
    as onset — this is the exact false-start bug found on real 2019 data."""
    values = [0.0] * 50 + [25.0] * 7 + [0.0] * 300
    series = make_series(values)
    result = rain_onset(series, 2019)
    # No sustained monsoon ever arrives in this series — should find no onset
    assert result["onset_doy"] is None


def test_no_rain_all_year_returns_none():
    """A year with no rainfall at all should return None, not crash."""
    values = [0.0] * 365
    series = make_series(values)
    result = rain_onset(series, 2020)
    assert result["onset_doy"] is None
    assert result["onset_amount_mm"] is None


def test_handles_short_year_gracefully():
    """A partial year near the end of available data shouldn't crash even
    if there aren't enough days left to run the full confirm window."""
    values = [0.0] * 10 + [30.0] * 7
    series = make_series(values)
    result = rain_onset(series, 2025)
    # Should not raise an exception — result may or may not have an onset,
    # but must return the expected dict shape either way
    assert "onset_doy" in result



def test_dry_spell_length_finds_longest_run():
    values = [0.0, 5.0, 0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    series = make_series(values)
    # Longest run of dry days (< 1.0mm) here is 5, at the end
    assert dry_spell_length(series) == 5


def test_analog_year_self_match_is_zero_distance():
    """A season matched against a feature table containing its own exact
    values should find itself, at distance 0 — the core sanity check
    that caught the normalization working correctly during development."""
    feature_table = pd.DataFrame({
        "onset_doy": [120, 140, 160],
        "onset_amount_mm": [30.0, 50.0, 70.0],
        "dry_spell_days": [40, 50, 60],
        "mean_t2m_c": [24.5, 25.0, 25.5],
    }, index=pd.Index([2001, 2002, 2003], name="year"))

    current_season = feature_table.loc[2002].to_dict()
    result = nearest_analog_year(current_season, feature_table)

    assert result["analog_year"] == 2002
    assert result["distance"] == 0.0


def test_analog_year_picks_closest_not_furthest():
    """A season clearly closer to one year than the others should match
    that year, not an arbitrary one."""
    feature_table = pd.DataFrame({
        "onset_doy": [100, 150, 200],
        "onset_amount_mm": [20.0, 50.0, 80.0],
        "dry_spell_days": [30, 50, 70],
        "mean_t2m_c": [24.0, 25.0, 26.0],
    }, index=pd.Index([2001, 2002, 2003], name="year"))

    # Clearly closest to 2001's values
    current_season = {"onset_doy": 105, "onset_amount_mm": 22.0,
                       "dry_spell_days": 32, "mean_t2m_c": 24.1}
    result = nearest_analog_year(current_season, feature_table)

    assert result["analog_year"] == 2001