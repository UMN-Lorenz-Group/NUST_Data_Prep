import pandas as pd

df = pd.read_csv("output_1980/combined_1980_MetaTable.csv", dtype=str, keep_default_na=False)
print("Columns:", list(df.columns))
print("Shape:", df.shape)

null_rows = df[df["Value"].str.strip() == ""]
print(f"\nNull value rows: {len(null_rows)}")
print(null_rows[["Year-Test", "Test-Year", "Location"]].to_string())

pv = df[df["Location"].str.startswith("Portageville")]
print(f"\nPortageville entries: {len(pv)}")
print(pv[["Year-Test", "Test-Year", "Location", "Meta_data_type"]].drop_duplicates().to_string())

print("\nDistinct Locations in metaTable:")
print(sorted(df["Location"].unique()))
