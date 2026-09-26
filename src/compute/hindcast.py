"""
src/compute/hindcast.py

Leave-one-year-out hindcast, group comparisons (the El Nino lens), trend
statistics and onset sensitivity for CropShift (Task 5b). Deterministic,
no AI involvement.

A rabi "season Y" runs from Nov 1 of year Y to Apr 30 of Y+1, and the
decision is made on Oct 31 of Y. Every function takes plain pandas
objects so it can be tested on tiny synthetic data;
scripts/run_hindcast.py feeds it NASA POWER series and writes
docs/results/hindcast.md.

These are checks of skill vs the long-term average of the other years,
never predictions of a season.
"""

import numpy as np
import pandas as pd
from scipy import stats

from agroclimate import FEATURES, nearest_analog_year, rain_onset


# ---------------- seasonal totals ----------------

def window_stat(series, start, end, how="sum"):
    """Sum or mean of a daily series from start to end (inclusive).
    NaN unless every day in the window is present and not missing, so a
    partly covered season never passes as a real total."""
    dates = pd.date_range(start, end, freq="D")
    values = series.reindex(dates)
    if values.isna().any():
        return np.nan
    return float(values.sum() if how == "sum" else values.mean())


def seasonal_series(series, years, start_mmdd, end_mmdd, start_offset=0, end_offset=0,
                    how="sum"):
    """window_stat() for every year Y in years: the window runs from
    start_mmdd of Y+start_offset to end_mmdd of Y+end_offset. The rabi
    season is ("11-01", "04-30", 0, 1); the next monsoon of season Y is
    ("06-01", "09-30", 1, 1). Returns a Series indexed by Y."""
    out = {}
    for year in years:
        start = pd.Timestamp(f"{year + start_offset}-{start_mmdd}")
        end = pd.Timestamp(f"{year + end_offset}-{end_mmdd}")
        out[year] = window_stat(series, start, end, how)
    return pd.Series(out, dtype=float)


# ---------------- leave-one-year-out hindcast ----------------

def rank_analogs(current_season, feature_table, candidate_years, k, features=FEATURES):
    """The k candidate years closest to current_season, nearest first.
    Calls nearest_analog_year() k times, removing each winner from the
    candidates, so scaling and distance are exactly that function's."""
    remaining = list(candidate_years)
    ranked = []
    while remaining and len(ranked) < k:
        best = nearest_analog_year(current_season, feature_table, features,
                                   candidate_years=remaining)["analog_year"]
        ranked.append(best)
        remaining.remove(best)
    return ranked


def loo_hindcast(outcome, features=None, phases=None, k=5, feature_cols=FEATURES):
    """
    Leave-one-year-out comparison of four ways to estimate a season's
    outcome from the OTHER seasons only.

    outcome : pd.Series indexed by season year (NaN = no value; skipped).
    features : DataFrame indexed by year (build_feature_table() output,
        i.e. data known on the decision date), or None.
    phases : Series indexed by year of ENSO phase labels, or None.
    k : number of analogs averaged by the second analog method.

    For each held-out year Y with a value:
      climatology : mean of all other years.
      analog_1    : the single nearest analog's value (nearest_analog_year;
                    feature scaling uses every other year with features).
      analog_{k}  : mean of the k nearest analogs' values (fewer if fewer
                    candidates exist).
      enso_phase  : mean of the other years in Y's ENSO phase; falls back
                    to climatology (enso_fallback = True) when no other
                    year shares the phase.
    Analog columns are NaN when Y has no feature row (e.g. no monsoon
    onset found that year). Y itself is never a candidate or in any mean.

    Returns a DataFrame indexed by held-out year.
    """
    outcome = outcome.dropna()
    rows = []
    for year, observed in outcome.items():
        others = outcome.drop(index=year)
        clim = float(others.mean()) if len(others) else np.nan
        row = {"year": year, "observed": float(observed), "climatology": clim,
               "analog_1": np.nan, f"analog_{k}": np.nan, "analog_year": np.nan,
               "enso_phase": np.nan, "enso_fallback": False}

        if features is not None and year in features.index:
            table = features.drop(index=year)
            candidates = [y for y in table.index if y in others.index]
            if candidates:
                current = features.loc[year, feature_cols].to_dict()
                ranked = rank_analogs(current, table, candidates, k, feature_cols)
                row["analog_year"] = ranked[0]
                row["analog_1"] = float(others[ranked[0]])
                row[f"analog_{k}"] = float(others[ranked].mean())

        if phases is not None:
            phase = phases.get(year)
            same = others[phases.reindex(others.index) == phase]
            if len(same):
                row["enso_phase"] = float(same.mean())
            else:
                row["enso_phase"] = clim
                row["enso_fallback"] = True
        rows.append(row)
    return pd.DataFrame(rows).set_index("year")


