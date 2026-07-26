"""
clean_location_ref.py
=====================
One-time cleanup of the nust_locations_ref.csv produced by the first geocoding run:

  1. Drop state-abbreviation duplicates (ILL/IL, IND/IN, KAN/KS, NEB/NE, PENN/PA)
     keeping the standard 2-letter code row.
  2. Strip trailing-comma artifacts from City names.
  3. Fix failed geocodes:
       Giradr IL    -> copy Girard IL coordinates
       Portageville Clay MO  -> use Portageville MO coordinates
       Portageville Loam MO  -> use Portageville MO coordinates (soil-type variant)
  4. Fix wrong geocode:
       Elkpoint SD  -> copy Elk Point SD coordinates (Nominatim returned California)
  5. Write cleaned nust_locations_ref.csv (overwrites) and a diff report.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

ref = pd.read_csv("reference/nust_locations_ref.csv")
original_len = len(ref)
print(f"Loaded {original_len} rows from reference/nust_locations_ref.csv")

# ---- 1. Strip trailing-comma artifacts from City names ----
ref["City"] = ref["City"].str.rstrip(",").str.strip()

# ---- 2. State-abbreviation duplicate collapse ----
# Rows where the "old" abbreviation exists AND the canonical form also exists:
# keep canonical, drop old.  If canonical doesn't exist, rename.
ABBREV_CANON = {
    "ILL": "IL", "IND": "IN", "KAN": "KS",
    "NEB": "NE", "PENN": "PA", "DEL": "DE",
}

rows_to_drop = []
for old, canon in ABBREV_CANON.items():
    old_rows   = ref[ref["State"] == old].copy()
    canon_rows = ref[ref["State"] == canon].copy()
    if old_rows.empty:
        continue
    for _, orow in old_rows.iterrows():
        city = orow["City"]
        # Check if same city exists in canonical state
        match = canon_rows[canon_rows["City"] == city]
        if not match.empty:
            # Exact duplicate — drop the old-abbrev row
            rows_to_drop.append(orow.name)
            print(f"  Drop duplicate: {city} {old} (kept as {city} {canon})")
        else:
            # Only exists in old form — rename state in-place
            ref.loc[orow.name, "State"] = canon
            print(f"  Rename state: {city} {old} -> {canon}")

ref = ref.drop(index=rows_to_drop).reset_index(drop=True)

# ---- 3. Fix Giradr IL (OCR typo for Girard IL) ----
girard = ref[ref["City"] == "Girard"]
giradr = ref[ref["City"] == "Giradr"]
if not girard.empty and not giradr.empty:
    lat, lon = girard.iloc[0]["lat"], girard.iloc[0]["lon"]
    ref.loc[giradr.index, ["lat", "lon", "Geocoded_City"]] = lat, lon, "Girard (via Girard IL)"
    ref.loc[giradr.index, "City"] = "Girard"
    # Now it's a duplicate of Girard IL — drop it
    idx_to_drop = giradr.index.tolist()
    ref = ref.drop(index=idx_to_drop).reset_index(drop=True)
    print(f"  Fixed Giradr IL -> Girard IL, removed duplicate")
elif not giradr.empty:
    # No Girard row to copy from — just rename and geocode city
    ref.loc[giradr.index, "City"] = "Girard"
    print(f"  Renamed Giradr -> Girard (manual coordinate lookup needed)")

# ---- 4. Fix Portageville Clay/Loam MO -> use Portageville MO coords ----
portage = ref[(ref["City"] == "Portageville") & (ref["State"] == "MO")]
for variant in ["Portageville Clay", "Portageville Loam"]:
    rows = ref[(ref["City"] == variant) & (ref["State"] == "MO")]
    if not rows.empty and not portage.empty:
        lat, lon = portage.iloc[0]["lat"], portage.iloc[0]["lon"]
        station  = portage.iloc[0]["StationName"]
        ref.loc[rows.index, ["lat", "lon", "Geocoded_City", "StationName",
                              "NeedsVerification"]] = lat, lon, "Portageville MO", station, 1
        print(f"  Fixed {variant} MO -> Portageville MO coordinates")
    elif not rows.empty:
        print(f"  WARNING: {variant} MO — no Portageville anchor to copy from")

# ---- 5. Fix Elkpoint SD (wrong geocode — California) ----
elk_point = ref[(ref["City"] == "Elk Point") & (ref["State"] == "SD")]
elkpoint  = ref[(ref["City"] == "Elkpoint")  & (ref["State"] == "SD")]
if not elk_point.empty and not elkpoint.empty:
    lat, lon = elk_point.iloc[0]["lat"], elk_point.iloc[0]["lon"]
    ref.loc[elkpoint.index, ["lat", "lon", "Geocoded_City"]] = lat, lon, "Elk Point SD (corrected)"
    print(f"  Fixed Elkpoint SD wrong geocode -> {lat}, {lon}")
elif not elkpoint.empty:
    print(f"  WARNING: Elkpoint SD — Elk Point anchor not found, needs manual fix")

# ---- Drop any remaining rows with non-geographic "state" values ----
REAL_STATES = {
    "IL","IN","IA","MN","WI","MI","OH","MO","ND","SD","KS","NE","KY",
    "MD","VA","PA","NJ","NY","DE","GA","NC","SC","TX","OK","AR","TN",
    "AL","MS","LA","WA","OR","CA","ONT","MAN","SK","AB","BC","QC","NS","NB",
}
bad_state = ref[~ref["State"].isin(REAL_STATES)]
if not bad_state.empty:
    print(f"  Dropping {len(bad_state)} rows with invalid state codes: "
          f"{sorted(bad_state['State'].unique())}")
    ref = ref[ref["State"].isin(REAL_STATES)].reset_index(drop=True)

# ---- Final dedup on City+State (catches any remaining) ----
before_dedup = len(ref)
ref = ref.drop_duplicates(subset=["City", "State"]).reset_index(drop=True)
if len(ref) < before_dedup:
    print(f"  Dropped {before_dedup - len(ref)} remaining duplicates")

# ---- Save ----
ref.to_csv("reference/nust_locations_ref.csv", index=False)

print(f"\n=== Result ===")
print(f"  Before: {original_len} rows")
print(f"  After:  {len(ref)} rows")
print(f"  Geocoded:          {ref['lat'].notna().sum()}")
print(f"  Still failed:      {ref['lat'].isna().sum()}")
print(f"  Needs verification:{(ref['NeedsVerification']==1).sum()}")

remaining_null = ref[ref["lat"].isna()]
if not remaining_null.empty:
    print(f"\n  Remaining NULL coordinates (manual lookup needed):")
    print(remaining_null[["City","State","StationName"]].to_string(index=False))
