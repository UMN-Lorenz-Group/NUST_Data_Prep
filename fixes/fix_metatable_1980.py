"""
fix_metatable_1980.py
Add 5 null placeholder rows to combined_1980_MetaTable.csv for
Portageville_MO (PT-IV) — present in phenotypesTable but missing from metaTable.
"""
import shutil
import pandas as pd
from pathlib import Path

META_CSV = Path(__file__).parent.parent / "output_1980" / "combined_1980_MetaTable.csv"
BACKUP   = META_CSV.with_suffix(".csv.bak")

META_TYPES = ["C.V. (%)", "L.S.D. (5%)", "Reps", "Row sp (in.)", "Rows/plot"]

NEW_ROWS = [
    {
        "Year-Test":      "1980_PTIV",
        "Test-Year":      "PTIV_1980",
        "Location":       "Portageville_MO",
        "Trait":          "YieldBuA",
        "Meta_data_type": mt,
        "Value":          "",
    }
    for mt in META_TYPES
]


def main():
    df = pd.read_csv(META_CSV, dtype=str, keep_default_na=False)
    print(f"Loaded {len(df)} rows from {META_CSV.name}")

    shutil.copy(META_CSV, BACKUP)
    print(f"Backup -> {BACKUP.name}")

    # Check not already present
    already = df[
        (df["Location"] == "Portageville_MO") &
        (df["Test-Year"] == "PTIV_1980")
    ]
    if len(already):
        print(f"Portageville_MO PTIV already has {len(already)} rows — skipping add")
    else:
        df = pd.concat([df, pd.DataFrame(NEW_ROWS)], ignore_index=True)
        print(f"Added {len(NEW_ROWS)} null rows for Portageville_MO / PTIV_1980")

    df.to_csv(META_CSV, index=False)
    print(f"Written {len(df)} rows to {META_CSV.name}")


if __name__ == "__main__":
    main()
