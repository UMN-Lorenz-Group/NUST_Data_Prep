"""
apply_oil_perloc_recovery.py
============================
P1 oil-gap fill, part 2: fold the staged PER-LOCATION (per-strain x location) Oil
recoveries into the corpus for the early/mid-era UT cells that have yield + empty Oil
placeholders (the F4U pipeline made the placeholder grid but never filled the value).
Unlike the location_composite fold (apply_oil_composite_fold.py, Strain="Composite"),
these carry REAL strain names, so each recovered value UPDATES the matching empty
placeholder in place (mirrors apply_recovered_maturity); a value with no placeholder but
a paired YieldBuA row is ADDED; anything else is reported and skipped.

Cells filled (10 open per-location gaps; the only (TestMG, Year) taken from each source):
  oil_recovered_gapfill.csv          1962 UT-00/UT-0/UT-IV, 1964 UT-IV, 1972 UT-III   (OilPDF)
  oil_recovered_1979_ut0_i_iv.csv    1979 UT-00/UT-I/UT-IV                            (OilPDF_1979_recovered)
  oil_recovered_1979_utii.csv        1979 UT-II                                       (OilYellow_docAI)
  oil_recovered_modern_gaps.csv      1987 UT-I                                        (OilPDF_garbledfix)
(1979 UT-0 = MG 0 already has oil -> excluded; 1985 UT-III = the PT-IIIA mislabel, out
of scope -> excluded; 2011 III/IV = genuine absence.)

Basis: all staged values are DRY (raw report/PDF), consistent with pre-1989 corpus; the
x0.87 dry->13%mb correction is applied downstream by 11_build_wide. Store DRY.

Idempotent by construction: fills only still-null placeholders and adds a paired row only
when the cell has NO oil row at all -- so a key already filled by a prior run is skipped,
never duplicated (no strip/mutation of prior state needed).

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/apply_oil_perloc_recovery.py
Then: rebuild 11 (wide), regenerate 32 (boxplots).
"""
import os
import re
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(os.environ.get("NUST_REPO", "C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep"))
SH = REPO / "analysis" / "data" / "_shared"
STAGE2 = REPO / "data_prep" / "stage2_corpus"

# (staged file, {(TestMG, Year): keep}) -- only these cells are folded
SOURCES = [
    ("oil_recovered_gapfill.csv",
     {("00", 1962), ("0", 1962), ("IV", 1962), ("IV", 1964), ("III", 1972)}),
    ("oil_recovered_1979_ut0_i_iv.csv",
     {("00", 1979), ("I", 1979), ("IV", 1979)}),
    ("oil_recovered_1979_utii.csv",
     {("II", 1979)}),
    ("oil_recovered_modern_gaps.csv",
     {("I", 1987)}),
]


# normalized-key aliases for the few staged spellings that differ from the corpus canon
# (verified against the 1979 UT-II corpus roster): Lafayette IN == West Lafayette IN (Purdue);
# "Nebscy" is an OCR corruption of the check "Nebsoy".
CITY_ALIAS = {"lafayette": "westlafayette"}
STRAIN_ALIAS = {"nebscy": "nebsoy"}


def norm_city(s):
    s = re.sub(r"\([^)]*\)", "", str(s))
    c = re.sub(r"[^a-z0-9]", "", s.lower())
    return CITY_ALIAS.get(c, c)


def norm_strain(s):
    s = re.sub(r"\([^)]*\)", "", str(s))
    c = re.sub(r"[^a-z0-9]", "", s.lower())
    return STRAIN_ALIAS.get(c, c)


def nk(year, test, city, strain):
    return (str(year), str(test), norm_city(city), norm_strain(strain))


def load_recoveries():
    frames = []
    for fn, cells in SOURCES:
        d = pd.read_csv(STAGE2 / fn)
        d = d[[(str(m), int(y)) in cells for m, y in zip(d.TestMG, d.Year)]].copy()
        d["Value_num"] = pd.to_numeric(d.Value_num, errors="coerce")
        d = d[d.Value_num.between(10, 30)]
        frames.append(d)
        print(f"  {fn}: {len(d)} rows across {sorted(set(zip(d.TestMG, d.Year)))}")
    return pd.concat(frames, ignore_index=True)


FOLD_SOURCES = ["OilPDF", "OilPDF_1979_recovered", "OilYellow_docAI", "OilPDF_garbledfix"]


