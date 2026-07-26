"""
89b_extract_checks_2023_master.py
==================================
Extract 2023 check-variety designations from the user-provided master file:
    input_files/2023 Master Raw Data File - 20240110.xlsx
    sheet "Raw Test Data for Import"

WHY: script 65 skipped 2023 (it has 2022/2024/2025 but no 2023 source), leaving
2023 with no per-year checks. This master has an explicit Check column.

The Check column encodes the check slot: 0 = regular entry; 1/2/3/4 = a check
variety (the 4 designated checks per trial). Any Check > 0 is a check.
  Strain  : "IA2102 (II)" — parenthetical home-MG/trait suffix stripped to the
            bare code/name "IA2102" (matches how the combined file stores it).
  Trial   : "23PTIIA" / "23UTII" — MG parsed from the (UT|PT)<MG>[A|B] code.
Designation MG = the TRIAL's MG (matches TestMG in the combined file), so a
check used in multiple trial-MGs is recorded under each.

Per user instruction, matching is per (MG, Strain, Year) — Location/Trial detail
is collapsed.

Output: analysis/data/_shared/nust_checks_2023_from_master.csv  (MG, Strain, Year)

Usage:
    PYTHONUTF8=1 uv run python analysis/89b_extract_checks_2023_master.py
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO   = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
MASTER = REPO / "input_files/2023 Master Raw Data File - 20240110.xlsx"
SHEET  = "Raw Test Data for Import"
OUT    = REPO / "analysis/data/_shared/nust_checks_2023_from_master.csv"

MG_ORDER = ["00", "0", "I", "II", "III", "IV"]
# longest-first alternation so "IIA"->II, "IIIA"->III, "IVA"->IV, "00"->00
MG_FROM_TRIAL = re.compile(r"(?:UT|PT)\s*-?\s*(00|0|IV|III|II|I)", re.IGNORECASE)


def parse_mg(trial):
    m = MG_FROM_TRIAL.search(str(trial).upper())
    return m.group(1).upper() if m else None


def strip_paren(s):
    """'IA2102 (II)' -> 'IA2102'; drop ALL trailing parentheticals."""
    s = str(s).strip()
    prev = None
    while s != prev:
        prev = s
        s = re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()
    return s


def main():
    if not MASTER.exists():
        sys.exit(f"Master not found: {MASTER}")
    df = pd.read_excel(MASTER, sheet_name=SHEET,
                       usecols=lambda c: str(c) in ("Strain", "Check", "Trial", "Test", "Year"))
    df = df[pd.to_numeric(df["Check"], errors="coerce").fillna(0) > 0].copy()
    print(f"Check>0 rows: {len(df)}")

    out = set()
    n_nomg = 0
    for _, r in df.iterrows():
        mg = parse_mg(r.get("Trial")) or parse_mg(r.get("Test"))
        strain = strip_paren(r.get("Strain"))
        if mg in MG_ORDER and strain:
            out.add((mg, strain, 2023))
        else:
            n_nomg += 1

    res = pd.DataFrame(sorted(out), columns=["MG", "Strain", "Year"])
    res["MG"] = pd.Categorical(res["MG"], categories=MG_ORDER, ordered=True)
    res = res.sort_values(["MG", "Strain"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT, index=False)
    print(f"Wrote: {OUT}  ({len(res)} (MG,Strain,2023) check rows; {n_nomg} unparsed-MG rows skipped)")
    print("Per-MG check counts:")
    print(res.groupby("MG", observed=True).size().to_string())
    print("\nChecks by MG:")
    for mg in MG_ORDER:
        names = sorted(res[res["MG"] == mg]["Strain"].tolist())
        print(f"  {mg:<4s} ({len(names)}): {', '.join(names)}")


if __name__ == "__main__":
    main()
