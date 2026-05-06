import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

a = pd.read_csv("output_1980/combined_1980_maturityAnchorsTable.csv")
print(f"maturityAnchorsTable: {len(a)} rows")
print(f"Source breakdown: {dict(a['Source'].value_counts())}")
print(f"\nReference checks per test:")
for test, grp in a.groupby("Test"):
    refs = grp["ReferenceCheck"].unique()
    print(f"  {test}: {', '.join(refs)}  ({len(grp)} locations)")
print("\nSample rows:")
print(a.head(12).to_string(index=False))
