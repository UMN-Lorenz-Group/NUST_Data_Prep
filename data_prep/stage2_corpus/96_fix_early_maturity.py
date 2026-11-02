"""
96_fix_early_maturity.py
========================
Clean the pre-1990 implausible Maturity values (DOY outside [200,315]) — the
documented partial-DOY-conversion remainder. Two paths:

  1. RE-ANCHOR offset-form values (v < 150) where the extracted maturity anchor
     exists: DOY = AnchorDOY(Year,Test,City) + offset, from the per-year
     output_files/output_<y>/combined_<y>_maturityAnchorsTable.csv. The corpus
     location format is messy ("Evansville IN_1" = city + space-state + _rep);
     nc() strips the _N suffix and trailing state code so it matches the table.
  2. NULL the rest (no anchor table available = poor-print/sparse-source cells;
     summary-MEAN pseudo-locations; anchor-misreads) — a wrong/offset value is
     worse than missing, and these aren't recoverable from existing data.

Non-destructive: writes *.earlymatfixed.csv; --replace swaps in place
(backup .pre_earlymatfix.bak).

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/96_fix_early_maturity.py [--replace]
"""
import argparse
import csv
import glob
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
WIDE = REPO / "analysis/data/_shared/NUST_1941_2025_data_wide.csv"
LO, HI = 200, 315          # plausible maturity DOY range
OFFSET_MAX = 150           # value below this = un-anchored offset

STATES = set("ia il in mi mn ne oh sd nd ks mo ky pa ny va md de wi nj ont man que "
             "ar tn ms al ga sc nc la tx ok co ut".split())


def nt(t):
    return re.sub(r"[^A-Z0-9]", "", str(t).upper())


def nc(s):
    s = re.sub(r"_\d+$", "", str(s).strip())          # drop _1/_2 rep suffix
    parts = re.split(r"[_ ]+", s.lower())
    if len(parts) > 1 and parts[-1] in STATES:
        parts = parts[:-1]
    return re.sub(r"[^a-z0-9]", "", "".join(parts))


def load_anchors():
    anc = {}
    for f in glob.glob(str(REPO / "output_files/output_*/combined_*_maturityAnchorsTable.csv")):
        for x in csv.DictReader(open(f, encoding="utf-8", errors="replace")):
            if (x.get("AnchorDOY") or "").strip():
                try:
                    anc[(x["Year"], nt(x["Test"]), nc(x["City"]))] = float(x["AnchorDOY"])
                except ValueError:
                    pass
    return anc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()

    anc = load_anchors()
    print(f"maturity anchor cells loaded: {len(anc)}")

    out = WIDE.with_suffix(".earlymatfixed.csv")
    n = reanc = nulled = 0
    reanc_y = Counter(); null_y = Counter()
    with open(WIDE, newline="", encoding="utf-8", errors="replace") as fi, \
         open(out, "w", newline="", encoding="utf-8") as fo:
        r = csv.DictReader(fi); cols = r.fieldnames
        w = csv.DictWriter(fo, fieldnames=cols); w.writeheader()
        for x in r:
            n += 1
            try:
                y = int(x.get("Year", ""))
            except ValueError:
                y = None
            if y is not None and y < 1990:
                m = (x.get("Maturity") or "").strip()
                try:
                    v = float(m)
                except ValueError:
                    v = None
                if v is not None and not (LO <= v <= HI):
                    d = None
                    if v < OFFSET_MAX:   # offset-form -> try re-anchor
                        a = anc.get((x["Year"], nt(x.get("Experiment")), nc(x.get("Location"))))
                        if a is not None and LO <= a + v <= HI:
                            d = int(round(a + v))
                    if d is not None:
                        x["Maturity"] = str(d); reanc += 1; reanc_y[x["Year"]] += 1
                    else:
                        x["Maturity"] = ""; nulled += 1; null_y[x["Year"]] += 1
            w.writerow(x)
    print(f"rows={n:,}  RE-ANCHORED from tables={reanc}  NULLed(no anchor)={nulled}")
    print("  re-anchored by year:", dict(sorted(reanc_y.items())))
    print("  NULLed by year:     ", dict(sorted(null_y.items())))
    print(f"  wrote {out.name}")

    if args.replace:
        import shutil
        bak = WIDE.with_suffix(".pre_earlymatfix.bak")
        if not bak.exists():
            shutil.copy2(WIDE, bak)
        shutil.move(str(out), str(WIDE))
        print(f"  replaced {WIDE.name}  (backup {bak.name})")


if __name__ == "__main__":
    main()
