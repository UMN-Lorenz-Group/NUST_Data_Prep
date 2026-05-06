import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pathlib import Path

UPLOAD = Path(r"C:\Users\ivanv\Desktop\UMN_Projects\NUST_Projects\NUST_Data\NUST_Historical_Data\1980_Processing\Files4Upload")
SRC    = Path(r"C:\Users\ivanv\Desktop\UMN_GIT\NUST_Data_Prep\output_1980")

pheno   = pd.read_csv(UPLOAD / "phenotypesTable1.csv",  dtype=str, keep_default_na=False)
strains = pd.read_csv(UPLOAD / "strainsTable1.csv",     dtype=str, keep_default_na=False)
checks  = pd.read_csv(UPLOAD / "checksTable1.csv",      dtype=str, keep_default_na=False)
parent  = pd.read_csv(UPLOAD / "parentageTable1.csv",   dtype=str, keep_default_na=False)
meta    = pd.read_csv(UPLOAD / "metaTable1.csv",        dtype=str, keep_default_na=False)

# ---- 1. Century/UT-III and Hardin/UT-I ----
print("=== ISSUE 1: Century/UT-III and Hardin/UT-I ===")
for strain, test in [("Century", "UT-III"), ("Hardin", "UT-I")]:
    in_strain = strains[(strains["Strain"]==strain) & (strains["Test"]==test)]
    in_pheno  = pheno[(pheno["Strain"]==strain) & (pheno["Test"]==test)]
    in_check  = checks[(checks["Strain"]==strain) & (checks["Test"]==test)]
    print(f"\n{strain}/{test}:")
    print(f"  strainsTable: {len(in_strain)} rows")
    print(f"  phenotypesTable: {len(in_pheno)} rows")
    print(f"  checksTable: {len(in_check)} rows")
    # also check what Century/Hardin entries exist in strainsTable at all
    all_s = strains[strains["Strain"]==strain]
    print(f"  All {strain} in strainsTable: {all_s[['Test','OriginalStrain']].values.tolist()}")

# ---- 2. Pheno State mismatches for metaTable-missing cities ----
print("\n=== ISSUE 2: metaTable missing City_State keys ===")
for city_state in ["Ashland_KS", "Greenfield_IL", "Harrow_OH", "Sullivan_IL"]:
    city, state = city_state.rsplit("_", 1)
    rows = pheno[pheno["City"]==city]
    print(f"\n{city_state}: {len(rows)} pheno rows, States={rows['State'].unique().tolist()}, Tests={rows['Test'].unique().tolist()}")
    meta_match = meta[meta["Location"].str.startswith(city)]
    print(f"  metaTable entries starting with '{city}': {meta_match['Location'].unique().tolist()}")

# ---- 3. ParentageTable artifacts ----
print("\n=== ISSUE 3: ParentageTable artifact strains ===")
for s in ["Century(11)", "Hardin(A76-102009)", "L74D-609Pixie", "William79"]:
    rows = parent[parent["Strain"]==s]
    print(f"\n'{s}': {len(rows)} rows in parentageTable")
    print(rows[["Strain","Test","Female","Male"]].to_string())
