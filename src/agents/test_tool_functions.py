"""
Unit tests for src/agents/tool_functions.py
Run from src/agents with: pytest test_tool_functions.py -v

These hit the real district CSVs in data/processed/ (no mocking) since
the whole point of this layer is being the thing that touches real data.
"""

import pytest
from tool_functions import tool_nearest_analog_year, tool_backtest_rotation, SMAP_FIRST_YEAR


CURRENT_SEASON = {"onset_doy": 150, "onset_amount_mm": 40.0,
                  "dry_spell_days": 10, "mean_t2m_c": 26.0}


# ---------------- tool_nearest_analog_year ----------------

def test_nearest_analog_year_has_expected_keys():
    result = tool_nearest_analog_year("cumilla", CURRENT_SEASON)
    for key in ("best_match_overall", "best_match_with_soil_moisture",
               "year_to_backtest", "years_compared",
               "years_compared_with_soil_moisture", "note", "source"):
        assert key in result


def test_nearest_analog_year_source_has_dataset_and_url():
    """guard() requires every tool result's source to carry both fields —
    this is what makes cited numbers checkable."""
    result = tool_nearest_analog_year("cumilla", CURRENT_SEASON)
    assert "dataset" in result["source"]
    assert "url" in result["source"]


def test_nearest_analog_year_with_soil_moisture_is_2015_or_later():
    """year_to_backtest must always be SMAP-covered, since it's the year
    tool_backtest_rotation() will be called with."""
    result = tool_nearest_analog_year("cumilla", CURRENT_SEASON)
    assert result["year_to_backtest"] >= SMAP_FIRST_YEAR
    assert result["best_match_with_soil_moisture"]["analog_year"] >= SMAP_FIRST_YEAR


def test_nearest_analog_year_overall_pool_is_larger_than_soil_moisture_pool():
    """The full POWER pool (2001+) must be strictly larger than the
    SMAP-covered subset (2015+) for real district data."""
    result = tool_nearest_analog_year("cumilla", CURRENT_SEASON)
    assert result["years_compared"] > result["years_compared_with_soil_moisture"]


# ---------------- tool_backtest_rotation ----------------

def test_backtest_rotation_has_expected_keys():
    result = tool_backtest_rotation("cumilla", 2019,
                                    [{"crop": "rice", "start_date": "2019-06-01"}])
    for key in ("analog_year", "planned_days", "evaluated_days",
               "coverage_complete", "usable_moisture_days", "by_crop", "sources"):
        assert key in result


def test_backtest_rotation_sources_all_have_dataset_and_url():
    result = tool_backtest_rotation("cumilla", 2019,
                                    [{"crop": "rice", "start_date": "2019-06-01"}])
    assert len(result["sources"]) >= 1
    for source in result["sources"]:
        assert "dataset" in source
        assert "url" in source


def test_backtest_rotation_refuses_pre_2015_year():
    """Pre-SMAP years must raise, not silently return a hollow 0-of-0
    result."""
    with pytest.raises(ValueError, match="2010"):
        tool_backtest_rotation("cumilla", 2010,
                               [{"crop": "rice", "start_date": "2010-06-01"}])


def test_backtest_rotation_refuses_year_right_before_smap_starts():
    """SMAP starts 2015-03-31, so 2014 must still be refused."""
    with pytest.raises(ValueError):
        tool_backtest_rotation("cumilla", 2014,
                               [{"crop": "rice", "start_date": "2014-06-01"}])
