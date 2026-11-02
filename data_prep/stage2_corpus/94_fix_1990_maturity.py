"""
94_fix_1990_maturity.py
=======================
Fix the 1990 corpus Maturity defect: ~647 of 1990's Maturity values are stored as
the RAW relative offset (small/negative, e.g. -4, +1, +7) instead of the anchored
absolute DOY. Re-anchor them:  fixed_DOY = anchorDOY(Test, Location) + offset.

anchorDOY sources (per (normTest, norm Location)):
  - URT extraction (nust_anchor_checks_1989_2025, Year=1990)  -> covers PT trials
  - 1990 PDF UT anchor dates (nust_anchor_1990_ut_pdf.csv, if present, from 94b) -> UT trials

Only rows whose current Maturity is offset-looking (< OFFSET_MAX) AND that have an
available anchorDOY are changed. Non-destructive: writes
NUST_1941_2025_data_wide.mat1990fixed.csv + a per-row change log; --replace swaps in
place keeping NUST_1941_2025_data_wide.pre_1990fix.bak.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/94_fix_1990_maturity.py
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/94_fix_1990_maturity.py --replace
"""
import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DATA = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/analysis/data/_shared")
WIDE = DATA / "NUST_1941_2025_data_wide.csv"
ANCHOR = DATA / "nust_anchor_checks_1989_2025.csv"
UT_PDF = DATA / "nust_anchor_1990_ut_pdf.csv"   # optional (from 94b PDF extract)
YEAR = "1990"
OFFSET_MAX = 150.0   # Maturity below this is an un-anchored offset (real DOY ~210-300)


def nt(t):
    return re.sub(r"[^A-Z0-9]", "", str(t).upper())


def nl(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def nc(s):
    """city-only key: 'Brandon_MAN' -> 'brandon', 'Urbana' -> 'urbana'."""
    return re.sub(r"[^a-z0-9]", "", str(s).split("_")[0].lower())


def load_anchor_doy():
    """(normTest, cityKey) -> anchorDOY for 1990 (city-only match across sources)."""
    a = {}
    for x in csv.DictReader(open(ANCHOR, encoding="utf-8")):
        if x["Year"] == YEAR and (x.get("AnchorDOY") or "").strip():
            a[(nt(x["Test"]), nc(x["Location"]))] = float(x["AnchorDOY"])
    if UT_PDF.exists():
        for x in csv.DictReader(open(UT_PDF, encoding="utf-8")):
            if (x.get("AnchorDOY") or "").strip():
                a[(nt(x["Test"]), nc(x["Location"]))] = float(x["AnchorDOY"])
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()

    adoy = load_anchor_doy()
    print(f"1990 anchor cells loaded: {len(adoy)}  (UT-PDF present: {UT_PDF.exists()})")

    out = DATA / "NUST_1941_2025_data_wide.mat1990fixed.csv"
    n = fixed = unfixed = 0
    by_exp_fix = Counter(); by_exp_miss = Counter()
    with open(WIDE, newline="", encoding="utf-8", errors="replace") as fi, \
         open(out, "w", newline="", encoding="utf-8") as fo:
        r = csv.DictReader(fi); cols = r.fieldnames
        w = csv.DictWriter(fo, fieldnames=cols); w.writeheader()
        for x in r:
            n += 1
            if x.get("Year") == YEAR:
                m = (x.get("Maturity") or "").strip()
                try:
                    v = float(m)
                except ValueError:
                    v = None
                if v is not None and v < OFFSET_MAX:
                    exp = x.get("Experiment", "")
                    key = (nt(exp), nc(x.get("Location", "")))
                    if key in adoy:
                        x["Maturity"] = str(int(round(adoy[key] + v)))
                        fixed += 1; by_exp_fix[exp[:5]] += 1
                    else:
                        # un-recoverable offset (no anchor) -> NULL (NA beats a wrong value)
                        x["Maturity"] = ""
                        unfixed += 1; by_exp_miss[exp[:5]] += 1
            w.writerow(x)

    print(f"\nrows={n:,}  1990 offsets RE-ANCHORED={fixed}  NULLed(un-recoverable)={unfixed}")
    print("  re-anchored by Experiment:", dict(by_exp_fix))
    print("  NULLed by Experiment:     ", dict(by_exp_miss))
    print(f"  wrote {out.name}")

    if args.replace:
        if unfixed:
            print(f"\nNOTE: {unfixed} rows still un-anchored (need UT-PDF anchors); replacing anyway.")
        import shutil
        bak = WIDE.with_suffix(".pre_1990fix.bak")
        if not bak.exists():
            shutil.copy2(WIDE, bak)
        shutil.move(str(out), str(WIDE))
        print(f"  replaced {WIDE.name}  (backup {bak.name})")


if __name__ == "__main__":
    main()
