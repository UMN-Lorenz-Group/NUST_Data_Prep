"""
95_fix_modern_maturity.py
=========================
Fix the remaining offset-form Maturity values in the MODERN years where my anchor
reference has ground-truth per-entry DOY: 2025 (100% un-converted) + scattered
residuals in 2000-2004 and 2020.

Replaces each offset-looking (< OFFSET_MAX) corpus Maturity with the reference
absolute DOY from nust_entry_maturity_1989_2025.csv (built by scripts 91/92 directly
from the trial files: MaturityDOY = anchorDOY + offset). Match on
(Year, normStrain, cityKey). Un-matched offsets are NULLed (NA beats a wrong value).

Non-destructive: writes *.modmatfixed.csv; --replace swaps in place
(backup .pre_modmatfix.bak).

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/95_fix_modern_maturity.py [--replace]
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
REF  = DATA / "nust_entry_maturity_1989_2025.csv"
ANCHOR = DATA / "nust_anchor_checks_1989_2025.csv"
TARGET_YEARS = {"2000", "2001", "2002", "2003", "2004", "2020", "2025"}
OFFSET_MAX = 200.0


def nm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())


CITY_ALIAS = {"lafayette": "westlafayette", "morehead": "moorhead"}


def nc(s):
    k = re.sub(r"[^a-z0-9]", "", str(s).split("_")[0].lower())
    return CITY_ALIAS.get(k, k)


def nt(t):
    return re.sub(r"[^A-Z0-9]", "", str(t).upper())


def load_ref():
    """Primary: per-entry DOY by (Year, normStrain, city). Fallback: per-cell
    anchorDOY by (Year, normTest, city) -> add the corpus offset."""
    ref = {}
    for x in csv.DictReader(open(REF, encoding="utf-8")):
        if x["Year"] in TARGET_YEARS and (x.get("MaturityDOY") or "").strip():
            try:
                ref[(x["Year"], nm(x["Strain"]), nc(x["Location"]))] = round(float(x["MaturityDOY"]))
            except ValueError:
                pass
    anchor = {}
    for x in csv.DictReader(open(ANCHOR, encoding="utf-8")):
        if x["Year"] in TARGET_YEARS and (x.get("AnchorDOY") or "").strip():
            try:
                anchor[(x["Year"], nt(x["Test"]), nc(x["Location"]))] = float(x["AnchorDOY"])
            except ValueError:
                pass
    return ref, anchor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()

    ref, anchor = load_ref()
    print(f"reference: {len(ref)} per-entry DOY + {len(anchor)} per-cell anchors (target years)")

    out = DATA / "NUST_1941_2025_data_wide.modmatfixed.csv"
    n = fixed = via_anchor = nulled = 0
    fix_y = Counter(); null_y = Counter()
    with open(WIDE, newline="", encoding="utf-8", errors="replace") as fi, \
         open(out, "w", newline="", encoding="utf-8") as fo:
        r = csv.DictReader(fi); cols = r.fieldnames
        w = csv.DictWriter(fo, fieldnames=cols); w.writeheader()
        for x in r:
            n += 1
            y = x.get("Year")
            if y in TARGET_YEARS:
                m = (x.get("Maturity") or "").strip()
                try:
                    v = float(m)
                except ValueError:
                    v = None
                if v is not None and v < OFFSET_MAX:
                    d = ref.get((y, nm(x.get("Strain")), nc(x.get("Location"))))
                    if d is None:   # fallback: per-cell anchorDOY + this row's offset
                        a = anchor.get((y, nt(x.get("Experiment")), nc(x.get("Location"))))
                        if a is not None:
                            d = int(round(a + v)); via_anchor += 1
                    # plausibility guard: maturity DOY < 200 is impossible -> NULL
                    if d is not None and d >= 200:
                        x["Maturity"] = str(int(d)); fixed += 1; fix_y[y] += 1
                    else:
                        x["Maturity"] = ""; nulled += 1; null_y[y] += 1
            w.writerow(x)
    print(f"rows={n:,}  offsets RE-ANCHORED={fixed} (of which {via_anchor} via cell-anchor fallback)  NULLed={nulled}")
    print("  fixed by year: ", dict(sorted(fix_y.items())))
    print("  NULLed by year:", dict(sorted(null_y.items())))
    print(f"  wrote {out.name}")

    if args.replace:
        import shutil
        bak = WIDE.with_suffix(".pre_modmatfix.bak")
        if not bak.exists():
            shutil.copy2(WIDE, bak)
        shutil.move(str(out), str(WIDE))
        print(f"  replaced {WIDE.name}  (backup {bak.name})")


if __name__ == "__main__":
    main()
