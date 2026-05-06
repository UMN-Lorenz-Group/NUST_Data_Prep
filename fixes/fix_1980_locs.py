"""
fix_1980_locs.py
=================
Fixes for combined_1980_locationsTable.csv:
  1. Normalize state abbreviation variants (IND->IN, KAN->KS, ILL->IL, etc.)
  2. Fix OCR city name errors (Giradr, ElkPoint, Point Elk, Portageville soil-type malforms)
  3. Deduplicate Test×City×State rows produced by state-variant aliases
  4. Merge PlantingDate from supplemental_1980_location_raw.json
  5. Merge lat/lon from nust_locations_ref.csv
  6. Investigate 194 null-DOY rows in maturityVerification

FLAGS all potential issues for manual review.
Writes:
  output_1980/combined_1980_locationsTable.csv   (overwrite)
  output_1980/locs_fix_flags_1980.txt            (issue log)
"""
import sys, json
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np
from pathlib import Path

OUT_DIR = Path("output_1980")
flags = []   # (severity, message)  severity: INFO / WARN / FLAG

def flag(sev, msg):
    flags.append((sev, msg))
    print(f"  [{sev}] {msg}")

# ── Load ────────────────────────────────────────────────────────────────────
locs = pd.read_csv(OUT_DIR / "combined_1980_locationsTable.csv")
ref  = pd.read_csv("reference/nust_locations_ref.csv")
with open(OUT_DIR / "supplemental_1980_location_raw.json", encoding="utf-8") as f:
    supp_raw = json.load(f)
supp = pd.DataFrame(supp_raw["location_supplement"])

print(f"Loaded locationsTable: {len(locs)} rows")
print(f"Loaded nust_locations_ref: {len(ref)} rows")
print(f"Loaded supplemental: {len(supp)} rows\n")

# ── 1. Normalize state abbreviations ────────────────────────────────────────
print("=== Step 1: Normalize state abbreviations ===")
STATE_NORM = {
    "ill":  "IL",  "ind":  "IN",  "kan":  "KS",
    "neb":  "NE",  "penn": "PA",  "del":  "DE",
    "on":   "ONT", "man":  "MAN", "ont":  "ONT",
    # soil-type labels that leaked into State column
    "loam": None,  "clay": None,
}
before = len(locs)
for old_lower, canon in STATE_NORM.items():
    mask = locs["State"].str.strip().str.lower() == old_lower
    if mask.any():
        cities = locs.loc[mask, "City"].unique().tolist()
        if canon is None:
            # Soil-type label in State col — fix City + State
            # e.g. City="Portageville MO", State="Loam"
            for idx in locs.index[mask]:
                raw_city  = str(locs.at[idx, "City"]).strip()
                soil_type = old_lower.capitalize()
                # Remove trailing state token from city if present
                if raw_city.upper().endswith(" MO"):
                    new_city = "Portageville " + soil_type
                else:
                    new_city = raw_city + " " + soil_type
                locs.at[idx, "City"]  = new_city
                locs.at[idx, "State"] = "MO"
                flag("INFO", f"Fixed soil-label state: City='{raw_city}' State='{old_lower}' -> City='{new_city}' State='MO'")
        else:
            locs.loc[mask, "State"] = canon
            flag("INFO", f"Normalised State '{old_lower.upper()}' -> '{canon}' for cities: {cities}")

# ── 2. Fix OCR city name errors ─────────────────────────────────────────────
print("\n=== Step 2: Fix OCR city name errors ===")
CITY_FIXES = {
    "Giradr":    "Girard",     # OCR typo
    "ElkPoint":  "Elk Point",  # missing space
    "Point Elk": "Elk Point",  # transposed (same coords in ref)
}
for wrong, correct in CITY_FIXES.items():
    mask = locs["City"].str.strip() == wrong
    if mask.any():
        tests = locs.loc[mask, "Test"].unique().tolist()
        locs.loc[mask, "City"] = correct
        flag("INFO", f"Renamed City '{wrong}' -> '{correct}' in tests: {tests}")

# Strip whitespace from City/State throughout
locs["City"]  = locs["City"].str.strip()
locs["State"] = locs["State"].str.strip()

# ── 3. Deduplicate Test×City×State ──────────────────────────────────────────
print("\n=== Step 3: Deduplicate Test×City×State ===")
key = ["Test", "City", "State"]
dups = locs[locs.duplicated(subset=key, keep=False)].sort_values(key)
if not dups.empty:
    # Show what's being merged
    dup_groups = dups.groupby(key).size()
    flag("INFO", f"Found {len(dup_groups)} duplicate Test×City×State groups ({len(dups)} rows total)")
    for (test, city, state), cnt in dup_groups.items():
        flag("INFO", f"  Dedup: {test} / {city} {state} ({cnt} rows -> 1)")
    locs = locs.drop_duplicates(subset=key, keep="first").reset_index(drop=True)
    flag("INFO", f"After dedup: {len(locs)} rows (removed {before - len(locs)})")
