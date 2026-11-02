"""
apply_maturity_doy.py
=====================
After reviewing maturity_verification_{year}.csv, apply the ComputedDOY values
back to the main combined phenotypesTable.

Safe to re-run: only rows with Phenotype=="Maturity" and a valid ComputedDOY are touched.
All other rows are unchanged.

Usage:
    python apply_maturity_doy.py --year 1980
    python apply_maturity_doy.py --year 1980 --dry_run
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=1980)
    ap.add_argument("--csv_dir", default="output_files/output_1980")
    ap.add_argument("--dry_run", action="store_true", help="Show changes without writing")
    args = ap.parse_args()

    out_dir = Path(args.csv_dir)
    year = args.year

    ph_path   = out_dir / f"combined_{year}_phenotypesTable.csv"
    verif_path = out_dir / f"maturity_verification_{year}.csv"

    print(f"Loading {ph_path.name}...")
    ph = pd.read_csv(ph_path)

    print(f"Loading {verif_path.name}...")
    verif = pd.read_csv(verif_path)

    # Only apply rows that have a ComputedDOY
    to_apply = verif[verif["ComputedDOY"].notna()].copy()
    to_apply["ComputedDOY"] = to_apply["ComputedDOY"].astype(int)

    print(f"\nRows to update: {len(to_apply)}")
    print(f"Status breakdown:\n{to_apply['Status'].value_counts().to_string()}")

    # Build a lookup: (Strain, Year, Test, City) -> ComputedDOY
    to_apply["_key"] = list(zip(
        to_apply["Strain"].astype(str),
        to_apply["Year"].astype(str),
        to_apply["Test"].astype(str),
        to_apply["City"].astype(str),
    ))
    doy_map = dict(zip(to_apply["_key"], to_apply["ComputedDOY"]))

    mat_mask = ph["Phenotype"] == "Maturity"
    ph["_key"] = list(zip(
        ph["Strain"].astype(str),
        ph["Year"].astype(str),
        ph["Test"].astype(str),
        ph["City"].astype(str),
    ))

    updated = 0
    skipped_no_key = 0
    for i in ph[mat_mask].index:
        k = ph.at[i, "_key"]
        if k in doy_map:
            ph.at[i, "Value"] = doy_map[k]
            updated += 1
        else:
            skipped_no_key += 1

    ph.drop(columns=["_key"], inplace=True)

    print(f"\nUpdated:  {updated} rows")
    print(f"Skipped:  {skipped_no_key} rows (no ComputedDOY — null/special)")

    # Sanity check: all remaining Maturity values should be integers or null
    mat_vals = ph[mat_mask]["Value"].dropna()
    non_int = mat_vals[~mat_vals.apply(lambda v: str(v).lstrip("+-").replace(".","",1).isdigit())]
    if len(non_int) > 0:
        print(f"\nWARNING: {len(non_int)} non-numeric Maturity values remain:")
        print(non_int.head(10).to_string())
    else:
        print("\nAll remaining Maturity values are numeric or null. Good.")

    if args.dry_run:
        print("\n[dry_run] No file written.")
        return

    ph.to_csv(ph_path, index=False)
    print(f"\nSaved -> {ph_path}")

    # Show final Maturity range
    mat_final = pd.to_numeric(ph[mat_mask]["Value"], errors="coerce").dropna()
    print(f"Final Maturity DOY range: {int(mat_final.min())} – {int(mat_final.max())}")

if __name__ == "__main__":
    main()
