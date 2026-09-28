# Contract change proposals (from task 10a, the first real API)

`docs/api_contract.md` and `web/mock/` are shared files, so task 10a did **not**
edit them. This file lists every place where the real `app.py` differs from
the contract or the mock files, so the website side can review and agree. When
agreed, both sides update the contract and the mock files in one PR and raise
`api_version`, as the contract says.

What already matches (checked by `src/api/test_app.py`): the envelope keys, the
`{value, unit, src}` measure shape, every `src` id pointing to a provenance
entry with a dataset and URL, narration passing `guard()`, the error envelope,
and `is_mock: true` on endpoints that aren't built yet.

Status: **proposed, not yet agreed.**

---

## 1. Whole envelope

| # | Change | Why |
|---|---|---|
| 1.1 | Provenance ids are **stable names** (`imerg`, `power`, `smap`, `opera`, `fao56`, `calendar`, `post_flood`, `assumptions`) and `ref_NN` for each `data/reference/` source, instead of `p1…pN`. | The same source keeps the same id on every endpoint. The website should treat ids as opaque strings. |
| 1.2 | Rain has its own entry, `imerg` (NASA GPM IMERG V07 Final Run). The `power` entry now covers temperature, humidity, wind and solar only. | CLAUDE.md: rain comes from IMERG, never POWER. The mock files cite POWER for everything. |
| 1.3 | `source_mode` is `"cache"` on every real endpoint. | They read the processed archive in `data/processed/`. Nothing is fetched live yet. |
| 1.4 | A measure's `value` may be `null`, and the website should show "not computed". | Example: boro rice has no water-stress days, because the paddy model doesn't compute them. |
| 1.5 | HTTP status: `BAD_PARAMETER` and `DISTRICT_NOT_COVERED` → 400, `NO_DATA_FOR_PERIOD` → 404, `INTERNAL` → 500. An unknown path returns the error envelope with 404 and code `BAD_PARAMETER`. Option: add a `NOT_FOUND` code. | The contract has no status codes yet. |
| 1.6 | New provenance entry `assumptions`: CropShift modelling choices that come from no source (for example 7 days of turnaround after harvest). Every number that depends on one cites it. | Honesty: a reader can see which numbers rest on an assumption. |

## 2. `GET /api/v1/advisory`

**Parameters:** `?district=&prev_harvest=YYYY-MM-DD&flood_ready=YYYY-MM-DD(optional)&lang=en|bn`

| # | Change | Why |
|---|---|---|
| 2.1 | `decision_date` → **`prev_harvest`** (required): the harvest date of the previous crop, for example aman. Earliest sowing = harvest + 7 days (CropShift assumption). | This is what `risk_calendar.rotation_options()` takes. |
| 2.2 | New optional **`flood_ready`**: the post-flood ready date (from `/post-flood`). If it is later than harvest + 7 days, it sets the earliest sowing date. | The flood → planting chain. |
| 2.3 | `irrigation=yes|no` is **not supported yet**, so there is no `NO_IRRIGATION` filter. Every option shows irrigation mm instead. | No sourced rule yet for when a crop is infeasible without irrigation. |
| 2.4 | `data.decision_date` removed. New: `prev_harvest`, `flood_ready`, and `earliest_sowing_date: {date, basis:{en,bn}, src}`. | Follows 2.1 and 2.2. |
| 2.5 | New per option: `sowing_date: {date, src}` (the calendar date actually used); `window_status: {code: open\|late\|closed, en, bn}`; `hazards_checked: [{hazard, label, years_hit, threshold}]`; `hazards_checked_text: {en, bn}` (e.g. "Checked: heat at flowering, heat during grain fill."); `hazards_missing: [{hazard, label}]`; `coverage_notice` (`{en, bn}` = "Not all risks for this crop are checked yet." or `null`); `maturity_date: {date, src}`. | Every crop always says what was checked, so a crop is never read as "safe" just because fewer risks were checked. The words "full"/"partial" are never sent. |
| 2.6 | `sowing_window` keeps `{start, end, src}`, but it is now the **cited recommended window** (from `data/reference/crop_calendar.csv`), laid out in the season of the earliest sowing date. | Real data. |
| 2.7 | `main_risks` is kept (the hazards with `years_hit` > 0). `why` is `null` for unranked crops. | Same shape as the mock. |
| 2.8 | `filtered_out` items now carry the **whole option object** plus `reason_code`: `NO_RISK_CHECKED` (no sourced hazard yet, e.g. boro rice) or `TOO_LATE` (more than 4 weeks past the window). `NO_IRRIGATION` is not used yet (see 2.3). | These crops still have useful numbers (irrigation). |
| 2.9 | Not in the response yet: `field_twin_year`, `close_match`, `self_test`. | The analog "field twin" pick and the hindcast statement aren't wired into the API yet (next task). |

## 3. `GET /api/v1/risk-calendar`

