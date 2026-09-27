"""
Unit tests for src/compute/flood_area.py
Run from the repo root with: python -m pytest src -q
"""

import numpy as np
import pytest
from flood_area import combine_scenes, flood_mask, flood_stats, permanent_water_mask


def _a(rows):
    return np.array(rows, dtype=np.uint8)


# ---------------- combine_scenes ----------------

def test_combine_fills_gaps_from_other_scenes():
    a = _a([[0, 255], [251, 255]])
    b = _a([[255, 1], [0, 250]])
    assert combine_scenes([a, b]).tolist() == [[0, 1], [0, 250]]


def test_combine_water_wins_over_dry_when_both_valid():
    a = _a([[0, 3]])
    b = _a([[1, 0]])
    assert combine_scenes([a, b]).tolist() == [[1, 3]]


def test_combine_single_scene_is_unchanged():
    a = _a([[0, 1, 3, 250, 251, 255]])
    assert combine_scenes([a]).tolist() == a.tolist()


def test_combine_raises_on_empty():
    with pytest.raises(ValueError):
        combine_scenes([])


# ---------------- permanent_water_mask ----------------

def test_permanent_is_water_in_most_valid_reference_scenes():
    # pixel 0: water 3/3 -> permanent; pixel 1: water 1/3 -> not;
    # pixel 2: water 2/2 valid but only 2 valid readings -> unknown
    refs = [_a([[1, 1, 1]]), _a([[1, 0, 3]]), _a([[3, 0, 255]])]
    permanent, known = permanent_water_mask(refs, min_share=0.5, min_valid=3)
    assert permanent.tolist() == [[True, False, False]]
    assert known.tolist() == [[True, True, False]]


# ---------------- flood_stats ----------------

def test_flood_excludes_permanent_invalid_and_unknown_pixels():
    wtr = _a([[1, 1, 3, 0, 255, 1]])
    permanent = np.array([[True, False, False, False, False, False]])
    known = np.array([[True, True, True, True, True, False]])
    stats = flood_stats(wtr, permanent, known, pixel_km2=0.0009)
    # valid & known: pixels 0-3 (4); flood: pixels 1, 2 (pixel 0 is permanent)
    assert stats["flood_km2"] == pytest.approx(2 * 0.0009)
    assert stats["flood_fraction"] == pytest.approx(0.5)
    assert stats["valid_fraction"] == pytest.approx(4 / 6)
    assert flood_mask(wtr, permanent, known).tolist() == [[False, True, True, False, False, False]]


def test_flood_fraction_nan_when_nothing_valid():
    wtr = _a([[255, 251]])
    stats = flood_stats(wtr, np.zeros((1, 2), bool), np.ones((1, 2), bool), 0.0009)
    assert stats["flood_km2"] == 0
    assert np.isnan(stats["flood_fraction"])
    assert stats["valid_fraction"] == 0
