"""
compare_locations.py
Compare nust_locations_ref.csv (historical, 1941–1986) against
2024_NUST_Locations_PlotInfo.csv and 2025_NUST_Locations_PlotInfo.csv.

Outputs:
  1. Locations matched between historical and modern (coord diff + verification flag)
  2. Historical-only locations
  3. Modern-only locations
  4. Coord update suggestions for NeedsVerification=1 rows
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np

# ── Load files ──────────────────────────────────────────────────────────────
hist = pd.read_csv("reference/nust_locations_ref.csv")

mod24 = pd.read_csv("reference/2024_NUST_Locations_PlotInfo.csv", header=0)
mod25 = pd.read_csv("reference/2025_NUST_Locations_PlotInfo.csv", header=0)

# Both files use "location" / "State/Prov" / "Lat" / "Long"
# Drop separator rows (where trial == ".")
def clean_modern(df):
    df = df[df["trial"].notna() & (df["trial"] != ".")].copy()
    df = df.rename(columns={"location": "City", "State/Prov": "State",
                             "Lat": "lat", "Long": "lon"})
    df["City"]  = df["City"].str.strip()
    df["State"] = df["State"].str.strip().str.upper()
    df["lat"]   = pd.to_numeric(df["lat"],  errors="coerce")
    df["lon"]   = pd.to_numeric(df["lon"],  errors="coerce")
    return df[["City","State","lat","lon"]].drop_duplicates(subset=["City","State"])

mod24c = clean_modern(mod24)
mod25c = clean_modern(mod25)

# Check if 2024 == 2025
merged_check = mod24c.merge(mod25c, on=["City","State"], suffixes=("_24","_25"))
files_identical = (
    len(mod24c) == len(mod25c) and
    len(merged_check) == len(mod24c) and
    np.allclose(merged_check["lat_24"].fillna(0), merged_check["lat_25"].fillna(0), atol=1e-5) and
    np.allclose(merged_check["lon_24"].fillna(0), merged_check["lon_25"].fillna(0), atol=1e-5)
)
print(f"=== File comparison ===")
print(f"  2024 file: {len(mod24c)} unique locations")
print(f"  2025 file: {len(mod25c)} unique locations")
print(f"  Files are {'IDENTICAL' if files_identical else 'DIFFERENT'}")

# Use modern as the union (prefer 2025 coords where they differ)
modern = mod24c.merge(mod25c, on=["City","State"], how="outer", suffixes=("_24","_25"))
modern["lat"] = modern["lat_25"].combine_first(modern["lat_24"])
modern["lon"] = modern["lon_25"].combine_first(modern["lon_24"])
modern = modern[["City","State","lat","lon"]]
print(f"  Combined unique modern locations: {len(modern)}\n")

# Normalise historical state codes for matching
# "West Lafayette" (modern) <-> "Lafayette" (historical)
# "Ottawa-ONT" <-> "Ottawa"
NAME_MAP = {
    ("West Lafayette", "IN"): "Lafayette",
    ("Ottawa-ONT",     "ONT"): "Ottawa",
    ("Ottawa-KS",      "KS"): "Ottawa",
    ("Manhattan-B",    "KS"): "Manhattan",
    ("MAN", "MAN"): ("MAN", "MAN"),   # passthrough
}

def normalise_city(city, state):
    return NAME_MAP.get((city, state), city)

modern["CityNorm"] = modern.apply(lambda r: normalise_city(r["City"], r["State"]), axis=1)

# Normalise province codes
PROV_NORM = {"QUE": "QC", "SAS": "SK"}
modern["StateNorm"] = modern["State"].map(lambda s: PROV_NORM.get(s, s))

# Join historical on normalised city+state
hist["CityKey"]  = hist["City"].str.strip()
hist["StateKey"] = hist["State"].str.strip()
modern["CityKey"]  = modern["CityNorm"]
modern["StateKey"] = modern["StateNorm"]

merged = hist.merge(modern[["CityKey","StateKey","lat","lon","City"]],
                    on=["CityKey","StateKey"], suffixes=("_hist","_mod"),
                    how="outer", indicator=True)

matched   = merged[merged["_merge"] == "both"].copy()
hist_only = merged[merged["_merge"] == "left_only"].copy()
mod_only  = merged[merged["_merge"] == "right_only"].copy()

# ── 1. Matched locations ────────────────────────────────────────────────────
print(f"=== Matched locations ({len(matched)}) ===")
print(f"{'Historical City':<25} {'St':<5} {'Hist lat':>10} {'Mod lat':>10} "
      f"{'Δlat':>7} {'Δlon':>7} {'NeedsVerif':>10}")
print("-" * 80)
matched["dlat"] = (matched["lat_mod"] - matched["lat_hist"]).round(4)
matched["dlon"] = (matched["lon_mod"] - matched["lon_hist"]).round(4)
for _, r in matched.sort_values("StateKey").iterrows():
    flag = "**" if r.get("NeedsVerification") == 1 else ""
    print(f"  {r['CityKey']:<23} {r['StateKey']:<5} "
          f"{r['lat_hist']:>10.5f} {r['lat_mod']:>10.5f} "
          f"{r['dlat']:>+7.4f} {r['dlon']:>+7.4f}  {flag}")

# ── 2. Modern coords better for NeedsVerification rows ───────────────────────
verif_matches = matched[matched["NeedsVerification"] == 1].copy()
print(f"\n=== Coord update candidates (NeedsVerification=1 matched to modern) "
      f"({len(verif_matches)}) ===")
print(f"{'City':<25} {'St':<5} {'Old lat':>10} {'Old lon':>11} "
      f"{'New lat':>10} {'New lon':>11}")
print("-" * 75)
for _, r in verif_matches.sort_values("StateKey").iterrows():
    print(f"  {r['CityKey']:<23} {r['StateKey']:<5} "
          f"{r['lat_hist']:>10.5f} {r['lon_hist']:>11.5f} "
          f"{r['lat_mod']:>10.5f} {r['lon_mod']:>11.5f}")

# ── 3. Historical-only ────────────────────────────────────────────────────────
print(f"\n=== Historical-only locations ({len(hist_only)}) ===")
for _, r in hist_only.sort_values(["StateKey","CityKey"]).iterrows():
    verif = " [station]" if r.get("NeedsVerification") == 1 else ""
    print(f"  {r['CityKey']:<25} {r['StateKey']}{verif}")

# ── 4. Modern-only ────────────────────────────────────────────────────────────
print(f"\n=== Modern-only locations (new since historical era) ({len(mod_only)}) ===")
for _, r in mod_only.sort_values(["StateKey","CityKey"]).iterrows():
    lat = r.get("lat_mod", r.get("lat"))
    lon = r.get("lon_mod", r.get("lon"))
    print(f"  {r['CityKey']:<25} {r['StateKey']:<5}  lat={lat:.4f}  lon={lon:.4f}")
