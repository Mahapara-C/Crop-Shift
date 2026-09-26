"""
src/compute/enso.py

Labels calendar years as el_nino / la_nina / neutral from NOAA CPC's ONI
series (data/reference/oni.csv), using the standard CPC rule: an episode
is at least 5 consecutive overlapping (3-month) seasons with the ONI
anomaly >= +0.5 (El Nino) or <= -0.5 (La Nina). Deterministic, no AI
involvement.
"""

import pandas as pd

WARM_THRESHOLD = 0.5
COLD_THRESHOLD = -0.5
MIN_SEASONS = 5


def _episode_years(years, is_event, min_seasons):
    """Given a boolean Series `is_event` (already ordered chronologically)
    and the matching `years` Series, returns the set of years touched by
    any run of >= min_seasons consecutive True seasons."""
    run_id = (is_event != is_event.shift()).cumsum()
    table = pd.DataFrame({"is_event": is_event.values, "year": years.values,
                           "run_id": run_id.values})
    result = set()
    for _, group in table[table["is_event"]].groupby("run_id"):
        if len(group) >= min_seasons:
            result.update(group["year"].tolist())
    return result


def label_enso_years(oni_df, warm_threshold=WARM_THRESHOLD, cold_threshold=COLD_THRESHOLD,
                      min_seasons=MIN_SEASONS):
    """
    Parameters
    ----------
    oni_df : pd.DataFrame
        Must have columns 'season', 'year', 'anom', in chronological order
        (as saved by scripts/fetch_oni.py — one row per overlapping season).

    Returns
    -------
    pd.Series indexed by year (int), values 'el_nino' / 'la_nina' / 'neutral'.
    A year that overlaps both an El Nino and a La Nina run (only possible
    at a transition) is assigned to whichever event covers more of that
    year's seasons; a tie is 'neutral'.
    """
    df = oni_df.reset_index(drop=True)
    warm = df["anom"] >= warm_threshold
    cold = df["anom"] <= cold_threshold

    el_nino_years = _episode_years(df["year"], warm, min_seasons)
    la_nina_years = _episode_years(df["year"], cold, min_seasons)

    labels = {}
    for yr in sorted(df["year"].unique().tolist()):
        is_el = yr in el_nino_years
        is_la = yr in la_nina_years
        if is_el and is_la:
            el_count = int(((df["year"] == yr) & warm).sum())
            la_count = int(((df["year"] == yr) & cold).sum())
            labels[yr] = "el_nino" if el_count > la_count else (
                "la_nina" if la_count > el_count else "neutral")
        elif is_el:
            labels[yr] = "el_nino"
        elif is_la:
            labels[yr] = "la_nina"
        else:
            labels[yr] = "neutral"

    return pd.Series(labels, name="enso_phase")
