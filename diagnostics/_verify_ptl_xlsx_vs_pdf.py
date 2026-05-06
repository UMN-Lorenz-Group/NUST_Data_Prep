"""Verify XLSX tp7 offsets (ref=DOY 268) match PDF for all 13 flagged strains."""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from pathlib import Path

# XLSX tp7 offsets from the block (Union(IV)=REF, actual DOY=268)
REF_DOY = 268
XLSX_OFFSETS = {
    "Union (IV)":      0,
    "Williams79 (III)":-5,
    "A79-331020":      4,
    "A79-335034":     -6,
    "A79-336007":     -1,
    "A79-337020":     -1,
    "C1585":           3,
    "C1586":          -1,
    "C1587":           0,
    "C1588":           4,
    "C1589":           3,
    "HC76-4449":       7,
    "HC77-982":       -4,
    "HC77-1165":      -4,
    "HC77-5481":      -4,
    "HC77-5686":      -4,
    "K1033 Douglas":   8,
    "K1061":           9,
    "K1062":          -4,
    "K1063":          10,
    "K1066":           6,
    "K1067":           3,
    "Ky78-405":        9,
    "Ky78-1214":       9,
    "L77-515":        -3,
    "L77-546":        -3,
    "L77-8043":        3,
    "L77-8079":        3,
    "L77-8209":       10,
    "LN1053":          6,
    "LN1057":          8,
    "LN1058":          0,
    "LN1059":          7,
    "LS78-229":       23,
    "LS78-335":       22,
    "LS78-344":       17,
}

CSV = Path("output_1980/validated/combined_1980_phenotypesTable_approved.csv")
df = pd.read_csv(CSV)
ptl = df[(df["Test"]=="PT-IV") & (df["City"]=="Portageville Loam") & (df["Phenotype"]=="Maturity")]

qc = pd.read_csv("output_1980/qc/qc_1980_values.csv")
qc_ptl = qc[(qc["Test"]=="PT-IV") & (qc["City"]=="Portageville Loam") & (qc["phenotype"]=="Maturity")]
pdf_vals = dict(zip(qc_ptl["strain"], qc_ptl["pdf_value"]))

print(f"{'Strain':25s}  {'XLSX DOY':>8}  {'CSV DOY':>8}  {'PDF DOY':>8}  Status")
print("-" * 75)
patches_needed = []
for strain, offset in XLSX_OFFSETS.items():
    xlsx_doy = REF_DOY + offset
    csv_row = ptl[ptl["Strain"]==strain]
    csv_doy = int(csv_row["Value"].values[0]) if len(csv_row) else "MISSING"
    pdf_doy = pdf_vals.get(strain, "NOT IN QC")

    xlsx_pdf_match = isinstance(pdf_doy, (int,float)) and isinstance(xlsx_doy, int) and abs(float(xlsx_doy)-float(pdf_doy)) < 0.5
    csv_pdf_match  = isinstance(pdf_doy, (int,float)) and isinstance(csv_doy,  int) and abs(float(csv_doy) -float(pdf_doy)) < 0.5

    if isinstance(csv_doy, int) and isinstance(pdf_doy, (int,float)) and not csv_pdf_match:
        status = "PATCH"
        patches_needed.append((strain, float(pdf_doy)))
    elif csv_pdf_match:
        status = "OK"
    else:
        status = f"unk(pdf={pdf_doy})"

    print(f"{strain:25s}  {xlsx_doy:>8}  {str(csv_doy):>8}  {str(pdf_doy):>8}  {status}")

print(f"\nPatches needed: {len(patches_needed)}")
for s, v in patches_needed:
    print(f"  {s:25s} -> {v}")
