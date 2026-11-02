### NUST_HistProcessing.R
## Bridge script: converts Phase 2 Python output CSVs to the Phase 1 R-pipeline
## intermediate format so NUST_CheckFinalFiles.R can run unchanged as Step 2.
##
## Variables required in scope (set by run_nust_historical_pipeline.R):
##   SCRIPTS_DIR  — path to NUST_Data_Prep/ repo
##   HIST_CSV_DIR — path to Phase 2 output folder (*_phenotypes.csv, etc.)
##   DATA_DIR     — destination for intermediate files (also setwd'd to this)
##   YEAR         — character year, e.g. "1980"
##
## Output files written to DATA_DIR:
##   phenotypesTable0.csv          (wide, no Location col — matches NUST_Processing.R output)
##   strainsTable1.csv
##   strainsTable_From_DataFiles.csv
##   parentageTable1.csv
##   LocationsTable1.csv
##   checksTable1.csv              (0-row skeleton)

library(reshape2)

source(file.path(SCRIPTS_DIR, "nust_utils.R"))

# ---------------------------------------------------------------------------
# 0. Locate and read Phase 2 CSVs
#    Prefer combined pipeline outputs (combine_nust_outputs.py) when present.
#    Falls back to per-file raw extractions for single-file / un-combined runs.
# ---------------------------------------------------------------------------

# Resolve a file by trying explicit combined-table names first, then a glob pattern.
# required=FALSE returns an empty data frame instead of stopping when not found.
read_hist <- function(..., fallback_pattern, required = TRUE) {
  candidates <- c(...)
  for (p in candidates) {
    full <- file.path(HIST_CSV_DIR, p)
    if (file.exists(full)) {
      message(sprintf("  Reading %s", p))
      return(read.csv(full, stringsAsFactors = FALSE))
    }
  }
  f <- grep(fallback_pattern, list.files(HIST_CSV_DIR, full.names = TRUE), value = TRUE)
  if (!length(f)) {
    if (!required) {
      message(sprintf("  [optional] %s not found — skipping", fallback_pattern))
      return(data.frame())
    }
    stop(sprintf("[HistProcessing] No file for pattern '%s' in %s",
                 fallback_pattern, HIST_CSV_DIR))
  }
  message(sprintf("  Reading (fallback) %s", basename(f[1])))
  read.csv(f[1], stringsAsFactors = FALSE)
}

# Phenotypes: prefer validated approved file, then combined table, then raw per-file
pheno_validated <- file.path(HIST_CSV_DIR, "validated",
                             sprintf("combined_%s_phenotypesTable_approved.csv", YEAR))
pheno_long <- if (file.exists(pheno_validated)) {
  message(sprintf("  Reading validated: combined_%s_phenotypesTable_approved.csv", YEAR))
  read.csv(pheno_validated, stringsAsFactors = FALSE)
} else {
  read_hist(sprintf("combined_%s_phenotypesTable.csv", YEAR),
            fallback_pattern = "_phenotypesTable\\.csv$|combined.*_phenotypes\\.csv$")
}

strains_raw <- read_hist(sprintf("combined_%s_strainsTable.csv",  YEAR),
                         fallback_pattern = "_strains\\.csv$")
parent_raw  <- read_hist(sprintf("combined_%s_parentageTable.csv", YEAR),
                         fallback_pattern = "_parentage\\.csv$")
desc_raw    <- read_hist(sprintf("combined_%s_descriptive.csv",    YEAR),
                         fallback_pattern = "_descriptive\\.csv$", required = FALSE)

# ---------------------------------------------------------------------------
# 1. phenotypesTable0.csv — long → wide, per-location rows only
#    Column schema must match NUST_Processing.R output (no Location column)
# ---------------------------------------------------------------------------

