"""Cross-check PT-IV Oil values at Lexington in XLSX vs CSV vs PDF QC flags."""
import sys, openpyxl
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
XLSX = ROOT / "input_1980/1980/Sojabone-1980 (90-164 OR).xlsx"
CSV  = ROOT / "output_1980/validated/combined_1980_phenotypesTable_approved.csv"

wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active

# Find tp12b or Oil block for PT-IV — search for rows containing 'Lexington' near 'Oil' or 'tp12'
print("=== Rows containing 'tp12' or 'OIL' ===")
for row in ws.iter_rows():
    for cell in row:
        v = str(cell.value or "").lower()
        if "tp12" in v or v.strip() in ("oil (%)", "oil(%)", "oil"):
            vals = [ws.cell(row=cell.row, column=c).value for c in range(1, 10)]
            print(f"  Row {cell.row} Col {cell.column}: '{cell.value}' -> {vals}")
            break
