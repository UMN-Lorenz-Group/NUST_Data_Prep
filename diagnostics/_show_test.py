"""Show discrepancies for a specific test from QC output CSV.
Usage: python diagnostics/_show_test.py UT-0
"""
import sys, pandas as pd
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).parent.parent
test = sys.argv[1] if len(sys.argv) > 1 else "UT-0"

df = pd.read_csv(ROOT / "output_1980/qc/qc_1980_values.csv")
rows = df[df["Test"] == test].copy()

print(f"{test} discrepancies: {len(rows)} total")
print()
for city in sorted(rows["City"].unique()):
    grp = rows[rows["City"] == city]
    print(f"--- {city} ({len(grp)}) ---")
    for _, r in grp.iterrows():
        note = str(r.get("note", ""))
        note = "" if note == "nan" else f"  -> {note}"
        print(f"  {r['strain']:25s} | {r['phenotype']:12s} | csv={r['csv_value']} pdf={r['pdf_value']} | {r['verdict']}{note}")
    print()
