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

## License
Apache-2.0 — see [LICENSE](LICENSE).