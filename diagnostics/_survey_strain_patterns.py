"""Survey all strain names in combined_1980 tables for OCR-suspect patterns."""
import sys, re
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

df = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
strains = df["Strain"].dropna().unique()

checks = {
    "DecimalPrefix":    re.compile(r'^\d+\.'),           # 1.27, 1.77-8079
    "IntegerOnly":      re.compile(r'^\d+$'),             # 57073
    "DigitHyphenStart": re.compile(r'^\d+-\d'),           # 78-122028
    "DigitMGCode":      re.compile(r'\(\d+\)\s*$'),       # Pella (111), Hardin (1)
    "AlphaDigitMGCode": re.compile(r'\([A-Za-z]\d+\)\s*$'), # Pella (TII), Corsoy (1I)
    "LoneDigit_MG":     re.compile(r'\(\s*\d\s*\)\s*$'), # (1), (2)
}

found = {k: [] for k in checks}
for s in sorted(strains):
    for label, pat in checks.items():
        if pat.search(s):
            found[label].append(s)

for label, names in found.items():
    if names:
        print(f"\n[{label}] ({len(names)} strains):")
        for n in names:
            print(f"  {n}")
    else:
        print(f"\n[{label}] — none found")
