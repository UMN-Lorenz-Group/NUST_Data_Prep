"""Remove the PHANTOM `PT-00` test from the 1975 F4U.

1975 has 11 tests, not 12 -- proven three ways from the doc-AI title captions
(derive_1975_from_docai.py): (1) no page is captioned "PRELIMINARY TEST 00" anywhere; (2) the F4U
PT-00's 15 strains split across real UT-00 (CM147/CM148/M65-217/Altona, doc-AI pp.2-9) + real PT-0
(M67-*/M68-38, pp.17-19); (3) all 11 true caption-sections match their F4U label at roster overlap 1.0
while PT-00 alone has no caption-section. The PDF-direct extractor invented PT-00 by merging real
UT-00 + PT-0 rows.

Safety proven before removal: of PT-00's 1,100 rows, 133 are exact dups of UT-00, 914 of PT-0, and the
remaining 53 are VALUE-DRIFT dups -- every one of their (Strain,City) cells already exists in UT-00 or
PT-0 (0 cells are unique to PT-00). So nothing real is lost; UT-00/PT-0 are the authoritative extraction.
"""
import sys, shutil
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
F4U = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/"
           "NUST_Historical_Data_1941_1988/1975_Processing/Files4Upload/phenotypesTable1.csv")


def main():
    apply = "--apply" in sys.argv
    f = pd.read_csv(F4U, low_memory=False)
    mask = (f.Year == 1975) & (f.Test == "PT-00")
    pt00 = f[mask]
    print(f"1975 F4U: {len(f):,} rows | PT-00 phantom rows to remove: {mask.sum()} "
          f"({pt00.Strain.nunique()} strains, {sorted(pt00.City.unique())})")

    # re-prove safety: every PT-00 (Strain,City) cell exists in UT-00 or PT-0
    f75 = f[f.Year == 1975]
    real_sc = set(zip(f75[f75.Test == "UT-00"].Strain.astype(str), f75[f75.Test == "UT-00"].City.astype(str))) \
        | set(zip(f75[f75.Test == "PT-0"].Strain.astype(str), f75[f75.Test == "PT-0"].City.astype(str)))
    pt00_sc = set(zip(pt00.Strain.astype(str), pt00.City.astype(str)))
    orphan = pt00_sc - real_sc
    print(f"  PT-00 (Strain,City) cells absent from UT-00/PT-0: {len(orphan)} "
          f"{'-> ABORT, real data would be lost' if orphan else '-> none; safe to drop'}")
    assert not orphan, f"unexpected unique cells: {sorted(orphan)[:10]}"

    out = f[~mask].copy()
    print(f"  F4U after: {len(out):,} rows (removed {mask.sum()}); "
          f"1975 tests now: {sorted(out[out.Year == 1975].Test.unique())}")

    if apply:
        bak = F4U.with_suffix(".csv.bak_pre_pt00_remove")
        if not bak.exists():
            shutil.copy2(F4U, bak)
            print(f"  backed up -> {bak.name}")
        out.to_csv(F4U, index=False)
        print("  APPLIED: phantom PT-00 removed from 1975 F4U.")
    else:
        print("  (dry run; --apply to write)")


if __name__ == "__main__":
    main()
