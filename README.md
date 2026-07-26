# NUST Data Preparation Pipeline

**North American Uniform Soybean Trial (NUST) — Data Preparation**
University of Minnesota — Lorenz Lab

---

## Overview

This repository contains a staged data-preparation pipeline for processing North American Uniform Soybean Trial (NUST) data from multiple sources into a standardized long-format corpus (1941–2025) suitable for genomic analysis and database upload, plus a downstream realized-genetic-gain (RGG) analysis suite.

The reusable pipeline scripts live in `data_prep/`, organized by stage:

- **Stage 0 (`stage0_extraction/`)** — source preprocessing + raw PDF/XLSX extraction
- **Stage 1 (`stage1_processing/`)** — per-year R-bridge + QC + maturity-DOY + location reference (source-specific extraction → shared R formatting → Files4Upload)
- **Stage 2 (`stage2_corpus/`)** — cross-year corpus assembly, check curation, `IsCheck` rebuild, wide-format build, and the era-split

RGG modeling and diagnostics live in `analysis/`; superseded scripts, one-off per-year fix/run instances, backups, and historical logs are kept under `archive/` (history preserved).

All final output tables follow a standardized schema:

| Column | Description |
|---|---|
| `Strain` | Cleaned strain identifier |
| `Year` | Trial year |
| `Test` | Trial test group (e.g., UTI, UTII, PTII) |
| `City` | Trial location city |
| `State` | Trial location state/province |
| `Phenotype` | Trait name (e.g., YieldBuA, Lodging) |
| `Value` | Observed value |
| `Units` | Units of measurement |

---

## Repository Structure

```
NUST_Data_Prep/
│
├── data_prep/                          # Staged extraction & data-preparation pipeline
│   ├── stage0_extraction/              #   source preprocess + raw PDF/XLSX extraction
│   │   ├── extract_nust_xlsx.py        #     Historical XLSX extraction via Claude API
│   │   ├── extract_nust_pdf.py         #     PDF-direct extraction (years w/o XLSX)
│   │   ├── extract_nust_blocks.py      #     Per-block XLSX extraction (1987/1988)
│   │   ├── extract_test_map_pdf.py     #     Group→TestCode mapping from source PDF
│   │   ├── pdf_pipeline.py             #     Unified cached-PDF query orchestrator
│   │   ├── preprocess_pdf_compress.py  #     Shrink PDFs below API size limit
│   │   └── extract_*_anchors.py        #     Maturity reference-strain anchors
│   │
│   ├── stage1_processing/              #   per-year R-bridge + QC + maturity DOY + locations
│   │   ├── run_nust_pipeline.R         #     Entry point — annual data (2024+)
│   │   ├── run_nust_historical_pipeline.R #  Entry point — historical (pre-2023)
│   │   ├── nust_utils.R / nust_config.R   #  Shared utilities + year-aware config
│   │   ├── NUST_*Processing*.R / NUST_CheckFinalFiles.R  # R bridge + shared formatting
│   │   ├── validate_nust_hist.py / qc_pdf_vs_csv.py      # post-extraction QC
│   │   ├── combine_nust_outputs.py    #     Merge multi-file extractions + TEST_MAP
│   │   ├── compute_maturity_doy.py / apply_maturity_doy.py  # maturity DOY conversion
│   │   └── build_location_ref.py + location/maturity utilities
│   │
│   └── stage2_corpus/                  #   cross-year corpus, checks, IsCheck, wide, split
│       ├── 10_assemble_corpus.py       #     Build the 1941–2025 long corpus
│       ├── 11_build_wide_1941_2025.py  #     Pivot long → wide (22-col modeling schema)
│       ├── 35_apply_protein_oil_moisture_fix.py
│       ├── 65_build_check_lookup.py / 67_build_checks_from_pdf.py   # check curation
│       ├── 89_rebuild_combined_ischeck.py / 89a / 89b               # IsCheck rebuild
│       ├── 12_split_combined_by_era.py #     Split master into 3 era files
│       └── 08*_extraction_accuracy*.py #     Extraction-accuracy QC
│
├── analysis/                           # RGG modeling & diagnostics (scripts 12–86)
│   ├── trait_rgg_config.R              #   shared secondary-trait RGG config
│   └── data/                           #   canonical corpus + designation tables
│       ├── nust_1941_2025_combined.csv #     master long file (3.77M rows) — DO NOT open in Excel
│       ├── nust_1965_2025_combined.csv #     alias (same content)
│       ├── nust_1941-1984_combined.csv #     era split 1
│       ├── nust_1985-2004_combined.csv #     era split 2
│       ├── nust_2005-2025_combined.csv #     era split 3
│       ├── NUST_1941_2025_data_wide.csv      # wide modeling input
│       └── nust_check_designation_years_1941_2025.csv + nust_checks_* + lookup
│
├── archive/                            # superseded / one-off / historical (history preserved)
│   ├── scripts/                        #   88, tmp_*, early R 01–08, per-year fix/run instances
│   ├── data/                           #   *.bak, pre_*_fix, intermediate subset CSVs
│   ├── logs_docs/                      #   historical session logs + superseded docs
│   └── reference_output/               #   (reserved)
│
├── reference/                          # static reference tables (locations, units, PlotInfo)
├── diagnostics/                        # debug and inspection scripts
├── input_files/  output_files/         # per-year source + extracted data
└── docs/                               # current workflow documentation
```

---

## Pipeline Architecture

```
HISTORICAL PATH (pre-2020)              ANNUAL PATH (2024+)
────────────────────────────────        ────────────────────────────────
STEP 1H — Python extraction:            STEP 1A — R extraction:
  extract_nust_xlsx.py                    NUST_StrainsTable_Processing.R
    → *_phenotypes.csv (long)             NUST_ChecksTable_Processing.R
    → *_strains.csv                       NUST_LocationsTable_Processing.R
    → *_parentage.csv                     NUST_Processing.R
    → *_descriptive.csv
    → *_disease.csv
    → *_summary.csv
          │
  validate_nust_hist.py
    → *_approved.csv
          │
  NUST_HistProcessing.R (bridge)
    → phenotypesTable0.csv (wide)
    → strainsTable1.csv
    → parentageTable1.csv
    → LocationsTable1.csv
    → checksTable1.csv (0-row)
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
```

---

## Usage

### Annual Data (2024+)

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

### Historical Data (pre-2020 XLSX)

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

#### Step 3 — Run R bridge + formatting

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

#### Step 4 — Map test labels (optional)

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
- Tested on: annual 2024–2025 data; historical 1980 XLSX (`Sojabone-1980 (1-89 OR).xlsx`)

---

## Notes

- The `ANTHROPIC_API_KEY` should be passed via `--api_key` argument or set as an environment variable. **Never commit API keys to this repository.**
- Historical fatty acid / seed sugar traits (`PalmiticAcid`, `Oil`, etc.) are present as `NA` in pre-2023 output — these traits were not measured in early trials.
- `LocationsTable1.csv` for historical years contains `NA` for `lat`, `lon`, `Conductor`, and planting/maturity dates — not available in source documents.

---

## Author Contributions

**Primary author:** Vishnu (University of Minnesota)
**AI assistance:** Pipeline development and script implementation assisted by Claude (Anthropic, `claude-sonnet-4-6`) under author supervision.
