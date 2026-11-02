"""
swap_utpt_f4u.py  --  bake the UT<->PT dropped-section recoveries into the F4U SOURCE
=====================================================================================
Durability at source (the 1984 precedent): the 1985/1977/1988 recoveries are otherwise only
post-assembly folds of the combined (see finalize_corpus_recoveries.py) -- baking them into the
F4U `phenotypesTable1.csv` makes them survive a full 10_assemble too.

Per year (each rebuilt from a pristine `.bak_pre_utpt_swap` backup, so re-running is idempotent):
  1985: F4U has NO UT-III (dropped) -> APPEND reextract_1985_utiii_green.csv as UT-III.
  1977: F4U has NO UT-III & NO UT-IV (both dropped) -> APPEND reextract_1977_utiii_utiv_green.csv.
  1988: F4U "UT-0" = a MERGE of true UT-00 (17) + true UT-0 (33); no UT-00. -> reclassify UT-0 by
        complete PDF roster (UT-0 roster -> keep UT-0; UT-00 roster -> drop, superseded) + APPEND
        the image-verified staged UT-00 (ut00_1988_alltraits.csv). UT-I/UT-II already correct.

F4U schema = Strain,Year,Test,City,State,Phenotype,Value,Units. Protein/Oil are DRY (F4U
convention); Maturity is DOY under Units="date" (matches the reextract). YieldRank + the all-NaN
fatty-acid/sugar phenos are NOT added (same precedent as swap_1984).

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/swap_utpt_f4u.py            # dry run
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/swap_utpt_f4u.py --apply
"""
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
HIST = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/"
            "NUST_Historical_Data_1941_1988")
F4U_COLS = ["Strain", "Year", "Test", "City", "State", "Phenotype", "Value", "Units"]
UNIT_MAP = {"DOY": "date", "date": "date", "in": "inches", "inches": "inches", "score": "score",
            "g/100": "g/100", "g/100sd": "g/100", "%": "%", "bu/a": "bu/a", "bu/ac": "bu/a"}
DROP_PHENO = {"YieldRank", "LinoleicAcid", "LinolenicAcid", "OleicAcid", "PalmiticAcid",
              "StearicAcid", "Raffinose", "Stachyose", "Sucrose", "SugarTotal"}


def ck(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\([^)]*\)", "", str(s)).lower())


def fmt(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    return str(int(v)) if v == int(v) else f"{v:g}"


UT00_ROSTER = {ck(x) for x in ["Clay", "Maple Presto", "Maple Ridge", "McCall", "M84-93",
    "M84-456", "ND867", "ND868", "ND941", "ND2337", "ND2338", "ND2353", "OT84-12", "OT85-5",
    "OT87-7", "OT87-8", "OT87-12"]}
UT0_ROSTER = {ck(x) for x in ["Dawson", "Glenwood", "McCall", "Sibley", "M81-18", "M81-27",
    "M83-715", "M83-727", "M83-744", "M83-766", "M83-770", "M84-74", "M84-140", "M84-293",
    "M84-302", "M84-389", "M84-390", "M84-395", "M84-414", "M84-449", "M84-568", "M84-574",
    "M84-748", "M84-756", "M84-833", "M84-850", "ND1019", "ND2328", "ND2329", "ND2330",
    "ND2361", "ND2373", "OT86-5"]}


def reextract_as_f4u(path, year, tests):
    r = pd.read_csv(path, dtype=str)
    r = r[r.Test.isin(tests) & ~r.Phenotype.isin(DROP_PHENO)].copy()
    r["v"] = pd.to_numeric(r.Value_num, errors="coerce")
    r = r[r.v.notna()]
    return pd.DataFrame({
        "Strain": r.Strain, "Year": str(year), "Test": r.Test, "City": r.City, "State": r.State,
        "Phenotype": r.Phenotype, "Value": r.v.map(fmt),
        "Units": r.Units.map(lambda u: UNIT_MAP.get(str(u), str(u)))})[F4U_COLS]


def build_year(year):
    f4u = HIST / f"{year}_Processing" / "Files4Upload" / "phenotypesTable1.csv"
    bak = f4u.with_suffix(".csv.bak_pre_utpt_swap")
    base = pd.read_csv(bak if bak.exists() else f4u, dtype=str, low_memory=False)
    base["Year"] = base.Year.astype(str)
    add = []
    if year == 1985:
        add.append(reextract_as_f4u(HERE / "reextract_1985_utiii_green.csv", 1985, ["UT-III"]))
    elif year == 1977:
        add.append(reextract_as_f4u(HERE / "reextract_1977_utiii_utiv_green.csv", 1977,
                                    ["UT-III", "UT-IV"]))
    elif year == 1988:
        # reclassify the UT-0 merge: keep UT-0-roster, drop UT-00-roster (superseded by staged)
        ut0 = base.Test == "UT-0"
        drop = ut0 & base.Strain.map(lambda s: ck(s) in UT00_ROSTER and ck(s) not in UT0_ROSTER)
        base = base[~drop].copy()
        # staged clean UT-00 (all traits)
        u = pd.read_csv(HERE / "ut00_1988_alltraits.csv", dtype=str)
        u = u[~u.Phenotype.isin(DROP_PHENO)].copy()
        u["v"] = pd.to_numeric(u.Value_num, errors="coerce")
        u = u[u.v.notna()]
        add.append(pd.DataFrame({
            "Strain": u.Strain, "Year": "1988", "Test": "UT-00", "City": u.City, "State": u.State,
            "Phenotype": u.Phenotype, "Value": u.v.map(fmt),
            "Units": u.Units.map(lambda x: UNIT_MAP.get(str(x), str(x)))})[F4U_COLS])
    out = pd.concat([base[F4U_COLS]] + add, ignore_index=True)
    return f4u, bak, base, out, pd.concat(add, ignore_index=True)


def main():
    apply = "--apply" in sys.argv
    KEY = ["Year", "Test", "Strain", "City", "State", "Phenotype"]
    for year in (1985, 1977, 1988):
        f4u, bak, base, out, added = build_year(year)
        # the legacy F4U carries pre-existing NaN-padding dups; only assert the SWAP adds none.
        base_dups = int(base.duplicated(KEY).sum())
        added_internal = int(added.duplicated(KEY).sum())
        base_keys = set(map(tuple, base[KEY].astype(str).values))
        added_keys = set(map(tuple, added[KEY].astype(str).values))
        collide = len(base_keys & added_keys)
        print(f"\n=== {year} F4U ===")
        print(f"  base {len(base):,} -> rebuilt {len(out):,} rows (+{len(added)} recovered)")
        print(f"  tests now: {sorted(out.Test.unique())}")
        print(f"  added tests: {sorted(added.Test.unique())} "
              f"({added.Strain.nunique()} strains, {sorted(added.Phenotype.unique())})")
        print(f"  pre-existing base dup keys: {base_dups} (legacy, untouched) | "
              f"added internal dups: {added_internal} | added↔base collisions: {collide}")
        assert added_internal == 0 and collide == 0, f"{year}: swap introduces duplicate keys"
        if apply:
            if not bak.exists():
                shutil.copy2(f4u, bak)
                print(f"  backed up pristine -> {bak.name}")
            out.to_csv(f4u, index=False)
            print(f"  APPLIED -> {f4u.name}")
        else:
            print("  (dry run; pass --apply to write)")


if __name__ == "__main__":
    main()
