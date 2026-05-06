import pandas as pd, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

locs = pd.read_csv("output_1980/combined_1980_locationsTable.csv")
print(f"locationsTable: {len(locs)} rows, cols: {locs.columns.tolist()}")
print(f"  lat filled: {locs['lat'].notna().sum()} / {len(locs)}")
if locs['lat'].isna().any():
    print(f"  Missing:\n{locs[locs['lat'].isna()][['City','State','Test']].to_string(index=False)}")
else:
    print("  All coords present")

print()
ph = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
print(f"phenotypesTable: {len(ph)} rows")
print(f"  MaturityDOY filled: {ph['Maturity'].notna().sum()} / {len(ph)}")
print(f"  Columns: {ph.columns.tolist()}")

print()
checks = pd.read_csv("output_1980/combined_1980_checksTable.csv")
print(f"checksTable: {len(checks)} rows, cols: {checks.columns.tolist()}")
print(checks.head(5).to_string(index=False))
