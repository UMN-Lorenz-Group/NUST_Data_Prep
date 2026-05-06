"""
patch_location_coords.py
Apply 13 farm-level GPS coordinates from 2024_NUST_Locations_PlotInfo.csv
into nust_locations_ref.csv for NeedsVerification=1 rows that matched
modern trial locations.

Skips Ottawa KS (genuine location ambiguity, not a geocoding error).
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

# ── Modern coords to apply  (CityKey, StateKey) -> (new_lat, new_lon) ────────
# Sourced from 2024_NUST_Locations_PlotInfo.csv; verified against known stations.
UPDATES = {
    ("Ames",         "IA"):  (41.971272,  -93.630787),
    ("Belleville",   "IL"):  (38.533200,  -89.894514),
    ("Urbana",       "IL"):  (40.053555,  -88.235716),
    ("Lafayette",    "IN"):  (40.480647,  -87.004596),   # Purdue ACRE; modern calls it "West Lafayette"
    ("Manhattan",    "KS"):  (39.132250,  -96.618083),
    ("East Lansing", "MI"):  (42.630320,  -84.437597),
    ("Crookston",    "MN"):  (47.819986,  -96.627273),
    ("Lamberton",    "MN"):  (44.233340,  -95.304530),
    ("Rosemount",    "MN"):  (44.707076,  -93.101168),
    ("Waseca",       "MN"):  (44.073910,  -93.526580),
    ("Elora",        "ONT"): (43.636134,  -80.406403),
    ("Ottawa",       "ONT"): (45.368323,  -75.726330),
}

ref = pd.read_csv("reference/nust_locations_ref.csv")
print(f"Loaded {len(ref)} rows from reference/nust_locations_ref.csv")

updated = 0
for (city, state), (new_lat, new_lon) in UPDATES.items():
    mask = (ref["City"] == city) & (ref["State"] == state)
    if not mask.any():
        print(f"  WARNING: {city} {state} not found in ref — skipped")
        continue
    old_lat = ref.loc[mask, "lat"].iloc[0]
    old_lon = ref.loc[mask, "lon"].iloc[0]
    ref.loc[mask, "lat"] = new_lat
    ref.loc[mask, "lon"] = new_lon
    ref.loc[mask, "NeedsVerification"] = 0
    ref.loc[mask, "Source"] = "modern_plotinfo_2024"
    dlat = new_lat - old_lat
    dlon = new_lon - old_lon
    print(f"  Updated {city} {state}: ({old_lat:.5f},{old_lon:.5f}) -> "
          f"({new_lat:.5f},{new_lon:.5f})  Δ({dlat:+.4f},{dlon:+.4f})")
    updated += 1

ref.to_csv("reference/nust_locations_ref.csv", index=False)
print(f"\n  {updated} rows updated and saved to reference/nust_locations_ref.csv")
print(f"  NeedsVerification=1 remaining: {(ref['NeedsVerification']==1).sum()}")
