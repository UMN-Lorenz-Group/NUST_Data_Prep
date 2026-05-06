"""Fix Loam/Clay in State column of phenotypesTable."""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from pathlib import Path

OUT_DIR = Path("output_1980")
ph = pd.read_csv(OUT_DIR / "combined_1980_phenotypesTable.csv")

for soil in ["Loam", "Clay"]:
    mask = ph["State"] == soil
    if mask.any():
        # Fix City: prepend "Portageville " if not already
        ph.loc[mask, "City"] = ph.loc[mask, "City"].apply(
            lambda c: f"Portageville {soil}" if "Portageville" not in str(c) else
                      (c if soil in str(c) else f"Portageville {soil}")
        )
        ph.loc[mask, "State"] = "MO"
        print(f"  Fixed {mask.sum()} rows: State='{soil}' -> State='MO', City='Portageville {soil}'")

# Final check
CANON = {"IL","IN","IA","MN","WI","MI","OH","MO","ND","SD","KS","NE","KY",
         "MD","VA","PA","NJ","NY","DE","GA","NC","SC","TX","OK","AR","TN",
         "AL","MS","LA","WA","OR","CA","ONT","MAN","SK","AB","BC","QC","NS","NB"}
bad = ph[~ph["State"].isin(CANON)]["State"].value_counts()
if bad.empty:
    print("  All State codes canonical.")
else:
    print(f"  [FLAG] Still non-canonical: {bad.to_dict()}")

ph.to_csv(OUT_DIR / "combined_1980_phenotypesTable.csv", index=False)
print(f"Saved phenotypesTable ({len(ph)} rows). Unique states: {sorted(ph['State'].unique())}")
