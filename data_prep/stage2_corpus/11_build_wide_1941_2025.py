"""
11_build_wide_1941_2025.py
==========================
Pivot the unified long-format NUST corpus (1941-2025) to wide format matching
the schema used by NUST_Hist_Data_Scripts/*.R (originally NUST_1993_2020_data_wide.csv).

Wide schema (21 cols, in this exact order):
  Concatenate, Year, Experiment, MG, Location, GermplasmId, Strain,
  Chlorosis, DescriptiveCode, GreenStem, Height, Lodging, Maturity,
  Oil, Protein, SCL, SDS, SeedQuality, SeedSize, Shattering,
  YieldBuA
  (YieldRank dropped 2026-07-21 — redundant order-statistic of YieldBuA, unused
   downstream, transcribed values unreliable; see 10_assemble_corpus.py DROP_PHENOTYPES)

Construction rules:
  - Experiment = Test with hyphens stripped (UT-I -> UTI, PT-III -> PTIII)
  - MG         = TestMG with space stripped (MG I -> MGI, MG 00 -> MG00)
  - Location   = City + "_" + State (e.g., Arlington_WI)
  - GermplasmId = Strain + "_" + MG (pre-1989 has no genotype but the format
                  is uniform; downstream geno joins fail gracefully)
  - Concatenate = Year + Experiment + "_" + Year + Location + Strain

Legacy phenotypes (Oil_IodineNumber, SeedWeight) are NOT in the modern wide
schema; they're preserved in the long CSV but excluded here for compatibility
with the existing 1993-2020 scripts.

Input:
  analysis/data/_shared/nust_1965_2025_combined.csv (long, 3.63M rows, 84 yrs)

Output:
  analysis/data/_shared/NUST_1941_2025_data_wide.csv
"""
import sys
import re
import pandas as pd
import numpy as np
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
LONG_CSV = REPO / "analysis" / "data" / "_shared" / "nust_1965_2025_combined.csv"
OUT_CSV  = REPO / "analysis" / "data" / "_shared" / "NUST_1941_2025_data_wide.csv"

# Modern trait schema (15 cols, in this order)
WIDE_TRAITS = [
    "Chlorosis", "DescriptiveCode", "GreenStem",
    "Height", "Lodging", "Maturity",
    "Oil", "Protein", "SCL", "SDS",
    "SeedQuality", "SeedSize", "Shattering",
    "YieldBuA",
    # YieldRank intentionally excluded: it is a within-cell order-statistic of YieldBuA
    # (redundant), is consumed by no downstream analysis, and its transcribed values are
    # unreliable (2026-07-21 QC). Dropped from the assembled long corpus in
    # 10_assemble_corpus.py (DROP_PHENOTYPES); removed here to keep the wide schema clean.
]

FINAL_COLS = ["Concatenate", "Year", "Experiment", "MG", "Location",
              "GermplasmId", "Strain"] + WIDE_TRAITS + ["LocYear"]


def normalize_experiment(test: str) -> str:
    """UT-I -> UTI, PT-III -> PTIII, UT-00 -> UT00."""
    if pd.isna(test): return ""
    return str(test).replace("-", "").replace(" ", "")


def normalize_mg(test_mg: str) -> str:
    """MG I -> MGI, MG II -> MGII, MG 00 -> MG00, MG IIA -> MGIIA."""
    if pd.isna(test_mg): return ""
    return str(test_mg).replace(" ", "")


def build_location(row) -> str:
    """City_State (e.g., Arlington_WI). If State empty, just City."""
    city = str(row["City"]).strip() if pd.notna(row["City"]) else ""
    state = str(row["State"]).strip() if pd.notna(row["State"]) else ""
    if city and state:
        return f"{city}_{state}"
    return city


