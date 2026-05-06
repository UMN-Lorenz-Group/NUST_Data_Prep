# NUST Data Preparation Pipeline

**North American Uniform Soybean Trial (NUST) — Data Preparation**
University of Minnesota — Lorenz Lab

---

## Overview

This repository contains a two-stage data preparation pipeline for processing North American Uniform Soybean Trial (NUST) data from multiple sources into a standardized long-format output suitable for genomic analysis and database upload.

- **Stage 1** handles source-specific extraction — different for historical (pre-2020 XLSX) and annual (2021+ CSV) data
- **Stage 2** is a shared R formatting pipeline applied identically to both sources

---

## Pipeline Architecture

```
HISTORICAL PATH (pre-1989)              ANNUAL PATH (2020+)
────────────────────────────────        ────────────────────────────────
STEP 1H — Python + Claude API:          STEP 1A — R extraction:
  extract_nust_xlsx.py                    NUST_StrainsTable_Processing.R
    → long-format CSVs                    NUST_ChecksTable_Processing.R
      (phenotypes, strains,               NUST_LocationsTable_Processing.R
       parentage, descriptive,            NUST_Processing.R
       disease, summary)
          │
  validate_nust_hist.py
    → *_approved.csv
          │
  qc_pdf_vs_csv.py (Claude API)
    cell-by-cell validation
    against source PDF
    → patches applied via
      year-specific fixes/
          │
  NUST_HistProcessing.R (bridge)
    → R intermediates
      (wide format, ready for Step 2)
          │                                       │
          └─────────────────┬─────────────────────┘
                            ▼
          STEP 2 — SHARED (identical for both paths)
            NUST_CheckFinalFiles.R
                            │
                      Files4Upload/
                phenotypesTable1.csv
                strainsTable1.csv
                parentageTable1.csv
                LocationsTable1.csv
                checksTable1.csv
                metaTable1.csv
```

---

## Repository Structure

```
NUST_Data_Prep/
│
├── run_nust_pipeline.R              # Entry point — annual data (2020+)
├── run_nust_historical_pipeline.R   # Entry point — historical data (pre-1989)
│
├── Rscripts/                        # R processing modules
│   ├── nust_utils.R                 #   Shared utility functions
│   ├── nust_config.R                #   Year-aware config and test auto-detection
│   ├── NUST_StrainsTable_Processing.R   #   Annual: strains + parentage table
│   ├── NUST_ChecksTable_Processing.R    #   Annual: checks table
│   ├── NUST_LocationsTable_Processing.R #   Annual: locations table
│   ├── NUST_Processing.R                #   Annual: phenotype processing
│   ├── NUST_HistProcessing.R            #   Historical: bridge — Python CSVs → R intermediates
│   ├── NUST_CheckFinalFiles.R           #   SHARED Step 2: final QC + Files4Upload export
│   └── DataChecksScript.R               #   Manual QC checks
│
├── scripts/                         # Core Python pipeline scripts
│   ├── extract_nust_xlsx.py         #   Historical XLSX extraction via Claude API
│   ├── validate_nust_hist.py        #   Post-extraction validation
│   ├── combine_nust_outputs.py      #   Merge multi-file extractions + TEST_MAP
│   ├── extract_test_map_pdf.py      #   Group→TestCode mapping from source PDF
│   ├── extract_supplemental_pdf.py  #   Supplemental location data from PDF
│   ├── build_location_ref.py        #   Build/geocode nust_locations_ref.csv
│   ├── compute_maturity_doy.py      #   Convert maturity dates to DOY
│   ├── apply_maturity_doy.py        #   Apply DOY values to phenotypes table
│   ├── pdf_pipeline.py              #   PDF extraction utilities
│   └── qc_pdf_vs_csv.py             #   QC: compare PDF values against CSV output
│
├── fixes/                           # Year-specific fix and patch scripts
│   ├── fix_1980_locs.py             #   State norm, dedup, PlantingDate, lat/lon
│   ├── fix_maturity_1980.py
│   ├── fix_supplemental_1980.py
│   ├── apply_patches_1980.py
│   ├── compare_locations.py         #   Compare historical ref vs modern PlotInfo
│   ├── patch_location_coords.py     #   Apply modern GPS to NeedsVerification rows
│   └── clean_location_ref.py        #   One-time ref cleanup after initial geocoding
│
├── reference/                       # Reference tables (static + geocoded)
│   ├── nust_locations_ref.csv       #   115 geocoded locations (1941–1986)
│   ├── nust_locations_unique.csv    #   Unique City×State list from all years
│   ├── 2024_NUST_Locations_PlotInfo.csv
│   ├── 2025_NUST_Locations_PlotInfo.csv
│   └── phenotypesTable1_units_ref.csv  # Phenotype → Units lookup
│
├── docs/                            # Supporting documentation
│   ├── NUST_Phase2_Pipeline_Workflow.docx
│   ├── system_prompt_multiyr_notes.md
│   └── NUST_Processing_ReadMe.txt
│
├── logs/                            # Session notes, reports, open items
│   ├── NUST_Pipeline_Session_*.md
│   ├── NUST_1980_Open_Items.md
│   └── NUST_Location_Comparison_*.md
│
├── diagnostics/                     # Archived debug and inspection scripts
│
├── input_1980/                      # Source XLSX + PDF for 1980
└── output_1980/                     # Extracted CSVs for 1980
```

