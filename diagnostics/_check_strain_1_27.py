import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

df = pd.read_csv("output_1980/Sojabone-1980_1-89_OR_phenotypes.csv")

# All strains in UT-II (Group_5) — unique, in order of first appearance
utii = df[df["Test"] == "Group_5"].drop_duplicates(subset="Strain")[["Strain"]]
print("=== All strains in Group_5 (UT-II), in order ===")
for i, row in utii.reset_index(drop=True).iterrows():
    marker = " <-- OCR ERROR?" if str(row["Strain"]).strip() == "1.27" else ""
    print(f"  {i:3d}  {row['Strain']}{marker}")
