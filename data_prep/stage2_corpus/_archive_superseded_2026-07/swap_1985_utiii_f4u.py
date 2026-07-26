"""C2 PILOT: add the green-direct 1985 UT-III into the 1985 F4U phenotypesTable1.csv.

Context: 1985 UT-III was the DROPPED test (its parentage opener was a mislabeled tp1 at the head of the
split Green file 2, so `combine` folded it into GlobalParentage). The source is now fixed (tp2 inserted,
1985_test_map.json emits the 13-group map) and UT-III was GREEN-DIRECT re-extracted (no API) to
`reextract_1985_utiii_green.csv` (27 str x 21 loc x 8 traits, reconcile 26-27/27, beats the old PDF
recovery). The current F4U already carries the OTHER 12 tests with correct labels+data (the 110-relabel
un-shifted them) but UT-III is an honest GAP. This adds UT-III -> 13 tests, so a future clean rebuild
from Green+JSON needs no 110 relabel (retire at C4 after D1).

Strain naming: adopt the 1985 F4U convention (verified against the existing UT-II/other-test vocabulary):
NO MG parenthetical, NO internal spaces (e.g. 'Century 84 (II)' -> 'Century84', 'AHW-Pella BC' ->
'AHW-PellaBC'). Checks (Century84, Williams82, ...) MUST match the F4U's other-test spelling so the RGG
estimators anchor correctly -- validated below.

`--apply` backs up to `.bak_pre_1985utiii_swap` and writes. Idempotent (skips if UT-III already present).
"""
import sys
import shutil
from pathlib import Path
import re
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
GREEN = REPO / "data_prep" / "stage2_corpus" / "reextract_1985_utiii_green.csv"
F4U = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/"
           "NUST_Historical_Data_1941_1988/1985_Processing/Files4Upload/phenotypesTable1.csv")


def norm_strain(s):
    """1985 F4U convention: drop MG parenthetical, then remove internal whitespace."""
    s = re.sub(r"\s*\([^)]*\)", "", str(s)).strip()   # 'Century 84 (II)' -> 'Century 84'
    s = re.sub(r"\s+", "", s)                          # 'Century 84' -> 'Century84'
    return s


def normkey(s):
    """Fold for cross-test check MATCHING only (l/1/i, O/0, drop non-alnum)."""
    s = re.sub(r"[^A-Za-z0-9]", "", str(s)).upper()
    return s.replace("O", "0").replace("L", "1").replace("I", "1")


def main():
    apply = "--apply" in sys.argv
    f4u = pd.read_csv(F4U, low_memory=False)
    if "UT-III" in set(f4u.Test.astype(str)):
        print("1985 F4U already has UT-III -- nothing to do (idempotent).")
        return

    g = pd.read_csv(GREEN, low_memory=False)
    g = g[g.Test == "UT-III"].copy()
    g["Strain"] = g.Strain.map(norm_strain)

    # map green schema -> F4U schema
    add = pd.DataFrame({
        "Strain": g.Strain, "Year": g.Year, "Test": "UT-III",
        "City": g.City, "State": g.State, "Phenotype": g.Phenotype,
        "Value": g.Value_num, "Units": g.Units,
    })[list(f4u.columns)]

    # --- validation: UT-III check varieties must spell like the F4U's other-test checks ---
    f4u_vocab = {normkey(s): s for s in f4u.Strain.astype(str).unique()}
    checks = ["Century84", "Williams82", "Pella", "Zane", "Hobbit", "Fayette"]
    print("check-name reconciliation vs existing 1985 F4U vocabulary:")
    for c in checks:
        k = normkey(c)
        hit = f4u_vocab.get(k)
        present = c in set(add.Strain)
        print(f"  {c:12s} in UT-III add: {present} | F4U other-test spelling: {hit}")

    print(f"\nUT-III rows to add: {len(add)} | strains {add.Strain.nunique()} | locs {add.City.nunique()} "
          f"| traits {sorted(add.Phenotype.unique())}")
    print(f"strain sample: {sorted(add.Strain.unique())[:10]}")
    print(f"F4U before: {len(f4u)} rows, {f4u.Test.nunique()} tests (no UT-III)")

    out = pd.concat([f4u, add], ignore_index=True)
    print(f"F4U after:  {len(out)} rows, {out.Test.nunique()} tests")
    # geometry sanity: UT-III should be UNIFORM-shaped (~20 loc, ~27 str)
    ut3 = out[out.Test == "UT-III"]
    print(f"UT-III geometry: {ut3.Strain.nunique()} str x {ut3.City.nunique()} loc "
          f"({'UNIFORM-shaped OK' if ut3.City.nunique() >= 12 else 'CHECK - too few locs'})")

    if apply:
        bak = F4U.with_suffix(".csv.bak_pre_1985utiii_swap")
        if not bak.exists():
            shutil.copy2(F4U, bak)
            print(f"  backed up -> {bak.name}")
        out.to_csv(F4U, index=False)
        print("  APPLIED: 1985 UT-III added to F4U.")
    else:
        print("\n(dry run; --apply to write)")


if __name__ == "__main__":
    main()
