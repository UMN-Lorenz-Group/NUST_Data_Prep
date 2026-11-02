"""
apply_oil_composite_fold.py
===========================
P1 oil-gap fill: inject location-level composite Oil for the early-era (1941-1956) UT
cells that have yield but ZERO per-location Oil in the wide (the F4U extraction created
empty Oil placeholders but the annual reports gave only a location composite, never
per-strain oil). Composite values fold as new `Strain="Composite"` rows (one per
location), so they populate the per-location Oil distribution in 11_build_wide without
fabricating per-strain variation.

Gap definition (matches the boxplot audit): UT cell (MG, Year) with >=5 non-null
YieldBuA rows and 0 non-null Oil rows in NUST_1941_2025_data_wide.csv.

Sources (both DRY basis in file; 11_build_wide applies the ×0.87 dry->13%mb correction
for <=1992, so we store DRY):
  * oil_composite_t65.csv                     Aggregation=location_composite (already DRY)
  * nust_composition_composite_1947_1958.csv  Aggregation=location_composite; this file is
                                              13%mb, so divide by 0.87 to DRY-normalize
                                              before storing (avoids double-correction).

Dedup: a fold row is skipped only if a NON-NULL Oil value already exists for
(Year, Test, City) -- empty placeholders never block the fill.

Idempotent: re-running first strips prior fold rows
(Source in {OilComposite_T65, ComposRecover_1947_1958}) before re-adding.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/apply_oil_composite_fold.py
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
FOLD_SOURCES = ["OilComposite_T65", "ComposRecover_1947_1958"]
CORPUS_COLS = ["Year", "TestType", "TestMG", "Test", "Variant", "City", "State",
               "Strain", "Strain_raw", "Phenotype", "Value_num", "Units", "IsCheck", "Source"]


def gap_cells(comb):
    """UT (MG, Year) with >=5 non-null-yield rows and 0 non-null-oil rows in the passed
    combined corpus. Computed from the corpus itself (not the wide) so the fill is
    idempotent regardless of downstream wide state -- pass the fold-stripped combined."""
    d = comb[comb.TestType.astype(str).eq("UT")
             & comb.TestMG.isin(["00", "0", "I", "II", "III", "IV"])].copy()
    d["v"] = pd.to_numeric(d.Value_num, errors="coerce")
    yld = (d[d.Phenotype.eq("YieldBuA")].groupby(["TestMG", "Year"])
           .v.apply(lambda s: s.notna().sum()))
    oil = (d[d.Phenotype.eq("Oil")].groupby(["TestMG", "Year"])
           .v.apply(lambda s: s.notna().sum()))
    gaps = set()
    for (mg, yr), ny in yld.items():
        if ny >= 5 and oil.get((mg, yr), 0) == 0:
            gaps.add((mg, int(yr)))
    return gaps


def to_corpus(df, src, dry_div=None):
    d = df.copy()
    d["Value_num"] = pd.to_numeric(d.Value_num, errors="coerce")
    if dry_div:
        d["Value_num"] = d["Value_num"] / dry_div     # 13%mb -> DRY (11 re-applies ×0.87)
    d = d[d.Value_num.between(10, 30)]                 # physical oil% guard
    d["TestType"] = "UT"
    d["Test"] = "UT-" + d.TestMG.astype(str)
    d["Variant"] = "Conventional"
    d["Strain"] = "Composite"
    d["Strain_raw"] = "Composite"
    d["Phenotype"] = "Oil"
    d["Units"] = "%"
    d["IsCheck"] = "0"
    d["Source"] = src
    d["Year"] = d.Year.astype(str)
    return d[CORPUS_COLS]


def main():
    comb = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
    comb = comb[~comb.Source.isin(FOLD_SOURCES)]      # idempotent: strip prior fold first
    gaps = gap_cells(comb)
    print(f"gap cells (yield>=5, oil=0): {len(gaps)}")

    t = pd.read_csv(STAGE2 / "oil_composite_t65.csv")
    t = t[(t.Phenotype == "Oil") & (t.Aggregation == "location_composite")]
    t = t[[(m, int(y)) in gaps for m, y in zip(t.TestMG, t.Year)]]

    c = pd.read_csv(STAGE2 / "nust_composition_composite_1947_1958.csv")
    c = c[(c.Phenotype == "Oil") & (c.Aggregation == "location_composite") & (c.City.notna())]
    c = c[[(m, int(y)) in gaps for m, y in zip(c.TestMG, c.Year)]]
    # don't duplicate a (MG, Year) t65 already covers
    c = c[~c.set_index(["TestMG", "Year"]).index.isin(t.set_index(["TestMG", "Year"]).index)]

    fold = pd.concat([to_corpus(t, "OilComposite_T65"),
                      to_corpus(c, "ComposRecover_1947_1958", dry_div=0.87)], ignore_index=True)

    co = comb[comb.Phenotype == "Oil"].copy()
    co["v"] = pd.to_numeric(co.Value_num, errors="coerce")
    nonnull = set(zip(co[co.v.notna()].Year, co[co.v.notna()].Test, co[co.v.notna()].City.fillna("")))
    fold = fold[[(r.Year, r.Test, str(r.City) if pd.notna(r.City) else "") not in nonnull
                 for r in fold.itertuples()]]
    print(f"fold rows (vs non-null oil): {len(fold)}  | cells: {len(set(zip(fold.TestMG, fold.Year)))}")

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
