"""
gen_f4u_1989_1992_combine.py
============================
Combine the agronomic (report-CSV) + composition (report-PDF) staging tables into the
final per-year Files4Upload `phenotypesTable1.csv` (9 traits) for 1989/1991/1992, applying
a definitional value-range filter that drops physically-impossible extraction artifacts
(e.g. SeedQuality/Lodging outside the 1-5 score scale, an implausibly-low Protein) so the
distributions match the Master reference. Protein/Oil are DRY basis (report values);
11_build_wide applies ×0.87 for these years.

Usage:
    uv run python data_prep/stage2_corpus/gen_f4u_1989_1992_combine.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SRC = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/NUST_Data_1989_1992")
YEARS = [1989, 1991, 1992]

# definitional valid ranges. Score traits are 1-5 by definition; Protein/Oil are DRY basis
# (13% mb range / 0.87). Bounds chosen to keep genuine extremes that match Master (e.g. dry
# Protein 25.0 = 21.75 mb = Master min; dry Oil 12.4 = 10.79 mb = Master min) and drop only
# true artifacts (dry Protein 9.0, SeedQuality 6.7 / 0.9).
RANGES = {
    "YieldBuA": (0, 130), "YieldRank": (0, 999), "Maturity": (180, 330),
    "Lodging": (1, 5), "Height": (3, 70), "SeedQuality": (1, 5),
    "SeedSize": (2, 50), "Protein": (24, 52), "Oil": (12, 28),
}


def main():
    for y in YEARS:
        d = SRC / str(y) / f"{y}_Processing" / "Files4Upload"
        ag = pd.read_csv(d / "phenotypesTable1_agronomic.csv", low_memory=False)
        co = pd.read_csv(d / "phenotypesTable1_composition.csv", low_memory=False)
        comb = pd.concat([ag, co], ignore_index=True)
        v = pd.to_numeric(comb["Value"], errors="coerce")
        lo = comb["Phenotype"].map(lambda p: RANGES.get(p, (-1e9, 1e9))[0])
        hi = comb["Phenotype"].map(lambda p: RANGES.get(p, (-1e9, 1e9))[1])
        oob = v.notna() & ((v < lo) | (v > hi))
        if oob.any():
            print(f"{y}: dropping {int(oob.sum())} out-of-range cells:")
            print(comb.loc[oob, ["Test", "City", "Strain", "Phenotype", "Value"]]
                  .to_string(index=False, max_rows=20))
        comb = comb[~oob].copy()
        comb.to_csv(d / "phenotypesTable1.csv", index=False)
        print(f"{y}: {len(ag)} agronomic + {len(co)} composition - {int(oob.sum())} oob "
              f"= {len(comb)} -> phenotypesTable1.csv\n")


if __name__ == "__main__":
    main()
