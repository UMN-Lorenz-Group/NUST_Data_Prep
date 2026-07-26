#!/usr/bin/env python
"""
compile_maturity_gaps_table.py
===============================
Compile all remaining no-anchor Maturity (Year, Test, City) combos into
ONE consolidated table for visual inspection.

For each gap row, also include:
  - The closest-matching anchor city in the same (Year, Test) - helps
    spot OCR variants like "Indedence" -> "Independence"
  - The set of all Tests in the same year that DO have an anchor at the
    same city - helps spot Test-attribution errors
  - The original F4U City value (not just canon)

Output:
  logs/NUST_maturity_gaps_consolidated.csv        — wide form
  logs/NUST_maturity_gaps_consolidated.md          — human-readable
"""
import sys, re, difflib
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

_FIXES = Path(__file__).parent
sys.path.insert(0, str(_FIXES))

from apply_patches_corpus_maturity_doy import (
    find_f4u, parse_offset, is_doy, canonicalize_city,
)
from apply_patches_corpus_maturity_doy_via_ocr import (
    load_anchors_from_standardized,
)

REPO_ROOT = _FIXES.parent
STD_DIR = REPO_ROOT / "analysis" / "data" / "yellow_standardized"
LOGS = REPO_ROOT / "logs"


def best_anchor_match(city_canon: str, anchor_cities: set[str]) -> str:
    """Find closest-matching anchor city via difflib (helps spot OCR variants)."""
    if not anchor_cities:
        return ""
    matches = difflib.get_close_matches(city_canon, anchor_cities, n=1, cutoff=0.6)
    return matches[0] if matches else ""


