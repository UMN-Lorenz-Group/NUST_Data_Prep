# NUST Pipeline Session — 2026-04-27

Full-day session covering 1980 data completion, schema finalisation to Rex DB conventions,
PDF tooling, maturity DOY conversion, and pipeline architecture optimisation.

---

## 1. Session Setup — API Key & .Env

Set up secure API key storage via `.Env` file in the project root.
Updated `extract_nust_xlsx.py` to auto-load the key via `load_env_file()` so no key needs
to be passed on the command line.
Added `.Env`, `.env`, `*.env` to `.gitignore` to prevent accidental commits.

---

## 2. 1980 File 2 Extraction

Launched background extraction of `Sojabone-1980 (90-164 OR).xlsx`
(entries 90–164, MG III/IV — Groups 7–10).
Added rate-limit handling in `call_claude()`:
- `RateLimitError` → sleep 60 s and retry
- `APIStatusError 529` → sleep 30 s and retry

**Result:** 11,136 phenotype rows, 108 strains, 4 groups (UT-III, PT-III, UT-IV, PT-IV).
Combined with file 1 (10,125 rows) → **21,261 total phenotype rows** across all 10 1980 tests.

---

## 3. Multi-Year XLSX Scan (`scan_years.py`)

Scanned all 43 years of source XLSX files (`R:\NUST_Historical_Data\Green\`) to document
tp-marker structure, trait labels, and column layouts across the full 1941–1986 range.
Identified three structural eras:

| Era | Years | Key differences |
|---|---|---|
| Early | 1941–1956 | Merged tp markers, minimal trait labels, no disease/descriptive tables |
| Transitional | 1957–1969 | Noisy tp codes, location format `State. City`, trait label gaps |
| Modern | 1970–1986 | Stable tp1–tp12b structure, reliable trait labelling |

Wrote `system_prompt_multiyr_notes.md` documenting all structural differences and the
era-specific prompt addenda needed before batch processing.

---

## 4. Rex DB Formatting (`combine_nust_outputs.py` — major rewrite)

Read `Formatting_Note_From_Rex.docx` and overhauled `combine_nust_outputs.py` to produce
all 6 Rex-formatted output tables:

| Table | Key changes |
|---|---|
| `phenotypesTable` | Location composite (City_State), Rex phenotype names (YieldBuA, Height, etc.), column order: Strain, Year, Test, Location, City, State, Phenotype, Value, Units |
| `strainsTable` | Merged descriptive, Check flag via regex, renamed cols (Descriptive.Code, Gen.Comp., etc.) |
| `parentageTable` | Split Parentage on " x " → Female, Male |
| `locationsTable` | Unique City+State pairs, NULL placeholders for lat/lon/Conductor/dates |
| `checksTable` | Check=1 rows, MG label from strain name parenthetical first, RM=NULL |
| `MetaTable` | CV%, LSD, Reps, Row sp per location/trait/test |

**Units column order fix:** `Value` must precede `Units` (not after Phenotype).
Fixed across `extract_nust_xlsx.py`, `combine_nust_outputs.py`, and patch scripts.

---

## 5. Validation & Flagged-Value QC

Updated `validate_nust_hist.py` with Rex DB phenotype names and adjusted thresholds:

```
YieldBuA (0–120)   Lodging (1–5)     Height (9–80)
SeedQuality (1–5)  SeedSize (1–30)   Protein (30–55)   Oil (14–25)
```

`Maturity` designated as `DATE_OR_TEXT_TRAITS` (skips numeric range check).

Initial validation flagged 15 rows. All investigated against source PDF:
- 12 OIL flags → genuine low-oil values at Maryland/Missouri sites. Oil floor adjusted 15 → 14.
- 1 Height flag → floor adjusted 10 → 9.
- 2 confirmed OCR artifacts → patched.

---

## 6. PDF QC Tool (`qc_pdf_vs_csv.py`)

Built a two-mode PDF verification script using the Anthropic Files API:

- **`--mode roster`** — uploads PDF, asks Claude for strain/location roster per group,
  diffs against CSV to catch missing or extra strains.
- **`--mode flagged`** — looks up specific flagged values in the PDF, returns verdict:
  `confirmed_ocr_error | genuine_value | not_found | ambiguous`.

Single PDF upload is reused across both modes (same `file_id`).

---

## 7. OCR Patches (`apply_patches_1980.py`)

Applied 3 confirmed OCR corrections to the combined 1980 CSVs:

| Strain | Phenotype | Location | Old | New |
|---|---|---|---|---|
| `Clay (0)` | Lodging | Morden | `"Otbreek"` | `4.0` |
| `L74D-609` | YieldRank | Belleville | `"I"` | `1` |
| `K1033` | Oil | Manhattan | `"I"` | NULL |

Wrote to `output_1980/patched/` to avoid Windows file-lock issues (Excel open).

---

## 8. Supplemental PDF Extraction (`extract_supplemental_pdf.py`)

Built a two-call PDF extraction script for metadata absent from the XLSX:

- **Call 1 (LOCATION_PROMPT):** Conductor, PlantingDate, MaturityDate, check RM per location/test
- **Call 2 (METATABLE_PROMPT):** C.V.(%), L.S.D.(5%), Reps, Row spacing, Rows/plot per trait/location/test

Merged results into existing `locationsTable`, `checksTable`, and `MetaTable` CSVs.

**Result for 1980:** 121/159 PlantingDates filled, 655-row MetaTable
(YieldBuA-only — correct for 1980, which predates multi-trait footer statistics).

---

## 9. Supplemental Fixes (`fix_supplemental_1980.py`)

Three post-extraction fixes (year-specific, later generalised into `pdf_pipeline.py`):

- **checksTable RM:** Reset Roman numeral / single-digit values (e.g. "I", "0") to NULL —
  these were MG designations returned by Claude, not numeric RM (predates 1980).
- **MetaTable Trait names:** Applied PHENOTYPE_MAP to convert raw names
  (`"YIELD (bu/a)"`) to Rex DB names (`"YieldBuA"`).
- **PlantingDate format:** Standardised `"5/20"` → `"1980-05-20"` using year parameter.

---

## 10. Geocoding Design (`build_location_ref.py`)

Built (not yet run) a geocoding script using Nominatim (OpenStreetMap):

- Collects unique City+State pairs from all extracted CSVs + XLSX header scans.
- `parse_location_string()` handles both era formats
  (early: `State. City`, modern: `City State`).
- `STATE_NORM` dict: comprehensive historical abbreviation → standard mapping
  (e.g. `ONT` → `ON`).
- `KNOWN_STATIONS` dict: ~35 known research station names flagged with
  `NeedsVerification=1` (city-centre coordinates differ from farm coordinates).
- Outputs `nust_locations_unique.csv` + `nust_locations_ref.csv`.

---

## 11. Maturity DOY Pipeline

### Audit
Classified all 2,495 Maturity rows in `combined_1980_phenotypesTable.csv`:

| Format | Count | Description |
|---|---|---|
| Integer offsets | 2,106 (85%) | ± days relative to a reference check variety |
| ISO wrong-year | 72 (3%) | openpyxl read Excel date cells, serialised as 2026-MM-DD |
| M-DD text | 32 (1%) | Calendar dates as text strings (e.g. `9-18`, `10-1*`) |
| Frost/special | 14 (0.5%) | `frost`, `Frost Kill` — no valid maturity |
| Null | 271 (11%) | Missing |

### First-pass normalisation (`fix_maturity_1980.py`)
- `2026-MM-DD` → DOY with correct 1980 year
- `M-DD*` text → DOY; `* 9/17` annotation → DOY
- `frost` / `Frost Kill` / `+5*` → NULL
- Integer offsets left as-is (resolved via anchor step)

**Result:** 107 values converted, 13 nulled.

### Reference-check anchor system (`compute_maturity_doy.py`)

Three-tier anchor strategy to resolve the 85% relative-day offsets:

| Tier | Method | Tests covered |
|---|---|---|
| CSV | Check variety already has DOY values in phenotypesTable | UT-0, UT-II, UT-III, UT-IV, PT-IV |
| PDF | Upload source PDF, ask Claude for reference check calendar dates | UT-00, UT-I, PT-I, PT-II |
| Gap-fill | Median of any already-DOY values at that Test×Location | Mean rows, Marshalltown PT-II |

Reference checks identified by the PDF for all 10 tests:

| Test | Reference Check | Source |
|---|---|---|
| UT-00 | Portage (00) | PDF |
| UT-0 | Evans (0) | CSV |
| UT-I | Hodgson 78 (I) | PDF |
| PT-I | Hodgson 78 (I) | PDF |
| UT-II | Corsoy 79 (II) | CSV |
| PT-II | Corsoy 79 (II) | PDF |
| UT-III | Cumberland (III) | CSV |
| PT-III | Cumberland (III) | PDF |
| UT-IV | Union (IV) | CSV + gap-fill |
| PT-IV | Union (IV) | CSV |

**Final result:** 0 no-anchor rows. 2,105 offsets converted, 89 Mean rows averaged.

### Intermediate output files
- `combined_{year}_maturityAnchorsTable.csv` — audit record: `Year, Test, ReferenceCheck, City, State, AnchorDate, AnchorDOY, Source`
- `combined_{year}_maturityVerification.csv` — `OriginalMaturity, ComputedDOY, Status` per row

### Integration into `combine_nust_outputs.py`
Maturity DOY step integrated as a standard pipeline stage after `format_phenotypes()`.
Runs automatically; supports `--pdf`, `--pdf_json`, `--pdf_session`, `--no_maturity_doy`.

---

## 12. Pipeline Architecture Optimisation

### Problem identified
The PDF was being uploaded independently by three scripts
(`extract_supplemental_pdf.py`, `compute_maturity_doy.py`, `qc_pdf_vs_csv.py`),
paying upload cost and latency 2–3 times per year.

### Solution: `pdf_pipeline.py` (new unified script)
Single upload, three structured queries, one session file:

```
pdf_pipeline.py --pdf 1980_done.pdf --year 1980 --csv_dir output_1980/
```

| Query | Extracts | Replaces |
|---|---|---|
| A — Supplemental | Conductor, PlantingDate, check RM | `extract_supplemental_pdf.py` call 1 |
| B — MetaTable | CV%, LSD, Reps, Row spacing | `extract_supplemental_pdf.py` call 2 |
| C — Maturity anchors | Reference check calendar dates | PDF part of `compute_maturity_doy.py` |
| D — Roster QC | Strain/location lists vs CSV | `qc_pdf_vs_csv.py --mode roster` |

Saves `pdf_session_{year}.json` with `file_id` for downstream reuse.

### Updated validate pipeline
`validate_nust_hist.py` extended to auto-call flagged-value PDF lookup
using saved `file_id`, emit `patch_candidates_{year}.csv`,
and auto-apply confirmed OCR patches without manual intervention.

### Full optimised command sequence per year
```bash
python extract_nust_xlsx.py --file "<file1>.xlsx" --out_dir output_{year}/
python extract_nust_xlsx.py --file "<file2>.xlsx" --out_dir output_{year}/
python pdf_pipeline.py      --pdf <year>_done.pdf --year {year} --csv_dir output_{year}/
python combine_nust_outputs.py --out_dir output_{year}/ --year {year} \
       --pdf_session output_{year}/pdf_session_{year}.json
python validate_nust_hist.py   --year {year} --csv_dir output_{year}/ \
       --pdf_session output_{year}/pdf_session_{year}.json
python build_location_ref.py   --year {year} --csv_dir output_{year}/
```

---

## Scripts Created or Significantly Modified

| Script | Status | Notes |
|---|---|---|
| `extract_nust_xlsx.py` | Modified | .Env loader, rate-limit handling |
| `combine_nust_outputs.py` | Major rewrite | Rex formatting, 6 tables, Units fix, maturity DOY integrated, `--pdf_session` support |
| `validate_nust_hist.py` | Modified | Rex DB names, adjusted thresholds, `--pdf_session` auto-patch loop |
| `qc_pdf_vs_csv.py` | New | PDF roster + flagged-value QC (absorbed into `pdf_pipeline.py`) |
| `extract_supplemental_pdf.py` | New | Conductor/dates/MetaTable from PDF (absorbed into `pdf_pipeline.py`) |
| `fix_supplemental_1980.py` | New (one-off) | RM reset, trait name fix, date standardisation — generalised into `pdf_pipeline.py` |
| `apply_patches_1980.py` | New (one-off) | 3 OCR patches — replaced by auto-patch loop |
| `build_location_ref.py` | New | Geocoding via Nominatim (not yet run) |
| `scan_years.py` | New | Multi-year XLSX structure scan |
| `system_prompt_multiyr_notes.md` | New | Era-aware prompt modification plan |
| `compute_maturity_doy.py` | New | Standalone DOY conversion with PDF anchor extraction |
| `apply_maturity_doy.py` | New | Apply verified DOY to main CSV (re-run utility) |
| `fix_maturity_1980.py` | New (one-off) | First-pass date normalisation |
| `pdf_pipeline.py` | New | Unified PDF script — single upload, all PDF work |

---

## 1980 Final Output Files

| File | Rows | Notes |
|---|---|---|
| `combined_1980_phenotypesTable.csv` | 21,261 | Maturity in DOY, Rex DB phenotype names |
| `combined_1980_strainsTable.csv` | 316 | Check flag, DescriptiveCode merged |
| `combined_1980_parentageTable.csv` | 316 | Female/Male split |
| `combined_1980_locationsTable.csv` | 159 | PlantingDate 121/159 filled |
| `combined_1980_checksTable.csv` | 26 | MG Phenotype, RM=NULL |
| `combined_1980_MetaTable.csv` | 655 | YieldBuA only (correct for 1980) |
| `combined_1980_maturityAnchorsTable.csv` | 138 | Reference check + AnchorDate + Source per Test×Location |
| `combined_1980_maturityVerification.csv` | 2,495 | OriginalMaturity vs ComputedDOY for review |

---

## Remaining Work

### For 1980
- Run `build_location_ref.py` and manually verify research station coordinates
- Merge verified lat/lon into `locationsTable`

### Before batch processing 1941–1986
- Implement era-aware system prompt (per `system_prompt_multiyr_notes.md`)
- Handle 1975 (PDF-only, no XLSX) — separate extraction path
- Handle 1987/1988 (fragmented XLSX) — separate assembler
- Run `pdf_pipeline.py` for each year once PDFs are available
