import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pathlib import Path

UPLOAD = Path(r"C:\Users\ivanv\Desktop\UMN_Projects\NUST_Projects\NUST_Data\NUST_Historical_Data\1980_Processing\Files4Upload")
pheno = pd.read_csv(UPLOAD / "phenotypesTable1.csv", dtype=str, keep_default_na=False)
locs  = pd.read_csv(UPLOAD / "LocationsTable1.csv",  dtype=str, keep_default_na=False)

for city, wrong_state, right_state in [
    ("Ashland",    "KS",  "WI"),
    ("Greenfield", "IL",  "IN"),
    ("Harrow",     "OH",  "ONT"),
    ("Sullivan",   "IL",  "IN"),
]:
    rows = pheno[(pheno["City"]==city) & (pheno["State"]==wrong_state)]
    print(f"{city}: {len(rows)} rows with State={wrong_state} (should be {right_state})")
    print(f"  Tests: {rows['Test'].unique().tolist()}")
    # Check LocationsTable
    loc_wrong = locs[(locs["City"]==city) & (locs["State"]==wrong_state)]
    loc_right = locs[(locs["City"]==city) & (locs["State"]==right_state)]
    print(f"  LocationsTable with State={wrong_state}: {len(loc_wrong)} rows")
    print(f"  LocationsTable with State={right_state}: {len(loc_right)} rows -> Tests={loc_right['Test'].unique().tolist()}")
    print()