PHENO_MAP <- c(
  "YIELD (bu/a)"            = "YieldBuA",
  "YIELD RANK"              = "YieldRank",
  "MATURITY (date)"         = "Maturity",
  "LODGING (score)"         = "Lodging",
  "PLANT HEIGHT (inches)"   = "Height",
  "SEED QUALITY (score)"    = "SeedQuality",
  "SEED SIZE (g/100)"       = "SeedSize",
  "PROTEIN (%)"             = "Protein",
  "OIL (%)"                 = "Oil",
  # Legacy phenotypes from pre-1950 era (preserved as distinct traits per user
  # decision; previously dropped by R bridge). Coverage: SEED WEIGHT (cg) in
  # 1943-1954, IODINE NUMBER OF OIL in 1941-1948.
  "SEED WEIGHT (cg)"        = "SeedWeight",
  "SEED WEIGHT"             = "SeedWeight",
  "IODINE NUMBER OF OIL"    = "Oil_IodineNumber"
)
# AG_COLS deduplicates because PHENO_MAP has two keys pointing to SeedWeight.
AG_COLS <- unique(unname(PHENO_MAP))

FA_COLS <- c("PalmiticAcid", "StearicAcid", "OleicAcid", "LinoleicAcid",
             "LinolenicAcid", "Sucrose", "Raffinose", "Stachyose", "SugarTotal")

# Filter to per-location rows.
# The Phenotype column may contain either extraction-style labels ("YIELD (bu/a)")
# or R column names ("YieldBuA") depending on how the file was produced.
# Detect which format and map accordingly.
p <- pheno_long[pheno_long$City != "Mean" & pheno_long$City != "", ]

# Validated CSVs from combine_nust_outputs.py can contain a MIX of canonical
# names ("YieldBuA") for traits in PHENOTYPE_MAP and raw extraction names
# ("SEED WEIGHT", "IODINE NUMBER OF OIL") for traits not in that map (the
# legacy phenotypes). Handle both in a single pass: keep rows whose Phenotype
# is either a PHENO_MAP key OR a value, mapping keys through PHENO_MAP and
# leaving values unchanged.
p_by_key <- p[p$Phenotype %in% names(PHENO_MAP), ]
if (nrow(p_by_key) > 0) p_by_key$PhenoCol <- PHENO_MAP[p_by_key$Phenotype]
p_by_val <- p[p$Phenotype %in% unname(PHENO_MAP), ]
if (nrow(p_by_val) > 0) p_by_val$PhenoCol <- p_by_val$Phenotype
p <- unique(rbind(p_by_key, p_by_val))

# Pivot to wide: one row per Strain × Year × Test × City × State
pheno_wide <- dcast(
  p,
  Strain + Year + Test + City + State ~ PhenoCol,
  value.var    = "Value",
  fun.aggregate = function(x) x[1]   # take first value if accidental duplicates
)

# Ensure all 9 agronomic trait columns are present even if some were absent
for (col in AG_COLS) {
  if (!col %in% colnames(pheno_wide)) pheno_wide[[col]] <- NA_character_
}

# OriginalStrain before cleaning
pheno_wide$OriginalStrain <- pheno_wide$Strain
pheno_wide$Strain <- clean_strain_annotations(pheno_wide$Strain)

# Fatty-acid / seed-sugar columns — NA for all historical data
for (col in FA_COLS) pheno_wide[[col]] <- NA_real_

FINAL_COLS <- c("Strain", "Year", "Test", "City", "State", "OriginalStrain",
                AG_COLS, FA_COLS)
pheno_wide <- pheno_wide[, FINAL_COLS]

write.csv(pheno_wide, file.path(DATA_DIR, "phenotypesTable0.csv"),
          row.names = FALSE, quote = FALSE)
message(sprintf("[HistProcessing] phenotypesTable0.csv: %d rows, %d unique strains",
                nrow(pheno_wide), length(unique(pheno_wide$Strain))))

# ---------------------------------------------------------------------------
# 2. strainsTable1.csv — strains + descriptive codes
# ---------------------------------------------------------------------------

