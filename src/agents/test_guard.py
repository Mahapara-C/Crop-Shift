"""
Unit tests for src/agents/guard.py
Run from src/agents with: pytest test_guard.py -v
"""

import pytest
from guard import guard, find_numbers

POWER_SOURCE = {
    "dataset": "NASA POWER Daily Point API (AG community)",
    "url": "https://power.larc.nasa.gov/",
}

CITED_RESULT = {
    "best_match_overall": {"analog_year": 2019, "onset_doy": 122},
    "years_compared": 25,
    "source": POWER_SOURCE,
}

UNCITED_RESULT = {
    "fabricated_field": 999,
}


def test_real_number_passes():
    text = "The closest historical year was 2019, based on 25 years of NASA POWER data."
    result = guard(text, [CITED_RESULT])
    assert result["passed"] is True
    assert result["blocked_numbers"] == []
    assert result["checked"] == 2


def test_fabricated_number_is_blocked():
    text = "The closest historical year was 2019, with 87% confidence."
    result = guard(text, [CITED_RESULT])
    assert result["passed"] is False
    assert "87%" in result["blocked_numbers"]
    # 2019 is still cited, so it must not be blocked alongside the fabricated one.
    assert not any("2019" in blocked for blocked in result["blocked_numbers"])


def test_bangla_digits_work():
    # "২০১৯" = 2019, "২৫" = 25 -- both are in CITED_RESULT.
    text = "সবচেয়ে কাছের বছর ২০১৯, যা ২৫ বছরের তথ্যের ওপর ভিত্তি করে।"
    result = guard(text, [CITED_RESULT])
    assert result["passed"] is True
    assert result["blocked_numbers"] == []
    assert result["checked"] == 2


def test_result_without_dataset_and_url_is_blocked():
    text = "The tool found 999 matching days."
    result = guard(text, [UNCITED_RESULT])
    assert result["passed"] is False
    assert "999" in result["blocked_numbers"]


def test_source_missing_url_still_blocks():
    half_cited_result = {
        "value": 42,
        "source": {"dataset": "NASA POWER Daily Point API (AG community)"},
    }
    result = guard("The value was 42.", [half_cited_result])
    assert result["passed"] is False
    assert "42" in result["blocked_numbers"]


def test_dict_of_tool_results_is_accepted():
    text = "2019 was the closest year."
    result = guard(text, {"nearest_analog_year": CITED_RESULT})
    assert result["passed"] is True


def test_rounding_tolerance_allows_close_number():
    cited = {"value": 23.4607, "source": POWER_SOURCE}
    result = guard("Elevation is about 23.46 m.", [cited])
    assert result["passed"] is True


def test_find_numbers_handles_commas_and_decimals():
    numbers = find_numbers("Rainfall was 1,234.5mm over ৯০ days.")
    values = [n["value"] for n in numbers]
    assert 1234.5 in values
    assert 90.0 in values
