"""
Unit tests for src/compute/weather.py
Run from the repo root with: python -m pytest src -q
"""

import pandas as pd
import pytest
from weather import load_weather, RAIN_CITATIONS


def write_tiny(tmp_path, imerg_rain=(5.0, 0.0, 12.5)):
    """POWER for 1-5 Jan 2001 (rain 1..5 mm); IMERG for 2-4 Jan only."""
    power = pd.DataFrame({"date": pd.date_range("2001-01-01", periods=5).strftime("%Y-%m-%d"),
                          "rainfall_mm": [1.0, 2.0, 3.0, 4.0, 5.0],
                          "temp_mean_c": [20.0, 21.0, 22.0, 23.0, 24.0]})
    power.to_csv(tmp_path / "power_x_daily.csv", index=False)
    imerg = pd.DataFrame({"date": pd.date_range("2001-01-02", periods=len(imerg_rain)).strftime("%Y-%m-%d"),
                          "rainfall_mm": list(imerg_rain)})
    imerg.to_csv(tmp_path / "imerg_x_daily.csv", index=False)


def test_imerg_replaces_rain_and_keeps_power_temperature(tmp_path):
    write_tiny(tmp_path)
    w = load_weather("x", rain_source="imerg", data_dir=tmp_path)
    assert list(w.index.strftime("%Y-%m-%d")) == ["2001-01-02", "2001-01-03", "2001-01-04"]
    assert list(w["rainfall_mm"]) == [5.0, 0.0, 12.5]
    assert list(w["temp_mean_c"]) == [21.0, 22.0, 23.0]
    assert set(w["rain_source"]) == {"imerg"}


def test_imerg_is_the_default(tmp_path):
    write_tiny(tmp_path)
    assert set(load_weather("x", data_dir=tmp_path)["rain_source"]) == {"imerg"}


def test_power_source_is_unchanged(tmp_path):
    write_tiny(tmp_path)
    w = load_weather("x", rain_source="power", data_dir=tmp_path)
    assert len(w) == 5
    assert list(w["rainfall_mm"]) == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert set(w["rain_source"]) == {"power"}


def test_imerg_gap_is_an_error_not_filled_with_power(tmp_path):
    write_tiny(tmp_path)
    imerg = pd.read_csv(tmp_path / "imerg_x_daily.csv").drop(index=1)  # remove 3 Jan
    imerg.to_csv(tmp_path / "imerg_x_daily.csv", index=False)
    with pytest.raises(ValueError, match="missing days"):
        load_weather("x", data_dir=tmp_path)


def test_unknown_source_rejected(tmp_path):
    write_tiny(tmp_path)
    with pytest.raises(ValueError):
        load_weather("x", rain_source="gauge", data_dir=tmp_path)


def test_every_source_has_a_citation():
    for cite in RAIN_CITATIONS.values():
        assert cite["dataset"] and cite["url"].startswith("https://")
