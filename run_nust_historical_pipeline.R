# run_nust_historical_pipeline.R
# Entry point for the NUST historical data pipeline (pre-2023 XLSX files).
#
# Prerequisites — run Phase 2 Python scripts first:
#   python extract_nust_xlsx.py --file "Sojabone-YYYY (...).xlsx" --out_dir <HIST_CSV_DIR>
#   python validate_nust_hist.py --input <HIST_CSV_DIR>/..._phenotypes.csv --out_dir <HIST_CSV_DIR>/validated/
#
# Pipeline:
#   STEP 1  (Python, run separately above)
#     extract_nust_xlsx.py  →  HIST_CSV_DIR/*_phenotypes.csv, *_strains.csv,
#                               *_parentage.csv, *_descriptive.csv, *_summary.csv
#
#   STEP 2a (R bridge)
#     NUST_HistProcessing.R →  DATA_DIR/phenotypesTable0.csv  (wide)
#                               DATA_DIR/strainsTable1.csv
#                               DATA_DIR/strainsTable_From_DataFiles.csv
#                               DATA_DIR/parentageTable1.csv
#                               DATA_DIR/LocationsTable1.csv
#                               DATA_DIR/checksTable1.csv     (0-row skeleton)
#
#   STEP 2b (R shared — identical entry point as annual pipeline Step 2)
#     NUST_CheckFinalFiles.R → DATA_DIR/Files4Upload/
#                               phenotypesTable1.csv
#                               strainsTable1.csv
#                               parentageTable1.csv
#                               checksTable1.csv
#                               LocationsTable1.csv

SCRIPTS_DIR <- "C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/"

# ─── USER: configure per run ─────────────────────────────────────────────────
YEAR <- "1980"

# Folder containing Phase 2 Python output CSVs (*_phenotypes.csv, etc.)
HIST_CSV_DIR <- "C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/output_1980/"

# Working directory where intermediate files will be written and Files4Upload/ created
DATA_DIR <- "C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/NUST_Historical_Data/1980_Processing/"
# ─────────────────────────────────────────────────────────────────────────────

source(file.path(SCRIPTS_DIR, "nust_utils.R"))

# Minimal cfg list — NUST_CheckFinalFiles.R only needs cfg$year and cfg$data_dir
cfg <- list(year = YEAR, data_dir = DATA_DIR)

# Ensure output directories exist
if (!dir.exists(DATA_DIR)) dir.create(DATA_DIR, recursive = TRUE)
if (!dir.exists(file.path(DATA_DIR, "Files4Upload")))
  dir.create(file.path(DATA_DIR, "Files4Upload"), recursive = TRUE)

setwd(DATA_DIR)

# ─── STEP 2a: bridge — Phase 2 CSVs → Phase 1 intermediate format ────────────
message("\n=== STEP 2a: HistProcessing (bridge) ===")
source(file.path(SCRIPTS_DIR, "NUST_HistProcessing.R"))

# ─── STEP 2b: shared formatting — identical to annual pipeline Step 2 ─────────
message("\n=== STEP 2b: CheckFinalFiles [SHARED with annual pipeline] ===")
source(file.path(SCRIPTS_DIR, "NUST_CheckFinalFiles.R"))

message("\n=== Historical pipeline complete. Output files written to: ===")
message(file.path(DATA_DIR, "Files4Upload/"))
