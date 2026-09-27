"""
src/compute/flood_area.py

Task 7a-2: turn OPERA DSWx-S1 water maps over a ~20 km x 20 km area into a
FLOOD-water signal (water that is not normally there).

All arrays are DSWx-S1 WTR band codes on one fixed grid per district (built by
scripts/fetch_dswx.py --area):
  0 = not water, 1 = open water, 3 = inundated vegetation   -> valid
  250 = HAND-masked (too high to ever be water), 251 = layover/shadow,
  255 = fill / outside the swath                             -> not valid

  combine_scenes()        several granules of one date -> one map
  permanent_water_mask()  dry-season reference maps -> "permanent water" pixels
  flood_stats()           one date's map + permanent mask -> flood km2 / fractions
"""

import numpy as np

VALID_CODES = (0, 1, 3)
WATER_CODES = (1, 3)
FILL = 255


def combine_scenes(arrays):
    """
    Merges several WTR arrays (same grid, same date -- e.g. neighbouring
    tiles or overlapping tiles of one pass) into one. A pixel takes a valid
    reading if any scene has one; if any valid reading is water, it is water.
    Pixels with no valid reading keep the first mask code seen (250/251),
    else 255.
    """
    if len(arrays) == 0:
        raise ValueError("combine_scenes needs at least one array")
    out = np.full(arrays[0].shape, FILL, dtype=np.uint8)
    for arr in arrays:
        out_valid = np.isin(out, VALID_CODES)
        arr_valid = np.isin(arr, VALID_CODES)
        take = (~out_valid & arr_valid) | (out_valid & np.isin(arr, WATER_CODES))
        out[take] = arr[take]
        mask_code = (out == FILL) & ~arr_valid & (arr != FILL)
        out[mask_code] = arr[mask_code]
    return out


def permanent_water_mask(reference_arrays, min_share=0.5, min_valid=3):
    """
    Pixels that are water in MORE than `min_share` of the reference
    (dry-season) scenes where that pixel was valid.

    Returns (permanent, known): both boolean arrays. known = the pixel had at
    least `min_valid` valid reference readings; pixels that are not known
    can't be classed either way, and flood_stats() leaves them out.
    """
    if len(reference_arrays) == 0:
        raise ValueError("permanent_water_mask needs at least one reference array")
    stack = np.stack(reference_arrays)
    n_valid = np.isin(stack, VALID_CODES).sum(axis=0)
    n_water = np.isin(stack, WATER_CODES).sum(axis=0)
    known = n_valid >= min_valid
    share = np.divide(n_water, n_valid, out=np.zeros(n_valid.shape, dtype=float),
                      where=n_valid > 0)
    permanent = known & (share > min_share)
    return permanent, known


def flood_stats(wtr, permanent, known, pixel_km2):
    """
    FLOOD water = water now AND not permanent water AND valid (valid now and
    known in the reference).

    Returns {"flood_km2", "flood_fraction" (of valid pixels; NaN if none are
    valid), "valid_fraction" (valid pixels / all pixels in the window)}.
    """
    valid = np.isin(wtr, VALID_CODES) & known
    flood = np.isin(wtr, WATER_CODES) & ~permanent & valid
    n_valid = int(valid.sum())
    n_flood = int(flood.sum())
    return {
        "flood_km2": n_flood * pixel_km2,
        "flood_fraction": n_flood / n_valid if n_valid else float("nan"),
        "valid_fraction": n_valid / wtr.size,
    }


def flood_mask(wtr, permanent, known):
    """Boolean map of FLOOD pixels (same rule as flood_stats), for maps."""
    valid = np.isin(wtr, VALID_CODES) & known
    return np.isin(wtr, WATER_CODES) & ~permanent & valid
