import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

df = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
for s in ["57073", "59218"]:
    rows = df[df["Strain"] == s]
    print(f"--- {s}: {len(rows)} rows, Tests={rows['Test'].unique().tolist()}")
    print(rows[["Strain","Test","City","Phenotype","Value"]].head(5).to_string(index=False))
    print()

# Show surrounding strains in each test for context
for s, test in [("57073", None), ("59218", None)]:
    row0 = df[df["Strain"] == s].iloc[0] if len(df[df["Strain"] == s]) else None
    if row0 is None:
        continue
    t = row0["Test"]
    strains = df[df["Test"] == t].drop_duplicates("Strain")["Strain"].tolist()
    idx = strains.index(s) if s in strains else -1
    print(f"Neighbors of '{s}' in {t}:")
    for i in range(max(0, idx-3), min(len(strains), idx+4)):
        marker = " <--" if strains[i] == s else ""
        print(f"  {i:3d}  {strains[i]}{marker}")
    print()
