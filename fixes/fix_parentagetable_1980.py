"""
fix_parentagetable_1980.py
Patch combined_1980_parentageTable.csv:

  Renames (OCR fixes):
    1.25A  -> L25A   (UT-III — OCR misread of L prefix, matches strainsTable fix)

  Removals — OCR garbage Strains in GlobalParentage section:
    .164-185     (Chippewa 64 x Amsoy cross — strain name is OCR garbage)
    168-1034???  (York x PI71506 — strain name is OCR garbage)
    ???          (York x PI71506 — strain name is OCR garbage)
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import shutil
import pandas as pd
from pathlib import Path

PARENT_CSV = Path(__file__).parent.parent / "output_1980" / "combined_1980_parentageTable.csv"
BACKUP     = PARENT_CSV.with_suffix(".csv.bak")

RENAMES = {
    "1.25A":               "L25A",              # OCR: matches strainsTable fix
    "Century (11)":        "Century",            # OCR artifact: (11) = (II); only UT-III entry
    "Hardin (A76-102009)": "Hardin",             # OCR artifact: parentage ref in name; only UT-I entry
    "L74D-609 Pixie":      "L74D-609",           # OCR: matches strainsTable fix
    "William79 (III)":     "Williams79 (III)",   # typo: missing 's', matches strainsTable fix
}

REMOVE_STRAINS = {".164-185", "168-1034???", "???"}


def main():
    df = pd.read_csv(PARENT_CSV, dtype=str, keep_default_na=False)
    print(f"Loaded {len(df)} rows from {PARENT_CSV.name}")

    shutil.copy(PARENT_CSV, BACKUP)
    print(f"Backup -> {BACKUP.name}")

    # Renames
    rename_count = 0
    for old, new in RENAMES.items():
        mask = df["Strain"] == old
        n = mask.sum()
        if n:
            df.loc[mask, "Strain"] = new
            print(f"  Renamed '{old}' -> '{new}': {n} row(s)")
            rename_count += n

    # Removals
    remove_mask = df["Strain"].isin(REMOVE_STRAINS)
    n_remove = remove_mask.sum()
    if n_remove:
        for r in df.loc[remove_mask, ["Strain", "Test"]].itertuples():
            print(f"  Removed artifact: Strain='{r.Strain}', Test='{r.Test}'")
        df = df[~remove_mask].reset_index(drop=True)

    df.to_csv(PARENT_CSV, index=False)
    print(f"\nDone. {rename_count} rename(s), {n_remove} removal(s). {len(df)} rows written.")


if __name__ == "__main__":
    main()
