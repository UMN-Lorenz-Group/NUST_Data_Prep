"""
apply_1988_utpt_relabel.py  (PDF-grounded rebuild of the 1988 early block)
=========================================================================
1988 early-block corruption, resolved against the Red-PDF rosters (ground truth; both the
corpus AND output_1988 share the F4U assembly bug, so neither could be trusted -- the PDF
regional-summary + single-year yield tables were read directly, pp.6/16/27/53).

TRUTH:
  * corpus "UT-0" 1988 = a MERGE of true UT-00 (17 str) + true UT-0 (33 str) under one label
    -> MG-00 read as an empty no-test band, MG-0 mixed two MGs.
  * corpus "UT-I" 1988 = true UT-I  (CORRECT)  -- an earlier relabel attempt wrongly renamed it.
  * corpus "UT-II" 1988 = true UT-II (CORRECT).
FIX = split the merge by complete PDF roster, and REPLACE UT-00 with the image-verified staged
re-extraction (ut00_1988_alltraits.csv, all 8 traits). Reclassify EVERY 1988 row currently in
{UT-00, UT-0, UT-I} by strain:
    strain in UT-0 roster  -> UT-0   (incl M84-xxx/ND-xxxx single-year lines + shared checks
                                      McCall/Dawson/Sibley, which are legit UT-0 members)
    strain in UT-00 roster -> DROP   (superseded by the staged UT-00 file)
    else                   -> UT-I   (true UT-I lines A85/A86/M81-38x/M83-1xx.. + Elgin/Hardin)
Idempotent: reclassification is a pure function of strain; the staged UT-00 rows are stripped by
Source and re-added each run.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/apply_1988_utpt_relabel.py
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
UT00_FILE = S2 / "ut00_1988_alltraits.csv"
CANON = REPO / "reference" / "nust_location_canonical_map.csv"
UT00_TAG = "Recovered_UTPT_1988_UT00"
CC = ["Year", "TestType", "TestMG", "Test", "Variant", "City", "State",
      "Strain", "Strain_raw", "Phenotype", "Value_num", "Units", "IsCheck", "Source"]


def ck(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\([^)]*\)", "", str(s)).lower())


# complete PDF single-year rosters (1988_done.pdf p6 UT-00, p16 UT-0)
UT00_ROSTER = {ck(x) for x in [
    "Clay", "Maple Presto", "Maple Ridge", "McCall", "M84-93", "M84-456", "ND867", "ND868",
    "ND941", "ND2337", "ND2338", "ND2353", "OT84-12", "OT85-5", "OT87-7", "OT87-8", "OT87-12"]}
UT0_ROSTER = {ck(x) for x in [
    "Dawson", "Glenwood", "McCall", "Sibley", "M81-18", "M81-27", "M83-715", "M83-727",
    "M83-744", "M83-766", "M83-770", "M84-74", "M84-140", "M84-293", "M84-302", "M84-389",
    "M84-390", "M84-395", "M84-414", "M84-449", "M84-568", "M84-574", "M84-748", "M84-756",
    "M84-833", "M84-850", "ND1019", "ND2328", "ND2329", "ND2330", "ND2361", "ND2373", "OT86-5"]}


def norm_strain(s):
    return re.sub(r"\s+", "", re.sub(r"\s*\([^)]*\)", "", str(s)).strip())


def load_canon():
    m = pd.read_csv(CANON, dtype=str)
    by = {}
    for r in m.itertuples():
        by.setdefault((str(r.normkey), str(r.norm_state)), (r.canon_city, r.canon_state))
        by.setdefault((str(r.normkey), None), (r.canon_city, r.canon_state))
    return by


def classify(strain):
    k = ck(strain)
    if k in UT0_ROSTER:
        return ("UT-0", "0")
    if k in UT00_ROSTER:
        return None            # drop -> superseded by staged UT-00 file
    return ("UT-I", "I")       # true UT-I remainder


def main():
    comb = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
    # strip prior staged-UT-00 rows + any leftover relabel tag from earlier attempts
    comb = comb[comb.Source != UT00_TAG].copy()
    comb["Source"] = comb.Source.astype(str).str.replace("|relabel1988", "", regex=False)

    blk = (comb.Year == "1988") & comb.Test.isin(["UT-00", "UT-0", "UT-I"])
    n_blk = int(blk.sum())
    to_ut0 = to_uti = dropped = 0
    drop_idx = []
    for i in comb.index[blk]:
        res = classify(comb.at[i, "Strain"])
        if res is None:
            drop_idx.append(i)
            dropped += 1
        else:
            comb.at[i, "Test"], comb.at[i, "TestMG"] = res
            if res[0] == "UT-0":
                to_ut0 += 1
            else:
                to_uti += 1
    comb = comb.drop(index=drop_idx)
    print(f"reclassified {n_blk} early-block rows: ->UT-0 {to_ut0}, ->UT-I {to_uti}, "
          f"dropped(UT-00 superseded) {dropped}")

    # fold the staged, image-verified UT-00 (all traits); normalize to corpus conventions
    canon = load_canon()
    u = pd.read_csv(UT00_FILE, dtype=str)
    u["Value_num"] = pd.to_numeric(u.Value_num, errors="coerce")
    u = u[u.Value_num.notna()]
    checkset = {ck(s) for s in comb.loc[comb.IsCheck.isin(["1", "1.0", "True"]), "Strain"].dropna()}
    rows = []
    for r in u.itertuples():
        nk = ck(r.City)
        city, state = (canon.get((nk, str(r.State))) or canon.get((nk, None)) or (r.City, r.State))
        strain = norm_strain(r.Strain)
        rows.append({"Year": "1988", "TestType": "UT", "TestMG": "00", "Test": "UT-00",
                     "Variant": "Conventional", "City": city, "State": state, "Strain": strain,
                     "Strain_raw": str(r.Strain), "Phenotype": r.Phenotype, "Value_num": r.Value_num,
                     "Units": r.Units, "IsCheck": "1" if ck(strain) in checkset else "0",
                     "Source": UT00_TAG})
    f = pd.DataFrame(rows)
    print(f"folded staged UT-00: +{len(f)} rows, {f.Strain.nunique()} strains, "
          f"phenos={dict(f.Phenotype.value_counts())}")

    out = pd.concat([comb, f[CC]], ignore_index=True)
    for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
        out.to_csv(SH / name, index=False)
    out["_y"] = pd.to_numeric(out.Year, errors="coerce")
    for lo, hi, fn in [(1941, 1984, "nust_1941-1984_combined.csv"),
                       (1985, 2004, "nust_1985-2004_combined.csv"),
                       (2005, 2025, "nust_2005-2025_combined.csv")]:
        out[(out._y >= lo) & (out._y <= hi)].drop(columns="_y").to_csv(SH / fn, index=False)
    print(f"combined -> {len(out):,} rows; alias + era splits written. Next: 11, then 32.")


if __name__ == "__main__":
    main()
