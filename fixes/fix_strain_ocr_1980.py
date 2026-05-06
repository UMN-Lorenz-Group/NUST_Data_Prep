"""
fix_strain_ocr_1980.py
======================
Patch OCR-garbled strain names in the 1980 combined pipeline outputs.

Each entry renames a ghost strain created by OCR misread into the canonical
name, then deduplicates so traits under both rows are merged (first-wins).

Issues covered
--------------
Pre-QC renames (decimal prefix / dropped prefix / Roman numeral):
  "1.27"           ->  "L27"
  "1.77-8079"      ->  "L77-8079"
  "57073"          ->  "U57073"
  "59218"          ->  "U59218"
  "Corsoy 79 (11)" ->  "Corsoy 79 (II)"
  "Pella (111)"    ->  "Pella (III)"

ISSUE-5  — PT-I/II/III OCR errors:
  "A73D29"        ->  "A75D29"
  "Cnome"         ->  "Gnome"
  "H277-878"      ->  "HC77-878"
  "A790134034"    ->  "A79-134034"
  "L77-709"       ->  "L78-709"

ISSUE-11 — UT-0: extra space in "M72- 107"
  "M72- 107"      ->  "M72-107"

ISSUE-12 — UT-I only: "Hardin" ghost row (test-scoped rename)
  "Hardin" (Test=UT-I)  ->  "Hardin (I)"
  "Hardin (1)"          ->  "Hardin (I)"   (digit 1 vs letter I)

ISSUE-13 — UT-II: "(TII)" OCR of "(III)"
  "Pella (TII)"   ->  "Pella (III)"

ISSUE-14 — UT-II: doubled "20" in strain number
  "U2020325"      ->  "U20325"

ISSUE-15 — UT-II: extra "6"
  "U566355"       ->  "U56355"

ISSUE-16 — UT-III: digit transposition in "BSR 302"
  "BSR 320"       ->  "BSR 302"

ISSUE-17 — UT-IV: "K1033" misread as "K1035"
  "K1035"         ->  "K1033"

ISSUE-18 — UT-IV: three OCR ghost forms of "Ky75-146-74"
  "KG75-146-74"   ->  "Ky75-146-74"
  "K675-146-74"   ->  "Ky75-146-74"
  "K775-146-74"   ->  "Ky75-146-74"

ISSUE-19 — UT-IV: "HC" OCR'd as "H" in "HC76-3840"
  "H76-3840"      ->  "HC76-3840"

Files patched (relative to project root, i.e. run from NUST_Data_Prep/):
  output_1980/combined_1980_phenotypesTable.csv
  output_1980/combined_1980_strainsTable.csv
  output_1980/combined_1980_parentageTable.csv   (if garbled names appear)

Re-run validate_nust_hist.py and the R bridge pipeline after this patch.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pathlib import Path

OUT = Path("output_1980")

# ---------------------------------------------------------------------------
# Global renames — apply across all tests
# Each ghost name listed here is unique enough that a global replace is safe.
# ---------------------------------------------------------------------------
RENAMES = {
    # --- Pre-QC renames (decimal prefix / dropped prefix) ---
    "1.27":             "L27",
    "1.77-8079":        "L77-8079",
    "57073":            "U57073",
    "59218":            "U59218",
    "Corsoy 79 (11)":   "Corsoy 79 (II)",
    "Pella (111)":      "Pella (III)",

    # --- ISSUE-5 ---
    "A73D29":           "A75D29",
    "Cnome":            "Gnome",
    "H277-878":         "HC77-878",
    "A790134034":       "A79-134034",
    "L77-709":          "L78-709",

    # --- ISSUE-11 ---
    "M72- 107":         "M72-107",

    # --- ISSUE-12 (digit-1 form only; bare "Hardin" handled test-scoped below) ---
    "Hardin (1)":       "Hardin (I)",

    # --- ISSUE-13 ---
    "Pella (TII)":      "Pella (III)",

    # --- ISSUE-14 ---
    "U2020325":         "U20325",

    # --- ISSUE-15 ---
    "U566355":          "U56355",

    # --- ISSUE-16 ---
    "BSR 320":          "BSR 302",

    # --- ISSUE-17 ---
    "K1035":            "K1033",

    # --- ISSUE-18 ---
    "KG75-146-74":      "Ky75-146-74",
    "K675-146-74":      "Ky75-146-74",
    "K775-146-74":      "Ky75-146-74",

    # --- ISSUE-19 ---
    "H76-3840":         "HC76-3840",
}

# ---------------------------------------------------------------------------
# Test-scoped renames — only apply within a specific Test value
# Format: (ghost_name, canonical_name, test_value)
# ---------------------------------------------------------------------------
SCOPED_RENAMES = [
    # ISSUE-12: bare "Hardin" ghost row only exists in UT-I
    ("Hardin", "Hardin (I)", "UT-I"),
]

DEDUP_COLS = ["Strain", "Year", "Test", "City", "Phenotype"]


def apply_renames(df: pd.DataFrame, col: str = "Strain") -> pd.DataFrame:
    """Apply global and scoped renames to column `col` in-place."""
    # Global
    for bad, good in RENAMES.items():
        mask = df[col] == bad
        if mask.any():
            print(f"  global  '{bad}' -> '{good}'  ({mask.sum()} rows)")
        df[col] = df[col].replace({bad: good})

    # Scoped
    for bad, good, test_val in SCOPED_RENAMES:
        if "Test" not in df.columns:
            continue
        mask = (df[col] == bad) & (df["Test"] == test_val)
        if mask.any():
            print(f"  scoped  '{bad}' -> '{good}'  [Test={test_val}]  ({mask.sum()} rows)")
        df.loc[mask, col] = good

    return df


# ---------------------------------------------------------------------------
# phenotypesTable
# ---------------------------------------------------------------------------
pt_path = OUT / "combined_1980_phenotypesTable.csv"
pt = pd.read_csv(pt_path)
rows_before = len(pt)
print(f"\n=== phenotypesTable ({rows_before} rows) ===")
apply_renames(pt)
pt = pt.drop_duplicates(subset=DEDUP_COLS, keep="first")
pt.to_csv(pt_path, index=False)
print(f"  {rows_before} -> {len(pt)} rows after all renames + dedup")

# ---------------------------------------------------------------------------
# strainsTable
# ---------------------------------------------------------------------------
st_path = OUT / "combined_1980_strainsTable.csv"
if st_path.exists():
    st = pd.read_csv(st_path)
    rows_before = len(st)
    print(f"\n=== strainsTable ({rows_before} rows) ===")
    apply_renames(st)
    if "OriginalStrain" in st.columns:
        apply_renames(st, col="OriginalStrain")
    st = st.drop_duplicates(subset=["Strain", "Year", "Test"], keep="first")
    st.to_csv(st_path, index=False)
    print(f"  {rows_before} -> {len(st)} rows after rename + dedup")

# ---------------------------------------------------------------------------
# parentageTable
# ---------------------------------------------------------------------------
par_path = OUT / "combined_1980_parentageTable.csv"
if par_path.exists():
    par = pd.read_csv(par_path)
    any_found = any((par["Strain"] == bad).sum() for bad in RENAMES) or any(
        ((par["Strain"] == bad) & (par.get("Test", pd.Series()) == t)).any()
        for bad, _, t in SCOPED_RENAMES
    )
    if any_found:
        rows_before = len(par)
        print(f"\n=== parentageTable ({rows_before} rows) ===")
        apply_renames(par)
        par = par.drop_duplicates(subset=["Strain", "Year", "Test"], keep="first")
        par.to_csv(par_path, index=False)
        print(f"  {rows_before} -> {len(par)} rows after rename + dedup")
    else:
        print("\nparentageTable: no garbled names found, no change")

print("\nPatch complete. Re-run:")
print("  python scripts/validate_nust_hist.py --input output_1980/combined_1980_phenotypesTable.csv --out_dir output_1980/validated/")
print("  Rscript run_nust_historical_pipeline.R")
