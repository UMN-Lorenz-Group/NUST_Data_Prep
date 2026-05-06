# NUST Location Reference — Modern vs Historical Comparison
**Date:** 2026-04-27  
**Files compared:**
- `nust_locations_ref.csv` — historical geocoded reference (115 rows, 1941–1986 NUST trials)
- `2024_NUST_Locations_PlotInfo.csv` — 43 unique locations, trial-specific GPS
- `2025_NUST_Locations_PlotInfo.csv` — **identical to 2024 file** (same trial codes, same coords)

---

## Key Findings

### 1. Files are identical
Both 2024 and 2025 PlotInfo files contain the same 43 locations with the same trial codes (all prefixed `24`). The 2025 file appears to be a copy of 2024 and does not yet contain 2025 trial data.

### 2. Overlap: 18 matched locations
18 historical locations matched a modern equivalent by City+State (after name normalisation: `West Lafayette IN` → `Lafayette`, `Ottawa-ONT` → `Ottawa`). Of these, **13 have `NeedsVerification=1`** and the modern files provide farm-specific GPS coordinates that are meaningfully more accurate than Nominatim city-centre geocodes.

### 3. Coord updates applied (13 rows)
The following `NeedsVerification=1` rows were updated with modern trial GPS coordinates.  
`Source` column set to `modern_plotinfo_2024` and `NeedsVerification` cleared to `0`.

| City | State | Old lat | Old lon | New lat | New lon | Shift |
|---|---|---|---|---|---|---|
| Ames | IA | 42.02676 | -93.61705 | 41.97127 | -93.63079 | ~6 km S |
| Belleville | IL | 38.51358 | -89.98416 | 38.53320 | -89.89451 | ~8 km NE |
| Urbana | IL | 40.11172 | -88.20730 | 40.05356 | -88.23572 | ~6 km S to UIUC farm |
| Lafayette | IN | 40.41912 | -86.89190 | 40.48065 | -87.00460 | ~11 km NW to Purdue ACRE |
| Manhattan | KS | 39.18361 | -96.57167 | 39.13225 | -96.61808 | ~6 km SW to KSU farm |
| East Lansing | MI | 42.73203 | -84.47217 | 42.63032 | -84.43760 | ~11 km S to MSU farm |
| Crookston | MN | 47.77400 | -96.60812 | 47.81999 | -96.62727 | ~5 km N |
| Lamberton | MN | 44.23107 | -95.26416 | 44.23334 | -95.30453 | minimal lat; ~4 km W |
| Rosemount | MN | 44.73919 | -93.12611 | 44.70708 | -93.10117 | ~4 km S |
| Waseca | MN | 44.01722 | -93.58857 | 44.07391 | -93.52658 | ~7 km NE |
| Elora | ONT | 43.68115 | -80.42958 | 43.63613 | -80.40640 | ~5 km S |
| Ottawa | ONT | 45.42088 | -75.69011 | 45.36832 | -75.72633 | ~6 km S to AAFC farm |

> **Note on Lafayette IN:** Historical city name was "Lafayette"; modern trial uses "West Lafayette". Both refer to the Purdue ACRE (Agronomy Center for Research and Education). The new coordinates (40.4807°N, 87.0046°W) are the actual farm site.

### 4. Ottawa KS — intentionally skipped
Historical `Ottawa KS` geocoded to Ottawa County centroid (39.127°N, 97.657°W).  
Modern `Ottawa-KS KS` coordinates are the actual city of Ottawa, KS (38.540°N, 95.248°W) — a different location ~170 km apart. The historical entry likely refers to a county-level site; left unchanged pending verification.

### 5. Saskatoon SK — data issue in modern file
`Saskatoon SAS` in the modern file has `lon=+106.6702` (positive). Correct longitude should be `-106.6702`. Not merged into historical ref. Flag for correction in the PlotInfo file.

---

## 5 Matched but not updated (NeedsVerification=0, coords already reasonable)

| City | State | Δlat | Δlon | Note |
|---|---|---|---|---|
| Sutherland | IA | -0.049° | -0.030° | Small offset; city centre vs trial field |
| Ottawa | KS | -0.587° | +2.409° | Skipped — genuine location ambiguity |
| Novelty | MO | -0.069° | +0.149° | Small offset; no NeedsVerification flag |
| Mead | NE | -0.067° | +0.070° | Small offset |
| Hoytville | OH | +0.025° | +0.027° | Small offset |

---

## 98 Historical-only locations
Sites from the 1941–1986 era no longer in the modern NUST program. All retain Nominatim-geocoded coordinates in `nust_locations_ref.csv`. Stations (NeedsVerification=1) still needing manual verification: DeKalb IL, Brandon MAN, Morden MAN, Winnipeg MAN, Beltsville MD, Queenstown MD, Morris MN, Columbia MO, Portageville MO, Fargo ND, Wooster OH, Guelph ONT, Harrow ONT, Ridgetown ONT, State College PA, Brookings SD, Lubbock TX, Arlington WI, Ashland WI, Madison WI.

## 25 Modern-only locations (program expansion)
New sites not present in historical data:

| Location | State |
|---|---|
| Lucas | IA |
| Monmouth, Perry, Savoy | IL |
| Butlerville, Wanatah | IN |
| Carman | MAN |
| Britton, Saginaw | MI |
| Perley, Roseau, Thief River Falls | MN |
| Rock Port | MO |
| Casselton, Galesburg | ND |
| Cook, Cotesfield, Phillips, Steven's Creek | NE |
| Chatham, St. Marys, Woodstock | ONT |
| Saint Hyacinthe, Saint-Mathieu-de-Beloeil | QC |
| Saskatoon | SK |

These can be appended to `nust_locations_ref.csv` as needed when building a unified all-years location table.

---

## Files modified
- `nust_locations_ref.csv` — 13 coord rows updated (see table above)

## Scripts
- `compare_locations.py` — produces this comparison report
- `patch_location_coords.py` — applies modern coords to `nust_locations_ref.csv`
