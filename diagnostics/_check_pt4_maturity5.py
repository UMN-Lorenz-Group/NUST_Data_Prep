"""Read PT-IV Maturity block at row 1621 (tp7 marker) and compute DOY vs CSV."""
import sys, openpyxl, datetime
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
XLSX = ROOT / "input_1980/1980/Sojabone-1980 (90-164 OR).xlsx"
CSV  = ROOT / "output_1980/validated/combined_1980_phenotypesTable_approved.csv"

wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active

def doy_1980(v):
    if isinstance(v, (datetime.datetime, datetime.date)):
        return datetime.date(1980, v.month, v.day).timetuple().tm_yday
    return None

# PT-IV maturity block is at row 1621 (tp7 marker at 1620)
START = 1621
cols_raw = [ws.cell(row=START, column=c).value for c in range(1, 14)]
print(f"Header row {START}: {cols_raw}")

# Build location -> column map
loc_cols = {}
for c in range(2, 14):
    h = ws.cell(row=START, column=c).value
    if h:
        loc_cols[c] = str(h)

# Reference check row
ref_row = START + 1
ref_strain = ws.cell(row=ref_row, column=1).value
print(f"\nReference strain: {ref_strain}")
ref_doys = {}
for c, name in loc_cols.items():
    v = ws.cell(row=ref_row, column=c).value
    doy = doy_1980(v)
    ref_doys[c] = (name, doy)
    if doy:
        print(f"  {name}: {v.month}/{v.day} -> DOY {doy} (1980 leap)")
    else:
        print(f"  {name}: raw={v}")

# Load CSV PT-IV maturity for comparison
df = pd.read_csv(CSV)
pt4_mat = df[(df["Test"] == "PT-IV") & (df["Phenotype"] == "Maturity")]

def csv_val(strain, city):
    row = pt4_mat[(pt4_mat["Strain"] == strain) & (pt4_mat["City"] == city)]
    return row["Value"].values[0] if len(row) else "NOT FOUND"

print(f"\n{'Strain':25s}  {'Location':20s}  {'XLSX offset':>12}  {'Computed DOY':>12}  {'CSV DOY':>8}  Match?")
print("-" * 90)

FOCUS_LOCS = ["portageville loam", "eldorado", "queenstown"]

for r in range(ref_row + 1, START + 55):
    strain = ws.cell(row=r, column=1).value
    if strain is None:
        break
    if str(strain).startswith(("Date", "*Day", "C.V.", "L.S.D", "Row", "Reps")):
        continue

    for c, (name, ref_doy) in ref_doys.items():
        if not any(loc in name.lower() for loc in FOCUS_LOCS):
            continue
        offset = ws.cell(row=r, column=c).value
        if ref_doy is not None and isinstance(offset, (int, float)):
            computed = ref_doy + int(offset)
        elif isinstance(offset, (datetime.datetime, datetime.date)):
            computed = doy_1980(offset)
            offset = f"(date {offset.month}/{offset.day})"
        else:
            computed = None

        city_short = name.split(".")[-1].strip().split(" ")[0]
        city_full = name.split(".")[-1].strip()
        # strip state prefix e.g. "Mo. Portageville Loam" -> "Portageville Loam"
        city_csv = " ".join(city_full.split()[1:]) if city_full[0].isupper() and len(city_full.split()) > 1 else city_full
        # Handle "Mo. Portageville Loam" -> city_csv="Portageville Loam"
        # strip leading state abbrev word
        parts = city_full.split()
        city_csv = " ".join(parts[1:]) if len(parts) > 1 else city_full

        csv = csv_val(str(strain), city_csv)
        match = "OK" if str(csv) == str(computed) else "DIFF" if computed is not None else "?"
        print(f"{str(strain):25s}  {city_csv:20s}  {str(offset):>12}  {str(computed):>12}  {str(csv):>8}  {match}")
