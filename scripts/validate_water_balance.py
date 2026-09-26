"""
scripts/validate_water_balance.py

Checks the FAO-56 root-zone water balance (src/compute/water_balance.py)
against NASA SMAP L4 root-zone soil moisture, per district, 2015-2025.

For each district a reference-grass balance (Kc = 1.0, Zr = 1.0 m to match
SMAP's 0-100 cm root zone, p = 0.50) runs from 2014-08-01 (monsoon, root
zone assumed at field capacity) on daily rain and FAO-56 ET0. Its
relative soil water, 1 - Dr/TAW, is compared with SMAP sm_rootzone as
weekly anomalies (the shared seasonal cycle removed), and Pearson r is
written to docs/results/water_balance_validation.md.

Rain comes from src/compute/weather.py load_weather(): NASA GPM IMERG by
default. The balance is also run on NASA POWER rain over the same weeks, so
the two rain sources can be compared (see docs/results/rain_source_check.md).

Run from the repo root:
    python scripts/validate_water_balance.py
"""

import os
import re
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "compute"))
from water_balance import (load_crop_params, load_soil_params, weather_table,  # noqa: E402
                           reference_grass_balance, total_available_water,
                           weekly_anomaly_correlation, SOIL_PARAMS_PATH)
from weather import load_weather, RAIN_CITATIONS  # noqa: E402

DATA = os.path.join(ROOT, "data", "processed")
OUT_PATH = os.path.join(ROOT, "docs", "results", "water_balance_validation.md")
SPINUP_START = "2014-08-01"
START, END = "2015-01-01", "2025-12-31"  # SMAP's record starts 2015-03-31
RAIN_SOURCE = "imerg"   # main rain source; "power" is run on the same weeks for comparison
DRY_MONTHS = [11, 12, 1, 2, 3, 4]
WET_MONTHS = [5, 6, 7, 8, 9, 10]


def textures():
    """USDA texture per district (and the Table 19 row used, when that
    differs), read from the soil_params.csv notes."""
    notes = pd.read_csv(SOIL_PARAMS_PATH).set_index("item")["notes"]
    out = {}
    for item, note in notes.items():
        if item.endswith(".theta_fc_m3m3"):
            texture = re.search(r"USDA ([a-z ]+), classified", note).group(1)
            used = re.search(r"Table 19 ([a-z ]+) theta_FC range", note).group(1)
            out[item.split(".")[0]] = (texture if used == texture
                                       else f"{texture} (Table 19 row: {used})")
    return out


def years_at_field_capacity(daily, end):
    """Of the SMAP-era years, how many reach field capacity (Dr = 0) at
    least once between 15 July and 15 August: a check on the spin-up
    assumption used by crop_season()."""
    hits = 0
    years = range(2015, pd.Timestamp(end).year + 1)
    for year in years:
        window = daily.loc[f"{year}-07-15":f"{year}-08-15", "depletion_mm"]
        hits += int((window == 0).any())
    return hits, len(years)