else:
    flag("INFO", "No duplicates found after normalization")

print(f"  Rows after dedup: {len(locs)}")

# ── 4. Merge PlantingDate from supplemental JSON ────────────────────────────
print("\n=== Step 4: Merge PlantingDate from supplemental ===")

# Normalise supplemental state codes and city names
SUPP_STATE_NORM = {"ON": "ONT", "QC": "QC", "BC": "BC", "MB": "MAN", "SK": "SK"}
supp["State"] = supp["state"].str.strip().str.upper()
supp["State"] = supp["State"].apply(lambda s: SUPP_STATE_NORM.get(s, s))
supp["City"]  = supp["city"].str.strip().str.title()
supp["Test"]  = supp["test"].str.strip()

# Apply same OCR city fixes to supplemental
for wrong, correct in CITY_FIXES.items():
    supp.loc[supp["City"] == wrong.title(), "City"] = correct

# Convert planting_date "M/D" -> "1980-MM-DD"
def fmt_date(val):
    if not val or pd.isna(val):
        return None
    val = str(val).strip()
    if "/" in val:
        try:
            m, d = val.split("/")
            return f"1980-{int(m):02d}-{int(d):02d}"
        except Exception:
            return None
    return val

supp["PlantingDate_supp"] = supp["planting_date"].apply(fmt_date)
supp["MaturityDate_supp"] = supp["maturity_date"].apply(fmt_date)

supp_merge = supp[["Test","City","State","PlantingDate_supp","MaturityDate_supp"]].copy()
supp_merge = supp_merge.drop_duplicates(subset=["Test","City","State"])

before_cols = locs.columns.tolist()
locs = locs.merge(supp_merge, on=["Test","City","State"], how="left")

filled = locs["PlantingDate_supp"].notna().sum()
flag("INFO", f"PlantingDate merged: {filled}/{len(locs)} rows filled from supplemental")

# Write into PlantingDate column (supplemental wins; keep existing if already set)
locs["PlantingDate"] = locs["PlantingDate"].where(
    locs["PlantingDate"].notna(), locs["PlantingDate_supp"]
)
locs["MaturityDate"] = locs["MaturityDate"].where(
    locs["MaturityDate"].notna(), locs["MaturityDate_supp"]
)
locs.drop(columns=["PlantingDate_supp","MaturityDate_supp"], inplace=True)

unmatched_supp = supp_merge[
    ~supp_merge.set_index(["Test","City","State"]).index.isin(
        locs.set_index(["Test","City","State"]).index
    )
]
if not unmatched_supp.empty:
    flag("WARN", f"{len(unmatched_supp)} supplemental rows did not join to locationsTable:")
    for _, r in unmatched_supp.iterrows():
        flag("WARN", f"  {r['Test']} / {r['City']} {r['State']} (planting={r['PlantingDate_supp']})")

still_null = locs["PlantingDate"].isna().sum()
flag("FLAG" if still_null > 0 else "INFO",
     f"PlantingDate still NULL: {still_null}/{len(locs)} rows")
if still_null > 0:
    null_rows = locs[locs["PlantingDate"].isna()][["Test","City","State"]]
    for _, r in null_rows.iterrows():
        flag("FLAG", f"  No planting date: {r['Test']} / {r['City']} {r['State']}")

# ── 5. Merge lat/lon from nust_locations_ref.csv ────────────────────────────
print("\n=== Step 5: Merge lat/lon from nust_locations_ref ===")

# Build a lookup: (City, State) -> (lat, lon)
# Also handle aliases: Portageville Clay/Loam both match main Portageville entry if not found
ref_lookup = ref.set_index(["City","State"])[["lat","lon"]]

# Extra aliases for join mismatches
CITY_ALIASES = {
    # (city_in_locs, state) : (lookup_city, lookup_state)
    ("Elkpoint",         "SD"):  ("Elk Point",  "SD"),
    ("Point Elk",        "SD"):  ("Elk Point",  "SD"),
    ("Girard",           "IL"):  ("Girard",     "IL"),   # was Giradr, now fixed
    ("S. Charleston",    "OH"):  ("S. Charleston","OH"),
    ("Mt. Morris",       "IL"):  ("Mt. Morris", "IL"),
    ("Mt. Healthy",      "OH"):  ("Mt. Healthy","OH"),
    ("Burlington Co.",   "NJ"):  ("Burlington Co.","NJ"),
    ("Middlesex Co.",    "NJ"):  ("Middlesex Co.","NJ"),
    ("Portage La Prairie","MAN"):("Portage La Prairie","MAN"),
}

