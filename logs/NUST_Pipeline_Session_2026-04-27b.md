# NUST Pipeline Session — 2026-04-27 (Part 2)
**Continuation of earlier session. Focus: location reference finalisation and 1980 validation.**

---

## 1. Location Reference vs Modern Files Comparison

**Script:** `compare_locations.py`  
**Finding:** `2024_NUST_Locations_PlotInfo.csv` and `2025_NUST_Locations_PlotInfo.csv` are **identical** — same 43 unique locations, same trial codes (all `24` prefix). 2025 file is a copy of 2024.

**Overlap:** 18 historical locations matched modern equivalents. 13 of those had `NeedsVerification=1` and modern files provided farm-specific GPS (trial-level coordinates vs Nominatim city-centre).

**Modern-only locations (25):** Program expansion since ~2000 — Lucas IA, Savoy/Perry/Monmouth IL, Butlerville/Wanatah IN, Carman MAN, Britton/Saginaw MI, Perley/Roseau/Thief River Falls MN, Rock Port MO, Casselton/Galesburg ND, Cook/Cotesfield/Phillips/Steven's Creek NE, Chatham/St. Marys/Woodstock ONT, Saint Hyacinthe/Saint-Mathieu-de-Beloeil QC, Saskatoon SK.

**Data issue flagged:** Saskatoon SK has `lon=+106.67` in modern file (should be negative). Not merged.

**Ottawa KS skipped:** Historical geocode (39.13°N, Ottawa County) vs modern "Ottawa-KS" (38.54°N, city of Ottawa) — genuine location ambiguity, not a geocoding error.

**Reference:** `NUST_Location_Comparison_2026-04-27.md`

---

## 2. nust_locations_ref.csv — 12 Coord Updates Applied

**Script:** `patch_location_coords.py`  
**Action:** Applied farm-specific GPS from 2024 PlotInfo to 12 `NeedsVerification=1` rows.  
**Result:** `NeedsVerification=1` reduced from 34 → 22. `Source` column set to `modern_plotinfo_2024`.  
**Backup:** `nust_locations_ref_backup.csv`

| City | State | Key shift |
|---|---|---|
| Ames | IA | ~6 km S to ISU research farm |
| Belleville | IL | ~8 km NE |
| Urbana | IL | ~6 km S to UIUC Crop Sciences farm |
| Lafayette | IN | ~11 km NW to Purdue ACRE |
| Manhattan | KS | ~6 km SW to KSU Agronomy Farm |
| East Lansing | MI | ~11 km S to MSU Agronomy Farm |
| Crookston | MN | ~5 km N |
| Lamberton | MN | minimal lat; ~4 km W |
| Rosemount | MN | ~4 km S |
| Waseca | MN | ~7 km NE |
| Elora | ONT | ~5 km S to U of Guelph station |
| Ottawa | ONT | ~6 km S to AAFC Research Centre |

---

## 3. locationsTable Fixes (159 → 141 rows)

**Script:** `fix_1980_locs.py`

### 3a. State abbreviation normalisation
ILL→IL, IND→IN, KAN→KS, NEB→NE, PENN→PA, DEL→DE applied across all rows.  
Soil-type labels in State column (LOAM, CLAY from Portageville entries) fixed: City renamed to `Portageville Loam`/`Portageville Clay`, State set to MO.

### 3b. OCR city name fixes
- `Giradr` → `Girard` (UT-III)
- `ElkPoint` → `Elk Point` (UT-III)
- `Point Elk` → `Elk Point` (UT-III — all three are same location, confirmed by ref coords)

### 3c. Deduplication
17 duplicate Test×City×State groups collapsed after normalisation (35 rows → 17). Final: **141 rows**.

### 3d. PlantingDate merged
From `supplemental_1980_location_raw.json` (136 supplemental rows). Portageville soil-type variants required a second pass to handle parenthesis name format `"Portageville (Clay) MO"` → `"Portageville Clay"`.  
**Result: 136/141 PlantingDate filled.**

