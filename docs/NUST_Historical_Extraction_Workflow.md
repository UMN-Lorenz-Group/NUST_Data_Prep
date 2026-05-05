# NUST Historical XLSX Extraction — Workflow
**Last updated:** 2026-05-05
**Validated on:** 1980 (20,900 phenotype rows approved; 54,864 rows in Files4Upload; all cross-table checks pass)
**Scope:** Historical NUST XLSX reports, 1941–1986 (Green folder)

---

## Overview

Each historical NUST XLSX file contains one year's trial report for a subset of maturity
groups. The extraction pipeline sends raw cell grids to Claude (`claude-sonnet-4-6`), which
interprets the table structure and returns structured JSON. No rule-based parsing is used —
Claude handles all layout variation, OCR artifacts, and schema mapping.

---

## End-to-End Pipeline

```
XLSX file(s)
    │
    ▼
scripts/extract_nust_xlsx.py        ← Step 1: extract raw tables
    │   • openpyxl reads cells
    │   • find_group_boundaries() chunks sheet by tp2 markers
    │   • each chunk sent to Claude with era-aware system prompt
    │   • JSON → flat CSVs per table type
    ▼
output_{year}/
    ├── *_phenotypes.csv
    ├── *_strains.csv
    ├── *_parentage.csv
    ├── *_descriptive.csv
    ├── *_disease.csv
    └── *_summary.csv
    │
    ▼
scripts/combine_nust_outputs.py     ← Step 2: merge multi-file years + apply TEST_MAP
    │   • renumbers groups across files (File 2 groups offset by File 1 count)
    │   • renames Group_N → test codes (UT-I, PT-II, etc.) from TEST_MAP
    ▼
output_{year}/
    ├── combined_{year}_phenotypesTable.csv
    ├── combined_{year}_strainsTable.csv
    ├── combined_{year}_parentageTable.csv
    ├── combined_{year}_locationsTable.csv
    ├── combined_{year}_checksTable.csv
    └── combined_{year}_MetaTable.csv
    │
    ▼
fixes/fix_{year}_locs.py            ← Step 3: location table cleanup (year-specific)
    │   • normalize state abbreviations
    │   • fix OCR city name errors
    │   • deduplicate Test×City×State
    │   • merge PlantingDate from supplemental JSON
    │   • join lat/lon from reference/nust_locations_ref.csv
    ▼
scripts/validate_nust_hist.py       ← Step 4: validate phenotypes table
    │   • schema, range, and trait-completeness checks
    │   • outputs _approved.csv and _review_flagged.csv
    ▼
output_{year}/validated/
    ├── combined_{year}_phenotypesTable_approved.csv
    └── combined_{year}_phenotypesTable_review_flagged.csv
    │
    ▼
scripts/qc_pdf_vs_csv.py            ← Step 5: PDF cell-by-cell QC
    │   • compares approved CSV against source PDF for all Test×Location combos
    │   • modes: roster (strain list) | flagged | values (cell-by-cell)
    │   • uses Claude API with prompt caching for cost-effective cell verification
    │   • --resume flag resumes interrupted runs
    ▼
fixes/                              ← Step 6: apply confirmed fixes (year-specific scripts)
    │   • OCR strain renames, cell patches, state code corrections, table cleanup
    │   • re-run validate_nust_hist.py → new approved CSV
    │   • re-run R bridge → new Files4Upload/
    ▼
fixes/consistency_check_{year}.py   ← Step 7: cross-table verification (5 checks)
fixes/verify_phase3_{year}.py       ← Step 8: confirm patches present in Files4Upload
```

