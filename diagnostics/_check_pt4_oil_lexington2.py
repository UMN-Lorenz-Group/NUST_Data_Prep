"""Read PT-IV Oil block at row 1906, check L77-8079 and L77-8209 at Lexington."""
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

START = 1907  # header row (tp12b marker at 1906)
cols = [ws.cell(row=START, column=c).value for c in range(1, 12)]
print(f"Header: {cols}")

# Find Lexington column
lex_col = None
for c in range(1, 12):
    if "lexington" in str(ws.cell(row=START, column=c).value or "").lower():
        lex_col = c
        print(f"Lexington column: {c} ('{ws.cell(row=START, column=c).value}')")
        break

if lex_col is None:
    print("Lexington not found in this block.")
else:
    print(f"\n{'Strain':25s}  {'XLSX Oil':>10}  {'CSV Oil':>10}  Match?")
    print("-" * 55)

    df = pd.read_csv(CSV)
    pt4_oil = df[(df["Test"] == "PT-IV") & (df["Phenotype"] == "Oil")]

    for r in range(START + 1, START + 50):
        strain = ws.cell(row=r, column=1).value
        if strain is None:
            break
        if str(strain).startswith(("Date", "*Day", "C.V.", "L.S.D", "Row", "Reps")):
            continue
        xlsx_val = ws.cell(row=r, column=lex_col).value

        row = pt4_oil[(pt4_oil["Strain"] == str(strain)) & (pt4_oil["City"] == "Lexington")]
        csv_val = row["Value"].values[0] if len(row) else "NOT FOUND"

        match = ""
        if xlsx_val is not None and str(csv_val) != "NOT FOUND":
            match = "OK" if abs(float(xlsx_val) - float(csv_val)) < 0.05 else "DIFF"

        flag = " <-- ISSUE-9" if str(strain) in ("L77-8079", "L77-8209") else ""
        print(f"{str(strain):25s}  {str(xlsx_val):>10}  {str(csv_val):>10}  {match}{flag}")
