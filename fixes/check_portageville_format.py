import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from pathlib import Path

UPLOAD = Path(r"C:\Users\ivanv\Desktop\UMN_Projects\NUST_Projects\NUST_Data\NUST_Historical_Data\1980_Processing\Files4Upload")

pheno = pd.read_csv(UPLOAD / "phenotypesTable1.csv", dtype=str, keep_default_na=False)
locs  = pd.read_csv(UPLOAD / "LocationsTable1.csv",  dtype=str, keep_default_na=False)
meta  = pd.read_csv(UPLOAD / "metaTable1.csv",       dtype=str, keep_default_na=False)

print("metaTable columns:", list(meta.columns))

print("\nPortageville in phenotypesTable:")
pv = pheno[pheno["City"].str.startswith("Portageville")]
print(pv[["City","State","Test"]].drop_duplicates().to_string())

print("\nPortageville in metaTable:")
mv = meta[meta["Location"].str.startswith("Portageville")]
print(mv[["Location"]].drop_duplicates().to_string())

print("\nConsistency key format (City + '_' + State):")
for r in pv[["City","State"]].drop_duplicates().itertuples():
    print(f"  '{r.City}_{r.State}'")

print("\nOther multi-word cities in metaTable:")
multi = meta[meta["Location"].str.contains(" ")]
print(sorted(multi["Location"].unique()))
