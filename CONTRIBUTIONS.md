# Project Contributions Log
## NUST Soybean Trial Data Preparation Pipeline

**Project:** North American Uniform Soybean Trial (NUST) Data Preparation
**Institution:** University of Minnesota
**Repository:** `C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/`

---

## CRediT Author Contribution Summary
*(For manuscript methods / acknowledgements)*

| Role | Contributor |
|---|---|
| Conceptualization | Vishnu |
| Data curation | Vishnu |
| Investigation | Vishnu |
| Methodology | Vishnu |
| Project administration | Vishnu |
| Software — pipeline design & architecture | Vishnu (direction), Claude AI (implementation) |
| Software — R scripts (baseline, pre-AI) | Vishnu (sole author) |
| Software — R scripts (parameterized pipeline) | Vishnu (direction), Claude AI (implementation) |
| Software — Python extraction pipeline | Vishnu (direction), Claude AI (implementation) |
| Validation | Vishnu |
| Supervision | Vishnu |

**AI use disclosure (suggested Methods text):**
> Pipeline development, script refactoring, and data extraction automation were assisted by Claude (Anthropic, claude-sonnet-4-6), a large language model, under author supervision. All design decisions, requirements, and validation of outputs were made by the author. Code was reviewed and tested before use.

---

## Session Log

---

### Session 0 — Pre-2026-03-28 (Baseline)
**Focus:** Original annual pipeline scripts — written independently by Vishnu prior to AI-assisted development

**Author:** Vishnu (sole)

#### Scripts authored
| File | Purpose |
|---|---|
| `2025_StrainsTable_Processing.R` | Original strains table script (2025-specific, hardcoded) |
| `2025_ChecksTable_Processing.R` | Original checks table script (2025-specific, hardcoded) |
| `2025_LocationsTable_Processing.R` | Original locations table script (2025-specific, hardcoded) |
| `NUST_2025_Processing_V2.R` | Original main phenotype processing script (~971 lines) |
| `CheckFinalFiles.R` | Original final QC and file export script |
| `DataChecksScript.R` | Original data validation / QC script |

#### Notes
- These scripts constitute the intellectual foundation of the pipeline. All domain logic, data schema decisions, and processing workflows originate here.
- Sessions 1–3 refactored and extended these scripts into a year-agnostic, multi-source pipeline. The parameterized versions (`NUST_*.R`) are direct derivatives of this baseline work.
- No AI assistance was involved in authoring these scripts.

---

### Session 1 — 2026-03-28
**Focus:** Phase 1 — Year-parameterization of R pipeline

**Directed by:** Vishnu
**Implemented by:** Claude AI

#### Work completed
- Analyzed existing `2025_*` R scripts to identify all hardcoded year references
- Created `nust_utils.R` — shared utility library
  - `clean_strain_encoding()` — fixes non-ASCII characters in strain names
  - `clean_strain_annotations()` — removes annotation codes (GT, SCN, etc.)
  - `standardize_location_names()` — maps location name variants to canonical form
- Created `nust_config.R` — auto-detects test file lists from data directory (no manual editing per year)
- Created `run_nust_pipeline.R` — single entry point for annual pipeline
- Created `NUST_StrainsTable_Processing.R` — year-parameterized strains table
- Created `NUST_ChecksTable_Processing.R` — year-parameterized checks table

#### Key decisions (by Vishnu)
- Drop `Location` column from phenotypesTable schema (redundant with City + State)
- Auto-detect test list (Tests1/2/3) from CSV filenames in data directory — necessary because PT test structure differs between years (e.g., 2024: PTII vs. 2025: PTI, PTIIA, PTIIB)
- Use `cfg` list object as shared config passed across all sourced scripts

---

### Session 2 — 2026-03-28 to 2026-03-29
**Focus:** Phase 1 completion + Phase 2 design and implementation

**Directed by:** Vishnu
**Implemented by:** Claude AI

#### Work completed — Phase 1
- Created `NUST_LocationsTable_Processing.R` — year-parameterized locations table; trial year prefix parameterized with `sprintf("%02d", as.numeric(Year) - 2000 - 1)`
- Created `NUST_Processing.R` — main phenotype processing (~971 lines); removed `Location` from `selCols1`; parameterized all hardcoded year references
- Created `NUST_CheckFinalFiles.R` — final QC and CSV export to `Files4Upload/`; melt id.vars updated to remove `Location`

