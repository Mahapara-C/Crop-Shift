"""
Unit tests for src/compute/enso.py
Run from src/compute with: pytest test_enso.py -v
"""

import pandas as pd
from enso import label_enso_years


def make_oni(seasons, years, anoms):
    return pd.DataFrame({"season": seasons, "year": years, "anom": anoms})


def test_five_consecutive_warm_seasons_is_el_nino():
    """5 straight seasons >= +0.5 spanning two years should mark both years el_nino."""
    seasons = ["SON", "OND", "NDJ", "DJF", "JFM"]
    years =   [2015,  2015,  2015,  2016,  2016]
    anoms =   [0.6,   0.7,   0.9,   1.0,   0.8]
    result = label_enso_years(make_oni(seasons, years, anoms))
    assert result[2015] == "el_nino"
    assert result[2016] == "el_nino"


def test_five_consecutive_cold_seasons_is_la_nina():
    seasons = ["SON", "OND", "NDJ", "DJF", "JFM"]
    years =   [1988,  1988,  1988,  1989,  1989]
    anoms =   [-0.6,  -0.8,  -1.0,  -0.9,  -0.6]
    result = label_enso_years(make_oni(seasons, years, anoms))
    assert result[1988] == "la_nina"
    assert result[1989] == "la_nina"


def test_only_four_warm_seasons_is_not_enough():
    """CPC requires >= 5 overlapping seasons; 4 should stay neutral."""
    seasons = ["OND", "NDJ", "DJF", "JFM"]
    years =   [2004,  2004,  2005,  2005]
    anoms =   [0.6,   0.7,   0.9,   0.8]
    result = label_enso_years(make_oni(seasons, years, anoms))
    assert result[2004] == "neutral"
    assert result[2005] == "neutral"


def test_flat_neutral_series():
    seasons = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ"]
    years =   [2010] * 6
    anoms =   [0.1, -0.2, 0.0, 0.3, -0.1, 0.2]
    result = label_enso_years(make_oni(seasons, years, anoms))
    assert result[2010] == "neutral"


def test_borderline_threshold_values_count_as_events():
    """Exactly +0.5 / -0.5 should count (the rule is >=, <=), not strict inequality."""
    seasons = ["SON", "OND", "NDJ", "DJF", "JFM"]
    years =   [2000,  2000,  2000,  2001,  2001]
    anoms =   [0.5,   0.5,   0.5,   0.5,   0.5]
    result = label_enso_years(make_oni(seasons, years, anoms))
    assert result[2000] == "el_nino"
    assert result[2001] == "el_nino"


def test_warm_run_preceded_by_neutral_seasons_is_still_detected():
    """Regression: a run that starts after a neutral (non-event) season must
    still be recognized as its own 5-season run, not merged with the
    preceding non-event row."""
    seasons = ["MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON"]
    years =   [1997,  1997,  1997,  1997,  1997,  1997,  1997]
    anoms =   [0.1,   0.2,   0.6,   0.7,   0.9,   1.0,   1.1]
    result = label_enso_years(make_oni(seasons, years, anoms))
    assert result[1997] == "el_nino"


def test_short_warm_run_between_two_short_cold_runs_stays_neutral():
    """A run must itself be >= 5 seasons; runs don't accumulate across gaps."""
    seasons = ["JAS", "ASO", "SON", "OND", "NDJ", "DJF", "JFM"]
    years =   [1997,  1997,  1997,  1997,  1997,  1998,  1998]
    anoms =   [0.6,   0.7,   0.2,   -0.1,  0.6,   0.7,   0.6]
    result = label_enso_years(make_oni(seasons, years, anoms))
    assert result[1997] == "neutral"
    assert result[1998] == "neutral"


# ---------------- season_enso_labels (Oct 31 decision label) ----------------

from enso import classify_oni, season_enso_labels  # noqa: E402


def test_classify_oni_thresholds():
    assert classify_oni(1.5) == "strong_el_nino"
    assert classify_oni(1.49) == "el_nino"
    assert classify_oni(0.5) == "el_nino"
    assert classify_oni(0.49) == "neutral"
    assert classify_oni(-0.49) == "neutral"
    assert classify_oni(-0.5) == "la_nina"
    assert classify_oni(float("nan")) is None


def test_season_label_uses_only_the_aso_value():
    """Later seasons (SON, OND) are hot, but only ASO counts for Oct 31."""
    seasons = ["JAS", "ASO", "SON", "OND", "ASO"]
    years =   [2015,  2015,  2015,  2015,  2016]
    anoms =   [0.2,   0.3,   1.8,   2.2,   -0.7]
    labels = season_enso_labels(make_oni(seasons, years, anoms))
    assert labels.loc[2015, "oni"] == 0.3
    assert labels.loc[2015, "label"] == "neutral"
    assert labels.loc[2016, "label"] == "la_nina"
    assert list(labels.index) == [2015, 2016]


def test_strong_el_nino_phase_is_el_nino():
    labels = season_enso_labels(make_oni(["ASO", "ASO"], [1997, 2002], [2.1, 0.9]))
    assert labels.loc[1997, "label"] == "strong_el_nino"
    assert labels.loc[1997, "phase"] == "el_nino"
    assert labels.loc[2002, "label"] == "el_nino"
    assert labels.loc[2002, "phase"] == "el_nino"
