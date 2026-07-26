"""
fix_1972_utiii_labels.py
========================
Repair the corrupted city labels in the NUST 1972 UNIFORM TEST, Maturity Group III block.

The problem
-----------
An old extraction (Source `Recovered_1970_1988`, originating in `recovery_confirmed.csv`)
attached the 1972 UT-III per-location data to TRUNCATED / GARBLED name fragments instead of
the real city names -- e.g. `phia` (Adel-phia), `ticoW` (Quan-tico W), `townB` (Queens-town B),
`ville`, and one-cell OCR-noise rows. It also carries a `tralMean` ("Central Mean") SUMMARY
column stored as if it were a location, which violates the zero-stray-records requirement.

The values themselves are real (Maturity DOY, Yield, Height, Lodging, Protein, SeedQuality) --
only the label is wrong. This affects EVERY trait in the table, not just Maturity.

What this does
--------------
Data-driven from `g1972_label_map.csv` (one row per garbage label):
    label,correct_city,state,action,note
    action = "relabel"  -> set City/State to the correct value
    action = "drop"     -> remove the row (Mean column, unrecoverable OCR noise)

Applied at TWO layers so the fix is both immediate and durable:
  1. the assembled combined corpus (this is a post-assembly FOLD, because
     recovery_confirmed.csv is only re-integrated at a full stage-10 assembly, which we do
     not run in the patch-only rebuild path)
  2. recovery_confirmed.csv itself, so a future full re-assembly is also clean

After a relabel, a (Test,MG,City,State,Strain,Phenotype) key can collide with an
already-present row for the proper city (the proper-named rows exist but are mostly empty for
the traits the fragment carries). Collisions are de-duplicated keeping the row that HAS a
value.

Idempotent + guarded: only rows still carrying a mapped garbage label are touched, so
re-running after the fix -- and running inside finalize_corpus_recoveries.py -- is a no-op.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/fix_1972_utiii_labels.py [--apply]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SH = REPO / "analysis" / "data" / "_shared"
HERE = Path(__file__).resolve().parent
MAP = HERE / "g1972_label_map.csv"
RECOVERY = HERE / "recovery_confirmed.csv"
COMBINED = SH / "nust_1941_2025_combined.csv"

YEAR, TEST, MG = "1972", "UT", "III"
KEY = ["Year", "TestType", "TestMG", "City", "State", "Strain", "Phenotype"]


def load_map() -> pd.DataFrame:
    if not MAP.exists():
        sys.exit(f"missing {MAP} -- generate it from the agent mapping first")
    m = pd.read_csv(MAP, dtype=str, keep_default_na=False)
    need = {"label", "correct_city", "state", "action"}
    if not need.issubset(m.columns):
        sys.exit(f"{MAP.name} must have columns {need}, has {set(m.columns)}")
    return m


def relabel_frame(df: pd.DataFrame, m: pd.DataFrame, scope_mask) -> tuple[pd.DataFrame, dict]:
    """Apply relabel/drop within the rows selected by scope_mask; dedupe collisions."""
    df = df.copy()
    stats = {"relabelled": 0, "dropped": 0, "deduped": 0}
    lut = {r.label: r for r in m.itertuples()}

    idx = df.index[scope_mask(df)]
    drop_idx = []
    for i in idx:
        lab = str(df.at[i, "City"])
        e = lut.get(lab)
        if e is None:
            continue
        if e.action == "drop":
            drop_idx.append(i)
            stats["dropped"] += 1
        elif e.action == "relabel":
            df.at[i, "City"] = e.correct_city
            if e.state:
                df.at[i, "State"] = e.state
            stats["relabelled"] += 1
    if drop_idx:
        df = df.drop(index=drop_idx)

    # de-dupe keys created by relabel: prefer the row that carries a value
    has_key = all(k in df.columns for k in KEY)
    if has_key:
        v = pd.to_numeric(df.get("Value_num"), errors="coerce")
        touched = df.index[scope_mask(df)]
        # rank rows: valued first, so drop_duplicates(keep="first") keeps a valued row
        order = (~v.notna()).astype(int)
        df = df.assign(_ord=order).sort_values(["_ord"]).drop(columns="_ord")
        before = len(df)
        # only dedupe within the affected scope to avoid disturbing the rest of the corpus
        scope = df[scope_mask(df)]
        rest = df[~scope_mask(df)]
        scope2 = scope.drop_duplicates(subset=KEY, keep="first")
        stats["deduped"] = len(scope) - len(scope2)
        df = pd.concat([rest, scope2]).sort_index()
    return df, stats


def guard_present(df: pd.DataFrame, m: pd.DataFrame, scope_mask) -> bool:
    labs = set(m.label)
    return bool((scope_mask(df) & df.City.isin(labs)).any())


def main() -> None:
    apply = "--apply" in sys.argv
    m = load_map()
    print(f"loaded {len(m)} label mappings "
          f"({(m.action=='relabel').sum()} relabel, {(m.action=='drop').sum()} drop)")

    # ---- combined corpus (post-assembly) ----------------------------------------------
    def combined_scope(d):
        return (d.Year == YEAR) & (d.TestType == TEST) & (d.TestMG == MG)

    c = pd.read_csv(COMBINED, dtype=str, low_memory=False)
    if not guard_present(c, m, combined_scope):
        print("  combined: no garbage labels present -> skip (already fixed)")
    else:
        c2, st = relabel_frame(c, m, combined_scope)
        print(f"  combined: relabelled {st['relabelled']}, dropped {st['dropped']}, "
              f"deduped {st['deduped']}  ({len(c)} -> {len(c2)} rows)")
        if apply:
            for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
                c2.to_csv(SH / name, index=False)
            c2["_y"] = pd.to_numeric(c2.Year, errors="coerce")
            for lo, hi, fn in [(1941, 1984, "nust_1941-1984_combined.csv"),
                               (1985, 2004, "nust_1985-2004_combined.csv"),
                               (2005, 2025, "nust_2005-2025_combined.csv")]:
                c2[(c2._y >= lo) & (c2._y <= hi)].drop(columns="_y").to_csv(SH / fn, index=False)
            print("    APPLIED to combined + alias + era splits")

    # ---- recovery_confirmed.csv (source of record, for future re-assembly) ------------
    def rec_scope(d):
        return (d.Year == YEAR) & (d.TestType == TEST) & (d.TestMG == MG)

    r = pd.read_csv(RECOVERY, dtype=str, keep_default_na=False)
    if not guard_present(r, m, rec_scope):
        print("  recovery_confirmed.csv: no garbage labels present -> skip")
    else:
        r2, st = relabel_frame(r, m, rec_scope)
        print(f"  recovery_confirmed.csv: relabelled {st['relabelled']}, dropped {st['dropped']}, "
              f"deduped {st['deduped']}  ({len(r)} -> {len(r2)} rows)")
        if apply:
            r.to_csv(RECOVERY.with_suffix(".csv.bak_pre_1972labels"), index=False)
            r2.to_csv(RECOVERY, index=False)
            print("    APPLIED to recovery_confirmed.csv (backup written)")

    if not apply:
        print("\n(dry run; pass --apply to write)")


if __name__ == "__main__":
    main()
