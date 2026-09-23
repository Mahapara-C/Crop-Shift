"""
Unit tests for src/compute/agroclimate.py
Run with: pytest src/compute/test_agroclimate.py
"""

import pandas as pd
from agroclimate import rain_onset


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