def sign_test_p(wins, losses):
    """Two-sided sign test: probability of a win/loss split at least this
    uneven if each method were equally likely to be closer. Ties are left
    out before calling. NaN when there is nothing to test."""
    n = wins + losses
    if n == 0:
        return np.nan
    return float(stats.binomtest(wins, n, 0.5, alternative="two-sided").pvalue)


def skill_table(table, methods, reference="climatology"):
    """
    Skill of each method vs the reference, on the seasons where the
    observed value, the reference and EVERY method exist (so all methods
    are scored on the same seasons).

    skill = 1 - MAE_method / MAE_reference (1 = perfect, 0 = no better than
    the reference, < 0 = worse; NaN if the reference is already exact).
    wins / losses / ties: seasons where the method's absolute error is
    smaller / larger / equal. sign_p: two-sided sign test on wins vs losses.
    """
    cols = ["observed", reference, *methods]
    common = table[cols].dropna()
    ref_err = (common[reference] - common["observed"]).abs()
    mae_ref = float(ref_err.mean()) if len(common) else np.nan
    rows = []
    for method in methods:
        err = (common[method] - common["observed"]).abs()
        mae = float(err.mean()) if len(common) else np.nan
        skill = 1.0 - mae / mae_ref if mae_ref > 0 else np.nan
        wins = int((err < ref_err).sum())
        losses = int((err > ref_err).sum())
        rows.append({"method": method, "n": len(common), "mae_reference": mae_ref,
                     "mae": mae, "skill": skill, "wins": wins, "losses": losses,
                     "ties": len(common) - wins - losses,
                     "sign_p": sign_test_p(wins, losses)})
    return pd.DataFrame(rows).set_index("method")


# ---------------- group comparison (El Nino lens) ----------------

def compare_groups(group, rest):
    """Medians of two samples, their difference (group - rest) and the
    two-sided Mann-Whitney U p-value. Missing values are dropped."""
    a = pd.Series(group, dtype=float).dropna()
    b = pd.Series(rest, dtype=float).dropna()
    p = (float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
         if len(a) and len(b) else np.nan)
    median_a = float(a.median()) if len(a) else np.nan
    median_b = float(b.median()) if len(b) else np.nan
    return {"n_group": len(a), "n_rest": len(b), "median_group": median_a,
            "median_rest": median_b, "difference": median_a - median_b, "p": p}


# ---------------- trends ----------------

def trend(series):
    """
    Mann-Kendall trend test (Kendall's tau of the values against the year,
    scipy.stats.kendalltau) and Theil-Sen slope (scipy.stats.theilslopes),
    for a Series indexed by year. Serial autocorrelation is NOT corrected,
    so p-values may be too small when neighbouring years are alike.

    Returns n, tau, p, slope_per_decade and its 95% interval (lo, hi).
    A series with no variation has tau 0 and p 1 (Mann-Kendall S = 0).
    """
    s = series.dropna()
    years = np.asarray(s.index, dtype=float)
    values = s.to_numpy(dtype=float)
    if len(s) < 3:
        raise ValueError(f"Need at least 3 years for a trend, got {len(s)}")
    if np.ptp(values) == 0:
        tau, p = 0.0, 1.0
    else:
        result = stats.kendalltau(years, values)
        tau, p = float(result.statistic), float(result.pvalue)
    slope, _, lo, hi = stats.theilslopes(values, years, alpha=0.95)
    return {"n": len(s), "tau": tau, "p": p, "slope_per_decade": 10 * float(slope),
            "slope_lo": 10 * float(lo), "slope_hi": 10 * float(hi)}


