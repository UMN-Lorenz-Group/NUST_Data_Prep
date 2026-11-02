"""
35_apply_protein_oil_moisture_fix.py
====================================
DEPRECATED (2026-06-25): this correction is now baked into
`11_build_wide_1941_2025.py` (applied on every wide rebuild), so it survives
corpus rebuilds. Do NOT run this standalone on a freshly built wide file — it
would double-apply the ×0.87 factor. Kept only for provenance / the diagnostic.

Protein / Oil moisture-basis correction for the 1941–2025 wide CSV.

Rationale
---------
Per Wartha et al. 2025 (Crop Sci, p. 6):
  "Seed protein and oil percent were measured using near-infrared
  reflectance spectroscopy and expressed on a 130 g kg⁻¹ moisture basis.
  The reporting standards for seed protein and oil composition changed
  after 2005 from composition values being reported on a dry weight basis
  to a 13% moisture basis.  Seed composition data prior to and of 2005
  were all standardized to a 13% moisture basis in the dataset."

The published USDA UTN reports kept dry-basis reporting through 2005.
Our wide CSV inherited mixed conventions per ingestion path:

  Years sourced from the master DB → already on 13% moisture basis
    1989, 1991, 1992, 1993+

  Years sourced from local PDF / XLSX extraction → still on dry basis
    1941–1988, 1990

This script applies the dry → 13% moisture conversion factor (× 0.87) to
Protein and Oil values for the latter set so the entire panel is on a
consistent 13%-moisture basis (matching Wartha 2025 and Rincker 2014).

A backup of the un-corrected wide CSV is saved alongside, and a per-year
diagnostic of the before/after annual mean is logged.
"""
import shutil
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
WIDE = REPO / "analysis" / "data" / "_shared" / "NUST_1941_2025_data_wide.csv"
BACKUP = WIDE.with_suffix(".pre_moisture_fix.csv")
DIAGNOSTIC = REPO / "analysis" / "data" / "_shared" / "protein_oil_moisture_fix_diagnostic.csv"
DRY_TO_13MC = 0.87
DRY_BASIS_YEARS = list(range(1941, 1989)) + [1990]


def annual_means(df, label):
    ut = df[df["Experiment"].astype(str).str.startswith("UT", na=False)]
    rows = []
    for trait in ("Protein", "Oil"):
        if trait not in df.columns:
            continue
        v = ut[(ut[trait].notna())][["Year", trait]]
        if trait == "Protein":
            v = v[(v[trait] >= 20) & (v[trait] <= 55)]
        else:
            v = v[(v[trait] >= 10) & (v[trait] <= 28)]
        yr = v.groupby("Year")[trait].agg(["mean", "size"])
        for yr_val, row in yr.iterrows():
            rows.append({"label": label, "Year": int(yr_val),
                          "trait": trait, "mean": round(row["mean"], 3),
                          "n": int(row["size"])})
    return pd.DataFrame(rows)


def main():
    if not WIDE.exists():
        sys.exit(f"ERROR: {WIDE} not found")
    print(f"Loading {WIDE.name} ...", flush=True)
    df = pd.read_csv(WIDE, low_memory=False)
    print(f"  rows: {len(df):,}")

    # Snapshot pre-fix annual means
    pre = annual_means(df, "pre_fix")

    # Backup
    if not BACKUP.exists():
        shutil.copy(WIDE, BACKUP)
        print(f"  backup: {BACKUP.name}")
    else:
        print(f"  backup already present: {BACKUP.name}  (NOT overwriting)")

    # Apply conversion
    mask = df["Year"].isin(DRY_BASIS_YEARS)
    n_rows_affected = int(mask.sum())
    print(f"\nApplying ×{DRY_TO_13MC} to Protein and Oil for Year ∈ {{1941..1988, 1990}}")
    print(f"  affected rows: {n_rows_affected:,}  ({100*n_rows_affected/len(df):.1f}% of corpus)")

    n_prot_changed = int((mask & df["Protein"].notna()).sum())
    n_oil_changed  = int((mask & df["Oil"].notna()).sum())
    df.loc[mask, "Protein"] = df.loc[mask, "Protein"] * DRY_TO_13MC
    df.loc[mask, "Oil"]     = df.loc[mask, "Oil"]     * DRY_TO_13MC
    print(f"  Protein cells changed: {n_prot_changed:,}")
    print(f"  Oil     cells changed: {n_oil_changed:,}")

    # Save corrected wide CSV
    df.to_csv(WIDE, index=False)
    print(f"\nWrote corrected wide CSV: {WIDE.name}")

    # Post-fix annual means
    post = annual_means(df, "post_fix")
    diag = (pre.merge(post, on=["Year", "trait"], suffixes=("_pre", "_post"))
              .drop(columns=["label_pre", "label_post"])
              .sort_values(["trait", "Year"]))
    diag["delta"] = (diag["mean_post"] - diag["mean_pre"]).round(3)
    diag.to_csv(DIAGNOSTIC, index=False)

    # Print before/after for the relevant window
    print("\nProtein annual means 1985-2000 (before → after):")
    for _, r in diag[(diag["trait"] == "Protein") &
                     (diag["Year"] >= 1985) & (diag["Year"] <= 2000)].iterrows():
        flag = " *" if r["Year"] in DRY_BASIS_YEARS else ""
        print(f"  {int(r['Year'])}: {r['mean_pre']:.2f} → {r['mean_post']:.2f}  (Δ {r['delta']:+.2f}){flag}")

    print("\nOil annual means 1985-2000 (before → after):")
    for _, r in diag[(diag["trait"] == "Oil") &
                     (diag["Year"] >= 1985) & (diag["Year"] <= 2000)].iterrows():
        flag = " *" if r["Year"] in DRY_BASIS_YEARS else ""
        print(f"  {int(r['Year'])}: {r['mean_pre']:.2f} → {r['mean_post']:.2f}  (Δ {r['delta']:+.2f}){flag}")

    print(f"\nDiagnostic: {DIAGNOSTIC.name}")


if __name__ == "__main__":
    main()
