# nust_config.R
# Year-specific configuration for the NUST data processing pipeline.
# Returns a list of all year-dependent settings, with test lists auto-detected
# from CSV files present in the data directory.
#
# Usage:
#   cfg <- nust_config(
#     year    = "2025",
#     data_dir = "C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/"
#   )

nust_config <- function(year, data_dir) {

  files <- list.files(data_dir, pattern = "\\.csv$")

  # Auto-detect agronomic test files: UT00.csv, UTI.csv, PTI.csv, PTIIA.csv, etc.
  Tests1 <- sort(gsub("\\.csv$", "",
    grep("^(UT|PT)[0-9A-Z]+\\.csv$", files, value = TRUE, perl = TRUE)
  ))

  # Auto-detect trait-modified test files: UT0TM.csv, UTITM.csv, etc.
  Tests2 <- sort(gsub("\\.csv$", "",
    grep("^(UT)[0-9A-Z]+TM\\.csv$", files, value = TRUE, perl = TRUE)
  ))

  # Auto-detect seed traits files: "Seed Traits UT0TM.csv", etc.
  Tests3 <- sort(gsub("\\.csv$", "",
    grep("^Seed Traits ", files, value = TRUE)
  ))

  # Auto-detect year-specific reference files
  cal_matches  <- grep(paste0("LookUp_", year), files, value = TRUE)
  cal_file     <- if (length(cal_matches) > 0) cal_matches[1] else stop(paste("Calendar lookup file for", year, "not found in", data_dir))

  chk_matches  <- grep(year, grep("(?i)(check|list)", files, value = TRUE, perl = TRUE), value = TRUE)
  chk_file     <- if (length(chk_matches) > 0) chk_matches[1] else stop(paste("Checks list file for", year, "not found in", data_dir))

  loc_matches  <- grep(year, grep("Locations.*PlotInfo|PlotInfo.*Locations", files, value = TRUE, perl = TRUE), value = TRUE)
  loc_file     <- if (length(loc_matches) > 0) loc_matches[1] else stop(paste("Locations PlotInfo file for", year, "not found in", data_dir))

  message(sprintf(
    "[nust_config] Year: %s | Tests1: %d | Tests2: %d | Tests3: %d | cal: %s | chk: %s | loc: %s",
    year, length(Tests1), length(Tests2), length(Tests3), cal_file, chk_file, loc_file
  ))

  list(
    year     = year,
    data_dir = data_dir,
    Tests1   = Tests1,
    Tests2   = Tests2,
    Tests3   = Tests3,
    cal_file = cal_file,
    chk_file = chk_file,
    loc_file = loc_file
  )
}
