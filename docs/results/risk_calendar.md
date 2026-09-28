# Sowing-date risk calendar (task 6)

For each district, crop and weekly sowing date, the table in `data/processed/risk_calendar.csv` counts in how many of the 24 seasons 2001-2024 NASA data for the area around a field showed a problem: a **sourced** hazard threshold crossed at a sensitive crop stage. Net irrigation and water-stress days come from the FAO-56 root-zone balance (`water_balance.py`). This is a record of past seasons for comparing options, **not a forecast** of the coming season.

- Rain: NASA GPM IMERG V07 Final Run daily (GPM_3IMERGDF.07), 0.1 degree (https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDF_07/summary). Temperature, humidity, wind, solar: NASA POWER daily (https://power.larc.nasa.gov/), via `load_weather()`. ET0: FAO-56 Penman-Monteith.
- Researched values: `data/reference/` (crop_calendar.csv, crop_thresholds.csv, crop_params.csv, paddy_params.csv, soil_params.csv, crop_area_by_district.csv), read by the strict loader `src/compute/reference.py`. Files in `data/reference/` were not edited; bad rows are skipped and listed under DATA GAPS.
- A season counts in `n_years` only if the weather covers 240 days after sowing. Season Y = 1 Aug Y to 31 Jul Y+1. `worst20` = mean of the worst 20% of seasons.
- A crop with **no evaluable sourced hazard** has no problem-year share. It is listed but not ranked, because 'no hazard assessed' is not the same as 'no risk'.
- Feni and Noakhali share one NASA POWER cell, so their temperature-based results are the same; only their IMERG rain (and so the water numbers) differ.

## Which crops and hazards are live

| crop | sowing window | stage timing | cited stage days (mean climate, mid-window) | live hazards (threshold; source) | not evaluable |
|---|---|---|---|---|---|
| wheat | 11-15 to 11-30 (cited) | gdd (base 0 C) | flowering 58 d (55-60), maturity 104 d (100-108) | heat_anthesis (>31 C; Hassan); heat_grainfill (>35.4 C; Hassan) | none |
| mustard | 10-15 to 11-15 (cited) | gdd (base 12 C) | maturity 98 d (95-100) | waterlog (>=9 saturated days; Rasouli) | heat_flowering |
| lentil | 10-24 to 11-15 (cited) | gdd (base 5 C) | flowering 72 d, maturity 119 d | heat_flowering (>32 C; Sita); waterlog (>=5 saturated days; Nessa) | none |
| potato | 11-01 to 11-30 (cited, merged) | gdd (base 2 C) | tuber_start 35 d, tuber_end 55 d | night_heat_tuber (>20, severe 25 C; Muthoni & Shimelis) | none |
| boro_rice | 12-05 to 01-30 (derived) | none | none cited | none | heat_anthesis; cold_booting |

Water stress days and net irrigation (FAO-56) are computed for wheat, mustard, lentil and potato. Boro rice gets a ponded-paddy water need instead (below). Water numbers are reported alongside the risk; they do not count as 'problems', because no source gives a stress-day threshold.

## Options after an aman harvest on Nov 15

Earliest sowing = harvest + 7 days turnaround (CropShift assumption), then the first weekly calendar date on or after it. Ranked by problem-year share, then by worst-20% net irrigation. 'fits before boro' = median maturity is on or before boro's transplanting window end (Jan 30), for an aman - rabi crop - boro rotation. Area = BBS district area, information only (not a filter).

### Cumilla (earliest sowing Nov 22)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | wheat | Nov 22 | 11-15 to 11-30 | no | no | problems in 0 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 298 / 381 | 76 | Mar 07 | no | 496 |
| 2 | potato | Nov 22 | 11-01 to 11-30 | no | no | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 361 / 422 | 118 | – | – | 9900 |
| 3 | mustard | Nov 26 | 10-15 to 11-15 | yes | yes | problems in 0 of 24 years (checked: waterlogging only) | waterlog | partial — Not all risks for this crop are checked yet. | 243 / 293 | 50 | Mar 08 | no | – |
| 4 | lentil | Nov 28 | 10-24 to 11-15 | yes | yes | problems in 1 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 305 / 356 | 86 | Mar 23 | no | – |
| – | boro_rice | Dec 05 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 876 / 1010 | – | – | – | 156654 |

### Noakhali (earliest sowing Nov 22)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | wheat | Nov 22 | 11-15 to 11-30 | no | no | problems in 0 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 311 / 377 | 78 | Mar 07 | no | 56 |
| 2 | potato | Nov 22 | 11-01 to 11-30 | no | no | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 364 / 417 | 120 | – | – | 256 |
| 3 | mustard | Nov 26 | 10-15 to 11-15 | yes | yes | problems in 0 of 24 years (checked: waterlogging only) | waterlog | partial — Not all risks for this crop are checked yet. | 243 / 310 | 52 | Mar 08 | no | – |
| 4 | lentil | Nov 28 | 10-24 to 11-15 | yes | yes | problems in 1 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 306 / 355 | 86 | Mar 24 | no | – |
| – | boro_rice | Dec 05 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 909 / 1025 | – | – | – | 75631 |

### Feni (earliest sowing Nov 22)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | wheat | Nov 22 | 11-15 to 11-30 | no | no | problems in 0 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 294 / 349 | 77 | Mar 07 | no | 52 |
| 2 | potato | Nov 22 | 11-01 to 11-30 | no | no | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 351 / 410 | 119 | – | – | 348 |
| 3 | mustard | Nov 26 | 10-15 to 11-15 | yes | yes | problems in 0 of 24 years (checked: waterlogging only) | waterlog | partial — Not all risks for this crop are checked yet. | 236 / 277 | 50 | Mar 08 | no | – |
| 4 | lentil | Nov 28 | 10-24 to 11-15 | yes | yes | problems in 1 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 299 / 358 | 85 | Mar 24 | no | – |
| – | boro_rice | Dec 05 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 883 / 1011 | – | – | – | 31021 |

### Brahmanbaria (earliest sowing Nov 22)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | potato | Nov 22 | 11-01 to 11-30 | no | no | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 369 / 438 | 120 | – | – | 1029 |
| 2 | wheat | Nov 22 | 11-15 to 11-30 | no | no | problems in 1 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 312 / 396 | 77 | Mar 07 | no | 841 |
| 3 | mustard | Nov 26 | 10-15 to 11-15 | yes | yes | problems in 0 of 24 years (checked: waterlogging only) | waterlog | partial — Not all risks for this crop are checked yet. | 254 / 326 | 53 | Mar 07 | no | – |
| 4 | lentil | Nov 28 | 10-24 to 11-15 | yes | yes | problems in 1 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 316 / 378 | 86 | Mar 24 | no | – |
| – | boro_rice | Dec 05 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 1170 / 1309 | – | – | – | 111243 |

### Sylhet (earliest sowing Nov 22)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | wheat | Nov 22 | 11-15 to 11-30 | no | no | problems in 0 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 276 / 344 | 83 | Mar 07 | no | 261 |
| 2 | potato | Nov 22 | 11-01 to 11-30 | no | no | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 318 / 374 | 118 | – | – | 1240 |
| 3 | mustard | Nov 26 | 10-15 to 11-15 | yes | yes | problems in 0 of 24 years (checked: waterlogging only) | waterlog | partial — Not all risks for this crop are checked yet. | 215 / 287 | 50 | Mar 11 | no | – |
| 4 | lentil | Nov 28 | 10-24 to 11-15 | yes | yes | problems in 0 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 272 / 328 | 88 | Mar 25 | no | – |
| – | boro_rice | Dec 05 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 1014 / 1159 | – | – | – | 85478 |

## Options after an aman harvest on Dec 05

Earliest sowing = harvest + 7 days turnaround (CropShift assumption), then the first weekly calendar date on or after it. Ranked by problem-year share, then by worst-20% net irrigation. 'fits before boro' = median maturity is on or before boro's transplanting window end (Jan 30), for an aman - rabi crop - boro rotation. Area = BBS district area, information only (not a filter).

### Cumilla (earliest sowing Dec 12)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | potato | Dec 13 | 11-01 to 11-30 | yes | yes | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 404 / 465 | 117 | – | – | 9900 |
| 2 | lentil | Dec 12 | 10-24 to 11-15 | yes | yes | problems in 11 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 336 / 415 | 90 | Apr 02 | no | – |
| 3 | wheat | Dec 13 | 11-15 to 11-30 | yes | yes | problems in 13 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 355 / 436 | 88 | Mar 23 | no | 496 |
| – | mustard | – | 10-15 to 11-15 | yes | – | no date: more than 4 weeks past the window | waterlog | partial — Not all risks for this crop are checked yet. | – / – | – | – | – | – |
| – | boro_rice | Dec 12 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 863 / 988 | – | – | – | 156654 |

### Noakhali (earliest sowing Dec 12)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | potato | Dec 13 | 11-01 to 11-30 | yes | yes | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 412 / 479 | 120 | – | – | 256 |
| 2 | wheat | Dec 13 | 11-15 to 11-30 | yes | yes | problems in 5 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 367 / 444 | 92 | Mar 23 | no | 56 |
| 3 | lentil | Dec 12 | 10-24 to 11-15 | yes | yes | problems in 6 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 344 / 410 | 93 | Apr 02 | no | – |
| – | mustard | – | 10-15 to 11-15 | yes | – | no date: more than 4 weeks past the window | waterlog | partial — Not all risks for this crop are checked yet. | – / – | – | – | – | – |
| – | boro_rice | Dec 12 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 905 / 1027 | – | – | – | 75631 |

### Feni (earliest sowing Dec 12)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | potato | Dec 13 | 11-01 to 11-30 | yes | yes | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 395 / 460 | 118 | – | – | 348 |
| 2 | wheat | Dec 13 | 11-15 to 11-30 | yes | yes | problems in 5 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 350 / 429 | 90 | Mar 23 | no | 52 |
| 3 | lentil | Dec 12 | 10-24 to 11-15 | yes | yes | problems in 6 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 321 / 394 | 92 | Apr 02 | no | – |
| – | mustard | – | 10-15 to 11-15 | yes | – | no date: more than 4 weeks past the window | waterlog | partial — Not all risks for this crop are checked yet. | – / – | – | – | – | – |
| – | boro_rice | Dec 12 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 869 / 1004 | – | – | – | 31021 |

### Brahmanbaria (earliest sowing Dec 12)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | potato | Dec 13 | 11-01 to 11-30 | yes | yes | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 401 / 476 | 115 | – | – | 1029 |
| 2 | lentil | Dec 12 | 10-24 to 11-15 | yes | yes | problems in 15 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 335 / 420 | 91 | Apr 02 | no | – |
| 3 | wheat | Dec 13 | 11-15 to 11-30 | yes | yes | problems in 15 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 366 / 459 | 90 | Mar 23 | no | 841 |
| – | mustard | – | 10-15 to 11-15 | yes | – | no date: more than 4 weeks past the window | waterlog | partial — Not all risks for this crop are checked yet. | – / – | – | – | – | – |
| – | boro_rice | Dec 12 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 1159 / 1348 | – | – | – | 111243 |

### Sylhet (earliest sowing Dec 12)

| rank | crop | sow | window | window passed | outside window | problem years | hazards assessed | coverage | net irrigation mm (mean / worst20) | stress days (mean) | maturity | fits before boro | BBS area ha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | lentil | Dec 12 | 10-24 to 11-15 | yes | yes | problems in 0 of 24 years (checked: heat at flowering, waterlogging) | heat_flowering;waterlog | full | 273 / 358 | 88 | Apr 04 | no | – |
| 2 | potato | Dec 13 | 11-01 to 11-30 | yes | yes | problems in 0 of 24 years (checked: night heat only) | night_heat_tuber | full | 321 / 391 | 107 | – | – | 1240 |
| 3 | wheat | Dec 13 | 11-15 to 11-30 | yes | yes | problems in 1 of 24 years (checked: heat at flowering, heat during grain fill) | heat_anthesis;heat_grainfill | full | 309 / 394 | 88 | Mar 24 | no | 261 |
| – | mustard | – | 10-15 to 11-15 | yes | – | no date: more than 4 weeks past the window | waterlog | partial — Not all risks for this crop are checked yet. | – / – | – | – | – | – |
| – | boro_rice | Dec 12 | 12-05 to 01-30 | no | no | not assessed (no sourced hazard) | none | – | 982 / 1120 | – | – | – | 85478 |

## Sanity checks (real data, thresholds not tuned)

**Wheat sown late (Dec 15-31) should have at least as many heat problem years as wheat sown mid-November.** Cells: seasons (of 24) with any wheat heat problem; in brackets the count per hazard (heat_anthesis / heat_grainfill), and a season can have both.

| district | 11-15 | 12-15 | 12-22 | 12-29 | result |
|---|---|---|---|---|---|
| cumilla | 0 (0/0) | 13 (1/13) | 16 (7/16) | 18 (12/16) | PASS |
| noakhali | 0 (0/0) | 5 (0/5) | 12 (2/11) | 15 (8/12) | PASS |
| feni | 0 (0/0) | 5 (0/5) | 12 (2/11) | 15 (8/12) | PASS |
| brahmanbaria | 0 (0/0) | 17 (2/17) | 19 (8/19) | 21 (14/19) | PASS |
| sylhet | 0 (0/0) | 1 (0/1) | 1 (0/1) | 3 (0/3) | PASS |

**Boro transplanted in early December should have at least as many cold problem years as mid-January.**

CANNOT RUN: boro cold at booting is not evaluable. Reason: no sourced stage timing (boro_rice.stage.days_to_flowering, boro_rice.stage.days_to_panicle_initiation); 1 row(s) skipped in data/reference (placeholder x1); 1 row(s) skipped in data/reference (placeholder x1). The BRRI rows that cite boro durations (140 d for BRRI dhan28, 160 d for BRRI dhan29) and the 12-13 C booting cold threshold were skipped because their source_url is a PDF file name, not an http(s) link. Adding the public BRRI URL to those rows would unblock this check. The pytest for it is skipped, not passed.

## Sensitivity of problem years to the CropShift assumptions

At each crop's sowing date after a Nov 15 aman harvest (as in the first rotation tables). `hot N` = at least N hot/cold days in the stage make a problem year (default 3). `severe` = the severe end of a cited threshold range. `window 15` = 15-day flowering window instead of 7.

| district | crop | sow | default (hot 3) | hot 1 | hot 5 | severe | window 15 | n |
|---|---|---|---|---|---|---|---|---|
| cumilla | wheat | Nov 22 | 0 | 2 | 0 | 0 | 0 | 24 |
| cumilla | potato | Nov 22 | 0 | 0 | 0 | 0 | 0 | 24 |
| cumilla | mustard | Nov 26 | 0 | 0 | 0 | 0 | 0 | 24 |
| cumilla | lentil | Nov 28 | 1 | 3 | 0 | 1 | 3 | 24 |
| noakhali | wheat | Nov 22 | 0 | 0 | 0 | 0 | 0 | 24 |
| noakhali | potato | Nov 22 | 0 | 0 | 0 | 0 | 0 | 24 |
| noakhali | mustard | Nov 26 | 0 | 0 | 0 | 0 | 0 | 24 |
| noakhali | lentil | Nov 28 | 1 | 1 | 0 | 1 | 1 | 24 |
| feni | wheat | Nov 22 | 0 | 0 | 0 | 0 | 0 | 24 |
| feni | potato | Nov 22 | 0 | 0 | 0 | 0 | 0 | 24 |
| feni | mustard | Nov 26 | 0 | 0 | 0 | 0 | 0 | 24 |
| feni | lentil | Nov 28 | 1 | 1 | 0 | 1 | 1 | 24 |
| brahmanbaria | potato | Nov 22 | 0 | 0 | 0 | 0 | 0 | 24 |
| brahmanbaria | wheat | Nov 22 | 1 | 3 | 0 | 1 | 1 | 24 |
| brahmanbaria | mustard | Nov 26 | 0 | 0 | 0 | 0 | 0 | 24 |
| brahmanbaria | lentil | Nov 28 | 1 | 3 | 0 | 1 | 4 | 24 |
| sylhet | wheat | Nov 22 | 0 | 0 | 0 | 0 | 0 | 24 |
| sylhet | potato | Nov 22 | 0 | 0 | 0 | 0 | 0 | 24 |
| sylhet | mustard | Nov 26 | 0 | 0 | 0 | 0 | 0 | 24 |
| sylhet | lentil | Nov 28 | 0 | 0 | 0 | 0 | 0 | 24 |

## Boro rice: ponded-paddy water need

Land preparation 200 mm + daily ETc (FAO-56 rice Kc from kc_table, 150 days from transplanting) + percolation - rain, keeping a 100 mm water layer (Brouwer; percolation: clay 2 mm/d, Brouwer; loam 4.18 mm/d, Singha). Totals in mm per season (mean / worst20). No boro hazard is evaluable, so these rows carry water need only.

| district | percolation class | transplant 12-05 | transplant 12-19 | transplant 01-02 | transplant 01-16 | transplant 01-30 |
|---|---|---|---|---|---|---|
| cumilla | clay (2 mm/d) | 876 / 1010 | 871 / 1009 | 813 / 948 | 781 / 944 | 714 / 867 |
| noakhali | clay (2 mm/d) | 909 / 1025 | 894 / 1028 | 864 / 988 | 817 / 951 | 750 / 869 |
| feni | clay (2 mm/d) | 883 / 1011 | 841 / 967 | 834 / 988 | 768 / 889 | 708 / 845 |
| brahmanbaria | loam (4.18 mm/d) | 1170 / 1309 | 1135 / 1270 | 1066 / 1227 | 993 / 1151 | 898 / 1083 |
| sylhet | loam (4.18 mm/d) | 1014 / 1159 | 952 / 1101 | 874 / 1022 | 779 / 937 | 687 / 852 |

## CropShift assumptions (not from a source)

| name | value | sensitivity run | what it means |
|---|---|---|---|
| flowering_window_days | 7 | 15 | Heat at flowering/anthesis is counted over a window of this many days centred on the flowering date. |
| hot_days | 3 | 1, 5 | A season is a 'problem year' for a heat/cold hazard when at least this many days in the sensitive stage cross the cited threshold. |
| threshold_end | onset | severe | When a threshold is cited as a range (e.g. mustard 25-29 C, potato night 20-25 C) the onset end is used; the severe end is a sensitivity run. |
| waterlog_window_days | 30 | – | Waterlogging is checked in the first this-many days after sowing (from the task spec, not a source). |
| saturated_day | Dr = 0 and deep percolation > 0 | – | A 'saturated' day in the FAO-56 balance: the root zone is at field capacity and surplus water is draining that day (the balance has no runoff term, so this includes water that would pond or run off). |
| turnaround_days | 7 | – | Days between harvesting the previous crop and sowing the next one. |
| combine_sources | mean of per-source midpoints | – | When several kept rows cite a stage duration or threshold, each source's midpoint is taken and the mean of those is used; the full range is shown. |
| gdd_no_upper_cap | none | – | GDD uses no upper temperature cap (none is cited). |
| potato_main_season_window | 11-01 to 11-30 | – | Potato has three cited BARC windows. The North (Nov 1-7) and South (Nov 17-30) main-season windows are merged; the early-variety window (Sep 24-Oct 7) is excluded because its notes say it is a separate sub-type. |
| boro_transplant_window_start | earliest seedbed_start + shortest seedling_age | – | No kept row gives a boro transplanting window start, so it is derived from two cited values: the earliest seedbed sowing date plus the shortest seedling age. Boro 'sowing date' in this calendar means TRANSPLANTING date. |
| night_temperature | POWER T2M_MIN | – | The daily minimum 2 m temperature stands in for night temperature. |
| water_season_length | kc_table stage lengths | – | The water balance runs over the FAO-56 stage lengths in kc_table.csv (e.g. wheat 120 d), which differ from the cited maturity days. |
| paddy_refill | refill to ponding depth when the water layer is used up | – | Boro paddy: after land preparation the field holds the cited ponding depth; each day rain adds and ETc + percolation remove water; water above the ponding depth spills; when the layer would go below zero it is refilled to the ponding depth (counted as irrigation). Season = kc_table rice stage lengths (150 d), from transplanting. |
| paddy_percolation_class | clay if clay_pct >= 40 | – | Percolation uses the cited clay rate when SoilGrids clay >= 40% (USDA clay class lower bound), otherwise the cited loam rate. |

## District crop area (information only)

| district | boro_rice ha | aman_rice ha | wheat ha | potato ha |
|---|---|---|---|---|
| cumilla | 156654 | 129112 | 496 | 9900 |
| noakhali | 75631 | 160919 | 56 | 256 |
| feni | 31021 | 66450 | 52 | 348 |
| brahmanbaria | 111243 | 72612 | 841 | 1029 |
| sylhet | 85478 | 144825 | 261 | 1240 |

Source: BBS crop estimates (rows in `crop_area_by_district.csv`). No BBS area rows exist for mustard or lentil. Area never filters or ranks crops.

**Zoning rows are not used as a filter.** The 30 CZIS suitability rows were skipped by the loader (their source_url `czis.cropzoning.gov.bd` has no http(s) scheme), and they also conflict with BBS: CZIS says 'Not Suitable' where BBS reports substantial planted area:

| district | crop | CZIS class | BBS area ha |
|---|---|---|---|
| cumilla | aman_rice | Not Suitable | 129112 |
| brahmanbaria | potato | Not Suitable | 1029 |
| brahmanbaria | aman_rice | Not Suitable | 72612 |
| sylhet | wheat | Not Suitable | 261 |
| sylhet | potato | Not Suitable | 1240 |
| sylhet | aman_rice | Not Suitable | 144825 |

## DATA GAPS

Skipped reference rows by reason: source_url 48, placeholder 15, item 1, value 1 (total 65).

### Crops and hazards with no evaluable sourced threshold or stage

| crop | hazard / item | reason |
|---|---|---|
| mustard | heat_flowering | no sourced stage timing (mustard.stage.days_to_flowering); 2 row(s) skipped in data/reference (source_url x1, placeholder x1) |
| boro_rice | heat_anthesis | no sourced stage timing (boro_rice.stage.days_to_flowering); 1 row(s) skipped in data/reference (placeholder x1) |
| boro_rice | cold_booting | no sourced stage timing (boro_rice.stage.days_to_flowering, boro_rice.stage.days_to_panicle_initiation); 1 row(s) skipped in data/reference (placeholder x1); 1 row(s) skipped in data/reference (placeholder x1) |
| potato | (maturity date) | no kept potato.stage.days_to_maturity row; 1 row(s) skipped in data/reference (placeholder x1); the 'fits before next crop' check shows – |
| boro_rice | (maturity date) | no kept boro_rice.stage.days_to_maturity row; 2 row(s) skipped in data/reference (source_url x2); the 'fits before next crop' check shows – |

### Every skipped reference row

| file | line | item | reason | detail |
|---|---|---|---|---|
| crop_calendar.csv | 2 | mustard.stage.days_to_flowering_low | source_url | source_url is not http(s): '' |
| crop_calendar.csv | 3 | 2024-2025 | item | item name is malformed: '2024-2025' |
| crop_calendar.csv | 48 | boro_rice.stage.seedling_age | source_url | source_url is not http(s): 'adhunikDhanerChash.pdf (BRRI official handbook, provided dir' |
| crop_calendar.csv | 49 | aman_rice.stage.days_to_maturity | source_url | source_url is not http(s): 'adhunikDhanerChash.pdf (BRRI official handbook, provided dir' |
| crop_calendar.csv | 50 | boro_rice.flash_flood.season_start | source_url | source_url is not http(s): 'adhunikDhanerChash.pdf (BRRI official handbook, provided dir' |
| crop_calendar.csv | 51 | boro_rice.sow.seedbed_start | source_url | source_url is not http(s): 'adhunikDhanerChash.pdf (BRRI official handbook, provided dir' |
| crop_calendar.csv | 52 | boro_rice.stage.days_to_maturity | source_url | source_url is not http(s): 'brridhan28.pdf / brridhan29.pdf (BRRI official fact sheets, ' |
| crop_calendar.csv | 53 | boro_rice.stage.days_to_maturity | source_url | source_url is not http(s): 'brridhan28.pdf / brridhan29.pdf (BRRI official fact sheets, ' |
| crop_calendar.csv | 54 | boro_rice.stage.seedling_age | source_url | source_url is not http(s): 'brridhan28.pdf / brridhan29.pdf (BRRI official fact sheets, ' |
| crop_calendar.csv | 55 | boro_rice.sow.seedbed_start | source_url | source_url is not http(s): 'brridhan28.pdf / brridhan29.pdf (BRRI official fact sheets, ' |
| crop_calendar.csv | 56 | boro_rice.sow.seedbed_end | source_url | source_url is not http(s): 'brridhan28.pdf / brridhan29.pdf (BRRI official fact sheets, ' |
| crop_calendar.csv | 57 | boro_rice.sow.seedbed_start | source_url | source_url is not http(s): 'brridhan28.pdf / brridhan29.pdf (BRRI official fact sheets, ' |
| crop_calendar.csv | 58 | boro_rice.sow.seedbed_end | source_url | source_url is not http(s): 'brridhan28.pdf / brridhan29.pdf (BRRI official fact sheets, ' |
| crop_calendar.csv | 59 | boro_rice.sow.optimum | source_url | source_url is not http(s): 'brridhan28.pdf / brridhan29.pdf (BRRI official fact sheets, ' |
| crop_calendar.csv | 65 | mustard.sow.optimum | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 66 | mustard.stage.days_to_flowering | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 67 | wheat.sow.optimum | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 68 | wheat.stage.days_to_grain_fill_end | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 69 | potato.stage.days_to_flowering | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 70 | potato.stage.days_to_maturity | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 71 | boro_rice.sow.window_start | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 72 | boro_rice.stage.days_to_flowering | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 73 | boro_rice.stage.days_to_panicle_initiation | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 74 | aman_rice.sow.optimum | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 75 | aman_rice.sow.late_limit | placeholder | source_title starts with PLACEHOLDER |
| crop_calendar.csv | 76 | aman_rice.stage.days_to_flowering | placeholder | source_title starts with PLACEHOLDER |
| crop_thresholds.csv | 9 | aman_rice.wet.submergence_days | value | value does not parse ('10-16 (BRRI dhan51) or 10-14 (BRRI dhan52)' is not a number or an A-B range) |
| crop_thresholds.csv | 12 | boro_rice.cold.booting_tmin_low | source_url | source_url is not http(s): 'adhunikDhanerChash.pdf (BRRI official handbook, provided dir' |
| crop_thresholds.csv | 13 | boro_rice.cold.booting_tmin_high | source_url | source_url is not http(s): 'adhunikDhanerChash.pdf (BRRI official handbook, provided dir' |
| crop_thresholds.csv | 14 | boro_rice.heat.anthesis_tmax | source_url | source_url is not http(s): 'adhunikDhanerChash.pdf (BRRI official handbook, provided dir' |
| crop_thresholds.csv | 15 | aman_rice.wet.submergence_days | source_url | source_url is not http(s): 'adhunikDhanerChash.pdf (BRRI official handbook, provided dir' |
| crop_thresholds.csv | 16 | aman_rice.wet.submergence_days | source_url | source_url is not http(s): 'adhunikDhanerChash.pdf (BRRI official handbook, provided dir' |
| crop_thresholds.csv | 22 | boro_rice.cold.seedling_tmean | placeholder | source_title starts with PLACEHOLDER |
| crop_thresholds.csv | 23 | boro_rice.cold.seedling_days | placeholder | source_title starts with PLACEHOLDER |
| crop_thresholds.csv | 24 | aman_rice.cold.flowering_tmin | placeholder | source_title starts with PLACEHOLDER |
| crop_area_by_district.csv | 23 | zoning.cumilla.boro_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 24 | zoning.cumilla.wheat | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 25 | zoning.cumilla.potato | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 26 | zoning.cumilla.mustard | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 27 | zoning.cumilla.lentil | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 28 | zoning.cumilla.aman_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 29 | zoning.feni.boro_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 30 | zoning.feni.wheat | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 31 | zoning.feni.potato | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 32 | zoning.feni.mustard | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 33 | zoning.feni.lentil | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 34 | zoning.feni.aman_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 35 | zoning.noakhali.boro_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 36 | zoning.noakhali.wheat | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 37 | zoning.noakhali.potato | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 38 | zoning.noakhali.mustard | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 39 | zoning.noakhali.lentil | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 40 | zoning.noakhali.aman_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 41 | zoning.brahmanbaria.boro_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 42 | zoning.brahmanbaria.wheat | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 43 | zoning.brahmanbaria.potato | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 44 | zoning.brahmanbaria.mustard | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 45 | zoning.brahmanbaria.lentil | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 46 | zoning.brahmanbaria.aman_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 47 | zoning.sylhet.boro_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 48 | zoning.sylhet.wheat | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 49 | zoning.sylhet.potato | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 50 | zoning.sylhet.mustard | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 51 | zoning.sylhet.lentil | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
| crop_area_by_district.csv | 52 | zoning.sylhet.aman_rice | source_url | source_url is not http(s): 'czis.cropzoning.gov.bd' |
