"""
consistency_check_1980.py
Cross-table consistency check for 1980 Files4Upload.
Checks:
  1. Strains in phenotypesTable not in strainsTable
  2. Check strains not in strainsTable
  3. Locations in phenotypesTable not in LocationsTable
  4. Locations in phenotypesTable not in metaTable
  5. Strains in parentageTable not in strainsTable (non-GlobalParentage)
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pathlib import Path

UPLOAD = Path(r"C:\Users\ivanv\Desktop\UMN_Projects\NUST_Projects\NUST_Data\NUST_Historical_Data\1980_Processing\Files4Upload")

pheno   = pd.read_csv(UPLOAD / "phenotypesTable1.csv",  dtype=str, keep_default_na=False)
strains = pd.read_csv(UPLOAD / "strainsTable1.csv",     dtype=str, keep_default_na=False)
checks  = pd.read_csv(UPLOAD / "checksTable1.csv",      dtype=str, keep_default_na=False)
locs    = pd.read_csv(UPLOAD / "LocationsTable1.csv",   dtype=str, keep_default_na=False)
meta    = pd.read_csv(UPLOAD / "metaTable1.csv",        dtype=str, keep_default_na=False)
parent  = pd.read_csv(UPLOAD / "parentageTable1.csv",   dtype=str, keep_default_na=False)

ok = True

# 1. Pheno strains in strainsTable
pheno_strains = set(zip(pheno["Strain"], pheno["Test"]))
strain_keys   = set(zip(strains["Strain"], strains["Test"]))
missing_s = pheno_strains - strain_keys
if missing_s:
    print(f"FAIL — {len(missing_s)} pheno (Strain,Test) pairs missing from strainsTable:")
    for s,t in sorted(missing_s)[:20]:
        print(f"  {s} / {t}")
    ok = False
else:
    print("OK — All pheno strains present in strainsTable")

# 2. Check strains in strainsTable
check_strains = set(zip(checks["Strain"], checks["Test"]))
missing_c = check_strains - strain_keys
if missing_c:
    print(f"FAIL — {len(missing_c)} check (Strain,Test) pairs missing from strainsTable:")
    for s,t in sorted(missing_c):
        print(f"  {s} / {t}")
    ok = False
else:
    print("OK — All check strains present in strainsTable")

# 3. Locations in pheno → LocationsTable
pheno_locs = set(zip(pheno["City"], pheno["State"], pheno["Test"]))
loc_keys   = set(zip(locs["City"], locs["State"], locs["Test"]))
missing_l = pheno_locs - loc_keys
if missing_l:
    print(f"FAIL — {len(missing_l)} pheno (City,State,Test) combos missing from LocationsTable:")
    for c,s,t in sorted(missing_l)[:20]:
        print(f"  {c}, {s} / {t}")
    ok = False
else:
    print("OK — All pheno locations present in LocationsTable")

# 4. Locations in pheno → metaTable (Location = City_State key)
meta_locs = set(meta["Location"].unique())
pheno_meta_keys = set(f"{r.City}_{r.State}" for r in pheno[["City","State"]].drop_duplicates().itertuples())
missing_m = pheno_meta_keys - meta_locs
if missing_m:
    print(f"FAIL — {len(missing_m)} pheno City_State keys missing from metaTable:")
    for k in sorted(missing_m):
        print(f"  {k}")
    ok = False
else:
    print("OK — All pheno City_State keys present in metaTable")

# 5. parentageTable strains in strainsTable (skip if Test is GlobalParentage — already filtered by R)
parent_trial = parent[parent["Test"] != "GlobalParentage"]
parent_keys  = set(zip(parent_trial["Strain"], parent_trial["Test"]))
missing_p = parent_keys - strain_keys
if missing_p:
    print(f"FAIL — {len(missing_p)} parentage (Strain,Test) pairs missing from strainsTable:")
    for s,t in sorted(missing_p)[:20]:
        print(f"  {s} / {t}")
    ok = False
else:
    print("OK — All trial parentage strains present in strainsTable")

print()
if ok:
    print("=== ALL CHECKS PASSED ===")
else:
    print("=== SOME CHECKS FAILED — see above ===")
