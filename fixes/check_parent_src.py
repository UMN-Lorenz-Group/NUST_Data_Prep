import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
df = pd.read_csv("output_1980/combined_1980_parentageTable.csv", dtype=str, keep_default_na=False)
targets = ["Century", "Hardin", "L74D", "William", "L74D-609"]
for t in targets:
    rows = df[df["Strain"].str.contains(t, case=False, regex=False)]
    if len(rows):
        print(f"Rows containing '{t}':")
        print(rows[["Strain","Test","Year"]].to_string())
        print()