def main():
    meta = pd.read_csv(os.path.join(DATA, "district_metadata.csv"))
    soil = load_soil_params()
    grass = load_crop_params()["reference_grass"]
    texture = textures()

    # Both rain sources are scored on the same weeks: up to the last IMERG day.
    end = min(pd.Timestamp(END),
              min(load_weather(n, RAIN_SOURCE).index.max() for n in meta["district"]))
    end = end.strftime("%Y-%m-%d")

    rows = []
    for _, d in meta.iterrows():
        name = d["district"]
        smap = pd.read_csv(os.path.join(DATA, f"smap_{name}_2015_2026.csv"),
                           index_col="date", parse_dates=True)["sm_rootzone"].loc[START:end]

        def run(source):
            weather = weather_table(load_weather(name, source).loc[SPINUP_START:end],
                                    d["latitude"], d["elevation_m"])
            return reference_grass_balance(weather, soil[name], grass["zr_max_m"], grass["p"],
                                           SPINUP_START, end)

        daily = run(RAIN_SOURCE)
        model = daily["relative_soil_water"].loc[START:end]
        every = weekly_anomaly_correlation(model, smap)
        dry = weekly_anomaly_correlation(model, smap, months=DRY_MONTHS)
        wet = weekly_anomaly_correlation(model, smap, months=WET_MONTHS)
        power_model = run("power")["relative_soil_water"].loc[START:end]
        power_every = weekly_anomaly_correlation(power_model, smap)
        power_dry = weekly_anomaly_correlation(power_model, smap, months=DRY_MONTHS)
        fc_hits, fc_years = years_at_field_capacity(daily, end)
        weekly = model.resample("W").mean()
        wet_weeks = weekly[weekly.index.month.isin(WET_MONTHS)]
        near_fc = float((wet_weeks >= 0.95).mean())
        taw = total_available_water(soil[name]["theta_fc_m3m3"], soil[name]["theta_wp_m3m3"],
                                    grass["zr_max_m"])
        rows.append({"district": name, "texture": texture[name], "taw": taw,
                     "r": every["r"], "r_dry": dry["r"], "r_wet": wet["r"],
                     "r_raw": every["r_raw"], "n": every["n_weeks"],
                     "n_dry": dry["n_weeks"], "n_wet": wet["n_weeks"],
                     "fc": f"{fc_hits} of {fc_years}", "near_fc": near_fc,
                     "r_power": power_every["r"], "r_dry_power": power_dry["r"]})
        print(f"{name}: r = {every['r']:.2f} ({RAIN_SOURCE} rain), "
              f"{power_every['r']:.2f} (POWER rain) (n = {every['n_weeks']} weeks)")

    same_soil = all(soil["feni"][k] == soil["noakhali"][k]
                    for k in ("theta_fc_m3m3", "theta_wp_m3m3"))
    write_report(rows, same_soil, end)
    print(f"Wrote {os.path.relpath(OUT_PATH, ROOT)}")


