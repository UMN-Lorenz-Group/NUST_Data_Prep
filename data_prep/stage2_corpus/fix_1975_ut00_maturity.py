"""
fix_1975_ut00_maturity.py
=========================
Recover the 1975 UT-00 (MG-00) per-location Maturity that the doc-AI extraction dropped
(both phenotypesTable0 and the F4U have 77 all-EMPTY UT-00 Maturity placeholders). This is
the priority per-MG boxplot gap (1975 MG-00 maturity box is currently empty).

Source: the doc-AI intermediate page 7.1 for "UNIFORM TEST 00, 1975" — a clean columnized
xlsx (committed at source_tables/1975_ut00_maturity_7.1.xlsx, from the R: 1975_done archive).
The first trait block ("9 Tests") is per-location Maturity: the check variety **Portage** row
prints absolute maturity DATES (the per-location anchors), every other strain a
days-earlier(-)/later(+) offset. DOY = anchorDOY(loc) + offset (Portage's own DOY = its date).

Every anchor is cross-checked against the table's own "Date planted"/"+Days to mature" rows
(planted DOY + days == matured DOY) before use. Ashland WI has no printed anchor date
(blank/'*' — excluded from the mean) so it stays a documented gap.

--dry-run validator by default (writes nothing). --apply appends to recovery_confirmed.csv.

Usage:
    uv run python data_prep/stage2_corpus/fix_1975_ut00_maturity.py            # validate
    uv run python data_prep/stage2_corpus/fix_1975_ut00_maturity.py --apply    # -> ledger
"""
import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(os.environ.get("NUST_REPO", "C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep"))
# committed source table (provenance), read relative to this script so it works in any checkout
XLSX = Path(__file__).resolve().parent / "source_tables" / "1975_ut00_maturity_7.1.xlsx"

# xlsx column index -> (City, State) as spelled in the 1975 F4U UT-00 roster. Column 1 = Mean.
COLS = {
    2: ("Ottawa", "ONT"), 3: ("Elora", "ONT"), 4: ("Kemptville", "ONT"),
    5: ("Ashland", "WI"), 6: ("Crookston", "MN"), 7: ("Morris", "MN"),
    8: ("Rosemount", "MN"), 9: ("Portage la Prairie", "MAN"), 10: ("Morden", "MAN"),
    11: ("Brandon", "MAN"), 12: ("Fargo", "ND"),
}
CHECK = "Portage"                       # the MG-00 check whose row carries absolute dates
F4U_STRAINS = {"Altona", "Norman", "Portage", "CM121", "CM147", "CM148", "M65-217"}


def doy(m, d):
    return date(1975, m, d).timetuple().tm_yday


def parse_date(s):
    m = re.match(r"^\s*(\d{1,2})\s*[-/]\s*(\d{1,2})\s*$", str(s))
    if not m:
        return None
    mo, da = int(m.group(1)), int(m.group(2))
    if 1 <= mo <= 12 and 1 <= da <= 31:
        return doy(mo, da)
    return None


def parse_offset(s):
    t = str(s).strip().replace(" ", "")
    if t in ("O", "o"):          # OCR 'O' for zero
        return 0
    m = re.match(r"^([+-]?)(\d+)$", t)   # whole-number offsets only (means are .1 fractional)
    return int(m.group(2)) * (-1 if m.group(1) == "-" else 1) if m else None


def load_block():
    """Return (df_rows, anchors) for the Maturity block of page 7.1."""
    raw = pd.read_excel(XLSX, header=None)
    # Maturity block = rows between the 'N Tests MATURITY' caption and the 'Date planted' row.
    def find_col0(pat):
        for i in range(len(raw)):
            if re.search(pat, str(raw.iat[i, 0]), re.I):
                return i
        return None
    top = find_col0(r"MATURITY")
    planted = find_col0(r"Date\s*planted")
    return raw, top, planted


