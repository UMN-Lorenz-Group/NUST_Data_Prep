#!/usr/bin/env python
"""
extract_combined_anchors.py
============================
For years 1987 and 1988 (which use per-test xlsx files instead of an
aggregated Sojabone), read the already-produced
`output_files/output_{year}/combined_{year}_phenotypesTable.csv` and extract
reference-strain Maturity anchors directly.

The combined CSV was produced by `scripts/extract_nust_blocks.py` and
already contains per-(Test, Strain, City) Maturity values. Reference
strain rows have absolute calendar-date values (M-D format), comparator
strains have integer offsets. By filtering for the calendar-date rows
we get one anchor per (Test, City) — no need to walk the 193+ per-test
xlsx files.

Merges into the same `Sojabone-{year}_yellow_standardized.xlsx` anchors
sheet used by the OCR Maturity patcher.

Usage:
    uv run python fixes/extract_combined_anchors.py --years 1987,1988
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

_FIXES_DIR = Path(__file__).parent
sys.path.insert(0, str(_FIXES_DIR))

from apply_patches_corpus_maturity_doy import (  # type: ignore
    canonicalize_city,
    DOY_LO, DOY_HI,
)
from extract_sojabone_anchors import (  # type: ignore
    _normalize_test_code,
    merge_into_standardized,
    REPO_INPUT_ROOT,
    OUT_DIR_DEFAULT,
)

# Calendar-date M-D / M/D with optional .frac and optional trailing *
_CAL_RE = re.compile(r"^(\d{1,2})[-/](\d{1,2})(?:\.\d+)?\*?$")


def extract_combined_anchors(year: int) -> list[dict]:
    """Read combined_{year}_phenotypesTable.csv and extract Maturity
    rows whose Value matches a calendar date — these ARE the reference-
    strain rows. Returns standardized anchor dicts."""
    csv_path = REPO_INPUT_ROOT / f"output_files/output_{year}" / f"combined_{year}_phenotypesTable.csv"
    if not csv_path.exists():
        print(f"  {year}: no combined CSV at {csv_path}")
        return []
    df = pd.read_csv(csv_path, dtype=str)
    if "Phenotype" not in df.columns:
        return []
    mat = df[df["Phenotype"] == "Maturity"].copy()
    if mat.empty:
        return []

    anchors: list[dict] = []
    for _, row in mat.iterrows():
        v = row["Value"]
        if v is None or pd.isna(v):
            continue
        sv = str(v).strip()
        m = _CAL_RE.match(sv)
        if not m:
            continue
        mo, da = int(m.group(1)), int(m.group(2))
        if not (1 <= mo <= 12 and 1 <= da <= 31):
            continue
        try:
            # real report year, NOT a fixed reference year: a non-leap stand-in (this was
            # 2001) puts every post-Feb date 1 day early in a leap year
            doy = date(int(year), mo, da).timetuple().tm_yday
        except ValueError:
            continue
        if not (DOY_LO <= doy <= DOY_HI):
            continue
        # Normalize Test (UPT-X -> PT-X for 1988)
        test_code = _normalize_test_code(str(row["Test"]).strip())
        city = str(row["City"]).strip()
        if not city or not test_code:
            continue
        anchors.append({
            "Test": test_code,
            "City": city,
            "City_canon": canonicalize_city(city),
            "State": str(row.get("State", "") or "").strip(),
            "RefStrain": str(row["Strain"]).strip(),
            "AnchorDate_MD": f"{mo}-{da}",
            "AnchorDOY": int(doy),
            "Tier": "A",
            "Source": f"combined_{year}_phenotypesTable.csv",
        })
    return anchors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="1987,1988",
                    help="Comma-separated list (default: 1987,1988)")
    ap.add_argument("--out_dir", default=str(OUT_DIR_DEFAULT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    years = [int(y) for y in args.years.split(",")]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for year in years:
        print(f"\n=== {year} ===")
        anchors = extract_combined_anchors(year)
        unique = {(a["Test"], a["City_canon"]) for a in anchors}
        print(f"  raw anchor rows: {len(anchors)}  unique (Test, City): {len(unique)}")
        if args.dry_run:
            for a in anchors[:6]:
                print(f"    {a}")
            summary.append({"year": year, "raw": len(anchors), "unique": len(unique), "added": 0})
            continue
        m = merge_into_standardized(year, anchors, out_dir)
        print(f"  merged: added {m['added']} new -> total {m['merged']} in xlsx")
        summary.append({"year": year, "raw": len(anchors), "unique": len(unique), "added": m["added"]})

    print(f"\n=== Summary ===")
    print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    main()
