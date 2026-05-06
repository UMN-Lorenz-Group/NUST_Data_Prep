"""Check what PT-IV Portageville Loam Maturity rows exist in CSV and XLSX."""
import sys, openpyxl, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from pathlib import Path

ROOT = Path(".")
CSV  = ROOT / "output_1980/validated/combined_1980_phenotypesTable_approved.csv"
XLSX = ROOT / "input_1980/1980/Sojabone-1980 (90-164 OR).xlsx"

df = pd.read_csv(CSV)

# All PT-IV Maturity at Portageville Loam
ptl = df[(df["Test"]=="PT-IV") & (df["City"]=="Portageville Loam") & (df["Phenotype"]=="Maturity")]
print(f"PT-IV / Portageville Loam / Maturity rows in CSV: {len(ptl)}")
if len(ptl):
    print(ptl[["Strain","Value"]].to_string(index=False))

print()

# All PT-IV Maturity (all cities) for a few strains to see reference pattern
ref_strains = ["Union (IV)", "Williams79 (III)", "K1061"]
for s in ref_strains:
    rows = df[(df["Test"]=="PT-IV") & (df["Phenotype"]=="Maturity") & (df["Strain"]==s)]
    print(f"{s}:")
    print(rows[["City","Value"]].to_string(index=False))
    print()

# XLSX tp7 block: re-read with correct reference DOY
wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active

HEADER_ROW = 1621
PTL_COL = 3   # confirmed: Mo. Portageville Loam

# Reference strain is Union(IV) at row 1622
ref_raw = ws.cell(row=HEADER_ROW+1, column=PTL_COL).value
print(f"Union(IV) raw cell value: {ref_raw!r}  type={type(ref_raw).__name__}")

# Force DOY to 259 (9/15/1980 in leap year)
REF_DOY = 259
print(f"Reference DOY (9/15/1980 leap year): {REF_DOY}")
print()

# Read all strains and compute DOY
print(f"{'Strain':30s}  {'Offset':>8}  {'DOY':>5}")
print("-" * 50)
for r in range(HEADER_ROW+1, HEADER_ROW+60):
    strain = ws.cell(row=r, column=1).value
    if strain is None:
        break
    strain_s = str(strain).strip()
    if strain_s.startswith(("Date","*Day","C.V.","L.S.D","Row","Reps","Means","---")):
        continue
    raw = ws.cell(row=r, column=PTL_COL).value
    if raw is None:
        print(f"{strain_s:30s}  {'None':>8}  {'---':>5}")
        continue
    if isinstance(raw, datetime.datetime):
        offset = 0
        doy = REF_DOY  # reference strain itself
    else:
        offset = int(raw)
        doy = REF_DOY + offset
    print(f"{strain_s:30s}  {str(offset) if offset!=0 else 'REF':>8}  {doy:>5}")
