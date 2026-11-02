"""
apply_protein_composite_fold.py
===============================
P1 protein-gap fill (mirror of apply_oil_composite_fold.py): fold the per-LOCATION composite
Protein from nust_composition_composite_1947_1958.csv into the early-era UT cells that have
yield but ZERO per-location Protein (the F4U placeholder grid was never filled -- the annual
reports gave only a location composite). Folds as new Strain="Composite" rows (one per
location) so they populate the per-location Protein distribution in 11_build_wide.

Gap definition: UT cell (MG, Year) with >=5 non-null YieldBuA rows and 0 non-null Protein rows
in the combined corpus (computed from the corpus, not the wide -> idempotent).

Basis: the composite file is 13% mb; 11_build_wide re-applies the x0.87 dry->13%mb correction
for <=1992, so we DRY-normalize (/0.87) before storing to avoid a double correction (same rule
apply_oil_composite_fold uses for its composite_1947_1958 rows).

Idempotent: strips prior fold rows (Source ProteinComposite_1947_1958) before re-adding, and
dedups only vs NON-NULL protein.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/apply_protein_composite_fold.py
Then: rebuild 11 (wide), regenerate 32 (boxplots).
"""
import os
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(os.environ.get("NUST_REPO", "C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep"))
SH = REPO / "analysis" / "data" / "_shared"
STAGE2 = REPO / "data_prep" / "stage2_corpus"
SRC = STAGE2 / "nust_composition_composite_1947_1958.csv"
FOLD_SOURCE = "ProteinComposite_1947_1958"
CORPUS_COLS = ["Year", "TestType", "TestMG", "Test", "Variant", "City", "State",
               "Strain", "Strain_raw", "Phenotype", "Value_num", "Units", "IsCheck", "Source"]


def gap_cells(comb):
    d = comb[comb.TestType.astype(str).eq("UT")
             & comb.TestMG.isin(["00", "0", "I", "II", "III", "IV"])].copy()
    d["v"] = pd.to_numeric(d.Value_num, errors="coerce")
    yld = d[d.Phenotype.eq("YieldBuA")].groupby(["TestMG", "Year"]).v.apply(lambda s: s.notna().sum())
    pro = d[d.Phenotype.eq("Protein")].groupby(["TestMG", "Year"]).v.apply(lambda s: s.notna().sum())
    return {(mg, int(yr)) for (mg, yr), ny in yld.items()
            if ny >= 5 and pro.get((mg, yr), 0) == 0}


def main():
    comb = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
    comb = comb[comb.Source != FOLD_SOURCE]                # idempotent strip
    gaps = gap_cells(comb)
    print(f"protein gap cells (yield>=5, protein=0): {len(gaps)}")

    c = pd.read_csv(SRC)
    c = c[(c.Phenotype == "Protein") & (c.Aggregation == "location_composite") & (c.City.notna())]
    c = c[[(str(m), int(y)) in gaps for m, y in zip(c.TestMG, c.Year)]].copy()
    c["Value_num"] = pd.to_numeric(c.Value_num, errors="coerce") / 0.87   # 13%mb -> DRY
    c = c[c.Value_num.between(28, 52)]                     # physical protein guard (dry)
    c["TestType"] = "UT"
    c["Test"] = "UT-" + c.TestMG.astype(str)
    c["Variant"] = "Conventional"
    c["Strain"] = "Composite"
    c["Strain_raw"] = "Composite"
    c["Phenotype"] = "Protein"
    c["Units"] = "%"
    c["IsCheck"] = "0"
    c["Source"] = FOLD_SOURCE
    c["Year"] = c.Year.astype(str)
    fold = c[CORPUS_COLS]

    co = comb[comb.Phenotype == "Protein"].copy()
    co["v"] = pd.to_numeric(co.Value_num, errors="coerce")
    nonnull = set(zip(co[co.v.notna()].Year, co[co.v.notna()].Test, co[co.v.notna()].City.fillna("")))
    fold = fold[[(r.Year, r.Test, str(r.City) if pd.notna(r.City) else "") not in nonnull
                 for r in fold.itertuples()]]
    print(f"fold rows (vs non-null protein): {len(fold)}  | cells: {len(set(zip(fold.TestMG, fold.Year)))}")

    out = pd.concat([comb, fold[comb.columns]], ignore_index=True)
    for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
        out.to_csv(SH / name, index=False)
    out["y"] = pd.to_numeric(out.Year, errors="coerce")
    for lo, hi, fn in [(1941, 1984, "nust_1941-1984_combined.csv"),
                       (1985, 2004, "nust_1985-2004_combined.csv"),
                       (2005, 2025, "nust_2005-2025_combined.csv")]:
        out[(out.y >= lo) & (out.y <= hi)].drop(columns="y").to_csv(SH / fn, index=False)
    print(f"combined: {len(comb):,} -> {len(out):,} rows; alias + era splits written")
    print("Next: rebuild 11 (wide), then 32 (boxplots).")


if __name__ == "__main__":
    main()