After completing Steps 5–8, `Files4Upload/` is ready for database upload.
See the [QC and Fix Workflow](#qc-and-fix-workflow) section below for the full 3-phase approach.

---

## Era-Aware System Prompt

The `SYSTEM_PROMPT` base covers the Modern era (1970–1986, validated on 1980). For
earlier years, `build_system_prompt(year)` appends an era-specific addendum.

| Era | Years | Addendum |
|---|---|---|
| Early | 1941–1956 | `ERA_ADDENDUM_EARLY` |
| Transitional | 1957–1969 | `ERA_ADDENDUM_TRANSITIONAL` |
| Modern | 1970–1986 | none (base prompt only) |

### What the addenda add

**Early (1941–1956):**
- Location format: City-first with dotted state abbreviation (`"Morris Minn."` → `city="Morris", state="MN"`)
- Footnote stripping from location headers (`"Guelph Ont.1"` → `"Guelph Ont."`)
- Fused tp marker handling: `tp6+7`, `tp9+10`, `tp8+11a`, `tp8+12a` — Claude splits into two phenotype sections per block
- Absent sections: tp1, tp3a, tp3b not present in early years; empty list expected
- Iodine Number of Oil trait (`IODINE NUMBER OF OIL`) — present ~1943–1948 only
- Seed Weight in centigrams (`SEED WEIGHT (cg)`) — kept separate from `SEED SIZE (g/100)`

**Transitional (1957–1969):**
- Mixed location formats — both modern (`"Ont. Ottawa"`) and early (`"Ottawa Ont."`) may appear in the same file
- Fused markers: `tp12a & tp12b`, `tp10 & tp12b`, `tp6+7`
- OCR normalization: `tptp11a` → tp11a, `tp 2` → tp2, `tp24` → skip, bare `tp3` → treat as tp3a if morphological
- `tp3c` (1972 only) — extract into descriptive table as-is
- Expanded multi-year summary skip list (more common in this era)

**All eras (base prompt):**
- Extended trait label mappings: all known variants across 46 years mapped to canonical names
- Multi-year summary skip labels: `"2-year summary"`, `"1968-70 MEAN YIELD"`, etc.
- Continuation header handling: `"(Continued)"` rows skipped, not treated as new sections

### How `_normalize_tp()` works

`find_group_boundaries()` uses `_normalize_tp()` to map raw column-A cell values to
canonical tp codes before boundary detection. This means the chunking logic (which splits
large groups at tp6) correctly finds `tp6+7` as the first per-location marker, enabling
proper sub-chunking of large early-era groups.

| Raw cell value | Canonical | Notes |
|---|---|---|
| `tp6+7` | `tp6` | fused yield + rank |
| `tp9+10` | `tp9` | fused lodging + height |
| `tp 2` | `tp2` | spaced OCR artifact |
| `tp6 (Continued)` | `tp6` | continuation annotation |
| `tp2 (NB Baie swak beeld)` | `tp2` | Afrikaans annotation stripped |
| `tptp11a` | `tp11a` | doubled-prefix OCR |
| `tp??` | *(skip)* | unknown marker |
| `tp24` | *(skip)* | OCR error |
| `tp` (bare) | *(skip)* | separator artifact |

---

## Running the Pipeline

### Single year, two XLSX files (e.g. 1980)

```bash
# Step 1 — extract each file
python scripts/extract_nust_xlsx.py \
  --file "input_1980/1980/Sojabone-1980 (1-89 OR).xlsx" \
  --out_dir output_1980/

python scripts/extract_nust_xlsx.py \
  --file "input_1980/1980/Sojabone-1980 (90-164 OR).xlsx" \
  --out_dir output_1980/

# Step 2 — combine and apply TEST_MAP
python scripts/combine_nust_outputs.py \
  --input_dir output_1980/ \
  --out_dir output_1980/ \
  --test_map "Group_1=UT-00,Group_2=UT-0,Group_3=UT-I,Group_4=PT-I,Group_5=UT-II,Group_6=PT-II,Group_7=UT-III,Group_8=PT-III,Group_9=UT-IV,Group_10=PT-IV"

# Step 3 — location cleanup (year-specific fix script)
python fixes/fix_1980_locs.py

# Step 4 — validate
python scripts/validate_nust_hist.py \
  --input output_1980/combined_1980_phenotypesTable.csv \
  --out_dir output_1980/validated/
```

### Batch run (all XLSX files in a folder)

```bash
python scripts/extract_nust_xlsx.py \
  --dir "R:/NUST_Historical_Data/Green-.../Green/1952/" \
  --out_dir output_1952/
```

The era is detected automatically from the year in the filename.
The active era and prompt length are printed at the start of each file:

```
Processing: Sojabone-1952 (1-60 OR).xlsx
  Year detected: 1952
  Era: early (system prompt: 9417 chars)
  Sections found: ['GlobalParentage', 'Group_1', 'Group_2', ...]
```

### Identifying the TEST_MAP for a year

If the Group→TestCode mapping is not known, use `extract_test_map_pdf.py` with the source
PDF for that year:

```bash
python scripts/extract_test_map_pdf.py \
  --pdf "input_{year}/{year}_source.pdf" \
  --out_dir output_{year}/
```

Outputs a JSON file and an R snippet ready to paste into `combine_nust_outputs.py`.

---

## QC and Fix Workflow

Three phases, confirmed on 1980.

**Phase 1 — Extract and validate**
Extract → combine → fix_locs → validate. Review the `_review_flagged.csv` output; accept the `_approved.csv` and proceed.

**Phase 2 — QC against PDF**
Run `qc_pdf_vs_csv.py --mode values` for all Test×Location combos. The script uses the Claude API with prompt caching for cost-effective comparison. Use `--resume` to continue interrupted runs. Log confirmed issues to `logs/NUST_{year}_QC_Issues.md`.

**Phase 3 — Patch and verify**
Apply year-specific fix scripts in `fixes/` for each confirmed issue. Re-validate → re-run R bridge → run `consistency_check_{year}.py` (5 cross-table checks) → run `verify_phase3_{year}.py` (all patches confirmed in Files4Upload).

> **Leap-year note:** `qc_pdf_vs_csv.py` may flag Maturity dates as off-by-1 for leap years (e.g., 1980, 1984) — this is a false positive; CSV values are correct.

---

## Output Tables

| File | Content | Format |
|---|---|---|
| `combined_{year}_phenotypesTable.csv` | Strain × Location × Trait values | long (one row per observation) |
| `combined_{year}_strainsTable.csv` | Strain, generation, previous testing | wide |
| `combined_{year}_parentageTable.csv` | Strain, Female × Male cross | wide |
| `combined_{year}_locationsTable.csv` | City, State, lat, lon, PlantingDate, Conductor | wide |
| `combined_{year}_checksTable.csv` | Check entries, RM (NULL for pre-~1985) | wide |
| `combined_{year}_MetaTable.csv` | Per-location statistical metadata (CV%, LSD, row spacing, reps) | wide |
| `combined_{year}_maturityVerification.csv` | Maturity date → DOY conversion | wide |

---

## Validation Rules

`scripts/validate_nust_hist.py` checks:
- **Schema:** all required columns present
- **Range:** numeric traits within plausible bounds
- **Non-numeric:** unexpected string values in numeric phenotype columns
- **Trait completeness:** expected traits present in every test group (with known omissions per era)
- **Strain count consistency:** uniform strain count across traits within each group (tolerance ±5)

Known trait omissions (suppressed from completeness warnings):

| Test pattern | Exempt traits | Reason |
|---|---|---|
| `PT-*` | YieldRank | Preliminary tests never assigned ranks |
| `PT-III` | YieldRank, Maturity | MG III prelim omits maturity |
| `UT-0` | YieldRank | Not reported (1980 confirmed) |
| `UT-III` | YieldRank | Not reported (1980 confirmed) |

> Additional exemptions may need to be added for other years — confirm against source PDF
> before adding to `KNOWN_TRAIT_OMISSIONS`.

---

## Reference Files

| File | Purpose |
|---|---|
| `reference/nust_locations_ref.csv` | 115 geocoded locations (1941–1986); NeedsVerification=22 |
| `reference/2024_NUST_Locations_PlotInfo.csv` | Modern trial GPS (43 locations; identical to 2025 file) |
| `docs/system_prompt_multiyr_notes.md` | Detailed notes behind era addenda; open questions |
| `logs/NUST_Batch_Cost_Estimate.md` | API cost projections by era |
| `logs/NUST_1980_Open_Items.md` | Documented data gaps for 1980 (reference for other years) |

---

## Known Gaps and Remaining Work

| Item | Notes |
|---|---|
| **Era-aware prompt** | Base prompt (Modern era) validated on 1980; pre-1970 era addenda written but not yet test-run on actual XLSX files — run a test year from each era before full batch |
| **1975** | PDF-only — no XLSX in Green folder; separate extraction path needed |
| **1987–1988** | Fragmented XLSX structure; separate assembler script needed |
| **Historical MG → RM table** | Needed to populate checksTable RM for pre-~1985 years; RM NULL until resolved |
| **Conductor field** | Absent from 1980 publication (all rows NULL); verify availability in other years |
| **PlantingDate** | NULL for 5 of 141 locations in 1980 (manual PDF lookup required); other years may vary |
| **Seed Weight (cg) unit** | Pre-~1968 seed size in cg, not g/100 — confirm crossover year; may need unit conversion for unified analysis |
| **Iodine Number** | Last year to verify (~1948); not relevant after that |
| **tp3c (1972)** | Inspect that file to determine what data is present |
| **Open questions** | See `docs/system_prompt_multiyr_notes.md` Section 7 |
