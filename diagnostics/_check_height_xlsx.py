"""Scan UT-00 section rows 228-280 to find SeedQuality table."""
import openpyxl, sys
sys.stdout.reconfigure(encoding="utf-8")

xlsx_path = r"R:\NUST_Historical_Data\Green-20260427T181938Z-3-001\Green\1980\Sojabone-1980 (1-89 OR).xlsx"
wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
ws = wb["Sheet1"]
rows = list(ws.iter_rows(values_only=True))

print("=== Rows 228–295 (between Height and SeedSize) ===")
for i in range(227, 295):
    row = rows[i]
    if any(v is not None for v in row):
        print(f"  [{i+1:4d}]: {row[:12]}")

print("\n\n=== All tp markers in first 300 rows ===")
for i in range(min(300, len(rows))):
    row = rows[i]
    if row[0] is not None and str(row[0]).startswith("tp"):
        print(f"  [{i+1:4d}]: {row[:4]}")

wb.close()
