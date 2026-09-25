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

**Hugging Face Inference Providers** — a free, open-source hosted model
(Llama-3.1-8B-Instruct) is used as the CropShift agent's reasoning layer
(Layer 3, `src/agents/`). Per the project's architecture rules, this model
never computes any statistic or number itself — it only calls deterministic
Python tools (Layer 1, `src/compute/`) and narrates their results. This is
enforced by a provenance gate (`guard()`/`cite_check`, in progress) that
blocks any narrated number that didn't come from a tool result.

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