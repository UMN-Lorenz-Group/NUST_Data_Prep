# NUST Data Preparation Pipeline

**North American Uniform Soybean Trial (NUST) — Data Preparation**
University of Minnesota — Lorenz Lab

---

## Overview

This repository contains a two-stage data preparation pipeline for processing North American Uniform Soybean Trial (NUST) data from multiple sources into a standardized long-format output suitable for genomic analysis and database upload.

- **Stage 1** handles source-specific extraction — different for historical (pre-2020 XLSX) and annual (2021+ CSV) data
- **Stage 2** is a shared R formatting pipeline applied identically to both sources

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
├── run_nust_pipeline.R              # Entry point — annual data (2024+)
├── run_nust_historical_pipeline.R   # Entry point — historical data (pre-2023)
│
├── nust_utils.R                     # Shared utility functions
├── nust_config.R                    # Year-aware config and test auto-detection
│
├── NUST_StrainsTable_Processing.R   # Annual: strains + parentage table
├── NUST_ChecksTable_Processing.R    # Annual: checks table
├── NUST_LocationsTable_Processing.R # Annual: locations table
├── NUST_Processing.R                # Annual: phenotype processing (~971 lines)
│
├── extract_nust_xlsx.py             # Historical: XLSX extraction via Claude API
├── validate_nust_hist.py            # Historical: post-extraction validation
├── NUST_HistProcessing.R            # Historical: bridge — Python CSVs → R intermediates
│
├── NUST_CheckFinalFiles.R           # SHARED Step 2: final QC + Files4Upload export
│
├── reference/
│   └── phenotypesTable1_units_ref.csv  # Static Phenotype → Units lookup
│
├── 2025_StrainsTable_Processing.R   # Baseline scripts (2025-specific originals)
├── 2025_ChecksTable_Processing.R
├── 2025_LocationsTable_Processing.R
├── NUST_2025_Processing_V2.R
├── CheckFinalFiles.R
└── DataChecksScript.R
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
python extract_nust_xlsx.py \
  --file "Sojabone-YYYY (1-89 OR).xlsx" \
  --out_dir ./output_YYYY/ \
  --api_key "sk-ant-..."
```

Requires an [Anthropic API key](https://console.anthropic.com). The script uses `claude-sonnet-4-6` to interpret the legacy table structure and outputs structured CSVs.

#### Step 2 — Validate extraction output

```bash
python validate_nust_hist.py \
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
