"""
fix_strainstable_1980.py
Patch combined_1980_strainsTable.csv:

  Renames (OCR / typo fixes):
    1.25A          -> L25A        (OCR misread of L prefix)
    L74D-609 Pixie -> L74D-609    (spurious cultivar suffix)
    William79 (III)-> Williams79 (III)  (missing 's', same as checksTable fix)

  Additions:
    K1033 (UT-IV)  — K1035->K1033 fix was applied to phenotypesTable but
                     strainsTable had no K1035 entry (only K1033 Douglas, a
                     separate cultivar), so K1033 was never registered here.

  Removals — clear artifacts:
    ???            OCR garbage
    .164-185       OCR garbage
    168-1034???    OCR garbage
    Hardin (A76-102009) / UT-I   — parentage ref absorbed into name; Hardin already present
    Century (11)   / UT-III      — (11) is OCR of (II); Century already present as check

  Removals — GlobalParentage registry:
    All 91 rows with Test == "GlobalParentage" — these are parent varieties from
    the XLSX parentage cross-reference section, not direct trial entries. They
    belong only in parentageTable, not in the trial strains registry.
"""
import shutil
import pandas as pd
from pathlib import Path

STRAINS_CSV = Path(__file__).parent.parent / "output_1980" / "combined_1980_strainsTable.csv"
BACKUP = STRAINS_CSV.with_suffix(".csv.bak")

RENAMES = {
    "1.25A":               "L25A",
    "L74D-609 Pixie":      "L74D-609",
    "L74D-609Pixie":       "L74D-609",    # catch post-space-strip variant too
    "William79 (III)":     "Williams79 (III)",
    "Century (11)":        "Century",     # OCR artifact: (11) is misread of (II); only UT-III entry
    "Hardin (A76-102009)": "Hardin",      # OCR artifact: parentage ref absorbed into name; only UT-I entry
    # NOTE: "K1033 Douglas" is a DIFFERENT cultivar from K1033 — do not rename it.
    # K1033 (OCR fix of K1035) is handled separately below via ADD_ROWS.
}

# Exact-name artifact rows to drop (Test-agnostic)
REMOVE_STRAINS = {"???", ".164-185", "168-1034???"}

# New rows to insert — strains present in phenotypesTable but absent from strainsTable
# because the OCR fix renamed them in pheno but no corresponding entry existed here.
ADD_ROWS = [
    {
        "Year": "1980", "Test": "UT-IV", "Strain": "K1033",
        "OriginalStrain": "K1035", "Descriptive.Code": "",
        "Unique.traits": "", "Gen.Comp.": "", "Check": "0",
    },
]


def main():
    df = pd.read_csv(STRAINS_CSV, dtype=str, keep_default_na=False)
    print(f"Loaded {len(df)} rows from {STRAINS_CSV.name}")

    shutil.copy(STRAINS_CSV, BACKUP)
    print(f"Backup written to {BACKUP.name}")

    # Renames
    rename_count = 0
    for old, new in RENAMES.items():
        mask = df["Strain"] == old
        n = mask.sum()
        if n:
            df.loc[mask, "Strain"] = new
            print(f"  Renamed '{old}' -> '{new}': {n} row(s)")
            rename_count += n

    # Removals — named artifacts
    remove_mask = df["Strain"].isin(REMOVE_STRAINS)
    n_remove = remove_mask.sum()
    if n_remove:
        for r in df.loc[remove_mask, "Strain"].tolist():
            print(f"  Removed artifact: Strain='{r}'")
        df = df[~remove_mask].reset_index(drop=True)

    # Removals — GlobalParentage registry rows
    gp_mask = df["Test"] == "GlobalParentage"
    n_gp = gp_mask.sum()
    if n_gp:
        print(f"  Removed {n_gp} GlobalParentage rows (parent varieties, not trial entries)")
        df = df[~gp_mask].reset_index(drop=True)
    n_remove += n_gp

    # Add missing rows
    add_count = 0
    for row in ADD_ROWS:
        already = ((df["Strain"] == row["Strain"]) & (df["Test"] == row["Test"])).any()
        if not already:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            print(f"  Added row: Strain='{row['Strain']}', Test='{row['Test']}', "
                  f"OriginalStrain='{row['OriginalStrain']}'")
            add_count += 1
        else:
            print(f"  Skip add: Strain='{row['Strain']}' Test='{row['Test']}' already present")

    df.to_csv(STRAINS_CSV, index=False, quoting=0)
    print(f"\nDone. {rename_count} rename(s), {n_remove} removal(s), "
          f"{add_count} addition(s). {len(df)} rows written.")


if __name__ == "__main__":
    main()
