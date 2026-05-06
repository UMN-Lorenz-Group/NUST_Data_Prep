import pandas as pd

df = pd.read_csv("output_1980/combined_1980_MetaTable.csv", dtype=str, keep_default_na=False)

# Show full null rows
null_rows = df[df["Value"].str.strip() == ""]
print("Full null rows:")
print(null_rows.to_string())

# Check phenotypesTable for plain Portageville
pheno = pd.read_csv("output_1980/validated/combined_1980_phenotypesTable_approved.csv", dtype=str, keep_default_na=False)
pv_pheno = pheno[pheno["City"].str.startswith("Portageville")]
print("\nPortageville cities in phenotypesTable:")
print(pv_pheno[["City","State","Test"]].drop_duplicates().to_string())
