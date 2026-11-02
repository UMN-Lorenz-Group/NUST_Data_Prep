"""Rebuild the 1983 F4U phenotypesTable1.csv WHOLESALE from the green-direct extraction.

The 1983 F4U was badly SCRAMBLED (only 9 labels, merges: PT-IIIA UT-shaped 63str/30loc, UT-IV PT-shaped
46str/7loc, UT-I 38str = UT-I+PT-I; missing PT-I/PT-IIIB/PT-IV). 1983 was NEVER 110-relabeled, so the F4U
is the raw scrambled extraction and there is nothing to reconcile. The Green tp2 markers are now repaired
(fix_1983_tp2.py -> 12 correct groups) and all 12 tests were GREEN-DIRECT re-extracted (no API) to
`reextract_1983_green.csv` (26,543 rows, 12 tests, correct geometry, yield 100% reconcile). This REPLACES
the entire 1983 F4U with those 12 clean tests x 8 core traits.

Per the 1984 precedent, the 9 all-NaN fatty-acid/sugar phenotypes (0 non-null in 1983) + YieldRank
(derivable) are dropped; the F4U keeps the 8 core traits. Strain names already follow the F4U convention
(no MG parenthetical, no internal spaces). `--apply` backs up to `.bak_pre_1983swap` and writes.
Idempotent: re-runs rebuild from the same recovery CSV.
"""
import sys
import shutil
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
GREEN = REPO / "data_prep" / "stage2_corpus" / "reextract_1983_green.csv"
F4U = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/"
           "NUST_Historical_Data_1941_1988/1983_Processing/Files4Upload/phenotypesTable1.csv")


def main():
    apply = "--apply" in sys.argv
    g = pd.read_csv(GREEN, low_memory=False)
    old = pd.read_csv(F4U, low_memory=False)

    new = pd.DataFrame({
        "Strain": g.Strain, "Year": 1983, "Test": g.Test, "City": g.City, "State": g.State,
        "Phenotype": g.Phenotype, "Value": g.Value_num, "Units": g.Units,
    })[list(old.columns)]

    print(f"OLD 1983 F4U: {len(old):>7} rows, {old.Test.nunique()} tests {sorted(old.Test.unique())}")
    print(f"NEW 1983 F4U: {len(new):>7} rows, {new.Test.nunique()} tests {sorted(new.Test.unique())}")
    print(f"  traits kept: {sorted(new.Phenotype.unique())}")
    print(f"  dropped (all-NaN fatty/sugar + YieldRank): "
          f"{sorted(set(old.Phenotype) - set(new.Phenotype))}")
    # geometry sanity
    print("  geometry:")
    for t, s in new.groupby("Test"):
        geo = "UT" if s.City.nunique() >= 12 else "PT"
        print(f"    {t:8s} {s.Strain.nunique():2d}str {s.City.nunique():2d}loc [{geo}]")
    print(f"  dup keys: {new.duplicated(['Strain','Test','City','State','Phenotype']).sum()}")

    if apply:
        bak = F4U.with_suffix(".csv.bak_pre_1983swap")
        if not bak.exists():
            shutil.copy2(F4U, bak)
            print(f"  backed up -> {bak.name}")
        new.to_csv(F4U, index=False)
        print("  APPLIED: 1983 F4U rebuilt from green-direct (12 clean tests).")
    else:
        print("\n(dry run; --apply to write)")


if __name__ == "__main__":
    main()
