"""
102_recovery_manifest.py
========================
Build the TARGETED manifest of missing UT trait-cells to recover via the dual-source
(Green XLSX + local Red-PDF) cross-check pipeline (scripts 103/104/105).

A "missing cell" = a (Phenotype, TestMG, Year) with NO non-null value in the corpus,
INTERIOR to that (Phenotype, TestMG)'s own coverage span (so we don't chase pre-first /
post-last edges, only true holes). Restricted to historical UT (Year <= 1988) and the
core agronomic/composition traits — the data confirmed present in BOTH Green and the Red
PDFs but dropped in the Green->F4U extraction (see the plan / analysis_notes).

Composition 1947-1958 is EXCLUDED (already recovered to the standalone composite file,
script 101). Output drives the extractors; it is NOT a corpus edit.

Output: data_prep/stage2_corpus/recovery_manifest.csv
  columns: Year, TestMG, traits (comma-joined), n_traits, kind (whole_section|partial)
"""
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
CORPUS = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
OUT = REPO / "data_prep" / "stage2_corpus" / "recovery_manifest.csv"

TRAITS = ["YieldBuA", "Maturity", "Height", "Lodging", "Protein", "Oil", "SeedSize", "SeedQuality"]
MGS = ["00", "0", "I", "II", "III", "IV"]
MAX_YEAR = 1988                      # historical (Green/PDF) era
COMPOSITION = {"Protein", "Oil", "SeedSize", "SeedQuality"}
COMPOSITE_DONE = set(range(1947, 1959))   # composition 1947-58 -> standalone composite file (101)


def interior_gaps(years):
    if len(years) < 2:
        return []
    return sorted(set(range(min(years), max(years) + 1)) - set(years))


def main():
    L = pd.read_csv(CORPUS, low_memory=False,
                    usecols=["Year", "TestType", "TestMG", "Phenotype", "Value_num"])
    ut = L[(L["TestType"] == "UT") & (L["Value_num"].notna())]

    # (Phenotype, MG) -> set of years with data; collect missing interior cells
    missing = {}   # (Year, MG) -> set(traits)
    for tr in TRAITS:
        t = ut[ut["Phenotype"] == tr]
        for mg in MGS:
            yrs = sorted(int(y) for y in t[t["TestMG"].astype(str) == mg]["Year"].unique())
            for gy in interior_gaps(yrs):
                if gy > MAX_YEAR:
                    continue
                if tr in COMPOSITION and gy in COMPOSITE_DONE:
                    continue           # already in the composite standalone file
                missing.setdefault((gy, mg), set()).add(tr)

    rows = []
    for (yr, mg), traits in sorted(missing.items()):
        kind = "whole_section" if len(traits) >= 6 else "partial"
        rows.append({"Year": yr, "TestMG": mg, "traits": ",".join(sorted(traits)),
                     "n_traits": len(traits), "kind": kind})
    man = pd.DataFrame(rows).sort_values(["Year", "TestMG"])
    man.to_csv(OUT, index=False)

    print(f"Recovery manifest: {len(man)} (Year,MG) cells -> {OUT.name}")
    print(f"  whole-section: {(man.kind == 'whole_section').sum()} | partial: {(man.kind == 'partial').sum()}")
    print("\nby year:")
    print(man.assign(cell=man.Year.astype(str) + ':' + man.TestMG)
             .groupby("Year").agg(cells=("cell", "size"),
                                  MGs=("TestMG", lambda x: ",".join(sorted(x)))).to_string())
    print("\nwhole-section cells (all-trait gaps):")
    print(man[man.kind == "whole_section"][["Year", "TestMG", "n_traits"]].to_string(index=False))


if __name__ == "__main__":
    main()
