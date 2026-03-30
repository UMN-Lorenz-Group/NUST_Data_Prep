# nust_utils.R
# Shared utility functions for the NUST data processing pipeline.
# Source this file at the top of each processing script:
#   source("C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/nust_utils.R")

# ---------------------------------------------------------------------------
# clean_strain_encoding
# Converts non-ASCII characters to spaces and trims whitespace.
# Replaces the locally-defined `clean_strain` function in multiple scripts.
# ---------------------------------------------------------------------------
clean_strain_encoding <- function(x) {
  x <- iconv(x, from = "UTF-8", to = "ASCII", sub = " ")
  x <- gsub("[[:space:]]+", " ", x)
  x <- trimws(x)
  return(x)
}

# ---------------------------------------------------------------------------
# clean_strain_annotations
# Removes parenthetical annotation codes (GT, SCN, OLE, I*, V, 0*, IV)
# and all spaces from strain name strings.
# Replaces the repeated 10-step gsub chain used across multiple scripts.
# ---------------------------------------------------------------------------
clean_strain_annotations <- function(x) {
  x <- gsub("\\(GT SCN\\)|\\(GT\\)|\\(SCN\\)|\\([OLE]\\)|\\([I]*\\)|\\([V]\\)|\\([0]*\\)|\\(IV\\)", "", x)
  x <- gsub(" ", "", x)
  return(x)
}

# ---------------------------------------------------------------------------
# standardize_location_names
# Maps known misspelled or run-together location name variants to their
# canonical form. Returns the input vector with variants replaced.
# Replaces the repeated 60-line if/else block used across multiple scripts.
# ---------------------------------------------------------------------------
standardize_location_names <- function(x) {
  loc_map <- c(
    "Cooik"                 = "Cook",
    "SaginawCounty"         = "Saginaw",
    "Saginaw Co."           = "Saginaw",
    "Saginaw."              = "Saginaw",
    "Costesfield"           = "Cotesfield",
    "Ubana"                 = "Urbana",
    "UrbanaIL"              = "Urbana",
    "EastLansing"           = "East Lansing",
    "ElmCreek"              = "Elm Creek",
    "Southerland"           = "Sutherland",
    "WestLafayette"         = "West Lafayette",
    "LafayetteIN"           = "West Lafayette",
    "Lafayette"             = "West Lafayette",
    "PortagevilleLoam"      = "Portageville-Loam",
    "Holderage"             = "Holdrege",
    "RoseMount"             = "Rosemount",
    "ThiefRiver Falls"      = "Thief River Falls",
    "Thief RiverFalls"      = "Thief River Falls",
    "ThiefRiverFallsMN"     = "Thief River Falls",
    "ThiefRiverFalls"       = "Thief River Falls",
    "Carnan"                = "Carman",
    "Porageville-Clay"      = "Portageville-Clay",
    "PortagevilleClay"      = "Portageville-Clay",
    "St.Pauls"              = "St. Pauls",
    "StHyacinthe"           = "St. Hyacinthe",
    "SaintHyacinthe"        = "St. Hyacinthe",
    "St.Hyacinthe"          = "St. Hyacinthe",
    "Saint Hyacinthe"       = "St. Hyacinthe",
    "StMathieudeBeloeil"    = "St. Mathieu de Beloeil",
    "St Mathieu de Beloeil" = "St. Mathieu de Beloeil",
    "St Mathieude Beloeil"  = "St. Mathieu de Beloeil",
    "St.MathieudeBeloeil"   = "St. Mathieu de Beloeil",
    "SaintMathieudeBeloeil" = "St. Mathieu de Beloeil",
    "StMarys"               = "St. Marys",
    "St.Marys"              = "St. Marys",
    "Steven'sCreek"         = "Stevens Creek",
    "StevensCreek"          = "Stevens Creek",
    "RockPort"              = "Rock Port",
    "RockPortMO"            = "Rock Port",
    "ManhattanLoc A"        = "Manhattan",
    "ManhattanLocA"         = "Manhattan",
    "Loc B"                 = "ManhattanB",
    "LocB"                  = "ManhattanB",
    "CrookstonMN"           = "Crookston",
    "NoveltyMO"             = "Novelty",
    "WanatahIN"             = "Wanatah",
    "AmesIA"                = "Ames",
    "ButlervilleIN"         = "Butlerville"
  )
  mapped <- loc_map[x]
  x[!is.na(mapped)] <- mapped[!is.na(mapped)]
  return(x)
}
