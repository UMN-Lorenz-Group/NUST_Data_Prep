"""
93_extract_anchor_checks_2016_2021.py
=====================================
Fill 2016 and 2021 in the maturity anchor-check compilation. Unlike the other
years, these have NO maturity-relative-to-anchor (offset) structure in the
source. But the DATED anchor was proven (across all 552 1989-2025 trials, 100%)
to be the INTERMEDIATE check (Phenotype "MG <mg>", never Early-/Late-MG). So:

  - anchor check  := the intermediate check from checksTable1.csv
                     (Phenotype == "MG <testMG>", excluding Early-/Late-/trait rows)
  - anchor DOY    := that check's per-location Maturity from phenotypesTable1.csv
                     (already absolute DOY; no offset reconstruction)
  - per-entry DOY := direct from phenotypesTable1 (RelOffset left blank)

Source (read-only): R:/cfans_agro_lore0149_lorenzlabresearch/NUST_Data/NUST_Data/{2016,2021}/
  checksTable1.csv     Year,Test,Strain,Phenotype
  phenotypesTable1.csv Year,Test,Location,State,Strain,...,Maturity,...

Outputs (analysis/data/): nust_anchor_checks_2016_2021.csv, nust_entry_maturity_2016_2021.csv
SrcEra tag = "<year>-direct" (no offset provenance) when merged into the unified file.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/93_extract_anchor_checks_2016_2021.py
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

NUST = Path(r"R:\cfans_agro_lore0149_lorenzlabresearch\NUST_Data\NUST_Data")
OUT  = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/analysis/data/_shared")
YEARS = [2016, 2021]

MG_FROM_TEST = re.compile(r"^(?:UT|PT)\s*-?\s*(00|0|IV|III|II|I)", re.IGNORECASE)


def parse_mg(test):
    m = MG_FROM_TEST.search(str(test).upper())
    return m.group(1).upper() if m else None


def norm_test(t):
    return re.sub(r"[^A-Z0-9]", "", str(t).upper())


def norm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)\s*$", "", str(s)).lower())


def to_num(s):
    s = str(s).strip()
    try:
        return float(s)
    except ValueError:
        return None


def intermediate_anchor(year):
    """norm_test -> (display_strain, norm_strain) of the intermediate check."""
    fp = NUST / str(year) / "checksTable1.csv"
    inter = defaultdict(dict)
    for x in csv.DictReader(open(fp, encoding="utf-8", errors="replace")):
        test, strain = (x.get("Test") or "").strip(), (x.get("Strain") or "").strip()
        ph = (x.get("Phenotype") or "").strip()
        mg = parse_mg(test)
        if not mg or not strain or strain.upper() == "NA":
            continue
        if ph.upper() == f"MG {mg}":            # plain central MG = intermediate
            inter[norm_test(test)][norm(strain)] = strain
    anchor = {}
    for nt, d in inter.items():
        if len(d) == 1:
            anchor[nt] = next(iter(d.items()))[::-1]   # (display, norm)
        elif d:
            ns, ds = sorted(d.items())[0]               # >1 intermediate -> first; logged
            anchor[nt] = (ds, ns)
            print(f"  {year} {nt}: {len(d)} intermediate checks {sorted(d.values())} -> using {ds}")
    return anchor


def extract_year(year):
    anchor = intermediate_anchor(year)
    ph = NUST / str(year) / "phenotypesTable1.csv"
    anchors, entries = [], []
    # anchor DOY per (test, location): the intermediate check's Maturity
    adoy = {}   # (norm_test, norm_loc) -> doy
    rows = list(csv.DictReader(open(ph, encoding="utf-8", errors="replace")))
    for x in rows:
        nt = norm_test(x.get("Test"))
        a = anchor.get(nt)
        if a and norm(x.get("Strain")) == a[1]:
            d = to_num(x.get("Maturity"))
            if d is not None:
                adoy[(nt, norm(x.get("Location")))] = d
    seen_anchor = set()
    for x in rows:
        test = (x.get("Test") or "").strip()
        nt = norm_test(test)
        mg = parse_mg(test)
        loc = (x.get("Location") or "").strip()
        state = (x.get("State") or "").strip()
        strain = (x.get("Strain") or "").strip()
        a = anchor.get(nt)
        if not a or not strain:
            continue
        is_anchor = int(norm(strain) == a[1])
        d = to_num(x.get("Maturity"))
        if d is not None:
            entries.append((year, test, mg, loc, state, strain, "", d, is_anchor))
        # one anchor row per (test, location)
        akey = (nt, norm(loc))
        if akey in adoy and akey not in seen_anchor:
            seen_anchor.add(akey)
            anchors.append((year, test, mg, loc, state, a[0], "", adoy[akey], "", ""))
    n_tests = len({norm_test(t) for (_, t, *_rest) in anchors})
    print(f"  {year}: {len(anchor)} trial-anchors; {n_tests} tests with DOY; "
          f"{len(anchors)} anchor rows, {len(entries)} entry rows")
    return anchors, entries


def main():
    all_a, all_e = [], []
    for y in YEARS:
        print(f"=== {y} ===")
        a, e = extract_year(y)
        all_a.extend(a); all_e.extend(e)
    with open(OUT / "nust_anchor_checks_2016_2021.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Year", "Test", "MG", "Location", "State", "AnchorStrain",
                    "AnchorDate", "AnchorDOY", "DatePlanted", "DaysToMature"])
        w.writerows(all_a)
    with open(OUT / "nust_entry_maturity_2016_2021.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Year", "Test", "MG", "Location", "State", "Strain",
                    "RelOffset", "MaturityDOY", "IsAnchor"])
        w.writerows(all_e)
    print(f"\nanchor rows: {len(all_a):,}  entry rows: {len(all_e):,}")
    print(f"Wrote 2 CSVs to {OUT}")


if __name__ == "__main__":
    main()
