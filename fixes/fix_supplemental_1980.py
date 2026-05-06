"""Fix supplemental extraction issues for 1980."""
import re
import sys
import pandas as pd
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUT = Path("output_1980")
YEAR = "1980"

PHENOTYPE_MAP = {
    "YIELD (bu/a)": "YieldBuA", "YIELD": "YieldBuA",
    "YIELD RANK": "YieldRank",
    "LODGING (score)": "Lodging", "LODGING": "Lodging",
    "PLANT HEIGHT (inches)": "Height", "HEIGHT (inches)": "Height", "HEIGHT": "Height",
    "MATURITY (date)": "Maturity", "MATURITY": "Maturity",
    "SEED QUALITY (score)": "SeedQuality", "SEED QUALITY": "SeedQuality",
    "SEED SIZE (g/100)": "SeedSize", "SEED SIZE": "SeedSize",
    "PROTEIN (%)": "Protein", "PROTEIN": "Protein",
    "OIL (%)": "Oil", "OIL": "Oil",
}

# ---- 1. checksTable: RM values like "0","I","III" are MG designations, not numeric RM ----
ck = pd.read_csv(OUT / f"combined_{YEAR}_checksTable.csv")
# Real numeric RM would be e.g. 0.5, 2.3, 3.8 — single digits or Roman numerals are not valid
def is_real_rm(val):
    if pd.isna(val):
        return False
    try:
        f = float(val)
        return f > 5  # numeric RM for soybeans is typically 0.0-10.0 but a bare "0" or "4" is ambiguous
    except (ValueError, TypeError):
        return False  # "I", "II", "III", "IV", "00" etc — not numeric RM

ck["RM"] = ck["RM"].apply(lambda v: v if is_real_rm(v) else None)
ck.to_csv(OUT / f"combined_{YEAR}_checksTable.csv", index=False)
n_rm = ck["RM"].notna().sum()
print(f"checksTable: RM reset — {n_rm} real numeric values kept (expected 0 for 1980)")

# ---- 2. MetaTable: normalize Trait names + drop invalid rows ----
meta = pd.read_csv(OUT / f"combined_{YEAR}_MetaTable.csv")

meta["Trait"] = meta["Trait"].apply(
    lambda v: PHENOTYPE_MAP.get(str(v).strip(), PHENOTYPE_MAP.get(str(v).strip().upper(), str(v).strip()))
)
meta.to_csv(OUT / f"combined_{YEAR}_MetaTable.csv", index=False)
print(f"MetaTable: {len(meta)} rows, Trait values: {sorted(meta['Trait'].unique())}")

# ---- 3. locationsTable: standardize PlantingDate M/DD -> YYYY-MM-DD ----
locs = pd.read_csv(OUT / f"combined_{YEAR}_locationsTable.csv")

def standardize_date(val, year):
    if pd.isna(val) or str(val).strip() in ("", "nan", "None"):
        return None
    s = str(val).strip()
    # Already ISO format
    if re.match(r'\d{4}-\d{2}-\d{2}', s):
        return s
    # M/DD or MM/DD
    m = re.match(r'^(\d{1,2})/(\d{1,2})$', s)
    if m:
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return s

locs["PlantingDate"] = locs["PlantingDate"].apply(lambda v: standardize_date(v, YEAR))
locs.to_csv(OUT / f"combined_{YEAR}_locationsTable.csv", index=False)
n_pd = locs["PlantingDate"].notna().sum()
print(f"locationsTable: {n_pd}/{len(locs)} PlantingDate filled")
print(locs[locs["PlantingDate"].notna()].head(4)[["Year","Test","City","State","PlantingDate"]].to_string(index=False))
