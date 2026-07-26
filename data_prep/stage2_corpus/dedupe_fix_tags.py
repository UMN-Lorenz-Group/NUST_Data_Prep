"""
dedupe_fix_tags.py
==================
Collapse repeated provenance tags in the corpus Source field.

Why: fix_maturity_anchor.py appends "|fix_mat_anchor" to Source on every row it changes. If a cell is
corrected and later re-corrected through a second CONFIG entry (e.g. the 1971 III Clarksville
apply -> revert-by-counter-shift cycle), the tag is appended twice, leaving
"F4U_1941_1988|fix_mat_anchor|fix_mat_anchor". The VALUE is unaffected, but a duplicated tag
double-counts in any tag-based audit (e.g. the --ledger row set) and misreads as two corrections.

This collapses any run of repeated identical tags down to one, for every tag, idempotently.

Usage: PYTHONUTF8=1 uv run python data_prep/stage2_corpus/dedupe_fix_tags.py [--apply]
Then rebuild 11 (wide) + 12 (era) — or run it just before those in a batch.
"""
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(os.environ.get("NUST_REPO", "C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep"))
SH = REPO / "analysis" / "data" / "_shared"


def dedupe(src: str) -> str:
    """'A|t|t|u|u' -> 'A|t|u' (collapse duplicate pipe-separated tags, keep first occurrence order)."""
    parts = str(src).split("|")
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return "|".join(out)


def main():
    apply = "--apply" in sys.argv
    c = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
    src = c["Source"].astype(str)
    # rows where some tag repeats
    dup_mask = src.map(lambda s: len(s.split("|")) != len(set(s.split("|"))))
    n = int(dup_mask.sum())
    print(f"rows with a duplicated Source tag: {n}")
    if n:
        ex = c.loc[dup_mask, ["Year", "TestMG", "TestType", "City", "Source"]].drop_duplicates("Source")
        for r in ex.head(10).itertuples():
            print(f"   {r.Year} {r.TestMG} {r.TestType} {str(r.City)[:16]:16} {r.Source}  ->  {dedupe(r.Source)}")
        c.loc[dup_mask, "Source"] = src[dup_mask].map(dedupe)
    if not n:
        print("nothing to do (idempotent no-op).")
        return
    if apply:
        for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
            c.to_csv(SH / name, index=False)
        c["_y"] = pd.to_numeric(c.Year, errors="coerce")
        for lo, hi, fn in [(1941, 1984, "nust_1941-1984_combined.csv"),
                           (1985, 2004, "nust_1985-2004_combined.csv"),
                           (2005, 2025, "nust_2005-2025_combined.csv")]:
            c[(c._y >= lo) & (c._y <= hi)].drop(columns="_y").to_csv(SH / fn, index=False)
        print(f"APPLIED: deduped {n} rows. Rebuild 11 + 12 next.")
    else:
        print("(dry run; pass --apply to write)")


if __name__ == "__main__":
    main()