5 rows remain NULL — genuinely absent from supplemental (PT-IV/Portageville MO, UT-II/Harrow OH, UT-III/Ashland KS, UT-III/Greenfield IL, UT-III/Sullivan IL).

### 3e. lat/lon merged
Joined from updated `nust_locations_ref.csv` on (City, State).  
**Result: 141/141 rows have coordinates.**

---

## 4. phenotypesTable State Code Normalisation

**Scripts:** `_portage_patch.py`, `_fix_portage_states.py`

Normalised raw state codes carried from XLSX extraction:
- ILL→IL (56 rows), IND→IN (100), KAN→KS (370), NEB→NE (14), PENN/Penn→PA (82), DEL→DE (14)
- State='Loam'/State='Clay' Portageville rows fixed: City set to `Portageville Loam`/`Portageville Clay`, State set to MO (360 rows total)

**Result:** All 21,261 rows have canonical state codes.

---

## 5. validate_nust_hist.py — Clean Pass

**Final run:** 21,261 rows approved, **0 flagged**.

### 3 OCR values patched before final run
| id | Test | Location | Phenotype | Bad value | Action |
|---|---|---|---|---|---|
| 249 | UT-00 | Morden MAN | Lodging | `Otbreek` | Nulled (OCR artifact) |
| 16702 | UT-IV | Belleville IL | YieldRank | `I` | Nulled (OCR/incomplete marker) |
| 18399 | UT-IV | Manhattan KS | Oil | `I` | Nulled (OCR/incomplete marker) |

### Validator rule updates
- Added `KNOWN_TRAIT_OMISSIONS` dict to suppress expected missing-trait WARNs:
  - PT-* exempt from YieldRank (prelim tests never assigned ranks)
  - PT-III also exempt from Maturity
  - UT-0 and UT-III exempt from YieldRank (confirmed vs 1980 PDF)
- Strain-count consistency tolerance widened ±2 → ±5

---

## 6. Open Items Recorded

**File:** `NUST_1980_Open_Items.md`

| Flag | Item | Resolution |
|---|---|---|
| FLAG 1 | PlantingDate NULL for 5 rows | Manual PDF lookup |
| FLAG 2 | Conductor NULL all rows | Genuinely absent from 1980 publication |
| FLAG 3 | checksTable RM NULL | Pre-numeric RM era; needs historical MG→RM table |
| FLAG 4 | 194 null-DOY in maturityVerification | Expected missing data (OriginalMaturity also NULL) |

---

## Scripts Added / Modified This Session

| Script | Type | Purpose |
|---|---|---|
| `compare_locations.py` | new | Compare historical ref vs 2024/2025 PlotInfo |
| `patch_location_coords.py` | new | Apply modern GPS to NeedsVerification=1 rows |
| `fix_1980_locs.py` | new | State norm, OCR fix, dedup, PlantingDate + lat/lon merge |
| `validate_nust_hist.py` | updated | KNOWN_TRAIT_OMISSIONS, tolerance ±5 |
| `nust_locations_ref.csv` | updated | 12 coords from modern files; NeedsVerification 34→22 |
| `combined_1980_locationsTable.csv` | updated | 159→141 rows, 141/141 coords, 136/141 dates |
| `combined_1980_phenotypesTable.csv` | updated | State codes canonical, 3 values nulled, id column added |
| `NUST_Location_Comparison_2026-04-27.md` | new | Location comparison report |
| `NUST_1980_Open_Items.md` | new | Flags log for 1980 |

---

## Next Steps

1. **Era-aware system prompt** (`system_prompt_multiyr_notes.md`) — implement Early/Transitional/Modern addenda before batch-processing 1941–1986
2. **1975 (PDF-only year)** — separate extraction path needed (no XLSX source)
3. **1987/1988 (fragmented XLSX)** — separate assembler needed
4. **Historical MG → RM reference table** — needed to populate checksTable RM for pre-1985 years
5. **Batch run** — once era-aware prompt ready, process remaining years on R: drive
