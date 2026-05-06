import sys, pandas as pd
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

UPDATES = {
    ("Ames",         "IA"):  (41.971272, -93.630787),
    ("Belleville",   "IL"):  (38.533200, -89.894514),
    ("Urbana",       "IL"):  (40.053555, -88.235716),
    ("Lafayette",    "IN"):  (40.480647, -87.004596),
    ("Manhattan",    "KS"):  (39.132250, -96.618083),
    ("East Lansing", "MI"):  (42.630320, -84.437597),
    ("Crookston",    "MN"):  (47.819986, -96.627273),
    ("Lamberton",    "MN"):  (44.233340, -95.304530),
    ("Rosemount",    "MN"):  (44.707076, -93.101168),
    ("Waseca",       "MN"):  (44.073910, -93.526580),
    ("Elora",        "ONT"): (43.636134, -80.406403),
    ("Ottawa",       "ONT"): (45.368323, -75.726330),
}

ref = pd.read_csv("nust_locations_ref.csv")
for (city, state), (lat, lon) in UPDATES.items():
    m = (ref["City"] == city) & (ref["State"] == state)
    ref.loc[m, "lat"]               = lat
    ref.loc[m, "lon"]               = lon
    ref.loc[m, "NeedsVerification"] = 0
    ref.loc[m, "Source"]            = "modern_plotinfo_2024"

ref.to_csv("nust_locations_ref_patched.csv", index=False)
print(f"Saved nust_locations_ref_patched.csv  ({len(ref)} rows)")
print(f"NeedsVerification=1 remaining: {(ref['NeedsVerification']==1).sum()}")