def main():
    comb = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
    cols = list(comb.columns)

    # RESET (idempotent + self-correcting): revert any prior perloc fill back to an empty
    # F4U placeholder, so a re-run recomputes the fill cleanly from the current staged data.
    prior = comb.Phenotype.eq("Oil") & comb.Source.isin(FOLD_SOURCES)
    if prior.any():
        comb.loc[prior, "Value_num"] = pd.NA
        comb.loc[prior, "Source"] = "F4U_1941_1988"
        print(f"reset {int(prior.sum())} prior perloc-fill rows -> empty F4U placeholders")

    rec = load_recoveries()
    print(f"recovered per-location oil rows: {len(rec)}")

    v = pd.to_numeric(comb.Value_num, errors="coerce")
    is_oil = comb.Phenotype.eq("Oil")
    # "real" locations = raw City spellings that carry >=1 non-null YieldBuA in the (Year,Test)
    # cell. Used to steer a value onto the REAL location row when the corpus holds a duplicate
    # spelling (e.g. real "Dekalb" [has yield] + phantom "DeKalb" [null yield], same norm key).
    yv = comb[comb.Phenotype.eq("YieldBuA")].copy()
    yv["v"] = pd.to_numeric(yv.Value_num, errors="coerce")
    real_cities = {(r.Year, r.Test, str(r.City))
                   for r in yv[yv.v.notna()].itertuples()}

    def is_real(row):
        return (row.Year, row.Test, str(row.City)) in real_cities

    # index EMPTY oil placeholders; real-location rows win the norm key (processed first)
    oil_ph = comb[is_oil & v.isna()]
    oil_idx = {}
    for pref in (True, False):
        for i, r in zip(oil_ph.index, oil_ph.itertuples()):
            if is_real(r) == pref:
                oil_idx.setdefault(nk(r.Year, r.Test, r.City, r.Strain), i)
    # ALL oil-row keys (null + non-null): a key already carrying oil is skipped -> idempotent
    oil_all = {nk(r.Year, r.Test, r.City, r.Strain) for r in comb[is_oil].itertuples()}
    # index yield rows to source metadata for ADDED oil rows (no placeholder at all)
    yld = comb[comb.Phenotype.eq("YieldBuA")]
    yld_meta = {}
    for pref in (True, False):
        for r in yld.itertuples():
            if is_real(r) == pref:
                yld_meta.setdefault(nk(r.Year, r.Test, r.City, r.Strain), r)

    updated = added = skipped = missing = 0
    add_rows = []
    miss_keys = []
    for r in rec.itertuples():
        k = nk(r.Year, r.Test, r.City, r.Strain)
        if k in oil_idx:
            i = oil_idx[k]
            comb.at[i, "Value_num"] = f"{r.Value_num:g}"
            comb.at[i, "Units"] = "%"
            comb.at[i, "Source"] = r.Source
            updated += 1
        elif k in oil_all:            # already filled (prior run) -> idempotent skip
            skipped += 1
        elif k in yld_meta:
            base = yld_meta[k]._asdict()
            base.pop("Index", None)
            base["Phenotype"] = "Oil"
            base["Value_num"] = f"{r.Value_num:g}"
            base["Units"] = "%"
            base["Source"] = r.Source
            add_rows.append({c: base.get(c) for c in cols})
            added += 1
        else:
            missing += 1
            miss_keys.append((r.Year, r.Test, r.City, r.Strain))
    if add_rows:
        comb = pd.concat([comb, pd.DataFrame(add_rows)[cols]], ignore_index=True)

    print(f"  updated placeholders: {updated}  added paired rows: {added}  "
          f"already-filled(idempotent): {skipped}  unmatched(dropped): {missing}")
    if miss_keys:
        from collections import Counter
        print("  unmatched by (Year,Test):", dict(Counter((y, t) for y, t, _, _ in miss_keys)))
        print("  sample unmatched:", miss_keys[:8])

    for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
        comb.to_csv(SH / name, index=False)
    comb["y"] = pd.to_numeric(comb.Year, errors="coerce")
    for lo, hi, fn in [(1941, 1984, "nust_1941-1984_combined.csv"),
                       (1985, 2004, "nust_1985-2004_combined.csv"),
                       (2005, 2025, "nust_2005-2025_combined.csv")]:
        comb[(comb.y >= lo) & (comb.y <= hi)].drop(columns="y").to_csv(SH / fn, index=False)
    print(f"combined rows: {len(comb):,}; alias + era splits written")
    print("Next: rebuild 11 (wide), then 32 (boxplots).")


if __name__ == "__main__":
    main()
