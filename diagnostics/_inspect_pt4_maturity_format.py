"""Check existing PT-IV Maturity rows in approved CSV for format, and
   read the tp7 XLSX block to get all Portageville Loam values."""
import sys, openpyxl, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from pathlib import Path

ROOT = Path(".")
CSV  = ROOT / "output_1980/validated/combined_1980_phenotypesTable_approved.csv"
XLSX = ROOT / "input_1980/1980/Sojabone-1980 (90-164 OR).xlsx"

# --- existing PT-IV Maturity rows (format check) ---
df = pd.read_csv(CSV)
pt4_mat = df[(df["Test"]=="PT-IV") & (df["Phenotype"]=="Maturity")].head(10)
print("=== Existing PT-IV Maturity rows (sample) ===")
print(pt4_mat[["Test","City","State","Strain","Phenotype","Value","Units"]].to_string(index=False))
print()

# --- XLSX tp7 block ---
wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active

# Locate tp7 marker (confirmed at row 1620)
TP7_MARKER_ROW = 1620
HEADER_ROW     = 1621

print(f"=== tp7 header (row {HEADER_ROW}) ===")
headers = [ws.cell(row=HEADER_ROW, column=c).value for c in range(1, 15)]
print(headers)
print()

# Find Portageville Loam column
ptl_col = None
for c in range(1, 15):
    val = str(ws.cell(row=HEADER_ROW, column=c).value or "").lower()
    if "portageville" in val and "loam" in val:
        ptl_col = c
        print(f"Portageville Loam column: {c}  header='{ws.cell(row=HEADER_ROW, column=c).value}'")
        break
if ptl_col is None:
    # try just portageville (first occurrence)
    for c in range(1, 15):
        val = str(ws.cell(row=HEADER_ROW, column=c).value or "").lower()
        if "portageville" in val:
            ptl_col = c
            print(f"Portageville col (first): {c}  header='{ws.cell(row=HEADER_ROW, column=c).value}'")
            break
print()

def to_doy(val):
    """Convert an XLSX cell value to 1980 DOY."""
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val.timetuple().tm_yday
    if isinstance(val, (int, float)):
        # Excel serial date: offset from 1899-12-30
        dt = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=int(val))
        return dt.timetuple().tm_yday
    # string like "9/15" or "9/15/1980"
    s = str(val).strip()
    for fmt in ("%m/%d/%Y", "%m/%d", "%-m/%-d"):
        try:
            dt = datetime.datetime.strptime(s, fmt)
            if dt.year == 1900:
                dt = dt.replace(year=1980)
            return dt.timetuple().tm_yday
        except ValueError:
            pass
    return f"UNPARSED:{val}"

print(f"{'Strain':30s}  {'Raw value':15s}  {'DOY':>5}")
print("-" * 55)
for r in range(HEADER_ROW + 1, HEADER_ROW + 60):
    strain = ws.cell(row=r, column=1).value
    if strain is None:
        break
    strain_s = str(strain).strip()
    if strain_s.startswith(("Date", "*Day", "C.V.", "L.S.D", "Row", "Reps", "Means", "---")):
        continue
    raw = ws.cell(row=r, column=ptl_col).value if ptl_col else "N/A"
    doy = to_doy(raw) if ptl_col else "N/A"
    print(f"{strain_s:30s}  {str(raw):15s}  {str(doy):>5}")
