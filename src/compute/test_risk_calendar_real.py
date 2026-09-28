"""
Sanity checks of src/compute/risk_calendar.py on the real 2001-2024 data
(NASA POWER temperature via load_weather). Thresholds are never tuned to
make these pass: a failure is a finding to report.
Run from the repo root with: python -m pytest src -q
"""

import pandas as pd
import pytest

from risk_calendar import (DISTRICT_METADATA_PATH, SEASONS, build_crop_specs, crop_calendar,
                           load_reference_for_calendar)
from weather import load_weather

DISTRICTS = tuple(pd.read_csv(DISTRICT_METADATA_PATH)["district"])


@pytest.fixture(scope="module")
def specs():
    return build_crop_specs(load_reference_for_calendar())


@pytest.fixture(scope="module")
def weather():
    return {d: load_weather(d) for d in DISTRICTS}


def _problem_years(district, spec, weather, sow_dates):
    """Years with any problem per sowing date, from a temperature-only run
    (no water balance), so waterlogging is not included."""
    rows = crop_calendar(district, spec, weather[district], SEASONS, sow_dates=sow_dates,
                         sensitivity=False)
    return {r["sowing_mmdd"]: r["problem_years"] for r in rows}, rows


def test_every_live_threshold_is_cited_with_http(specs):
    for spec in specs.values():
        for hazard in spec["hazards"]:
            assert hazard["threshold"]["citations"]
            assert all(c["source_url"].startswith("http") for c in hazard["threshold"]["citations"])


@pytest.mark.parametrize("district", DISTRICTS)
def test_late_wheat_has_at_least_as_many_heat_problem_years_as_mid_november(district, specs,
                                                                         weather):
    spec = specs["wheat"]
    if not spec["hazards"]:
        pytest.skip("no sourced wheat heat hazard")
    assert all(h["hazard"].startswith("heat") for h in spec["hazards"])
    years, rows = _problem_years(district, spec, weather, [(11, 15), (12, 15), (12, 22), (12, 29)])
    assert all(r["n_years"] == len(SEASONS) for r in rows)
    for late in ("12-15", "12-22", "12-29"):
        assert years[late] >= years["11-15"], (district, late, years)


@pytest.mark.parametrize("district", DISTRICTS)
def test_early_december_boro_has_at_least_as_many_cold_problem_years_as_mid_january(
        district, specs, weather):
    spec = specs["boro_rice"]
    if not any(h["hazard"] == "cold_booting" for h in spec["hazards"]):
        reason = [m["reason"] for m in spec["missing"] if m["hazard"] == "cold_booting"]
        pytest.skip(f"cannot run: boro cold_booting is not evaluable - {reason}")
    rows = crop_calendar(district, spec, weather[district], SEASONS,
                         sow_dates=[(12, 5), (1, 15)], sensitivity=False)
    years = {r["sowing_mmdd"]: r["problem_years_cold_booting"] for r in rows}
    assert years["12-05"] >= years["01-15"], (district, years)