def main():
    if not LONG_CSV.exists():
        sys.exit(f"ERROR: missing {LONG_CSV}")

    print(f"Loading {LONG_CSV.name}...", flush=True)
    df = pd.read_csv(LONG_CSV, low_memory=False)
    print(f"  long-format rows: {len(df):,}")
    print(f"  year range: {df['Year'].min()}-{df['Year'].max()}")
    print(f"  distinct phenotypes: {df['Phenotype'].nunique()}")

    # Alias the modern "IDC" label (iron-deficiency chlorosis; used only for the
    # 2020 queryportal source) to the historical 1989-2019 "Chlorosis" label so
    # both fold into a single Chlorosis trait column. Same 1-5 visual IDC scale.
    n_idc = int((df["Phenotype"] == "IDC").sum())
    if n_idc:
        df["Phenotype"] = df["Phenotype"].replace({"IDC": "Chlorosis"})
        print(f"  aliased {n_idc:,} 'IDC' rows -> 'Chlorosis'")

    # Filter to modern wide-format traits only (drop legacy phenos)
    df = df[df["Phenotype"].isin(WIDE_TRAITS)].copy()
    print(f"  after filtering to modern traits: {len(df):,} rows")

    # Drop Mean rows (modern per-location wide format only)
    df = df[(df["City"].notna()) & (df["City"] != "Mean") & (df["City"] != "")]
    print(f"  after dropping Mean rows: {len(df):,} rows")

    # Normalize columns
    df["Experiment"] = df["Test"].apply(normalize_experiment)
    df["MG"]         = df["TestMG"].apply(normalize_mg)
    df["Location"]   = df.apply(build_location, axis=1)

    # Pivot phenotypes to wide
    print("Pivoting to wide format (this may take a minute on 3M rows)...", flush=True)
    keys = ["Year", "Experiment", "MG", "Location", "Strain"]
    wide = df.pivot_table(
        index=keys,
        columns="Phenotype",
        values="Value_num",
        aggfunc="first",  # take first if accidental duplicates
    ).reset_index()
    print(f"  wide rows: {len(wide):,}")

    # Ensure all 15 trait columns exist (NA for absent ones)
    for t in WIDE_TRAITS:
        if t not in wide.columns:
            wide[t] = np.nan

    # Add GermplasmId and Concatenate
    wide["GermplasmId"] = wide["Strain"].astype(str) + "_" + wide["MG"].astype(str)
    wide["Concatenate"] = (wide["Year"].astype(str) + wide["Experiment"].astype(str)
                           + "_" + wide["Year"].astype(str) + wide["Location"].astype(str)
                           + wide["Strain"].astype(str))
    # LocYear used by NUST_Trial_Connectivity_Methods.R and NUST_GxE_BLUEs_WithEnvModel.R
    wide["LocYear"] = wide["Location"].astype(str) + "_" + wide["Year"].astype(str)

    # Reorder to match canonical column order
    wide = wide[FINAL_COLS]

    # Protein/Oil moisture-basis correction (formerly the standalone post-patch
    # 35_apply_protein_oil_moisture_fix.py; baked in here so it survives every rebuild).
    # Per Wartha et al. 2025: reporting switched from dry-weight to a 13% moisture
    # basis after 2005, and the master DB (1989+) standardized historical values to
    # 13% mb. Our locally-extracted years (1941-1988 + the 1990 PDF pilot) are still
    # on a dry basis, so scale Protein/Oil by 0.87 (dry -> 13% mb) for those years to
    # put the whole panel on one basis. Yield is unaffected (13% mb since 1941).
    DRY_TO_13MC = 0.87
    # 2026-07-12: 1989/1991/1992 Protein/Oil now come from the from-source F4U (report PDFs),
    # which are DRY basis like the other locally-extracted years — so they join the ×0.87 set.
    DRY_BASIS_YEARS = list(range(1941, 1993))   # 1941-1992 (all locally-extracted, dry basis)
    mask = wide["Year"].isin(DRY_BASIS_YEARS)
    for trait in ("Protein", "Oil"):
        if trait in wide.columns:
            n = int((mask & wide[trait].notna()).sum())
            wide.loc[mask, trait] = wide.loc[mask, trait] * DRY_TO_13MC
            print(f"  moisture-basis ×{DRY_TO_13MC} applied to {trait}: {n:,} cells (1941-1992)")

    # Write
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV.name}: {len(wide):,} rows × {len(wide.columns)} cols")

    # Per-year row count sanity check
    print("\nRows per decade:")
    decade = (wide["Year"] // 10) * 10
    print(decade.value_counts().sort_index().to_string())

    # Per-trait coverage
    print("\nPer-trait non-NA row counts:")
    for t in WIDE_TRAITS:
        nn = wide[t].notna().sum()
        print(f"  {t:<18} {nn:>9,}")

if __name__ == "__main__":
    main()
