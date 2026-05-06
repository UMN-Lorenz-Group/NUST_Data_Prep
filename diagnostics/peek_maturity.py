import pandas as pd

df = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
mat = df[df["Phenotype"] == "Maturity"]

print(f"Total Maturity rows: {len(mat)}")
print(f"Null values: {mat['Value'].isna().sum()}")
print(f"Unique value count: {mat['Value'].nunique()}")

vals = sorted(mat["Value"].dropna().unique())
print(f"\nAll unique values ({len(vals)} total):")
for v in vals:
    print(f"  {repr(v)}")

print(f"\nTests: {sorted(mat['Test'].unique())}")
print(f"\nSample rows (first 10):")
print(mat[["Strain","Year","Test","City","State","Phenotype","Value"]].head(10).to_string(index=False))
