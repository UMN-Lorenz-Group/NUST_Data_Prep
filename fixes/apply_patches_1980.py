"""One-off: add Units column + apply 3 OCR patches to 1980 combined phenotypes CSVs."""
import re
import sys
import pandas as pd
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUT_DIR = Path("output_1980")

def split_trait_units(trait: str):
    m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', str(trait).strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else (str(trait).strip(), "")

# OCR patches: (Strain, Test, City, State, Phenotype_name, old_value) -> new_value
# Phenotype names AFTER split (no units)
PATCHES = [
    # confirmed_ocr_error: Otbreek -> 4.0
    {"Strain": "Clay (0)",  "Test": "UT-00", "City": "Morden",      "State": "MAN", "Phenotype": "Lodging",   "old": "Otbreek", "new": "4.0"},
    # confirmed_ocr_error: I -> 1 (yield rank)
    {"Strain": "L74D-609", "Test": "UT-IV",  "City": "Belleville",  "State": "IL",  "Phenotype": "YieldRank", "old": "I",       "new": "1"},
    # not_found / OCR of dash: I -> null (missing data)
    {"Strain": "K1033",    "Test": "UT-IV",  "City": "Manhattan",   "State": "KAN", "Phenotype": "Oil",       "old": "I",       "new": None},
]

for suffix in ("", "_raw"):
    path = OUT_DIR / f"combined_1980_phenotypes{suffix}.csv"
    if not path.exists():
        print(f"  Skipping (not found): {path.name}")
        continue

    df = pd.read_csv(path)

    # 1. Add Units column if missing
    if "Units" not in df.columns:
        split = df["Phenotype"].apply(split_trait_units)
        value_idx = df.columns.get_loc("Value")
        df["Phenotype"] = split.apply(lambda x: x[0])
        df.insert(value_idx + 1, "Units", split.apply(lambda x: x[1]))
        print(f"  {path.name}: Units column added after Value")
    elif list(df.columns).index("Units") < list(df.columns).index("Value"):
        # Units is before Value — reorder
        cols = [c for c in df.columns if c != "Units"]
        val_idx = cols.index("Value")
        cols.insert(val_idx + 1, "Units")
        df = df[cols]
        print(f"  {path.name}: Units moved to after Value")

    # 2. Apply OCR patches
    for p in PATCHES:
        mask = (
            (df["Strain"]    == p["Strain"])   &
            (df["Test"]      == p["Test"])      &
            (df["City"]      == p["City"])      &
            (df["State"]     == p["State"])     &
            (df["Phenotype"] == p["Phenotype"]) &
            (df["Value"].astype(str) == str(p["old"]))
        )
        n = mask.sum()
        if n:
            df.loc[mask, "Value"] = p["new"]
            action = f"-> {p['new']}" if p["new"] is not None else "-> null"
            print(f"  {path.name}: patched {n} row(s): {p['Strain']} / {p['Phenotype']} {p['old']} {action}")
        else:
            print(f"  {path.name}: patch not matched (already fixed?): {p['Strain']} / {p['Phenotype']} {p['old']}")

    out_path = path.parent / "patched" / path.name
    out_path.parent.mkdir(exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"  -> written to patched/{path.name} ({len(df)} rows)")