#### Work completed — Phase 2 (historical XLSX extraction)
- Analyzed `Sojabone-1980 (1-89 OR).xlsx` to map document structure (2082 rows, 18 cols, 6 entry groups, tp* section markers)
- Created `extract_nust_xlsx.py` — main extraction script
  - openpyxl reads raw cells → serialized as TSV grid
  - Sent to `claude-sonnet-4-6` (streaming, max_tokens=32000)
  - Claude identifies all table boundaries, normalizes locations and trait names, extracts data
  - Returns structured JSON → flattened to long-format CSVs
  - Chunking strategy: groups >300 rows split at tp6; b-chunks >150 rows split per trait (tp6…tp12b)
  - Retry logic: 3 attempts with 20s backoff
- Created `validate_nust_hist.py` — post-extraction validation
  - Schema check, range checks, non-numeric flagging, trait completeness, strain consistency
  - Outputs `approved.csv` + `review_flagged.csv`
- Tested on `Sojabone-1980 (1-89 OR).xlsx` — 10,125 phenotype rows extracted; 10,124/10,125 approved

#### Key decisions (by Vishnu)
- Use Claude API as primary interpreter (pure Option C) — no rule-based parsing in Python
- Extract ALL table types (phenotypes, parentage, descriptive, disease, summary) not just phenotypes
- Use tp* section tags as Test identifiers (Group_1…Group_6); user maps to UT00/UTI/etc. after review
- Split large groups per-trait to avoid API output limits (~65K char JSON limit)

---

### Session 3 — 2026-03-29
**Focus:** Unified pipeline architecture — linking Phase 2 to Phase 1

**Directed by:** Vishnu
**Implemented by:** Claude AI

#### Work completed
- Created `NUST_HistProcessing.R` — bridge script converting Phase 2 Python CSVs to Phase 1 intermediate format:
  - Pivots `_phenotypes.csv` (long) → `phenotypesTable0.csv` (wide, no Location col)
  - Builds `strainsTable1.csv` from `_strains.csv` + `_descriptive.csv`
  - Builds `parentageTable1.csv` (Parentage string → Female; Male = NA for historical)
  - Builds `LocationsTable1.csv` (City/State from data; lat/lon/Conductor/dates = NA)
  - Builds empty `checksTable1.csv` skeleton (no formal checks list in historical data)
  - Includes commented-out Test label remap block (Group_1 → UT0, etc.)
- Created `run_nust_historical_pipeline.R` — historical pipeline entry point
- Created `reference/phenotypesTable1_units_ref.csv` — static Phenotype/Units lookup (9 agronomic traits)
- Modified `NUST_CheckFinalFiles.R` — 3 guards for historical path compatibility:
  - Guard A: fallback to bundled units reference when `phenotypesTable1_2023.csv` absent
  - Guard B: skip checks cleaning when checksTable is empty
  - Guard C: copy `LocationsTable1.csv` to `Files4Upload/` (now works for both paths)
- Modified `run_nust_pipeline.R` — added Step 1/Step 2 boundary annotations
- Created `NUST_Phase2_Pipeline_Workflow.docx` — workflow documentation

#### Key decisions (by Vishnu)
- `NUST_CheckFinalFiles.R` is the shared Step 2 entry point for both historical and annual paths
- Historical parentage stored as single string in Female column (no Female/Male split available)
- Test label mapping left to user — commented remap block provided as hook
- LocationsTable1.csv with NA lat/lon is valid output for historical years

---

### Session 4 — 2026-03-29
**Focus:** End-to-end test of historical pipeline on 1980 data; bug fix in units reference

**Directed by:** Vishnu
**Implemented by:** Claude AI