if ("Descriptive.Code" %in% colnames(strains_raw)) {
  # Combined strainsTable already has Descriptive.Code merged in — use directly
  s <- strains_raw
  s$Strain        <- clean_strain_annotations(s$Strain)
  required_cols <- c("Year", "Test", "Strain", "OriginalStrain",
                     "Descriptive.Code", "Unique.traits", "Gen.Comp.", "Check")
  for (col in required_cols) if (!col %in% colnames(s)) s[[col]] <- ""
  strains_out <- unique(s[, required_cols])
} else {
  # Per-file raw extraction — build from strains_raw + desc_raw
  s <- merge(
    strains_raw[, c("Strain", "Test", "Year")],
    desc_raw[, c("Strain", "DescriptiveCode", "Test", "Year")],
    by     = c("Strain", "Test", "Year"),
    all.x  = TRUE
  )
  s$OriginalStrain   <- s$Strain
  s$Strain           <- clean_strain_annotations(s$Strain)
  s$Descriptive.Code <- ifelse(is.na(s$DescriptiveCode), "", s$DescriptiveCode)
  s$Unique.traits    <- ""
  s$Gen.Comp.        <- ""
  s$Check            <- 0L
  strains_out <- unique(s[, c("Year", "Test", "Strain", "OriginalStrain",
                               "Descriptive.Code", "Unique.traits", "Gen.Comp.", "Check")])
}

write.csv(strains_out, file.path(DATA_DIR, "strainsTable1.csv"),
          row.names = FALSE, quote = FALSE)
# NUST_CheckFinalFiles.R also reads strainsTable_From_DataFiles.csv
write.csv(strains_out, file.path(DATA_DIR, "strainsTable_From_DataFiles.csv"),
          row.names = FALSE, quote = FALSE)
message(sprintf("[HistProcessing] strainsTable1.csv: %d rows", nrow(strains_out)))

# ---------------------------------------------------------------------------
# 3. parentageTable1.csv — single Parentage string → Female; Male = NA
# ---------------------------------------------------------------------------

if ("Female" %in% colnames(parent_raw)) {
  # Combined parentageTable already split Female/Male — use directly
  parent_out <- parent_raw
  parent_out$Strain <- clean_strain_annotations(parent_out$Strain)
  parent_out <- unique(parent_out[!is.na(parent_out$Strain) & parent_out$Strain != "", ])
} else {
  parent_out <- data.frame(
    Year   = parent_raw$Year,
    Test   = parent_raw$Test,
    Strain = clean_strain_annotations(parent_raw$Strain),
    Female = parent_raw$Parentage,
    Male   = NA_character_,
    stringsAsFactors = FALSE
  )
  parent_out <- unique(parent_out[!is.na(parent_out$Strain) & parent_out$Strain != "", ])
}

write.csv(parent_out, file.path(DATA_DIR, "parentageTable1.csv"),
          row.names = FALSE, quote = FALSE)
message(sprintf("[HistProcessing] parentageTable1.csv: %d rows", nrow(parent_out)))

# ---------------------------------------------------------------------------
# 4. LocationsTable1.csv — prefer combined table (has lat/lon/PlantingDate);
#    fall back to building from pheno_long with NA fields.
# ---------------------------------------------------------------------------

combined_locs_path <- file.path(HIST_CSV_DIR,
                                sprintf("combined_%s_locationsTable.csv", YEAR))

if (file.exists(combined_locs_path)) {
  message(sprintf("  Reading combined: combined_%s_locationsTable.csv", YEAR))
  loc_raw <- read.csv(combined_locs_path, stringsAsFactors = FALSE)
  loc_out  <- loc_raw[, c("Year", "Test", "City", "State", "lat", "lon",
                           "Conductor", "PlantingDate", "MaturityDate")]
  loc_out$City <- standardize_location_names(loc_out$City)
  loc_out$City <- gsub("Steven's", "Stevens", loc_out$City)
  loc_out <- loc_out[order(loc_out$Year, loc_out$Test, loc_out$City), ]
} else {
  loc_rows <- pheno_long[pheno_long$City != "Mean" & pheno_long$City != "", ]
  loc_base  <- unique(loc_rows[, c("Year", "Test", "City", "State")])
  loc_out <- data.frame(
    Year         = loc_base$Year,
    Test         = loc_base$Test,
    City         = standardize_location_names(loc_base$City),
    State        = loc_base$State,
    lat          = NA_real_,
    lon          = NA_real_,
    Conductor    = NA_character_,
    PlantingDate = NA_character_,
    MaturityDate = NA_character_,
    stringsAsFactors = FALSE
  )
  loc_out$City <- gsub("Steven's", "Stevens", loc_out$City)
  loc_out <- loc_out[order(loc_out$Year, loc_out$Test, loc_out$City),
                     c("Year", "Test", "City", "State", "lat", "lon",
                       "Conductor", "PlantingDate", "MaturityDate")]
}

