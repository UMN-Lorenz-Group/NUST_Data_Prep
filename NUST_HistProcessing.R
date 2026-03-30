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
# ---------------------------------------------------------------------------

read_hist <- function(suffix) {
  f <- grep(suffix, list.files(HIST_CSV_DIR, full.names = TRUE), value = TRUE)
  if (!length(f)) stop(paste("[HistProcessing] No file matching", suffix, "in", HIST_CSV_DIR))
  message(sprintf("  Reading %s", basename(f[1])))
  read.csv(f[1], stringsAsFactors = FALSE)
}

pheno_long  <- read_hist("_phenotypes\\.csv$")
strains_raw <- read_hist("_strains\\.csv$")
parent_raw  <- read_hist("_parentage\\.csv$")
desc_raw    <- read_hist("_descriptive\\.csv$")

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
  "OIL (%)"                 = "Oil"
)
AG_COLS <- unname(PHENO_MAP)

FA_COLS <- c("PalmiticAcid", "StearicAcid", "OleicAcid", "LinoleicAcid",
             "LinolenicAcid", "Sucrose", "Raffinose", "Stachyose", "SugarTotal")

# Filter to per-location rows and known agronomic phenotypes
p <- pheno_long[pheno_long$City != "Mean" & pheno_long$City != "", ]
p <- p[p$Phenotype %in% names(PHENO_MAP), ]
p$PhenoCol <- PHENO_MAP[p$Phenotype]

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

s <- merge(
  strains_raw[, c("Strain", "Test", "Year")],
  desc_raw[, c("Strain", "DescriptiveCode", "Test", "Year")],
  by     = c("Strain", "Test", "Year"),
  all.x  = TRUE
)

s$OriginalStrain   <- s$Strain
s$Strain           <- clean_strain_annotations(s$Strain)
s$Descriptive.Code <- ifelse(is.na(s$DescriptiveCode), "", s$DescriptiveCode)
s$Unique.traits    <- ""     # not available in historical source
s$Gen.Comp.        <- ""     # not available in historical source
s$Check            <- 0L    # no formal checks list for historical data

strains_out <- unique(s[, c("Year", "Test", "Strain", "OriginalStrain",
                              "Descriptive.Code", "Unique.traits", "Gen.Comp.", "Check")])

write.csv(strains_out, file.path(DATA_DIR, "strainsTable1.csv"),
          row.names = FALSE, quote = FALSE)
# NUST_CheckFinalFiles.R also reads strainsTable_From_DataFiles.csv
write.csv(strains_out, file.path(DATA_DIR, "strainsTable_From_DataFiles.csv"),
          row.names = FALSE, quote = FALSE)
message(sprintf("[HistProcessing] strainsTable1.csv: %d rows", nrow(strains_out)))

# ---------------------------------------------------------------------------
# 3. parentageTable1.csv — single Parentage string → Female; Male = NA
# ---------------------------------------------------------------------------

parent_out <- data.frame(
  Year   = parent_raw$Year,
  Test   = parent_raw$Test,
  Strain = clean_strain_annotations(parent_raw$Strain),
  Female = parent_raw$Parentage,   # full cross string (e.g. "Amsoy x Wayne")
  Male   = NA_character_,
  stringsAsFactors = FALSE
)
parent_out <- unique(parent_out[!is.na(parent_out$Strain) & parent_out$Strain != "", ])

write.csv(parent_out, file.path(DATA_DIR, "parentageTable1.csv"),
          row.names = FALSE, quote = FALSE)
message(sprintf("[HistProcessing] parentageTable1.csv: %d rows", nrow(parent_out)))

# ---------------------------------------------------------------------------
# 4. LocationsTable1.csv — unique City/State per Year/Test; NA for unavailable fields
# ---------------------------------------------------------------------------

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

write.csv(loc_out, file.path(DATA_DIR, "LocationsTable1.csv"),
          row.names = FALSE, quote = FALSE)
message(sprintf("[HistProcessing] LocationsTable1.csv: %d location rows", nrow(loc_out)))

# ---------------------------------------------------------------------------
# 5. checksTable1.csv — 0-row skeleton with correct column schema
# ---------------------------------------------------------------------------

checks_empty <- data.frame(
  Year           = character(0),
  Test           = character(0),
  Strain         = character(0),
  OriginalStrain = character(0),
  Phenotype      = character(0),
  RM             = character(0),
  stringsAsFactors = FALSE
)
write.csv(checks_empty, file.path(DATA_DIR, "checksTable1.csv"),
          row.names = FALSE, quote = FALSE)
message("[HistProcessing] checksTable1.csv: 0-row skeleton (no formal checks for historical data)")

# ---------------------------------------------------------------------------
# 6. Optional: remap Group_N test labels to standard NUST codes
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
