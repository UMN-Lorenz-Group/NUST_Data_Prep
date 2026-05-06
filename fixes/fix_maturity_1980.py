"""Convert Maturity values in 1980 phenotypesTable to DOY where possible.

Rules:
  iso2026  (2026-MM-DD 00:00:00) -> replace year with 1980, compute DOY
  M-DD     (9-18, 10-1*)         -> parse as 1980 MM/DD, compute DOY; strip *
  date-annot (* 9/17, *9/22)     -> extract date with M/DD, compute DOY; strip *
  frost / Frost Kill / +5*       -> NULL (frost killed before natural maturity)
  integer offsets (-16 to +29)   -> keep as-is (relative days from check)
  null                           -> keep as null
"""
import re
import sys
import pandas as pd
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

YEAR = 1980
OUT = Path("output_1980")

def to_doy(month: int, day: int) -> int:
    return date(YEAR, month, day).timetuple().tm_yday

def parse_maturity(val):
    if pd.isna(val):
        return val

    s = str(val).strip()

    # frost entries -> NULL
    if re.search(r'frost', s, re.IGNORECASE):
        return None
    if s == "--":
        return None

    # annotated frost offset like +5* with no date component
    if re.match(r'^[+-]?\d+\*$', s) and not re.search(r'/', s):
        # e.g. "+5*" — offset with frost marker, no reliable maturity
        return None

    # iso2026: "2026-MM-DD 00:00:00" or "2026-MM-DD"
    m = re.match(r'^2026-(\d{2})-(\d{2})', s)
    if m:
        return to_doy(int(m.group(1)), int(m.group(2)))

    # date with annotation prefix: "* 9/17" or "*9/22"
    m = re.match(r'^\*\s*(\d{1,2})[/\-](\d{1,2})', s)
    if m:
        return to_doy(int(m.group(1)), int(m.group(2)))

    # M-DD or M/DD (possibly with trailing *)
    s_clean = s.rstrip("*").strip()
    m = re.match(r'^(\d{1,2})[\-/](\d{1,2})$', s_clean)
    if m:
        return to_doy(int(m.group(1)), int(m.group(2)))

    # integer offset (may have leading + or -)
    m = re.match(r'^([+-]?\d+)$', s_clean)
    if m:
        return s_clean  # keep as-is (relative days from check)

    # unrecognized — return as-is with warning
    return s


df = pd.read_csv(OUT / "combined_1980_phenotypesTable.csv")
mat_mask = df["Phenotype"] == "Maturity"

before = df.loc[mat_mask, "Value"].copy()
df.loc[mat_mask, "Value"] = df.loc[mat_mask, "Value"].apply(parse_maturity)
after = df.loc[mat_mask, "Value"]

# Report
changed = (before != after) | (before.isna() != after.isna())
print(f"Maturity rows:     {mat_mask.sum()}")
print(f"Values changed:    {changed.sum()}")
print(f"Nulled (frost):    {(before.notna() & after.isna()).sum()}")
print(f"Converted to DOY:  {after.apply(lambda v: isinstance(v, int) and v > 100).sum()}")
print(f"Still relative:    {after.apply(lambda v: str(v).lstrip('+-').isdigit() and (isinstance(v, str) and int(v) <= 100 if isinstance(v, str) else False) or (isinstance(v, (int, float)) and not pd.isna(v) and abs(float(v)) <= 50)).sum()}")

print("\nSample converted (iso2026):")
mask_iso = before.str.startswith("2026", na=False)
print(pd.DataFrame({"before": before[mask_iso], "after": after[mask_iso]}).head(6).to_string())

print("\nSample converted (M-DD):")
mask_mdd = before.str.match(r'^\d{1,2}-\d{1,2}', na=False)
print(pd.DataFrame({"before": before[mask_mdd], "after": after[mask_mdd]}).head(6).to_string())

print("\nRemaining non-numeric (sample):")
non_numeric = after[after.apply(lambda v: not pd.isna(v) and not str(v).lstrip("+-").isdigit())]
print(non_numeric.head(10))

df.to_csv(OUT / "combined_1980_phenotypesTable.csv", index=False)
print(f"\nSaved -> {OUT}/combined_1980_phenotypesTable.csv")
