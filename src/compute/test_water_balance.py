"""
Unit tests for src/compute/water_balance.py
Run from the repo root with: python -m pytest src -q
"""

import os

import numpy as np
import pandas as pd
import pytest
from water_balance import (simulate_balance, total_available_water, adjusted_p, kc_daily,
                           crop_season, crop_season_all_years, weekly_anomaly_correlation,
                           weather_table, load_crop_params, load_soil_params)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")


def run(rain, et0, taw=100.0, p=0.5, kc=None, dr0=0.0, **kwargs):
    """Helper: balance with Kc = 1 unless given. Default TAW 100 mm, p 0.5,
    so RAW = 50 mm."""
    kc = np.ones(len(rain)) if kc is None else kc
    return simulate_balance(np.asarray(rain, float), np.asarray(et0, float), kc,
                            taw, p, dr0, **kwargs)


# ---------------- building blocks ----------------

def test_taw_matches_eq82():
    assert total_available_water(0.30, 0.15, 1.0) == pytest.approx(150.0)
    assert total_available_water(0.29, 0.15, 0.5) == pytest.approx(70.0)


def test_taw_rejects_field_capacity_below_wilting_point():
    with pytest.raises(ValueError):
        total_available_water(0.15, 0.30, 1.0)


def test_p_adjustment_follows_table22_footnote_and_limits():
    assert adjusted_p(0.50, 5.0) == pytest.approx(0.50)
    assert adjusted_p(0.55, 2.0) == pytest.approx(0.67)
    assert adjusted_p(0.70, 0.0) == pytest.approx(0.80)   # capped at 0.8
    assert adjusted_p(0.20, 10.0) == pytest.approx(0.10)  # floored at 0.1


def test_kc_interpolates_linearly_not_stepwise():
    table = pd.DataFrame({"crop": ["x"] * 4,
                          "stage": ["initial", "development", "mid", "late"],
                          "length_days": [10, 20, 30, 10],
                          "kc": [0.4, 0.4, 1.2, 0.6]})
    kc = kc_daily(table, "x")
    assert len(kc) == 70
    assert np.allclose(kc[:10], 0.4)
    assert kc[19] == pytest.approx(0.8)    # day 20: halfway through development
    assert kc[29] == pytest.approx(1.2)    # last development day reaches Kc_mid
    assert (np.diff(kc[10:30]) > 0).all()  # rises every day, no steps
    assert np.allclose(kc[30:60], 1.2)
    assert kc[64] == pytest.approx(0.9)    # day 65: halfway down the late stage
    assert kc[-1] == pytest.approx(0.6)    # ends at Kc_end


def test_every_kc_table_crop_has_table22_params():
    kc_table = pd.read_csv(os.path.join(DATA_DIR, "kc_table.csv"))
    params = load_crop_params()
    for crop in kc_table["crop"].unique():
        assert crop in params, crop
        assert 0 < params[crop]["zr_min_m"] <= params[crop]["zr_max_m"]
        assert 0 < params[crop]["p"] < 1


def test_every_district_has_cited_soil_params():
    districts = pd.read_csv(os.path.join(DATA_DIR, "district_metadata.csv"))["district"]
    soil = load_soil_params()
    raw = pd.read_csv(os.path.join(DATA_DIR, "..", "reference", "soil_params.csv"))
    assert raw["source_url"].str.startswith("https://").all()
    for district in districts:
        assert soil[district]["theta_fc_m3m3"] > soil[district]["theta_wp_m3m3"], district


# ---------------- the daily balance ----------------

@pytest.mark.parametrize("irrigate", [False, True])
def test_mass_balance_closes(irrigate):
    """Eq. 85 holds every day, and over the whole run water in minus
    water out equals the change in root-zone storage."""
    rng = np.random.default_rng(0)
    n = 365
    rain = rng.gamma(0.5, 12.0, n) * (rng.random(n) < 0.3)  # mostly dry, some storms
    et0 = rng.uniform(1.5, 6.0, n)
    kc = rng.uniform(0.3, 1.2, n)
    d = simulate_balance(rain, et0, kc, 120.0, 0.5, 30.0, irrigate=irrigate)

    expected = (d["depletion_start_mm"] - d["eff_rain_mm"] - d["irrigation_mm"]
                + d["etc_adj_mm"] + d["deep_percolation_mm"])
    np.testing.assert_allclose(d["depletion_mm"], expected, atol=1e-9)

    water_in = d["eff_rain_mm"].sum() + d["irrigation_mm"].sum()
    water_out = d["etc_adj_mm"].sum() + d["deep_percolation_mm"].sum()
    assert water_in - water_out == pytest.approx(30.0 - d["depletion_mm"].iloc[-1])
    assert d["depletion_mm"].between(0, 120).all()
    # the random case really exercises drainage and drying
    assert d["deep_percolation_mm"].sum() > 0
    assert (d["irrigation_mm"].sum() > 0) if irrigate else d["water_stress"].any()


