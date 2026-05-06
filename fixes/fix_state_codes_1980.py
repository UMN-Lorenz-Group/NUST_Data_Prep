"""
fix_state_codes_1980.py
Fix wrong State codes in:
  1. combined_1980_phenotypesTable_approved.csv
  2. combined_1980_locationsTable.csv

Corrections (all are extraction errors — the city exists only in the correct state):
  Ashland  / UT-III  KS -> WI   (Ashland, WI; KS is OCR error)
  Greenfield / UT-III IL -> IN  (Greenfield, IN; IL is OCR error)
  Harrow   / UT-II   OH -> ONT  (Harrow, Ontario; OH is OCR error)
  Sullivan / UT-III  IL -> IN   (Sullivan, IN; IL is OCR error)
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import shutil
import pandas as pd
from pathlib import Path

SRC = Path(__file__).parent.parent / "output_1980"

PHENO_CSV = SRC / "validated" / "combined_1980_phenotypesTable_approved.csv"
LOCS_CSV  = SRC / "combined_1980_locationsTable.csv"

FIXES = [
    # (City, wrong_state, right_state, test)
    ("Ashland",    "KS",  "WI",  "UT-III"),
    ("Greenfield", "IL",  "IN",  "UT-III"),
    ("Harrow",     "OH",  "ONT", "UT-II"),
    ("Sullivan",   "IL",  "IN",  "UT-III"),
]


def patch_state(df, city, wrong, right, test):
    mask = (df["City"] == city) & (df["State"] == wrong)
    if test:
        mask = mask & (df["Test"] == test)
    n = mask.sum()
    if n:
        df.loc[mask, "State"] = right
        print(f"  {city}: {n} rows {wrong} -> {right} (Test={test})")
    else:
        print(f"  {city}: no rows matched State={wrong}, Test={test}")
    return df


def main():
    # --- Phenotypes ---
    pheno = pd.read_csv(PHENO_CSV, dtype=str, keep_default_na=False)
    print(f"Phenotypes: {len(pheno)} rows")
    shutil.copy(PHENO_CSV, PHENO_CSV.with_suffix(".csv.bak"))
    for city, wrong, right, test in FIXES:
        pheno = patch_state(pheno, city, wrong, right, test)
    pheno.to_csv(PHENO_CSV, index=False)
    print(f"Phenotypes written: {len(pheno)} rows\n")

    # --- Locations ---
    locs = pd.read_csv(LOCS_CSV, dtype=str, keep_default_na=False)
    print(f"Locations: {len(locs)} rows")
    shutil.copy(LOCS_CSV, LOCS_CSV.with_suffix(".csv.bak"))
    for city, wrong, right, test in FIXES:
        locs = patch_state(locs, city, wrong, right, test)
    locs.to_csv(LOCS_CSV, index=False)
    print(f"Locations written: {len(locs)} rows")


if __name__ == "__main__":
    main()