write.csv(loc_out, file.path(DATA_DIR, "LocationsTable1.csv"),
          row.names = FALSE, quote = FALSE)
message(sprintf("[HistProcessing] LocationsTable1.csv: %d location rows", nrow(loc_out)))

# ---------------------------------------------------------------------------
# 5. checksTable1.csv — use combined checks when available; else 0-row skeleton
# ---------------------------------------------------------------------------

combined_checks_path <- file.path(HIST_CSV_DIR,
                                  sprintf("combined_%s_checksTable.csv", YEAR))

if (file.exists(combined_checks_path)) {
  message(sprintf("  Reading combined: combined_%s_checksTable.csv", YEAR))
  checks_out <- read.csv(combined_checks_path, stringsAsFactors = FALSE)
  required_chk <- c("Year", "Test", "Strain", "OriginalStrain", "Phenotype", "RM")
  for (col in required_chk) if (!col %in% colnames(checks_out)) checks_out[[col]] <- NA_character_
  checks_out <- checks_out[, required_chk]
  write.csv(checks_out, file.path(DATA_DIR, "checksTable1.csv"),
            row.names = FALSE, quote = FALSE)
  message(sprintf("[HistProcessing] checksTable1.csv: %d rows", nrow(checks_out)))
} else {
  checks_empty <- data.frame(
    Year = character(0), Test = character(0), Strain = character(0),
    OriginalStrain = character(0), Phenotype = character(0), RM = character(0),
    stringsAsFactors = FALSE
  )
  write.csv(checks_empty, file.path(DATA_DIR, "checksTable1.csv"),
            row.names = FALSE, quote = FALSE)
  message("[HistProcessing] checksTable1.csv: 0-row skeleton (no formal checks for historical data)")
}

# ---------------------------------------------------------------------------
# 6. metaTable1.csv — statistical metadata (CV%, LSD, Row spacing, Reps)
#    Read from combined MetaTable if available; skip silently if absent.
# ---------------------------------------------------------------------------

combined_meta_path <- file.path(HIST_CSV_DIR,
                                sprintf("combined_%s_MetaTable.csv", YEAR))

if (file.exists(combined_meta_path)) {
  message(sprintf("  Reading combined: combined_%s_MetaTable.csv", YEAR))
  meta_out <- read.csv(combined_meta_path, stringsAsFactors = FALSE)
  write.csv(meta_out, file.path(DATA_DIR, "metaTable1.csv"),
            row.names = FALSE, quote = FALSE)
  message(sprintf("[HistProcessing] metaTable1.csv: %d rows", nrow(meta_out)))
} else {
  message("[HistProcessing] No combined MetaTable found — metaTable1.csv skipped")
}

# ---------------------------------------------------------------------------
# 7. Optional: remap Group_N test labels to standard NUST codes
#    Uncomment and adjust TEST_MAP for the specific year before running.
# ---------------------------------------------------------------------------
#
# TEST_MAP <- c(
#   "Group_1" = "UT0",
#   "Group_2" = "UTI",
#   "Group_3" = "UTII",
#   "Group_4" = "UTIII",
#   "Group_5" = "UTIV",
#   "Group_6" = "UTVMG"
# )
# remap_files <- c("phenotypesTable0.csv", "strainsTable1.csv",
#                  "parentageTable1.csv", "LocationsTable1.csv",
#                  "strainsTable_From_DataFiles.csv")
# for (fname in remap_files) {
#   fpath <- file.path(DATA_DIR, fname)
#   if (!file.exists(fpath)) next
#   x <- read.csv(fpath, stringsAsFactors = FALSE)
#   if ("Test" %in% colnames(x))
#     x$Test <- ifelse(x$Test %in% names(TEST_MAP), TEST_MAP[x$Test], x$Test)
#   write.csv(x, fpath, row.names = FALSE, quote = FALSE)
#   message(sprintf("  Remapped Test labels in %s", fname))
# }

message("\n[HistProcessing] All intermediate files written to: ", DATA_DIR)