def test_no_rain_depletion_grows_but_never_passes_taw():
    d = run(np.zeros(60), np.full(60, 5.0))
    depletion = d["depletion_mm"].to_numpy()
    assert (np.diff(depletion) > 0).all()
    assert depletion[-1] < 100.0
    # Ks only cuts ET once the start-of-day depletion is past RAW (Eq. 84)
    assert (d.loc[d["depletion_start_mm"] <= 50, "ks"] == 1).all()
    assert (d.loc[d["depletion_start_mm"] > 50, "ks"] < 1).all()
    assert (d["deep_percolation_mm"] == 0).all()


def test_heavy_rain_drains_to_deep_percolation():
    d = run([100.0], [4.0], dr0=20.0)
    # Eq. 88: DP = P - ETc - Dr,i-1 = 100 - 4 - 20
    assert d["deep_percolation_mm"].iloc[0] == pytest.approx(76.0)
    assert d["depletion_mm"].iloc[0] == 0.0


def test_rain_that_only_partly_refills_does_not_drain():
    d = run([10.0], [4.0], dr0=20.0)
    assert d["depletion_mm"].iloc[0] == pytest.approx(14.0)
    assert d["deep_percolation_mm"].iloc[0] == 0.0


def test_rain_below_a_fifth_of_et0_is_ignored():
    assert run([0.5], [5.0])["eff_rain_mm"].iloc[0] == 0.0
    assert run([1.0], [5.0])["eff_rain_mm"].iloc[0] == pytest.approx(1.0)


def test_irrigation_refills_to_field_capacity_when_raw_is_passed():
    d = run(np.zeros(30), np.full(30, 5.0), irrigate=True)
    irrigation = d["irrigation_mm"].to_numpy()
    # Dr = 5, 10, ... 50 (not above RAW), then 55 on day 11 -> refill 55 mm
    assert np.flatnonzero(irrigation).tolist() == [10, 21]
    assert irrigation[10] == pytest.approx(55.0)
    assert irrigation[21] == pytest.approx(55.0)
    assert d["depletion_mm"].iloc[10] == 0.0
    assert (d["depletion_mm"] <= 50).all()
    assert not d["water_stress"].any()
    assert (d["deep_percolation_mm"] == 0).all()  # I <= Dr, so nothing drains


def test_stress_day_count_on_synthetic_case():
    """TAW 100, RAW 50, ET0 5, Kc 1, one 60 mm storm on day 13.
    Day 11: Dr 55 (stressed). Day 12: Ks 0.9 -> Dr 59.5 (stressed).
    Day 13: Ks 0.81 -> Dr 59.5 - 60 + 4.05 = 3.55. Then +5 a day:
    day 22 is 48.55 (not stressed), day 23 is 53.55 (stressed)."""
    rain = np.zeros(25)
    rain[12] = 60.0
    d = run(rain, np.full(25, 5.0))
    assert d["depletion_mm"].iloc[12] == pytest.approx(3.55)
    assert (np.flatnonzero(d["water_stress"]) + 1).tolist() == [11, 12, 23, 24, 25]


# ---------------- crop seasons ----------------

KC_TABLE = pd.DataFrame({"crop": ["x"] * 4,
                         "stage": ["initial", "development", "mid", "late"],
                         "length_days": [10, 20, 30, 10],
                         "kc": [0.4, 0.4, 1.2, 0.6]})
CROP_PARAMS = {"x": {"zr_min_m": 0.5, "zr_max_m": 1.0, "p": 0.5}}
SOIL = {"theta_fc_m3m3": 0.30, "theta_wp_m3m3": 0.15}  # TAW 150 mm/m