# ---------------- onset sensitivity ----------------

def unconfirmed_onset(onset_doy, year, decision_date="10-31", dry_spell_days=7):
    """True when an onset lies so close to the decision date that fewer
    than dry_spell_days days follow it. rain_onset() then skips its
    dry-spell and 30-day checks and accepts the window unconfirmed (for an
    Oct 31 cutoff: onsets on Oct 25-31). False for a missing onset."""
    if onset_doy is None or pd.isna(onset_doy):
        return False
    onset = pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=int(onset_doy) - 1)
    days_after = (pd.Timestamp(f"{year}-{decision_date}") - onset).days
    return days_after < dry_spell_days


def onset_sensitivity(rain, years, week_mm=(15.0, 20.0, 25.0),
                      confirm_mm=(350.0, 450.0, 550.0), decision_date="10-31"):
    """
    rain_onset() for every year and every pair of thresholds: the 7-day
    total that starts the monsoon (min_week_mm) and the 30-day total that
    confirms it (min_confirm_total_mm). Each year uses Jan 1 to
    decision_date only, as build_feature_table() does.

    Returns a long DataFrame: year, min_week_mm, confirm_mm, onset_doy
    (NaN when no onset is found with those thresholds) and unconfirmed
    (see unconfirmed_onset()).
    """
    rows = []
    for year in years:
        cutoff = pd.Timestamp(f"{year}-{decision_date}")
        year_rain = rain[(rain.index.year == year) & (rain.index <= cutoff)]
        if year_rain.empty:
            continue
        for w in week_mm:
            for c in confirm_mm:
                onset = rain_onset(year_rain, year, min_week_mm=w, min_confirm_total_mm=c)
                doy = onset["onset_doy"]
                rows.append({"year": year, "min_week_mm": w, "confirm_mm": c,
                             "onset_doy": np.nan if doy is None else float(doy),
                             "unconfirmed": unconfirmed_onset(doy, year, decision_date)})
    return pd.DataFrame(rows)


def onset_shift_summary(table, default=(20.0, 450.0)):
    """
    For each threshold pair in an onset_sensitivity() table (several
    districts may be stacked, with a 'district' column), how far the onset
    moves from the default pair, per year: shift = onset - default onset
    (days; + = later). Only years with an onset under both pairs are
    compared.

    Returns one row per pair: rows (district-years), found (onsets found),
    median_doy, n_compared, median_shift, mean_abs_shift, max_abs_shift.
    """
    keys = ["district", "year"] if "district" in table.columns else ["year"]
    base = table[(table["min_week_mm"] == default[0]) & (table["confirm_mm"] == default[1])]
    base = base.set_index(keys)["onset_doy"]
    rows = []
    for (w, c), group in table.groupby(["min_week_mm", "confirm_mm"], sort=True):
        g = group.set_index(keys)["onset_doy"]
        shift = (g - base.reindex(g.index)).dropna()
        rows.append({"min_week_mm": w, "confirm_mm": c, "rows": len(g),
                     "found": int(g.notna().sum()), "median_doy": float(g.median()),
                     "n_compared": len(shift),
                     "median_shift": float(shift.median()) if len(shift) else np.nan,
                     "mean_abs_shift": float(shift.abs().mean()) if len(shift) else np.nan,
                     "max_abs_shift": float(shift.abs().max()) if len(shift) else np.nan})
    return pd.DataFrame(rows)