---

## Usage

### Annual Data (2020+)

1. Edit `run_nust_pipeline.R` — set `YEAR` and `DATA_DIR`:
   ```r
   YEAR     <- "2025"
   DATA_DIR <- "path/to/2025_NUST_Processing/"
   ```
2. Source the script in R:
   ```r
   source("run_nust_pipeline.R")
   ```
3. Output written to `DATA_DIR/Files4Upload/`

---

### Historical Data (pre-1989 XLSX)

#### Step 1 — Extract from XLSX

```bash
python scripts/extract_nust_xlsx.py \
  --file "Sojabone-YYYY (1-89 OR).xlsx" \
  --out_dir ./output_YYYY/ \
  --api_key "sk-ant-..."
```

Requires an [Anthropic API key](https://console.anthropic.com). The script uses `claude-sonnet-4-6` to interpret the legacy table structure and outputs structured CSVs.

#### Step 2 — Validate extraction output

```bash
python scripts/validate_nust_hist.py \
  --input ./output_YYYY/..._phenotypes.csv \
  --out_dir ./output_YYYY/validated/
```

Outputs `*_approved.csv` and `*_review_flagged.csv`. Review flagged rows before proceeding.

#### Step 3 — QC and fix (year-specific)

Run `scripts/qc_pdf_vs_csv.py` against the source PDF to identify cell-level discrepancies across all Test×Location combos. Apply year-specific fix scripts in `fixes/` to patch confirmed issues in the source tables, then re-validate. See `docs/NUST_Historical_Extraction_Workflow.md` for the full 3-phase QC workflow.

#### Step 4 — Run R bridge + formatting

Edit `run_nust_historical_pipeline.R` — set `YEAR`, `HIST_CSV_DIR`, and `DATA_DIR`:
```r
YEAR         <- "1980"
HIST_CSV_DIR <- "path/to/output_1980/"
DATA_DIR     <- "path/to/1980_Processing/"
```

Then source in R:
```r
source("run_nust_historical_pipeline.R")
```

Output written to `DATA_DIR/Files4Upload/`

#### Step 5 — Verify cross-table consistency

```bash
python fixes/consistency_check_{year}.py   # strains, locations, checks, metaTable
python fixes/verify_phase3_{year}.py       # confirm PDF-patched cells in Files4Upload
```

#### Step 6 — Map test labels (optional)

The extraction uses `Group_1`…`Group_6` as test identifiers. To remap to standard NUST codes (`UT00`, `UTI`, etc.), uncomment and fill in the `TEST_MAP` block at the bottom of `NUST_HistProcessing.R`:

```r
TEST_MAP <- c(
  "Group_1" = "UT0",
  "Group_2" = "UTI",
  ...
)
```

---

## Output Tables

| File | Description |
|---|---|
| `phenotypesTable1.csv` | Long-format phenotypes: Strain × Location × Trait |
| `strainsTable1.csv` | Strain metadata: descriptive codes, check status |
| `parentageTable1.csv` | Parentage: Female × Male cross |
| `LocationsTable1.csv` | Location metadata: City, State, lat, lon, Conductor |
| `checksTable1.csv` | Check entries and relative maturity |
| `metaTable1.csv` | Per-location statistical metadata: CV%, LSD, row spacing, reps |

---

## Dependencies

### R packages
- `reshape2` — wide/long pivoting (`melt`, `dcast`)

### Python packages
- `openpyxl` — XLSX reading
- `anthropic` — Claude API client

Install Python dependencies:
```bash
pip install openpyxl anthropic
```

---

## Tested Environments

- R 4.4.2 (Windows)
- Python 3.10 (Windows)
- Tested on: annual 2024–2025 data; historical 1980 XLSX (fully QC'd against source PDF; all cross-table checks pass)

---

## Notes

- The `ANTHROPIC_API_KEY` should be passed via `--api_key` argument or set as an environment variable. **Never commit API keys to this repository.**
- Historical fatty acid / seed sugar traits (`PalmiticAcid`, `Oil`, etc.) are present as `NA` in pre-2023 output — these traits were not measured in early trials.
- `LocationsTable1.csv` for historical years contains `NA` for `Conductor` and planting/maturity dates — not available in source documents. Coordinates (`lat`, `lon`) are populated from `reference/nust_locations_ref.csv` (115 geocoded locations, 1941–1986; 22 flagged `NeedsVerification`).

---

## Author Contributions

**Primary author:** Vishnu (University of Minnesota) 
**PI:** Aaron Lorenz (University of Minnesota) & Rex Nelson (USDA)     
**AI assistance:** Pipeline development and script implementation assisted by Claude (Anthropic, `claude-sonnet-4-6`) under author supervision.