def lookup_coords(city, state):
    if (city, state) in ref_lookup.index:
        row = ref_lookup.loc[(city, state)]
        return float(row["lat"]), float(row["lon"])
    if (city, state) in CITY_ALIASES:
        c2, s2 = CITY_ALIASES[(city, state)]
        if (c2, s2) in ref_lookup.index:
            row = ref_lookup.loc[(c2, s2)]
            return float(row["lat"]), float(row["lon"])
    return None, None

locs["lat"] = np.nan
locs["lon"] = np.nan

no_coord = []
for idx, row in locs.iterrows():
    lat, lon = lookup_coords(row["City"], row["State"])
    if lat is not None:
        locs.at[idx, "lat"] = lat
        locs.at[idx, "lon"] = lon
    else:
        no_coord.append((row["Test"], row["City"], row["State"]))

filled_coords = locs["lat"].notna().sum()
flag("INFO", f"lat/lon filled: {filled_coords}/{len(locs)} rows")

if no_coord:
    flag("FLAG", f"{len(no_coord)} rows with no coordinate match — need manual lookup:")
    for test, city, state in sorted(no_coord, key=lambda x: (x[2], x[1])):
        flag("FLAG", f"  {test} / {city} {state}")

# ── 6. Investigate null-DOY maturity rows ───────────────────────────────────
print("\n=== Step 6: Investigate 194 null-DOY maturity rows ===")
mv = pd.read_csv(OUT_DIR / "combined_1980_maturityVerification.csv")
null_doy = mv[mv["ComputedDOY"].isna()].copy()

has_orig = null_doy["OriginalMaturity"].notna().sum()
no_orig  = null_doy["OriginalMaturity"].isna().sum()

flag("INFO", f"Null-DOY rows: {len(null_doy)} total")
flag("INFO", f"  OriginalMaturity also NULL (expected missing): {no_orig}")
flag("INFO" if has_orig == 0 else "FLAG",
     f"  OriginalMaturity HAS a value but DOY failed:        {has_orig}")

if has_orig > 0:
    problem = null_doy[null_doy["OriginalMaturity"].notna()]
    flag("FLAG", f"  These need anchor investigation:")
    for _, r in problem.iterrows():
        flag("FLAG", f"    {r['Test']} / {r['City']} {r['State']} / {r['Strain']} "
                     f"orig={r['OriginalMaturity']}")

# Check if null-DOY rows are all Mean rows or specific locations
mean_null  = null_doy[null_doy["City"].isna() | (null_doy["City"] == "Mean")]
loc_null   = null_doy[~(null_doy["City"].isna() | (null_doy["City"] == "Mean"))]
flag("INFO", f"  Mean/null-city rows:     {len(mean_null)}")
flag("INFO" if len(loc_null) == 0 else "WARN",
     f"  Specific-location rows:  {len(loc_null)}")
if len(loc_null) > 0:
    flag("WARN", "  Location-specific null DOY (no anchor resolved):")
    print(loc_null[["Test","City","State","Strain","OriginalMaturity"]].to_string(index=False))

# ── 7. Save ──────────────────────────────────────────────────────────────────
print("\n=== Saving ===")
locs.to_csv(OUT_DIR / "combined_1980_locationsTable.csv", index=False)
print(f"  Saved combined_1980_locationsTable.csv  ({len(locs)} rows)")
print(f"  PlantingDate filled: {locs['PlantingDate'].notna().sum()}/{len(locs)}")
print(f"  lat/lon filled:      {locs['lat'].notna().sum()}/{len(locs)}")

# Write flags log
flag_path = OUT_DIR / "locs_fix_flags_1980.txt"
with open(flag_path, "w", encoding="utf-8") as fh:
    fh.write("1980 locationsTable fix — flags log\n")
    fh.write("=" * 60 + "\n\n")
    for sev, msg in flags:
        fh.write(f"[{sev}] {msg}\n")
print(f"  Flags written to {flag_path}")

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n=== Summary ===")
warns  = [m for s, m in flags if s == "WARN"]
flgs   = [m for s, m in flags if s == "FLAG"]
print(f"  INFO:  {sum(1 for s,_ in flags if s=='INFO')}")
print(f"  WARN:  {len(warns)}")
print(f"  FLAG:  {len(flgs)}")
if flgs:
    print("\nFLAGs requiring attention:")
    for m in flgs:
        print(f"  {m}")
