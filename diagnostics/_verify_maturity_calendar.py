"""
Cross-check stored DOY values against the source PDF anchor dates
to determine whether the 1980 XLSX used the perpetual or leap-year calendar.

The source PDF shows the anchor check's maturity as M/D calendar dates.
We compare those to the DOY values stored in the combined phenotypesTable.
"""
import sys, re
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from datetime import date
import calendar

YEAR = 1980
print(f"Is {YEAR} a leap year? {calendar.isleap(YEAR)}")
print()

ph = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
ck = pd.read_csv("output_1980/combined_1980_checksTable.csv")
mat = ph[(ph["Phenotype"] == "Maturity") & (ph["City"] != "Mean")].copy()

check_strains = set(ck["Strain"].str.strip())
print(f"Check strains: {sorted(check_strains)}")
print()

# Load PDF-derived anchor dates from the cached JSON (if available)
import os, json
pdf_json = "output_1980/check_maturity_pdf_raw_1980.json"
if os.path.exists(pdf_json):
    with open(pdf_json, encoding="utf-8") as f:
        pdf_data = json.load(f)

    print("=== PDF anchor dates vs stored DOY values ===")
    print(f"{'Test':<10} {'City':<18} {'PDF M/D':<10} {'Perp DOY':<10} {'Leap DOY':<10} {'Stored DOY':<12} {'Calendar used'}")
    print("-" * 90)

    for entry in pdf_data.get("anchors", []):
        test = entry["test"]
        ref  = entry.get("reference_check", "?")
        for loc in entry.get("locations", []):
            city      = loc["city"].strip()
            md_str    = loc.get("maturity_date", "")
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})$', md_str.strip())
            if not m:
                continue
            mo, dy     = int(m.group(1)), int(m.group(2))
            perp_doy   = date(YEAR - 1, mo, dy).timetuple().tm_yday if mo <= 2 else \
                         date(YEAR, mo, dy).timetuple().tm_yday - 1  # approximate perpetual
            leap_doy   = date(YEAR, mo, dy).timetuple().tm_yday

            # Look up stored DOY for this check strain at this test×city
            mask = (
                (mat["Test"] == test) &
                (mat["City"].str.strip() == city) &
                (mat["Strain"].str.strip() == ref.strip())
            )
            stored_rows = mat[mask]["Value"].dropna()
            stored = stored_rows.iloc[0] if len(stored_rows) > 0 else "NOT FOUND"

            try:
                stored_f = float(str(stored))
                cal = "LEAP" if abs(stored_f - leap_doy) < abs(stored_f - perp_doy) else "PERPETUAL"
                diff_leap = stored_f - leap_doy
                diff_perp = stored_f - perp_doy
                match_str = f"{cal} (vs leap: {diff_leap:+.0f}, vs perp: {diff_perp:+.0f})"
            except Exception:
                match_str = "---"

            print(f"{test:<10} {city:<18} {md_str:<10} {perp_doy:<10} {leap_doy:<10} {str(stored):<12} {match_str}")
else:
    print(f"PDF JSON not found at {pdf_json}")
    print("Run compute_maturity_doy.py with --pdf first, or use --pdf_json with cached result.")
    print()
    # Show anchor table for manual inspection
    anchors = pd.read_csv("output_1980/maturity_anchors_1980.csv")
    print("Anchor DOY table (all values):")
    print(anchors.to_string(index=False))
    print()
    print("Interpret: for Sep dates, perpetual=DOY-1, leap=DOY")
    print("e.g., if anchor says 252 for UT-0/Rosemount:")
    print("  Perpetual interpretation: Sep 9 (252 in perpetual = Sep 9)")
    print("  Leap interpretation:      Sep 8 (DOY 252 in 1980 = Sep 8)")