| # | Change | Why |
|---|---|---|
| 3.1 | `sowing_dates` are **`MM-DD`** (e.g. `"11-15"`), the same day in every season 2001-2024, plus `sowing_dates_format`. | The calendar counts over all past seasons. A YYYY date would look like a forecast for one year. |
| 3.2 | `best_window` → **`recommended_window: {start, end, format:"MM-DD", method, src}`**, which is the cited window. No "best window" is computed. | The contract doesn't define "best". The website can highlight the lowest `any_problem_years` itself only if we agree a rule (it must not compute). |
| 3.3 | New: `crop_name`, `hazards_checked_text`, `hazards_missing`, `coverage_notice`, `grid.n_years`, `grid.outside_window` (one bool per date). | Coverage honesty, and marking dates outside the window. |
| 3.4 | New block `water: {src, units, irrigation_mm_mean[], irrigation_mm_worst20[], stress_days_mean[], stress_days_worst20[]}`. | The Kc-weighted water comparison per sowing date. |
| 3.5 | New block `sensitivity: {src, unit, rows:[{id, label, any_problem_years[]}]}` for 1 or 5 hot days (main is 3), the severe end of the threshold, and a 15-day flowering window (main is 7). | Shows how much the counts depend on CropShift assumptions. |
| 3.6 | `hazards[].threshold.unit` says the direction, e.g. `"°C daily maximum, problem above"`. | Clearer than "≥3 days" in the unit. The day count is an assumption (see sensitivity). |

## 4. `GET /api/v1/post-flood`

**Parameters:** `?district=&flood_date=YYYY-MM-DD&lang=`. The `sand` parameter is **dropped** (there is no data for it), and `data.sand_answer` and `data.event` are removed.

| # | Change | Why |
|---|---|---|
| 4.1 | `water_on_ground` is reshaped around the 20 km DSWx-S1 area method from `docs/results/post_flood.md`: `available`, `conclusive`, `reason` (when not available or not conclusive), `peak_date`, `peak_flood_share` (%), `peak_flood_area` (km²), `dry_season_floor` (%), `water_gone_date`, `days_peak_to_gone`, `scenes_used`, `rule`, `resolution_note`, and **`curve: {src, units, rows:[{date, flood_km2, flood_pct, observed_pct, used}]}`**. It replaces `first_seen`, `last_seen_flooded` and `days_observed`. | The flood-area curve for a chart. Noakhali's peak comes months after the flood, so it is marked not conclusive and only SMAP is used. |
| 4.2 | `soil_back_to_normal.days_after_peak` → **`days_after_flood`** (counted from `flood_date`). New `sensitivity: [{pct: 70\|80\|90, date, days_after_flood}]`. `from_test_26_sep` removed. | This is what `smap_days_to_normal()` returns. |
| 4.3 | `earliest_sowing_date: {date, basis, src}` (a `basis` was added). It is `null` if soil or water never recovered in the data. | |
| 4.4 | `still_possible` / `no_longer_possible` items are the **same option objects as `/advisory`**, computed at the ready date. `window_open_until` is replaced by `sowing_window.end`. | One component on the website can render both. |
| 4.5 | New **`cascade: {src, compares:{en,bn}, rows:[{crop, crop_name, if_ready_at_once:{sowing_date, problem_years}, after_flood:{sowing_date, problem_years}, change:{code: same\|fewer\|riskier\|lost, en, bn}, coverage_notice}]}`**. It compares "field ready 7 days after the flood" with "field ready at the post-flood date". | The flood → late sowing → risk chain. |

## 5. `GET /api/v1/field-twin`

| # | Change | Why |
|---|---|---|
| 5.1 | `weekly.rows[]` adds `days`, `tmax_mean_c`, `tmax_highest_c`, `tmin_mean_c`, `soil_water_pct` (rainfed, end of week), `irrigation_mm`, `irrigation_events`, and `smap_rootzone_m3m3` (SMAP, for comparison; `null` before 2015). | The week-by-week replay asked for in task 10a. |
| 5.2 | `totals` adds `irrigation_events`, `rain` and `crop_water_demand`. | |
| 5.3 | `smap_check.agreement_r` → `smap_check.note`. No per-season r is computed. The validation r is in `docs/results/water_balance_validation.md`. | One season is too short for an honest r. SMAP's rain forcing is corrected to IMERG, so it is not independent evidence. |
| 5.4 | New: `crop_name`, `season_end`. `year` may be the sowing year or the season year, and the API checks it against `sow_date`. | |
| 5.5 | `boro_rice` is not supported yet and returns `BAD_PARAMETER`. | Boro uses a ponded-paddy model with no daily soil-water table. |

## 6. `GET /api/v1/districts`

| # | Change | Why |
|---|---|---|
| 6.1 | New per district: `coverage: {rain, temperature, soil_moisture, flood_maps (null for Sylhet), risk_calendar_crops}`, each with `period` and `src`. | Lets the website show what data exists for each district. |

## 7. Not built yet (they serve the mock)

`/enso-lens`, `/ask` (POST) and also **`/warnings`** return the `web/mock/` file
with `is_mock: true` and a first notice that starts "Not built yet". `/warnings` wasn't in
the task list, but it is in the contract, so the website gets the mock instead of a 404.

## 8. Text for review

Every Bangla string in `app.py` (notices, labels, narration templates, error
messages) was written with AI help. **A Bangla speaker on the team should
review them** before the demo.
