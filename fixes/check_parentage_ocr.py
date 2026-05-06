import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

df = pd.read_csv("output_1980/combined_1980_parentageTable.csv", dtype=str, keep_default_na=False)
print("ParentageTable shape:", df.shape)
print("Columns:", list(df.columns))

artifacts = [".164-185", "168-1034???", "???", "1.25A"]
ocr_rows = df[df["Strain"].isin(artifacts)]
print(f"\nOCR artifact rows ({len(ocr_rows)}):")
print(ocr_rows.to_string())

print("\nAll unique Strains containing '?' or starting with '.':")
odd = df[df["Strain"].str.contains(r"[?]|\.\d", regex=True)]
print(odd[["Strain","Test","Year","Female"]].to_string())
