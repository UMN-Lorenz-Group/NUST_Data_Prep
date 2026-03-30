# run_nust_pipeline.R
# Entry point for the NUST annual data processing pipeline (2024+).
# Edit YEAR and DATA_DIR below, then source this file.
#
# For historical XLSX data (pre-2023) use run_nust_historical_pipeline.R instead.
#
# Pipeline:
#   STEP 1 — Annual data extraction  (R scripts; different for historical path)
#     1a. NUST_StrainsTable_Processing.R   -> strainsTable1.csv, parentageTable1.csv
#     1b. NUST_ChecksTable_Processing.R    -> checksTable1.csv
#     1c. NUST_LocationsTable_Processing.R -> LocationsTable1.csv
#     1d. NUST_Processing.R                -> phenotypesTable0.csv, MetaTable.csv
#   ──────────────────────────────────────────────────────────────────────────
#   STEP 2 — Shared formatting  (IDENTICAL entry point for historical path)
#     NUST_CheckFinalFiles.R               -> Files4Upload/

SCRIPTS_DIR <- "C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/"

# -------------------------------------------------------------------------
# USER: set year and data directory for the run
# -------------------------------------------------------------------------
YEAR     <- "2025"
DATA_DIR <- "C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/"
# -------------------------------------------------------------------------

# Load shared utilities and config
source(file.path(SCRIPTS_DIR, "nust_utils.R"))
source(file.path(SCRIPTS_DIR, "nust_config.R"))

# Build year-specific configuration (auto-detects test lists)
cfg <- nust_config(year = YEAR, data_dir = DATA_DIR)

# Set working directory to data folder for all subsequent scripts
setwd(DATA_DIR)

# STEP 1 — Annual data extraction
message("\n=== STEP 1a: Strains & Parentage Table ===")
source(file.path(SCRIPTS_DIR, "NUST_StrainsTable_Processing.R"))

message("\n=== STEP 1b: Checks Table ===")
source(file.path(SCRIPTS_DIR, "NUST_ChecksTable_Processing.R"))

message("\n=== STEP 1c: Locations Table ===")
source(file.path(SCRIPTS_DIR, "NUST_LocationsTable_Processing.R"))

message("\n=== STEP 1d: Phenotypes Processing ===")
source(file.path(SCRIPTS_DIR, "NUST_Processing.R"))

# STEP 2 — Shared formatting (identical entry point for historical pipeline)
message("\n=== STEP 2: Final Validation & Output [SHARED] ===")
source(file.path(SCRIPTS_DIR, "NUST_CheckFinalFiles.R"))

message("\n=== Pipeline complete. Output files written to: ===")
message(file.path(DATA_DIR, "Files4Upload/"))