def synthetic_weather(rain=0.0, et0=4.0, start="2020-01-01", end="2022-12-31"):
    index = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"rainfall_mm": rain, "et0_mm": et0}, index=index)


def test_crop_season_dry_weather_needs_irrigation():
    out = crop_season("x", "2020-11-15", synthetic_weather(), KC_TABLE, CROP_PARAMS,
                      SOIL, initial_depletion_frac=0.0)
    assert out["season_days"] == 70
    assert out["harvest_date"] == "2021-01-23"
    assert out["taw_mm"] == pytest.approx(150.0)  # rainfed run uses zr_max
    assert out["water_stress_days"] == int(out["daily"]["water_stress"].sum()) > 0
    assert out["net_irrigation_mm"] == pytest.approx(
        out["daily_irrigated"]["irrigation_mm"].sum(), abs=0.05)
    assert out["net_irrigation_mm"] > 0
    assert not out["daily_irrigated"]["water_stress"].any()


def test_crop_season_wet_weather_has_no_stress_and_drains():
    out = crop_season("x", "2020-11-15", synthetic_weather(rain=20.0), KC_TABLE,
                      CROP_PARAMS, SOIL, initial_depletion_frac=0.0)
    assert out["water_stress_days"] == 0
    assert out["net_irrigation_mm"] == 0
    assert out["deep_percolation_mm"] > 0


def test_spin_up_starts_dry_season_sowing_with_some_depletion():
    out = crop_season("x", "2020-11-15", synthetic_weather(), KC_TABLE, CROP_PARAMS, SOIL)
    assert out["initial_depletion_mm"] > 0
    with pytest.raises(ValueError, match="does not cover"):
        crop_season("x", "2020-11-15", synthetic_weather(start="2020-09-01"),
                    KC_TABLE, CROP_PARAMS, SOIL)


def test_all_years_skips_years_the_weather_does_not_cover():
    table = crop_season_all_years("x", "11-15", synthetic_weather(), KC_TABLE,
                                  CROP_PARAMS, SOIL)
    # 2022's season would end in Jan 2023, after the weather stops
    assert table["year"].tolist() == [2020, 2021]
    assert "daily" not in table.columns


def test_real_cumilla_wheat_runs_every_year():
    power = pd.read_csv(os.path.join(DATA_DIR, "power_cumilla_daily.csv"),
                        index_col="date", parse_dates=True).loc["2018":"2021"]
    weather = weather_table(power, 23.4607, 28.08)
    kc_table = pd.read_csv(os.path.join(DATA_DIR, "kc_table.csv"))
    table = crop_season_all_years("wheat", "11-15", weather, kc_table,
                                  load_crop_params(), load_soil_params()["cumilla"])
    assert table["year"].tolist() == [2018, 2019, 2020]
    assert not table.isna().any().any()
    assert (table["water_stress_days"].between(0, table["season_days"])).all()
    assert (table["net_irrigation_mm"] < table["etc_mm"]).all()


# ---------------- validation helper ----------------

def weekly_signal(seed=1):
    index = pd.date_range("2016-01-04", "2019-12-29", freq="D")  # Monday to Sunday
    rng = np.random.default_rng(seed)
    signal = pd.Series(rng.normal(size=len(index)), index=index)
    season = pd.Series(np.sin(2 * np.pi * index.isocalendar().week.to_numpy() / 52),
                       index=index)
    return signal, season


def test_weekly_anomaly_correlation_removes_the_seasonal_cycle():
    signal, season = weekly_signal()
    observed = signal + season
    model = 0.5 * signal - 3 * season + 10  # opposite seasonal cycle, same anomalies
    out = weekly_anomaly_correlation(model, observed)
    assert out["r"] == pytest.approx(1.0)
    assert out["r_raw"] < 0
    assert out["n_weeks"] == 208


def test_weekly_anomaly_correlation_drops_incomplete_weeks_and_filters_months():
    signal, season = weekly_signal()
    observed = (signal + season).drop(pd.Timestamp("2017-06-14"))
    assert weekly_anomaly_correlation(signal, observed)["n_weeks"] == 207
    dry = weekly_anomaly_correlation(signal, observed, months=[11, 12, 1, 2, 3, 4])
    assert 0 < dry["n_weeks"] < 207
