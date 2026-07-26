"""Known-unrecoverable Maturity gap cells.

Cells documented in logs/NUST_maturity_known_unrecoverable.md as
verified-blank in the source PDF (or otherwise unreachable from
Sojabone-only). The mark_unrecoverable() function sets these cells'
Value to "" (NA) in the F4U Maturity rows, removing them from the
hard-violation count.

Format: dict keyed by year, values are list of (Test, City_canon) tuples.
Reading is done against canonicalize_city() of the F4U's City field.

To add a new entry: also update logs/NUST_maturity_known_unrecoverable.md
so the documentation and the code stay in sync.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

_FIXES = Path(__file__).parent
sys.path.insert(0, str(_FIXES))

from apply_patches_corpus_maturity_doy import find_f4u, canonicalize_city, DOY_LO, DOY_HI

# (Year, Test, City_canon) tuples that are verified-blank in the source PDF.
# When set to NA, these cells are excluded from the hard-violation count.
UNRECOVERABLE: dict[int, list[tuple[str, str]]] = {
    1946: [
        ("UT-IV", "madison"),     # multi-trait summary block, "Mean" strain row
        ("UT-IV", "walkerton"),   # same
    ],
    1947: [
        ("UT-I", "wooster"),      # Maturity sub-table truncation ("Mean of 7 Tests")
        ("UT-I", "cresco"),       # same
    ],
    1951: [
        ("UT-I", "eastlansing"),  # PDF blanks (user-verified 2026-05-21)
        ("UT-I", "mthealthy"),    # PDF blanks (user-verified 2026-05-21)
    ],
    1954: [
        ("UT-I", "eastlansing"),  # PDF '--' in matured + planted + days (user-verified)
    ],
    1958: [
        ("UT-00", "brandon"),     # PDF '--' in matured + planted + days
    ],
    1969: [
        ("UT-IV", "centerton"),   # PDF '--' in matured + days (planted is clean)
    ],
}


# (Year, Test, City_canon) tuples that are PARTIALLY recoverable -- some
# cells have clean DOYs from a cleaner companion block, but other cells
# carry OCR garbage like '+:', '=', '()', '+c', ':' from a bad print run
# (e.g. 1969 PT-00 Block 3 R366-R378 has explicit "QUALITY TOO POOR"
# annotation at R379). For these combos, mark_partial_garbage_year()
# sets the non-numeric, non-blank cells to "" (NA) while preserving any
# clean DOY values that survived.
PARTIAL_GARBAGE: dict[int, list[tuple[str, str]]] = {
    1969: [
        # PT-00 Block 3 R366-R378 explicitly marked "QUALITY TOO POOR".
        # All Block 3 cities except those that map to a cleaner block.
        ("PT-00", "kemptville"),
        ("PT-00", "elora"),
        ("PT-00", "ashland"),
        ("PT-00", "crookston"),
        ("PT-00", "morden"),
        ("PT-00", "fargo"),
        ("PT-00", "davis"),
    ],
}


def _is_gap(v) -> bool:
    """True if cell holds an offset (non-DOY numeric) value."""
    if pd.isna(v) or v == "":
        return False
    try:
        f = float(v)
    except (ValueError, TypeError):
        return False
    return not (DOY_LO <= f <= DOY_HI)


def mark_unrecoverable_year(year: int, dry_run: bool = False) -> dict:
    """Set Maturity Value to "" (NA) for all UNRECOVERABLE (Test, city)
    cells in the year's F4U phenotypesTable1.csv. Returns stats."""
    items = UNRECOVERABLE.get(year, [])
    if not items:
        return {"year": year, "cells_set_na": 0, "items": []}

    p = find_f4u(year)
    if p is None or not p.exists():
        return {"year": year, "error": "no F4U"}

    df = pd.read_csv(p, dtype=str)
    target_idx = []
    per_item_counts = []
    for (test, city_canon) in items:
        mask = (
            (df["Phenotype"] == "Maturity")
            & (df["Test"] == test)
            & (df["City"].apply(lambda c: canonicalize_city(str(c)) == city_canon))
            & (df["Value"].apply(_is_gap))
        )
        n = int(mask.sum())
        per_item_counts.append((test, city_canon, n))
        target_idx.extend(df[mask].index.tolist())

    if not dry_run and target_idx:
        df.loc[target_idx, "Value"] = ""
        df.to_csv(p, index=False)

    return {
        "year": year,
        "cells_set_na": len(target_idx),
        "items": per_item_counts,
        "dry_run": dry_run,
    }