def analyze_year(year: int) -> list[dict]:
    """Return list of dicts, one per (Test, City) gap for the year."""
    f4u = find_f4u(year)
    if not f4u:
        return []
    df = pd.read_csv(f4u, dtype=str)
    if "Phenotype" not in df.columns:
        return []
    mat = df[df["Phenotype"] == "Maturity"].copy()
    if mat.empty:
        return []
    anchors, test_means = load_anchors_from_standardized(year, STD_DIR)

    # Index anchors by Test -> set of city_canon
    anchors_by_test: dict[str, set[str]] = {}
    for (t, c), _doy in anchors.items():
        anchors_by_test.setdefault(t, set()).add(c)
    # And by City -> set of Tests (for spotting Test-attribution misses)
    tests_by_city: dict[str, set[str]] = {}
    for (t, c), _doy in anchors.items():
        tests_by_city.setdefault(c, set()).add(t)

    no_anchor: dict[tuple[str, str, str], int] = {}
    for _, row in mat.iterrows():
        v = row["Value"]
        if v is None or pd.isna(v):
            continue
        sv = str(v).strip()
        if is_doy(sv):
            continue
        if parse_offset(sv) is None:
            continue
        t = str(row["Test"]).strip()
        c_raw = str(row["City"]).strip()
        c_canon = canonicalize_city(c_raw)
        if (t, c_canon) in anchors:
            continue
        # State-stripped fallback (same as patcher)
        if len(c_canon) > 2:
            m = re.match(r"^(.+?)([a-z]{2})$", c_canon)
            STATES = {"al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id",
                      "il","in","ia","ks","ky","la","me","md","ma","mi","mn","ms",
                      "mo","mt","ne","nv","nh","nj","nm","ny","nc","nd","oh","ok",
                      "or","pa","ri","sc","sd","tn","tx","ut","vt","va","wa","wv",
                      "wi","wy","on","mb","qc","sk","ab","bc"}
            if m and m.group(2) in STATES:
                if (t, m.group(1)) in anchors:
                    continue
        no_anchor[(t, c_raw, c_canon)] = no_anchor.get((t, c_raw, c_canon), 0) + 1

    rows_out = []
    for (test, city_raw, city_canon), n in no_anchor.items():
        # Find closest anchor city in same Test
        same_test_cities = anchors_by_test.get(test, set())
        nearest = best_anchor_match(city_canon, same_test_cities)
        # Find which other Tests have an anchor at this city
        other_tests_with_city = sorted(tests_by_city.get(city_canon, set()) - {test})
        # Also check state-stripped form
        if not other_tests_with_city and len(city_canon) > 2:
            m = re.match(r"^(.+?)([a-z]{2})$", city_canon)
            if m:
                other_tests_with_city = sorted(tests_by_city.get(m.group(1), set()) - {test})
        rows_out.append({
            "Year": year,
            "Test": test,
            "City_raw": city_raw,
            "City_canon": city_canon,
            "Cells": n,
            "Nearest_anchor_city": nearest,
            "Other_tests_with_city_anchor": ",".join(other_tests_with_city)[:60],
        })
    return rows_out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_csv", default=None,
                    help="Override output CSV path (e.g. for v2 / temp runs "
                         "when the default file is locked by Excel)")
    ap.add_argument("--out_md", default=None, help="Override output MD path")
    args = ap.parse_args()

    all_rows = []
    for year in range(1941, 1989):
        if year == 1975:
            continue
        all_rows.extend(analyze_year(year))

    df = pd.DataFrame(all_rows)
    if df.empty:
        print("No gaps found — corpus is 100% complete!")
        return
    # Sort by City_canon first (groups recurring cities across years),
    # then by Year, then by Test
    df = df.sort_values(["City_canon", "Year", "Test"])

    out_csv = (Path(args.out_csv) if args.out_csv
               else LOGS / "NUST_maturity_gaps_consolidated.csv")
    df.to_csv(out_csv, index=False)
    print(f"Wrote {out_csv.name} ({len(df)} gap rows, {df['Cells'].sum():,} cells)")

    # Markdown: grouped by city
    md = []
    md.append("# Consolidated Maturity Gaps Table")
    md.append("")
    md.append(f"**{len(df):,} (Year, Test, City) combos** across "
              f"**{df['Year'].nunique()} years**, totaling **{df['Cells'].sum():,} "
              f"unanchored Maturity cells**.")
    md.append("")
    md.append("Sorted by City to spot recurring cities/OCR-variant patterns across years.")
    md.append("Columns:")
    md.append("- **City_raw**: as stored in F4U")
    md.append("- **City_canon**: canonical form (spaces/punct stripped, lowercase)")
    md.append("- **Cells**: count of cells with raw offsets at this combo")
    md.append("- **Nearest_anchor_city**: closest-matching city in our anchor set "
              "for the same Test (helps spot OCR variants like Indedence -> Independence)")
    md.append("- **Other_tests_with_city_anchor**: Tests where we DO have an anchor "
              "for this city (helps spot Test-attribution gaps)")
    md.append("")
    md.append("## Table (sorted by City)")
    md.append("")
    md.append("| Year | Test | City_raw | City_canon | Cells | Nearest_anchor | Other_tests_w_anchor |")
    md.append("|---:|:---|:---|:---|---:|:---|:---|")
    for _, r in df.iterrows():
        md.append(f"| {r['Year']} | {r['Test']} | {r['City_raw']} | {r['City_canon']} "
                  f"| {r['Cells']} | {r['Nearest_anchor_city']} "
                  f"| {r['Other_tests_with_city_anchor']} |")

    md.append("")
    md.append("## Recurring cities (appear in 3+ year/Test gap rows)")
    md.append("")
    recurring = df.groupby("City_canon").agg(
        total_cells=("Cells", "sum"),
        n_rows=("Cells", "count"),
        years=("Year", lambda y: sorted(set(y))),
        tests=("Test", lambda t: sorted(set(t))),
    ).reset_index()
    recurring = recurring[recurring["n_rows"] >= 3].sort_values("total_cells", ascending=False)
    md.append("| City_canon | Total cells | Rows | Years | Tests |")
    md.append("|:---|---:|---:|:---|:---|")
    for _, r in recurring.iterrows():
        md.append(f"| {r['City_canon']} | {r['total_cells']} | {r['n_rows']} "
                  f"| {','.join(str(y) for y in r['years'])} "
                  f"| {','.join(r['tests'])} |")

    out_md = (Path(args.out_md) if args.out_md
              else LOGS / "NUST_maturity_gaps_consolidated.md")
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {out_md.name}")


if __name__ == "__main__":
    main()
