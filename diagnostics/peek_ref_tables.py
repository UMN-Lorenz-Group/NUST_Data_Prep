import pandas as pd
import os

BASE = "C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/Files4Upload"

for fname in ["LocationsTable1.csv", "checksTable1.csv", "phenotypesTable1.csv", "strainsTable1.csv", "parentageTable1.csv"]:
    path = os.path.join(BASE, fname)
    df = pd.read_csv(path)
    print(f"\n=== {fname} ({len(df)} rows) ===")
    print(f"Columns: {list(df.columns)}")
    print(df.head(5).to_string(index=False))

# Also check for MetaTable
for root, dirs, files in os.walk("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025"):
    for f in files:
        if "meta" in f.lower() or "Meta" in f:
            print(f"\nFound: {os.path.join(root, f)}")
            df2 = pd.read_csv(os.path.join(root, f))
            print(f"Columns: {list(df2.columns)}")
            print(df2.head(3).to_string(index=False))