def recover(verbose=True):
    raw, top, planted = load_block()
    # anchor row = the CHECK (Portage): its cells are dates
    anchors = {}
    for i in range(top + 1, planted):
        name = str(raw.iat[i, 0]).strip()
        if name.startswith(CHECK):
            for c, (city, st) in COLS.items():
                d = parse_date(raw.iat[i, c])
                if d is not None:
                    anchors[c] = d
            break
    # arithmetic self-check: planted DOY + days == matured DOY, per column
    days_row = planted + 1
    ok = bad = 0
    for c in COLS:
        pd_ = parse_date(raw.iat[planted, c])
        try:
            dd = int(float(str(raw.iat[days_row, c]).strip()))
        except (ValueError, TypeError):
            dd = None
        if c in anchors and pd_ is not None and dd is not None:
            (ok if abs((pd_ + dd) - anchors[c]) <= 1 else bad).__class__  # noqa
            if abs((pd_ + dd) - anchors[c]) <= 1:
                ok += 1
            else:
                bad += 1
                if verbose:
                    print(f"  !! anchor arithmetic mismatch col {c} {COLS[c]}: "
                          f"planted{pd_}+days{dd}={pd_+dd} vs anchor{anchors[c]}")
    if verbose:
        print(f"anchor arithmetic check: {ok} ok, {bad} mismatched")
        print("anchors:", {COLS[c][0]: anchors[c] for c in sorted(anchors)})

    rows = []                             # (strain, city, state, DOY, note)
    for i in range(top + 1, planted):
        name = str(raw.iat[i, 0]).strip()
        if name not in F4U_STRAINS:
            continue
        for c, (city, st) in COLS.items():
            cell = raw.iat[i, c]
            if name == CHECK:             # check row: its own printed date IS the DOY
                d = parse_date(cell)
                if d is not None:
                    rows.append((name, city, st, d, "date"))
            else:
                off = parse_offset(cell)
                if off is not None and c in anchors:
                    val = anchors[c] + off
                    if 175 <= val <= 340:
                        rows.append((name, city, st, val, f"{off:+d}"))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rows = recover()
    print(f"\n=== 1975 UT-00: {len(rows)} (strain,loc) Maturity cells recovered ===")
    grid = {}
    for s, city, st, d, note in rows:
        grid.setdefault(s, {})[city] = f"{d}"
    cities = [COLS[c][0] for c in sorted(COLS)]
    print("strain".ljust(9), " ".join(c[:8].rjust(9) for c in cities))
    for s, cells in grid.items():
        print(s.ljust(9), " ".join(cells.get(c, "-").rjust(9) for c in cities))

    if not args.apply:
        print("\n[dry-run] no files written. Re-run with --apply to append to recovery_confirmed.csv.")
        return

    rec_csv = REPO / "data_prep" / "stage2_corpus" / "recovery_confirmed.csv"
    ledger = pd.read_csv(rec_csv, low_memory=False)
    new = [{"Year": 1975, "TestType": "UT", "TestMG": "00", "Test": "UT-00",
            "Strain": s, "City": city, "State": st, "Phenotype": "Maturity",
            "Value_num": d, "Units": "date", "Source": "Recovered_1975_docAI"}
           for s, city, st, d, note in rows]
    new_df = pd.DataFrame(new)[list(ledger.columns)]
    prior = ((ledger["Year"] == 1975) & (ledger["Test"] == "UT-00")
             & (ledger["Phenotype"] == "Maturity"))
    if prior.any():
        print(f"  (removing {int(prior.sum())} previously-added 1975 UT-00 maturity rows)")
        ledger = ledger[~prior]
    out = pd.concat([ledger, new_df], ignore_index=True)
    out.to_csv(rec_csv, index=False)
    print(f"\nrecovery_confirmed.csv: +{len(new_df)} rows (1975 UT-00 Maturity) -> {len(out)} total")


if __name__ == "__main__":
    main()
