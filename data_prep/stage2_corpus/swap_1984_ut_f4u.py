"""Rebuild the 1984 F4U phenotypesTable1.csv from the two clean re-extractions, replacing the
whole-year label PERMUTATION.

Why a full rebuild rather than another in-place patch: EVERY 1984 label in the original F4U is
wrong (positional Group_N assignment bug), so the honest operation is "drop all scrambled cells,
insert the clean ones". Rebuilding from the pre-swap backup also makes this idempotent -- re-running
cannot double-apply -- and keeps a single provenance story for the year.

  pre-swap F4U (11 scrambled labels, 72,540 rows)
      -> DROP every phenotype row
      -> ADD reextract_1984_pt_recovered.csv  (7 real PT tests, PDF + Green)
      -> ADD reextract_1984_ut_recovered.csv  (6 real UT tests, Green)

Dropped on purpose (same precedent as the PT swap):
  * 9 fatty-acid/sugar phenotypes -- ALL-NaN placeholders in the source (0 non-null).
  * YieldRank -- derivable from YieldBuA; the PT swap already dropped it.

Coverage was proved before writing (see the coverage gate): every strain the scrambled UT labels
carried is present in the replacement, so nothing is lost.
"""
import sys, shutil
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

F4U = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/"
           "NUST_Historical_Data_1941_1988/1984_Processing/Files4Upload/phenotypesTable1.csv")
PRE = F4U.with_suffix(".csv.bak_pre_1984pt_swap")
HERE = Path(__file__).parent
PT = HERE / "reextract_1984_pt_recovered.csv"
UT = HERE / "reextract_1984_ut_recovered.csv"
UNIT_MAP = {"DOY": "date", "in": "inches", "score": "score", "g/100": "g/100", "%": "%", "bu/a": "bu/a"}


def fmt(v):
    return str(int(v)) if float(v) == int(v) else f"{v:g}"


def main():
    apply = "--apply" in sys.argv
    pre = pd.read_csv(PRE, low_memory=False)
    cur = pd.read_csv(F4U, low_memory=False)
    print(f"pre-swap F4U : {len(pre):,} rows, labels {sorted(pre.Test.unique())}")
    print(f"current F4U  : {len(cur):,} rows, labels {sorted(cur.Test.unique())}")
    assert (pre.Year == 1984).all(), "pre-swap F4U is not 1984-only"

    frames = []
    for src, tag in ((PT, "PT"), (UT, "UT")):
        r = pd.read_csv(src)
        frames.append(pd.DataFrame({
            "Strain": r.Strain, "Year": r.Year, "Test": r.Test, "City": r.City,
            "State": r.State, "Phenotype": r.Phenotype,
            "Value": r.Value_num.map(fmt), "Units": r.Units.map(lambda u: UNIT_MAP.get(u, u)),
        }))
        print(f"  + {tag}: {len(r):,} rows, {r.Test.nunique()} tests {sorted(r.Test.unique())}, "
              f"{r.Strain.nunique()} strains, State nulls {r.State.isna().sum()}")
    out = pd.concat(frames, ignore_index=True)[pre.columns]

    print(f"\nrebuilt 1984 F4U: {len(out):,} rows "
          f"(pre-swap {len(pre):,} -> {len(out):,}; current {len(cur):,})")
    print(f"  tests   : {out.Test.nunique()} {sorted(out.Test.unique())}")
    print(f"  strains : {out.Strain.nunique()}")
    print(f"  phenos  : {sorted(out.Phenotype.unique())}")
    print(f"  State nulls: {out.State.isna().sum()}")

    dup = out.duplicated(["Year", "Test", "Strain", "City", "State", "Phenotype"]).sum()
    print(f"  duplicate keys: {dup}")
    assert dup == 0, "duplicate keys in rebuilt F4U"

    # no strain from the old scrambled labels may vanish
    lost = set(pre.Strain.dropna()) - set(out.Strain.dropna())
    print(f"  strains present pre-swap but not in rebuild: {len(lost)} "
          f"{sorted(lost) if lost else '-> none'}")

    print("\n  rows per test:")
    print(out.groupby("Test").size().to_string())

    if apply:
        bak = F4U.with_suffix(".csv.bak_pre_1984ut_swap")
        if not bak.exists():
            shutil.copy2(F4U, bak)
            print(f"\nbacked up current -> {bak.name}")
        out.to_csv(F4U, index=False)
        print("APPLIED: 1984 phenotypesTable1.csv rebuilt from clean PT + UT.")
    else:
        print("\n(dry run; pass --apply to write)")


if __name__ == "__main__":
    main()