def write_report(rows, same_soil, end):
    table = "\n".join(
        f"| {r['district'].capitalize()} | {r['texture']} | {r['taw']:.0f} | "
        f"**{r['r']:.2f}** | {r['r_power']:.2f} | {r['r_dry']:.2f} | {r['r_dry_power']:.2f} | "
        f"{r['r_wet']:.2f} | {r['r_raw']:.2f} | "
        f"{r['n']} ({r['n_dry']} / {r['n_wet']}) | {r['fc']} | {r['near_fc']:.0%} |"
        for r in rows)
    feni_noakhali = ("They also got the same Table 19 soil values, so apart from rain their "
                     "two model series are the same."
                     if same_soil else
                     "Their soil values and their SMAP pixels differ.")

    def mean(key):
        return sum(r[key] for r in rows) / len(rows)
    text = f"""# Water balance validation against SMAP (Task 4)

Generated by `scripts/validate_water_balance.py`. Do not edit by hand; re-run the script.

## What is compared

- **Model:** the FAO-56 Chapter 8 daily root-zone balance in
  `src/compute/water_balance.py`, run for the *reference grass* (Kc = 1.0,
  Zr = 1.0 m, p = 0.50) from {SPINUP_START} at field capacity, on daily rain and
  FAO-56 Penman-Monteith ET0 (NASA POWER temperature, humidity, wind, radiation)
  for the area around each district point. Output: relative soil water = 1 - Dr/TAW.
- **Rain:** NASA GPM IMERG V07 Final Run daily (0.1 degree cell), the default rain
  source since Task 5d (`load_weather()` in `src/compute/weather.py`). The same
  balance on NASA POWER rain is run over the same weeks for comparison ("POWER rain"
  columns). POWER rain has a step change around 2014-15; see
  `docs/results/rain_source_check.md`.
- **Observation:** NASA SMAP L4 root-zone soil moisture (`sm_rootzone`, 0-100 cm,
  m3/m3) for the same district, {START} to {end} (the SMAP record starts 2015-03-31;
  the end is the last IMERG Final Run day).
- **Statistic:** Pearson r between **weekly anomalies**: each complete week's mean
  minus the mean of that ISO week over all years. Removing the seasonal cycle
  means r measures whether wetter- and drier-than-usual weeks line up, not just
  that both series have a monsoon. The raw weekly r (cycle included) is shown
  for context only.

## Results

| District | USDA texture (SoilGrids) | TAW, 1 m (mm) | r, all weeks | r, all weeks, POWER rain | r, Nov-Apr | r, Nov-Apr, POWER rain | r, May-Oct | raw weekly r | weeks (Nov-Apr / May-Oct) | years at field capacity 15 Jul-15 Aug | May-Oct weeks within 5% of field capacity |
|---|---|---|---|---|---|---|---|---|---|---|---|
{table}

Mean over the five districts: r, all weeks {mean('r'):.2f} with IMERG rain vs
{mean('r_power'):.2f} with POWER rain; r, Nov-Apr {mean('r_dry'):.2f} vs {mean('r_dry_power'):.2f}.
Columns other than the "POWER rain" ones use IMERG rain.

**The higher r with IMERG is not independent evidence that IMERG is right.** SMAP L4's
own land model is driven by rain that, outside North America, is corrected to match
IMERG daily totals (SMAP L4 Version 7 user guide). So the model and SMAP now share a
rain input, and part of the gain in r comes from that. The case for IMERG rests on
`docs/results/rain_source_check.md` (no step change); this table only shows the
switch does not make the match with SMAP worse.

"Years at field capacity" checks the spin-up assumption in `crop_season()`, which
starts each crop's spin-up at field capacity on 1 August: it counts the SMAP-era
years in which this grass balance actually reaches field capacity around that date.
The last column is the share of May-Oct weeks whose mean relative soil water is
0.95 or more.

## How to read this honestly

- **Feni and Noakhali share one NASA POWER weather cell** (identical temperature;
  only solar radiation and the latitude term of ET0 differ slightly). With IMERG
  their rain comes from different 0.1 degree cells, but the difference is small
  (Noakhali about 1-4% wetter).
  {feni_noakhali} Do not read a Feni-Noakhali contrast
  into these numbers.
- SMAP L4 is itself a model product (satellite brightness temperature assimilated
  into a land model), not an in-situ measurement, and its 9 km pixel is not a field.
- The anomaly climatology is computed from the same 2015-2025 weeks (in-sample),
  which is standard for anomaly correlation.
- Known model simplifications that lower r: runoff is not modelled (all water above
  field capacity drains), capillary rise from shallow monsoon water tables is set
  to zero, Zr and soil properties are single values per district (FAO-56 Table 19
  midpoints for the SoilGrids texture), and rain is a cell average (IMERG 0.1 degree).
- In May-Oct the model root zone sits at or near field capacity in most weeks
  (last column of the table; this bucket model cannot store water above field capacity, while SMAP keeps
  varying), so there is little week-to-week signal to correlate. The Nov-Apr r is
  the more relevant one for dry-season (rabi) crop stress and irrigation need.
- r measures timing of wet and dry spells. It does not validate the absolute
  depletion in mm, nor any crop other than the reference grass.

## Sources

- FAO-56: Allen, Pereira, Raes, Smith (1998), *Crop evapotranspiration*, FAO
  Irrigation and Drainage Paper 56, Chapter 8, Eq. 82-88,
  https://www.fao.org/4/x0490e/x0490e0e.htm ; Table 19 (soil water),
  https://www.fao.org/4/x0490e/x0490e0c.htm
- Soil texture: ISRIC SoilGrids 2.0, https://rest.isric.org/soilgrids/v2.0/properties/query
  (values and sample points in `data/reference/soil_params.csv`)
- Crop and reference-grass parameters: `data/reference/crop_params.csv`
- Rain: {RAIN_CITATIONS["imerg"]["dataset"]}, {RAIN_CITATIONS["imerg"]["url"]}
- NASA POWER daily (AG community; temperature, humidity, wind, radiation, and the
  comparison rain), https://power.larc.nasa.gov/
- NASA SMAP L4 SPL4SMGP root-zone soil moisture, https://nsidc.org/data/spl4smgp ;
  precipitation forcing corrected to IMERG outside North America: SMAP L4 Version 7
  user guide, https://nsidc.org/sites/default/files/documents/user-guide/multi_spl4smau-v007-userguide_1_0.pdf
"""
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


if __name__ == "__main__":
    main()
