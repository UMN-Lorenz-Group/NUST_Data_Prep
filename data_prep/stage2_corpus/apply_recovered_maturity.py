"""
apply_recovered_maturity.py
===========================
Inject the recovered Maturity gap cells (recovery_confirmed.csv, Source Recovered_1962_PDF /
Recovered_1975_docAI) into an already-assembled combined corpus (the 0aac7b12 pre-maturity-fix
base `_restored_combined.csv`), then apply the canonical `fix_maturity_doy` (imported from
10_assemble — single source of truth) so the result == the campaign's 0aac7b12 state + the
newly-filled per-location maturity. Writes the combined + aliases to OUT (NUST_REPO-aware, so
this can run isolated in a worktree without touching the primary checkout). Then rebuild 11
(wide), run the DOY gate, and the boxplots.

An empty placeholder Maturity row for a recovered cell is UPDATED in place; a cell with no
Maturity row (1962 PT-00, which the F4U never carried) is ADDED, copying Variant/IsCheck from
the same cell's YieldBuA row so it pairs in the wide build.

Usage:
    NUST_REPO=<worktree> uv run python data_prep/stage2_corpus/apply_recovered_maturity.py \
        --base <path to _restored_combined.csv>
"""
import argparse
import importlib.util
import os
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(os.environ.get("NUST_REPO", "C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep"))
PRIMARY = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")   # for fix_maturity_doy source
OUT = REPO / "analysis" / "data" / "_shared"
RECOVERY = REPO / "data_prep" / "stage2_corpus" / "recovery_confirmed.csv"
# our recovered maturity sources (do not touch the campaign's other recovery rows)
OUR_SOURCES = {"Recovered_1962_PDF", "Recovered_1975_docAI"}


def load_fix():
    """Import fix_maturity_doy from the primary checkout's (campaign WIP) 10_assemble."""
    p = PRIMARY / "data_prep" / "stage2_corpus" / "10_assemble_corpus.py"
    spec = importlib.util.spec_from_file_location("assemble10", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    args = ap.parse_args()

    df = pd.read_csv(args.base, low_memory=False)
    print(f"base: {len(df):,} rows  ({args.base})")

    rec = pd.read_csv(RECOVERY, low_memory=False)
    rec = rec[(rec["Source"].isin(OUR_SOURCES)) & (rec["Phenotype"] == "Maturity")].copy()
    print(f"recovered maturity to inject: {len(rec)} rows  "
          f"({sorted(rec['Test'].unique())})")

    cols = list(df.columns)
    key = ["Year", "Test", "City", "State", "Strain"]
    # normalized key: recovery keeps raw F4U spelling (canonicalized by 10_assemble on that path);
    # the _restored_combined base is already canonicalized, so match City case-insensitively.
    def nk(vals):
        y, t, c, s, st = (str(x) for x in vals)
        return (y, t, c.strip().lower(), s.strip().upper(), st)
    mat_mask = df["Phenotype"] == "Maturity"
    mat_idx = {nk(r): i
               for i, r in zip(df.index[mat_mask], df.loc[mat_mask, key].values)}
    # index YieldBuA rows to source metadata for ADDED maturity rows
    yld = df[df["Phenotype"] == "YieldBuA"]
    yld_meta = {nk(r[key].values): r for _, r in yld.iterrows()}

    updated = added = missing = 0
    add_rows = []
    for _, r in rec.iterrows():
        k = nk([r[c] for c in key])
        if k in mat_idx:
            df.at[mat_idx[k], "Value_num"] = r["Value_num"]
            df.at[mat_idx[k], "Units"] = "date"
            updated += 1
        elif k in yld_meta:
            base = yld_meta[k].copy()
            base["Phenotype"] = "Maturity"
            base["Value_num"] = r["Value_num"]
            base["Units"] = "date"
            base["Source"] = r["Source"]
            add_rows.append(base)
            added += 1
        else:
            missing += 1
    if add_rows:
        df = pd.concat([df, pd.DataFrame(add_rows)[cols]], ignore_index=True)
    print(f"  updated {updated} placeholder cells, added {added} new cells, "
          f"{missing} unmatched (no yield row)")

    # canonical DOY fix (reconstruct-or-NULL offset leaks; our valid DOYs pass through)
    mod = load_fix()
    before = len(df)
    df = mod.fix_maturity_doy(df)
    print(f"  fix_maturity_doy: {before:,} -> {len(df):,} rows")

    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
        df.to_csv(OUT / name, index=False)
        print(f"  wrote {name}: {len(df):,}")
    df[df["Year"] >= 1993].to_csv(OUT / "nust_1993_2025_combined.csv", index=False)
    df[df["Year"] <= 1988].to_csv(OUT / "nust_1941_1988_combined_f4u.csv", index=False)
    print("Done. Next: 11 (wide), gate, 32 (boxplots).")


if __name__ == "__main__":
    main()