#### Work completed
- Confirmed Phase 2 extraction output already present in `output_1980/` (10,125 rows; 10,124/10,125 approved)
- Located R 4.4.2 binary and ran `run_nust_historical_pipeline.R` end-to-end
- Identified bug: `reference/phenotypesTable1_units_ref.csv` used original XLSX trait names (`YIELD (bu/a)`) instead of R column names (`YieldBuA`) — Units column was NA for all rows
- Fixed by updating reference file to match R column names derived from the 2024 annual `phenotypesTable1.csv`
- Re-ran pipeline; all 9 agronomic traits now have correct units
- All 5 `Files4Upload/` tables verified correct

#### Validated output (1980)
| File | Rows | Notes |
|---|---|---|
| `phenotypesTable1.csv` | 28,098 | Units correct; FA cols present as NA |
| `strainsTable1.csv` | 208 | |
| `parentageTable1.csv` | 208 | Female = cross string; Male = NA |
| `LocationsTable1.csv` | 74 | 6 tests × ~12 locations |
| `checksTable1.csv` | 0 | Header-only skeleton; correct |

#### Key decisions (by Vishnu)
- Use R 4.4.2 (`/c/Program Files/R/R-4.4.2/bin/Rscript.exe`) as runtime for pipeline execution
- Units reference file must use R column names (`YieldBuA`, `Lodging`, etc.), not XLSX trait names — corrected and committed

---

## File Inventory

| File | Type | Purpose | Created/Modified |
|---|---|---|---|
| `2025_StrainsTable_Processing.R` | R | Original strains table (baseline) | Session 0 — Vishnu sole author |
| `2025_ChecksTable_Processing.R` | R | Original checks table (baseline) | Session 0 — Vishnu sole author |
| `2025_LocationsTable_Processing.R` | R | Original locations table (baseline) | Session 0 — Vishnu sole author |
| `NUST_2025_Processing_V2.R` | R | Original phenotype processing (baseline) | Session 0 — Vishnu sole author |
| `CheckFinalFiles.R` | R | Original QC + export script (baseline) | Session 0 — Vishnu sole author |
| `DataChecksScript.R` | R | Original data validation script (baseline) | Session 0 — Vishnu sole author |
| `nust_utils.R` | R | Shared utility functions | Session 1 |
| `nust_config.R` | R | Year-aware config auto-detection | Session 1 |
| `run_nust_pipeline.R` | R | Annual pipeline entry point | Session 1, updated Session 3 |
| `NUST_StrainsTable_Processing.R` | R | Strains + parentage table | Session 1 |
| `NUST_ChecksTable_Processing.R` | R | Checks table | Session 1 |
| `NUST_LocationsTable_Processing.R` | R | Locations table | Session 2 |
| `NUST_Processing.R` | R | Phenotype processing (~971 lines) | Session 2 |
| `NUST_CheckFinalFiles.R` | R | Final QC + Files4Upload export | Session 2, updated Session 3 |
| `extract_nust_xlsx.py` | Python | Historical XLSX extraction via Claude API | Session 2 |
| `validate_nust_hist.py` | Python | Post-extraction validation | Session 2 |
| `NUST_HistProcessing.R` | R | Phase 2 → Phase 1 bridge | Session 3 |
| `run_nust_historical_pipeline.R` | R | Historical pipeline entry point | Session 3 |
| `reference/phenotypesTable1_units_ref.csv` | CSV | Static Phenotype/Units lookup (corrected to R col names) | Session 3, fixed Session 4 |
| `NUST_Phase2_Pipeline_Workflow.docx` | Word | Pipeline workflow documentation | Session 2 |

---

## Notes for Manuscript Methods Section

**Data sources:** Historical NUST trial data (XLSX reports, pre-2023); Annual NUST trial data (CSV exports, 2024+)

**Pipeline overview:** A two-stage data preparation pipeline was developed. Stage 1 handles source-specific extraction: historical data is processed using a Python script (`extract_nust_xlsx.py`) that leverages a large language model API to parse legacy XLSX report structure; annual data is processed through a series of R scripts that read standardized per-test CSV exports. Stage 2 is a shared R formatting pipeline (`NUST_CheckFinalFiles.R`) that applies strain name standardization, location name harmonization, phenotype unit assignment, and long-format conversion, producing a consistent output schema regardless of data source.

**Output schema:** All final tables follow a standardized long format with columns: `Strain`, `Year`, `Test`, `City`, `State`, `Phenotype`, `Value`, `Units`.
