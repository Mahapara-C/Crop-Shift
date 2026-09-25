"""
Runs both tools on real data for every district, with no model involved.
Confirms file loading, column names, and JSON-safe results before the
agent loop depends on them. The rotation is illustrative, not advice.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))
from tool_functions import TOOL_FUNCTIONS, DISTRICT_META

season = {"onset_doy": 122, "onset_amount_mm": 45.0,
          "dry_spell_days": 60, "mean_t2m_c": 25.3}

for district in DISTRICT_META:
    match = TOOL_FUNCTIONS["nearest_analog_year"](district, season)
    year = match["year_to_backtest"]
    backtest = TOOL_FUNCTIONS["backtest_rotation"](
        district, year,
        [{"crop": "rice", "start_date": "2000-06-15"},
         {"crop": "mustard", "start_date": "2000-11-20"}],
    )
    json.dumps(match)
    json.dumps(backtest)  # raises if anything isn't JSON-safe
    print(f"{district:13s} overall={match['best_match_overall']['analog_year']} "
          f"backtest_year={year} years={match['years_compared']} "
          f"usable={backtest['usable_moisture_days']}/{backtest['evaluated_days']} "
          f"(planned {backtest['planned_days']})")