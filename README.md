# CropShift

**NASA Space Apps Challenge 2026 — Challenge 7: "Field Shift: Adapting Farms with NASA Data"**

CropShift finds the past year whose NASA climate signature most closely
matches the current growing season, replays what actually happened to
candidate crop rotations in that real historical year, and returns a
recommendation with the data "receipt" behind it — plus a live ML
classification feature and a bilingual (Bangla/English) narrating agent.

## Status
🚧 Under active development for the 2026 hackathon (13–14 Nov).

## Architecture
- `src/compute/` — deterministic science layer (analog-year matching, backtesting, no AI)
- `src/ml/` — trained classification model
- `src/agents/` — orchestrator agent (free Hugging Face model, tool-calling)
- `web/` — static frontend, calls the backend API only
- `app.py` — Hugging Face Space entry point

## AI use
See [docs/AI_USE.md](docs/AI_USE.md) for a running log of every AI tool used.
## Known data limitations

- **NASA POWER is coarser than a district.** POWER weather data comes on
  a grid of roughly 50 km cells. Noakhali and Feni fall in the same cell:
  their rainfall, temperature, humidity and wind are identical (only solar
  radiation differs), so they always receive the same analog year. Their
  backtests still differ slightly, because SMAP soil moisture (9 km grid)
  and solar radiation differ.
- **Soil-moisture records start in 2015.** Analog-year matching searches
  2001–2025, but rotation backtests use the closest match from 2015 onward
  (NASA SMAP starts 31 March 2015). Both matches are reported.
- **"Usable soil-moisture days" is relative, not absolute.** A day counts
  as usable when root-zone soil moisture is at or above the level typical
  for that time of year in other years, scaled to the crop's water demand
  (FAO-56 crop coefficients). A full FAO-56 soil-water balance is planned.
- **The monsoon-onset threshold was tuned on Cumilla.** Per-district
  validation of onset dates is still pending.

## Data validation

SMAP seasonal soil-moisture percentiles, compared with NASA POWER
June–November rainfall for 2015–2025, correlate at 0.60 (Cumilla), 0.64
(Brahmanbaria) and 0.42 (Noakhali), with no drift across years. Reproduce
with `python scripts/check_smap_years.py`.

## Reproducing the data

NASA POWER files: `python src/acquire/fetch_power.py <district>`
(districts: cumilla, noakhali, feni, brahmanbaria, sylhet).

## License
Apache-2.0 — see [LICENSE](LICENSE).