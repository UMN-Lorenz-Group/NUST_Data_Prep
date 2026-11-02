"""Record + sweep-NA all remaining Maturity hard-violation cells in the
ASSEMBLED CORPUS (1941-2025), aligned with the feasibility check rules.

Two tasks for the analysis session:
  (i)  Build a per-cell record (CSV) of every assembled-corpus Maturity
       cell that is a HARD VIOLATION (Value < 150 or Value > 366, or
       non-numeric junk like '+:', '--', '=', '()') or MISSING (blank).
       Includes Year, Test, Strain, City, raw Value, classification.
  (ii) Set ALL remaining hard-violation cells to NA so the analysis
       session starts from a clean "0 hard Maturity violations" baseline.

Feasibility-check ranges (analysis/23_feasibility_check_1941_2025.py):
  Maturity: hard_lo=150, soft_lo=220, soft_hi=330, hard_hi=366
  HARD violation: v < 150 OR v > 366
  SOFT violation: 150 <= v < 220 OR 330 < v <= 366
  OK:             220 <= v <= 330

Output:
  logs/NUST_maturity_na_cells_record.csv   -- per-cell record (HARD only)
  logs/NUST_maturity_na_cells_summary.csv  -- (Year,Test,City,class) roll-up
  Sweeps the assembled corpus CSV in-place (creates a .bak first).

Idempotent. --dry_run for preview without writing.
"""
from __future__ import annotations
import sys, shutil
from pathlib import Path
import pandas as pd

_FIXES = Path(__file__).parent
REPO = _FIXES.parent
LOGS = REPO / "logs"
DATA = REPO / "analysis" / "data" / "_shared"

# Feasibility check thresholds (mirrors analysis/23_feasibility_check_1941_2025.py)
MAT_HARD_LO = 150.0
MAT_SOFT_LO = 220.0
MAT_SOFT_HI = 330.0
MAT_HARD_HI = 366.0


def classify(v) -> str:
    """Classify a Maturity Value per the feasibility-check thresholds."""
    if pd.isna(v) or str(v).strip() == "":
        return "blank"
    s = str(v).strip()
    if s in ("--", "---", "..", "..."):
        return "hard_violation"  # treat OCR dashes as hard violations
    try:
        f = float(s)
    except (ValueError, TypeError):
        return "hard_violation"  # non-numeric junk = hard violation
    if f < MAT_HARD_LO or f > MAT_HARD_HI:
        return "hard_violation"
    if f < MAT_SOFT_LO or f > MAT_SOFT_HI:
        return "soft_violation"
    return "valid_doy"


def find_corpus_csv() -> Path:
    """Locate the assembled corpus CSV. Checks worktree DATA first then
    the main repo (the assembler writes to the main repo's analysis/data/)."""
    main_repo_data = Path(r"C:\Users\vramasub\Desktop\UMN_GIT\NUST_Data_Prep\analysis\data")
    candidates = [
        DATA / "nust_1941_2025_combined.csv",
        main_repo_data / "nust_1941_2025_combined.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fallback: any nust_*_combined.csv in either location
    for d in (DATA, main_repo_data):
        matches = sorted(d.glob("nust_*_combined.csv"))
        if matches:
            return matches[-1]
    raise FileNotFoundError(f"No assembled corpus CSV found in {DATA} or {main_repo_data}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--skip_sweep", action="store_true",
                    help="Only build the record; do not modify the corpus")
    ap.add_argument("--corpus", type=str, default=None,
                    help="Override corpus CSV path")
    args = ap.parse_args()

    corpus_path = Path(args.corpus) if args.corpus else find_corpus_csv()
    print(f"Reading corpus: {corpus_path}")
    df = pd.read_csv(corpus_path, dtype=str, low_memory=False)
    print(f"  Total rows: {len(df):,}")

    mat_mask = df["Phenotype"] == "Maturity"
    mat = df[mat_mask].copy()
    print(f"  Maturity rows: {len(mat):,}")

    mat["classification"] = mat["Value_num"].apply(classify)

    # Stats
    counts = mat["classification"].value_counts()
    print("\nClassification:")
    for k, v in counts.items():
        print(f"  {k:<20} {v:>8,}")

    # Per-year breakdown
    mat["Year_int"] = pd.to_numeric(mat["Year"], errors="coerce").astype("Int64")
    by_year = (mat.groupby(["Year_int", "classification"]).size()
                  .unstack(fill_value=0))
    print("\nPer-year (classification not 'valid_doy'):")
    cols_show = [c for c in ("hard_violation", "soft_violation", "blank")
                 if c in by_year.columns]
    by_year_show = by_year[cols_show]
    by_year_show = by_year_show[by_year_show.sum(axis=1) > 0]
    print(by_year_show.to_string())

    # ---- Record: per-cell HARD violations ----
    hard = mat[mat["classification"] == "hard_violation"].copy()
    record_cols = ["Year", "Test", "Strain", "City", "Value_num", "classification"]
    # Some corpus columns may be named differently; map flexibly
    if "Location" in mat.columns and "City" not in mat.columns:
        record_cols[record_cols.index("City")] = "Location"
    record = hard[[c for c in record_cols if c in hard.columns]].copy()
    out_csv = LOGS / "NUST_maturity_na_cells_record.csv"
    record.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv.name} ({len(record):,} hard-violation cells)")

    # Summary: (Year, Test, City, classification) -> N
    city_col = "City" if "City" in mat.columns else "Location"
    summary = (mat[mat["classification"].isin(("hard_violation", "soft_violation", "blank"))]
                  .groupby(["Year_int", "Test", city_col, "classification"])
                  .size().reset_index(name="N")
                  .rename(columns={"Year_int": "Year"}))
    out_sum = LOGS / "NUST_maturity_na_cells_summary.csv"
    summary.to_csv(out_sum, index=False)
    print(f"Wrote {out_sum.name} ({len(summary):,} grouping rows)")

    # ---- Sweep: set hard violations to NA in the corpus ----
    if args.skip_sweep:
        print("\nSkipping sweep (--skip_sweep set).")
        return
    n_hard = int((mat["classification"] == "hard_violation").sum())
    print(f"\n{'DRY RUN' if args.dry_run else 'APPLIED'}: sweep {n_hard} "
          f"hard-violation cells -> NA in {corpus_path.name}")
    if not args.dry_run and n_hard:
        # Build the mask on the full df
        full_mat_class = df["Value_num"].apply(
            lambda v: classify(v) if True else "blank"  # only applies to mat rows below
        )
        # Apply mask only on Maturity rows
        sweep_mask = mat_mask & df["Value_num"].apply(classify).eq("hard_violation")
        # Backup then write
        bak = corpus_path.with_suffix(corpus_path.suffix + ".bak")
        if not bak.exists():
            shutil.copy(corpus_path, bak)
            print(f"  Backup: {bak.name}")
        df.loc[sweep_mask, "Value_num"] = ""
        df.to_csv(corpus_path, index=False)
        print(f"  Wrote {corpus_path.name} with {int(sweep_mask.sum())} cells set NA")


if __name__ == "__main__":
    main()
