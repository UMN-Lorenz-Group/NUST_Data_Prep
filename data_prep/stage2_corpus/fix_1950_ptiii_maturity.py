"""
fix_1950_ptiii_maturity.py
==========================
Corrects the 1950 Preliminary Test Group-III (PT-III) Maturity DOY, which was reconstructed by
F4U with a WRONG per-location Lincoln anchor at 3 of its 4 locations (West Lafayette correct;
Worthington/Urbana/Columbia inflated ~+17..+35 days). Surfaced by the UT/PT split maturity plot
(PT-III 1950 median ~295 vs same-year UT-III ~274) and proven by the shared check Lincoln matching
UT-III at West Lafayette but 16-36 d later at the other three sites.

Ground truth = Red PDF 1950 Table 43 ("Summary of maturity data, days earlier/later than Lincoln
... Preliminary Test, Group III, 1950", p.83): maturity is an OFFSET vs Lincoln (the corpus
preserved these offsets exactly), and the "Lincoln matured" row gives the true anchor DATES ->
DOY (1950 non-leap): West Lafayette 10/4=277, Worthington 9/22=265, Urbana 9/30=273, Columbia
9/15=258.

Fix: re-anchor. For each location, correction = current_PT-III-1950_Lincoln_DOY - true_anchor;
new_DOY = old_DOY - correction. (Offsets untouched, so every strain is corrected consistently.)

Idempotent + guarded: only acts while the anomaly signature is present (PT-III 1950 Lincoln at
Columbia still ~293, i.e. > true 258 + a margin). Re-running after the fix is a no-op.

Usage: PYTHONUTF8=1 uv run python data_prep/stage2_corpus/fix_1950_ptiii_maturity.py [--apply]
Then rebuild 11 (wide) + 12 (era) + regenerate the split/boxplots.
"""
import os
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(os.environ.get("NUST_REPO", "C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep"))
SH = REPO / "analysis" / "data" / "_shared"
TAG = "|fix_1950_ptiii_mat"
# true Lincoln anchor DOY per location, from PDF Table 43 "Lincoln matured" (1950, non-leap)
TRUE_ANCHOR = {"West Lafayette": 277, "Worthington": 265, "Urbana": 273, "Columbia": 258}


def main():
    apply = "--apply" in sys.argv
    c = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
    mask = ((c.Year == "1950") & (c.TestMG == "III") & (c.TestType == "PT")
            & (c.Phenotype == "Maturity"))
    sub = c[mask].copy()
    sub["v"] = pd.to_numeric(sub.Value_num, errors="coerce")
    if sub.empty:
        sys.exit("no 1950 PT-III maturity rows found")

    # current (wrong) Lincoln anchor per location
    lin = sub[sub.Strain.str.contains("Lincoln", case=False, na=False)]
    cur_anchor = {r.City: r.v for r in lin.itertuples()}
    print("location | current Lincoln DOY | true (PDF) | correction")
    corr = {}
    for loc, true in TRUE_ANCHOR.items():
        cur = cur_anchor.get(loc)
        if cur is None:
            continue
        corr[loc] = int(round(cur - true))
        print(f"  {loc:16s} | {cur:6.0f} | {true:5d} | {corr[loc]:+d}")

    # guard: signature present?
    if cur_anchor.get("Columbia", 0) <= TRUE_ANCHOR["Columbia"] + 10:
        print("\nsignature ABSENT (already fixed) -> no-op.")
        return

    # validate on the OTHER shared check (Chief) vs UT-III before applying
    chief_pt = sub[sub.Strain.str.fullmatch("Chief", case=False, na=False)]
    utc = c[(c.Year == "1950") & (c.TestMG == "III") & (c.TestType == "UT")
            & (c.Phenotype == "Maturity") & c.Strain.str.fullmatch("Chief", case=False, na=False)].copy()
    utc["v"] = pd.to_numeric(utc.Value_num, errors="coerce")
    ut_chief = {r.City: r.v for r in utc.itertuples()}
    print("\nvalidation — Chief (shared check): corrected PT vs UT-III")
    for r in chief_pt.itertuples():
        newv = pd.to_numeric(r.Value_num, errors="coerce") - corr.get(r.City, 0)
        u = ut_chief.get(r.City)
        flag = "OK" if (u is not None and abs(newv - u) <= 4) else ("no UT" if u is None else "<<")
        print(f"  Chief {r.City:16s}: PT {r.Value_num}->{newv:.0f}  UT {u}  {flag}")

    n = 0
    for i in c.index[mask]:
        loc = c.at[i, "City"]
        if loc in corr and corr[loc]:
            v = pd.to_numeric(c.at[i, "Value_num"], errors="coerce")
            if pd.notna(v):
                c.at[i, "Value_num"] = f"{v - corr[loc]:g}"
                c.at[i, "Source"] = str(c.at[i, "Source"]) + TAG
                n += 1
    print(f"\ncorrected {n} PT-III 1950 maturity rows")
    if apply:
        for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
            c.to_csv(SH / name, index=False)
        c["_y"] = pd.to_numeric(c.Year, errors="coerce")
        for lo, hi, fn in [(1941, 1984, "nust_1941-1984_combined.csv"),
                           (1985, 2004, "nust_1985-2004_combined.csv"),
                           (2005, 2025, "nust_2005-2025_combined.csv")]:
            c[(c._y >= lo) & (c._y <= hi)].drop(columns="_y").to_csv(SH / fn, index=False)
        print("APPLIED: combined + alias + era splits written. Next: 11, 12, replot.")
    else:
        print("(dry run; pass --apply to write)")


if __name__ == "__main__":
    main()
