"""
Unit tests for src/compute/change_point.py
Run from the repo root with: python -m pytest src -q
"""

import numpy as np
import pytest
from change_point import pettitt_test


def test_worked_example():
    # U_3 = 3 x 3 pairs, each sign(x_i - x_j) = -1, so K = 9, split after 3 values.
    # p = 2 exp(-6 * 81 / (6^3 + 6^2)) = 2 exp(-486 / 252) = 0.2908
    r = pettitt_test([1, 2, 3, 10, 11, 12])
    assert r["K"] == 9
    assert r["split"] == 3
    assert r["p"] == pytest.approx(2 * np.exp(-486 / 252), rel=1e-9)
    assert r["mean_before"] == 2 and r["mean_after"] == 11


def test_finds_a_known_break():
    rng = np.random.default_rng(1)
    x = np.concatenate([rng.normal(1000, 150, 15), rng.normal(1600, 150, 10)])
    r = pettitt_test(x)
    assert r["split"] == 15
    assert r["p"] < 0.001
    assert r["mean_after"] > r["mean_before"]


def test_no_break_in_stationary_noise():
    rng = np.random.default_rng(7)
    r = pettitt_test(rng.normal(1000, 150, 25))
    assert r["p"] > 0.05


def test_downward_break_also_found():
    x = [5.0] * 8 + [1.0] * 12
    r = pettitt_test(x)
    assert r["split"] == 8
    assert r["mean_before"] == 5 and r["mean_after"] == 1


def test_bad_input():
    with pytest.raises(ValueError):
        pettitt_test([1.0, 2.0])
    with pytest.raises(ValueError):
        pettitt_test([1.0, np.nan, 2.0, 3.0])