def mark_unrecoverable_all(dry_run: bool = False) -> list[dict]:
    return [mark_unrecoverable_year(y, dry_run=dry_run) for y in sorted(UNRECOVERABLE)]


def _is_garbage(v) -> bool:
    """True if cell is non-blank, non-DOY, AND not a clean parseable number.
    Catches OCR junk like '+:', '=', '()', '+c', ':', '--' etc."""
    if pd.isna(v) or v == "":
        return False
    s = str(v).strip()
    if s in ("--", "---"):
        return True
    try:
        f = float(s)
    except (ValueError, TypeError):
        return True  # non-numeric junk
    # Parseable as number but outside DOY range = offset (NOT garbage --
    # the regular mark_unrecoverable_year handles those if listed).
    return False


def mark_partial_garbage_year(year: int, dry_run: bool = False) -> dict:
    """For PARTIAL_GARBAGE entries, set OCR-junk cells (non-numeric / '--')
    to NA while preserving clean DOY values. Useful for partially-illegible
    pages like 1969 PT-00 Block 3."""
    items = PARTIAL_GARBAGE.get(year, [])
    if not items:
        return {"year": year, "cells_set_na": 0, "items": []}
    p = find_f4u(year)
    if p is None or not p.exists():
        return {"year": year, "error": "no F4U"}
    df = pd.read_csv(p, dtype=str)
    target_idx = []
    per_item_counts = []
    for (test, city_canon) in items:
        mask = (
            (df["Phenotype"] == "Maturity")
            & (df["Test"] == test)
            & (df["City"].apply(lambda c: canonicalize_city(str(c)) == city_canon))
            & (df["Value"].apply(_is_garbage))
        )
        n = int(mask.sum())
        per_item_counts.append((test, city_canon, n))
        target_idx.extend(df[mask].index.tolist())
    if not dry_run and target_idx:
        df.loc[target_idx, "Value"] = ""
        df.to_csv(p, index=False)
    return {
        "year": year,
        "cells_set_na": len(target_idx),
        "items": per_item_counts,
        "dry_run": dry_run,
        "mode": "partial_garbage",
    }


def mark_partial_garbage_all(dry_run: bool = False) -> list[dict]:
    return [mark_partial_garbage_year(y, dry_run=dry_run) for y in sorted(PARTIAL_GARBAGE)]


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int)
    ap.add_argument("--dry_run", action="store_true",
                    help="Don't write F4U; just report what would change")
    args = ap.parse_args()

    if args.year:
        stats_list = [mark_unrecoverable_year(args.year, dry_run=args.dry_run)]
        stats_list += [mark_partial_garbage_year(args.year, dry_run=args.dry_run)]
    else:
        stats_list = mark_unrecoverable_all(dry_run=args.dry_run)
        stats_list += mark_partial_garbage_all(dry_run=args.dry_run)

    print(f"\n{'DRY RUN' if args.dry_run else 'APPLIED'}: known-unrecoverable + partial-garbage -> NA")
    print(f"{'Year':6} {'Test':8} {'City_canon':16} {'Cells_set_NA':>12} {'Mode':<16}")
    total = 0
    for s in stats_list:
        if "error" in s:
            print(f"{s['year']:6} ERROR: {s['error']}")
            continue
        mode = s.get("mode", "unrecoverable")
        for (test, city, n) in s.get("items", []):
            if n:
                print(f"{s['year']:<6} {test:8} {city:16} {n:>12} {mode:<16}")
                total += n
    print(f"\nTotal cells set to NA: {total}")


if __name__ == "__main__":
    main()
