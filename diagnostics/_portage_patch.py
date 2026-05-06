"""
Patch remaining 9 null PlantingDate rows in locationsTable.
4 Portageville variants: supplemental has them as "Portageville (Clay) MO" / "(Loam) MO"
  — extract dates directly.
5 others (Harrow OH, Ashland KS, Greenfield IL, Sullivan IL, Portageville plain):
  — genuinely absent from supplemental; left NULL and noted in flags.
Also: check/report phenotypesTable State code issues.
"""
import sys, json
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd, re
from pathlib import Path

OUT_DIR = Path("output_1980")

# ── Load supplemental and find Portageville rows ─────────────────────────────
with open(OUT_DIR / "supplemental_1980_location_raw.json", encoding="utf-8") as f:
    supp_raw = json.load(f)
supp = pd.DataFrame(supp_raw["location_supplement"])
print("Supplemental Portageville rows:")
pv = supp[supp["city"].str.contains("Portage", case=False, na=False)]
print(pv[["test","city","state","planting_date","maturity_date"]].to_string(index=False))

# Extract the soil-type from "(Clay)" / "(Loam)" city names
# "Portageville (Clay) MO" -> City="Portageville Clay", State="MO", pd=...
def parse_portage_city(raw_city, state):
    m = re.search(r'\((\w+)\)', raw_city)
    if m:
        soil = m.group(1).capitalize()
        return f"Portageville {soil}", "MO"
    return "Portageville", "MO"

portage_dates = {}
for _, r in pv.iterrows():
    city, state = parse_portage_city(r["city"], r["state"])
    test = r["test"].strip()
    pd_val = r["planting_date"]
    if pd_val:
        try:
            mo, dy = str(pd_val).split("/")
            date_str = f"1980-{int(mo):02d}-{int(dy):02d}"
        except Exception:
            date_str = None
    else:
        date_str = None
    portage_dates[(test, city)] = date_str
    print(f"  {test} / {city} MO -> planting={date_str}")

# ── Patch locationsTable ──────────────────────────────────────────────────────
locs = pd.read_csv(OUT_DIR / "combined_1980_locationsTable.csv")
null_mask = locs["PlantingDate"].isna()
print(f"\nNull PlantingDate before patch: {null_mask.sum()}")

patched = 0
for (test, city), date_str in portage_dates.items():
    mask = (locs["Test"] == test) & (locs["City"] == city) & locs["PlantingDate"].isna()
    if mask.any() and date_str:
        locs.loc[mask, "PlantingDate"] = date_str
        print(f"  Patched {test} / {city} MO -> {date_str}")
        patched += 1

null_after = locs["PlantingDate"].isna().sum()
print(f"Patched {patched} rows. Null PlantingDate after: {null_after}")

remaining = locs[locs["PlantingDate"].isna()][["Test","City","State"]]
if not remaining.empty:
    print("\nStill NULL (not in supplemental — manual lookup from PDF needed):")
    print(remaining.to_string(index=False))

locs.to_csv(OUT_DIR / "combined_1980_locationsTable.csv", index=False)
print(f"\nSaved. PlantingDate filled: {locs['PlantingDate'].notna().sum()}/{len(locs)}")

# ── Check phenotypesTable State codes ────────────────────────────────────────
print("\n=== phenotypesTable State code check ===")
ph = pd.read_csv(OUT_DIR / "combined_1980_phenotypesTable.csv")
CANON_STATES = {
    "IL","IN","IA","MN","WI","MI","OH","MO","ND","SD","KS","NE","KY",
    "MD","VA","PA","NJ","NY","DE","GA","NC","SC","TX","OK","AR","TN",
    "AL","MS","LA","WA","OR","CA","ONT","MAN","SK","AB","BC","QC","NS","NB",
}
non_canon = ph[~ph["State"].isin(CANON_STATES)]["State"].value_counts()
if not non_canon.empty:
    print(f"  Non-canonical State codes in phenotypesTable (need normalize):")
    print(non_canon.to_string())
else:
    print("  All State codes canonical.")

STATE_NORM = {
    "ILL":"IL","IND":"IN","KAN":"KS","NEB":"NE","PENN":"PA","Penn":"PA","DEL":"DE",
    "ON":"ONT",
}
for old, new in STATE_NORM.items():
    m = ph["State"] == old
    if m.any():
        cnt = m.sum()
        ph.loc[m, "State"] = new
        print(f"  Normalised {cnt} rows: State '{old}' -> '{new}'")

still_bad = ph[~ph["State"].isin(CANON_STATES)]["State"].value_counts()
if not still_bad.empty:
    print(f"\n  [FLAG] Still non-canonical after normalization:")
    print(still_bad.to_string())

ph.to_csv(OUT_DIR / "combined_1980_phenotypesTable.csv", index=False)
print(f"\nSaved phenotypesTable ({len(ph)} rows).")
