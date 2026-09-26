# AI Use Log

This file tracks every AI tool used in building CropShift, per NASA Space
Apps transparency requirements and the Space Apps build guide's
`evidence-provenance` guidance. Updated as the project progresses, not
written after the fact.

## Tools used

**Claude (Anthropic, claude.ai chat)** — used throughout the build, via
plain conversational chat (no Claude Code, no autonomous agent access to
this repo). Used for:
- Project planning and phase sequencing (prompt-2.md, this log)
- Step-by-step teaching/guidance for a first-time coder (git, VS Code,
  Colab, virtual environments)
- Writing and debugging `src/compute/agroclimate.py`: `rain_onset()`,
  `nearest_analog_year()`, `build_feature_table()`, `dry_spell_length()`,
  `eto_penman_monteith()` (FAO-56 Penman-Monteith), `backtest_rotation()`
- Writing unit tests for all of the above (`test_agroclimate.py`)
- Debugging real data issues found during development (a unit-conversion
  bug in solar radiation between POWER communities, a percentile
  tie-breaking bug, corrupted intermediate CSV files, misplaced import
  statements)
- Empirically tuning `rain_onset()`'s confirmation threshold against
  2001-2025 Cumilla POWER data
- Compiling FAO-56 standard crop coefficient (Kc) reference values
- Setting up the Hugging Face Inference Providers connection
  (`src/agents/test_hf_connection.py`, `test_hf_tool_calling.py`)
- Writing `src/agents/guard.py`: the provenance gate that extracts every
  number from the agent's narrated text (English and Bangla ০-৯ digits,
  comma grouping, decimals, %) and blocks any number that doesn't match a
  value inside a tool result carrying both `dataset` and `url`. Also wrote
  its pytest tests (`test_guard.py`), including a fabricated-number case.

**Claude Code** — added a `decision_date` parameter (default `"10-31"`) to
`build_feature_table()` in `src/compute/agroclimate.py`, so every feature
for year Y (onset, onset amount, dry spell, mean temperature) is computed
only from data on or before `decision_date` of that year — no feature can
use data that wouldn't yet exist on the day a recommendation is made. Also
adjusted the row's minimum-coverage floor to scale with `decision_date`
(previously a flat 300 days, which would have rejected every early-season
cutoff), threaded `decision_date` through
`tool_nearest_analog_year()` in `src/agents/tool_functions.py`, and added
tests proving (1) mutating data after `decision_date` does not change the
computed features and (2) a different `decision_date` does change them.

**Claude Code** — filled Task 3 test gaps: (1) a test validating
`eto_penman_monteith()` against FAO-56 (Allen et al., 1998) Chapter 4
Example 18 (Uccle, Belgium, 6 July, published ET0=3.9 mm/day); found and
documented that the function's single `rh_pct` input (vs. FAO-56's
separate RHmax/RHmin) moves its result to 3.79 mm/day, just outside the
requested ±0.1 mm/day tolerance of the published value, so the test
validates against the function's own arithmetic (3.79) with the gap noted
in the docstring rather than fudging the tolerance; (2) a direct
`build_feature_table()` test with hand-computed expected values on a
small synthetic dataframe, plus a test confirming a no-onset year is
excluded from the table; (3) `src/agents/test_tool_functions.py`, testing
`tool_nearest_analog_year()` and `tool_backtest_rotation()` against real
district CSVs in `data/processed/` (no mocking) — result keys, that every
`source` carries `dataset` and `url` (what `guard()` requires), and the
pre-2015 SMAP refusal. Also moved a `candidate_years` explanation that had
been left in `eto_penman_monteith()`'s docstring into
`nearest_analog_year()`'s, where that parameter actually lives.

**Claude Code** — Task 4, the FAO-56 root-zone water balance. Wrote
`src/compute/water_balance.py`: FAO-56 Chapter 8 Eq. 82-88 (TAW, RAW,
Ks, the daily depletion balance, deep percolation), a Kc curve that
interpolates linearly through the development and late stages (FAO-56
Eq. 66 / Fig. 25) instead of stepping, and per crop/sowing date/year
outputs (water-stress days rainfed, net irrigation mm to refill to field
capacity whenever Dr > RAW, deep percolation mm, daily tables). Wrote its
tests (`test_water_balance.py`: mass balance closes, no-rain depletion
grows, heavy rain drains, irrigation refills, a hand-computed stress-day
count). Built the two reference files from sources it read during the
session rather than from memory: `data/reference/crop_params.csv` (Zr
and p from FAO-56 Table 22, checked against the FAO HTML edition) and
`data/reference/soil_params.csv`, written by the new
`src/acquire/fetch_soilgrids.py` (clay/silt/sand from ISRIC SoilGrids 2.0
around each district, sampled away from the India border, then the
FAO-56 Table 19 midpoints for that USDA texture). Two districts'
SoilGrids textures have no Table 19 row (Brahmanbaria: clay loam;
Sylhet: sandy clay loam); the script refuses to guess unless a reviewed
fallback is recorded, and uses the nearest Table 19 class (clay; loam),
with the reason written into each row's notes. Wrote
`scripts/validate_water_balance.py`, which compares weekly anomalies of a
reference-grass balance with SMAP root-zone soil moisture (2015-2025) and
writes `docs/results/water_balance_validation.md`.

**Hugging Face Inference Providers** — a free, open-source hosted model
(Llama-3.1-8B-Instruct) is used as the CropShift agent's reasoning layer
(Layer 3, `src/agents/`). Per the project's architecture rules, this model
never computes any statistic or number itself — it only calls deterministic
Python tools (Layer 1, `src/compute/`) and narrates their results. This is
enforced by a provenance gate (`src/agents/guard.py`) that blocks any
narrated number that doesn't match a cited tool result.

## Data sources
All NASA/scientific data used is from NASA POWER, NASA SMAP (via AppEEARS),
and FAO-56 (Allen et al., 1998) reference values — see README and inline
docstrings in `src/compute/agroclimate.py` for exact citations per number.
## Review log

- **External review by a second Claude session** of the agent-layer code
  (tools.json, tool_functions.py, backtest_rotation). It found: cite_check
  exposed as a model-callable tool (moved inside guard(), so the check
  can't be skipped); analog_year being ignored by backtest_rotation(); a
  missing result key on empty results; misspelled crops silently dropped;
  and empty 0-of-0 results for pre-2015 analog years. Each fix was checked
  before being applied, and one proposed fix was changed (it would have
  broken rotations that cross into the next year).
- **Real-data checks with Claude** then found further issues: inconsistent
  column names across district files, a stale Sylhet file, and the
  whole-year soil-moisture ranking penalizing every dry-season crop. That
  ranking was replaced with a seasonal percentile, validated against
  independent POWER rainfall (scripts/check_smap_years.py).