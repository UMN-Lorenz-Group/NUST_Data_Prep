import pandas as pd
ph = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
if "id" not in ph.columns:
    ph.insert(0, "id", range(1, len(ph) + 1))
    ph.to_csv("output_1980/combined_1980_phenotypesTable.csv", index=False)
    print(f"Added id column. {len(ph)} rows.")
else:
    print("id column already present.")
