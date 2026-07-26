"""
apply_ut_pt_recovery.py
=======================
Recover the Uniform-Test cells DROPPED by the F4U positional-label backward-shift (UT<->PT
mislabel, see ut_pt_mislabel_audit_1941_1990.md). The dropped sections survive with CORRECT
labels in the per-year Green-direct re-extractions (data was lost only in F4U *assembly*), so
recovery = fold those sections back into the combined corpus (all 8 traits), no PDF re-extract.

Confirmed clean-shift years (current-state audit `audit_ut_pt_current.py`):
  1985 -> UT-III dropped            (reextract_1985_utiii_green.csv, 27 str x 8 traits)
  1977 -> UT-III + UT-IV shifted    (reextract_1977_utiii_utiv_green.csv, 41 str); the corpus's
          existing UT-IV holds shifted/wrong data -> REPLACE it.
  1988 -> UT-00 merged into UT-0    (output_files/output_1988/combined_1988_phenotypesTable.csv
          carries UT-00 correctly)  -> add UT-00; drop any UT-00 strains wrongly sitting in UT-0.

Normalization to corpus conventions: Strain -> F4U convention (drop MG parenthetical + internal
spaces, e.g. 'Century 84 (II)'->'Century84'); City -> canonical via reference map; IsCheck from the
corpus-wide check set; Variant='Conventional'. Protein/Oil stay DRY (11_build_wide applies x0.87
for <=1992). Idempotent: strips prior rows with the recovery Source tag before re-adding.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/apply_ut_pt_recovery.py 1985 [1977 1988]
Then rebuild 11 (wide), regenerate 32.
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SH = REPO / "analysis" / "data" / "_shared"
S2 = REPO / "data_prep" / "stage2_corpus"
CANON = REPO / "reference" / "nust_location_canonical_map.csv"
CC = ["Year", "TestType", "TestMG", "Test", "Variant", "City", "State",
      "Strain", "Strain_raw", "Phenotype", "Value_num", "Units", "IsCheck", "Source"]

RECOVERY = {
    1985: dict(source=S2 / "reextract_1985_utiii_green.csv", fmt="reextract",
               add=["UT-III"], remove=["UT-III"], tag="Recovered_UTPT_1985"),
    1977: dict(source=S2 / "reextract_1977_utiii_utiv_green.csv", fmt="reextract",
               add=["UT-III", "UT-IV"], remove=["UT-III", "UT-IV"], tag="Recovered_UTPT_1977"),
    1988: dict(source=REPO / "output_files/output_1988/combined_1988_phenotypesTable.csv",
               fmt="output", add=["UT-00"], remove=[], tag="Recovered_UTPT_1988"),
}


def norm_strain(s):
    s = re.sub(r"\s*\([^)]*\)", "", str(s)).strip()   # drop MG parenthetical
    return re.sub(r"\s+", "", s)                        # remove internal spaces


def ckey(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def load_canon():
    m = pd.read_csv(CANON, dtype=str)
    by = {}
    for r in m.itertuples():
        by[(str(r.normkey), str(r.norm_state))] = (r.canon_city, r.canon_state)
        by.setdefault((str(r.normkey), None), (r.canon_city, r.canon_state))
    return by


def canon_city(city, state, canon):
    nk = ckey(city)
    hit = canon.get((nk, str(state))) or canon.get((nk, None))
    return hit if hit else (city, state)


def load_section(cfg):
    """Return a long DataFrame in corpus schema for the tests in cfg['add']."""
    if cfg["fmt"] == "reextract":
        d = pd.read_csv(cfg["source"], dtype=str)
        d = d[d.Test.isin(cfg["add"])].copy()
        d["Value_num"] = pd.to_numeric(d.Value_num, errors="coerce")
    else:  # output phenotypesTable: Strain,Year,Test,Location,City,State,Phenotype,Value,Units
        d = pd.read_csv(cfg["source"], dtype=str)
        d["Test"] = d.Test.replace({"UT-O": "UT-0"})
        d = d[d.Test.isin(cfg["add"])].copy()
        d["Value_num"] = pd.to_numeric(d.Value, errors="coerce")
        d["TestType"] = "UT"
        d["TestMG"] = d.Test.str.replace("UT-", "", regex=False)
    d = d[d.Value_num.notna()]
    return d


def main():
    years = [int(a) for a in sys.argv[1:]]
    if not years:
        sys.exit("usage: apply_ut_pt_recovery.py <year> [year ...]")
    canon = load_canon()
    comb = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
    checkset = {ckey(s) for s in comb.loc[comb.IsCheck.isin(["1", "1.0", "True"]), "Strain"].dropna()}

    tags = [RECOVERY[y]["tag"] for y in years]
    comb = comb[~comb.Source.isin(tags)]                       # idempotent strip

    add_frames = []
    for year in years:
        cfg = RECOVERY[year]
        sec = load_section(cfg)
        # REMOVE wrong existing cells first (e.g. 1977 corpus UT-IV holds shifted data)
        if cfg["remove"]:
            before = len(comb)
            comb = comb[~((comb.Year == str(year)) & (comb.Test.isin(cfg["remove"])))]
            print(f"{year}: removed {before - len(comb)} wrong-label rows {cfg['remove']}")
        rows = []
        for r in sec.itertuples():
            city, state = canon_city(r.City, r.State, canon)
            strain = norm_strain(r.Strain)
            rows.append({
                "Year": str(year), "TestType": "UT", "TestMG": r.Test.replace("UT-", ""),
                "Test": r.Test, "Variant": "Conventional", "City": city, "State": state,
                "Strain": strain, "Strain_raw": str(r.Strain), "Phenotype": r.Phenotype,
                "Value_num": r.Value_num, "Units": r.Units,
                "IsCheck": "1" if ckey(strain) in checkset else "0", "Source": cfg["tag"]})
        f = pd.DataFrame(rows)
        add_frames.append(f)
        nchk = (f.IsCheck == "1").sum()
        print(f"{year}: +{len(f)} rows, tests={cfg['add']}, strains={f.Strain.nunique()}, "
              f"checks={f[f.IsCheck=='1'].Strain.nunique()}, "
              f"phenos={dict(f.Phenotype.value_counts())}")

    out = pd.concat([comb] + [af[CC] for af in add_frames], ignore_index=True)
    for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
        out.to_csv(SH / name, index=False)
    out["_y"] = pd.to_numeric(out.Year, errors="coerce")
    for lo, hi, fn in [(1941, 1984, "nust_1941-1984_combined.csv"),
                       (1985, 2004, "nust_1985-2004_combined.csv"),
                       (2005, 2025, "nust_2005-2025_combined.csv")]:
        out[(out._y >= lo) & (out._y <= hi)].drop(columns="_y").to_csv(SH / fn, index=False)
    print(f"\ncombined -> {len(out):,} rows; alias + era splits written. Next: 11, then 32.")


if __name__ == "__main__":
    main()
