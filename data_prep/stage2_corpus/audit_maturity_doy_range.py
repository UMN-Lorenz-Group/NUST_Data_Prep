"""
audit_maturity_doy_range.py
===========================
Rebuild GATE: fail loudly if any soybean Maturity value in the corpus is a
physically-impossible day-of-year (DOY). Run this AFTER every corpus rebuild,
alongside the stray-strain gate (13_qc_strain_germplasm_audit.py) and the grid-
integrity gate (analysis/scripts/Corpus_QC/audit_grid_integrity.py).

Why this exists: a class of maturity defect — raw ±day offsets (relative to a
dated check) and days-after-planting values leaking into the absolute-DOY
Maturity field — slipped past QC for years because the boxplot / distribution
visualisations dropped these as outliers BEFORE rendering, hiding them. This gate
checks the RAW corpus values with NO outlier filtering, so the anomaly can never
silently survive a rebuild again. The source fix lives in
data_prep/stage2_corpus/10_assemble_corpus.py::fix_maturity_doy.

Physical window: soybean R8 maturity in North America falls late summer→fall.
The empirical corpus floor is DOY 183 (early July; ultra-early MG-00 at southern
sites) and the latest plausible is ~DOY 330 (mid-Nov; deep-south late MG). The
window [175, 340] sits just below the 183 floor (an empty guard band spans DOY
165-182) and just above the latest observed legitimate value, so it flags only
genuinely-impossible values (e.g. June DOYs, negatives) without clipping real data.

Exit code: 0 if clean, 1 if ANY impossible Maturity value is present.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/audit_maturity_doy_range.py
"""
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
COMBINED = SHARED / "nust_1941_2025_combined.csv"
WIDE = SHARED / "NUST_1941_2025_data_wide.csv"

MAT_DOY_LO, MAT_DOY_HI = 175, 340   # physical DOY window (see module docstring)


def _report(name, sub, cols):
    """Print a bad-value block and return its row count."""
    if sub.empty:
        print(f"  [{name}] OK — 0 impossible Maturity values")
        return 0
    print(f"  [{name}] FAIL — {len(sub)} impossible Maturity values "
          f"(outside [{MAT_DOY_LO},{MAT_DOY_HI}])")
    print(f"    range: {sub['_v'].min()} .. {sub['_v'].max()}   negatives: {(sub['_v'] < 0).sum()}")
    print(f"    by year: {sub['Year'].value_counts().sort_index().to_dict()}")
    with pd.option_context("display.max_rows", 60, "display.width", 200):
        print(sub[cols + ["_v"]].sort_values(["Year"]).head(60).to_string(index=False))
    return len(sub)


def audit_combined():
    if not COMBINED.exists():
        print(f"  [combined] SKIP — {COMBINED.name} not found")
        return 0
    df = pd.read_csv(COMBINED, low_memory=False)
    mat = df[df["Phenotype"].astype(str).str.fullmatch("Maturity", case=False, na=False)].copy()
    mat["_v"] = pd.to_numeric(mat["Value_num"], errors="coerce")
    bad = mat[mat["_v"].notna() & ((mat["_v"] < MAT_DOY_LO) | (mat["_v"] > MAT_DOY_HI))]
    cols = [c for c in ["Year", "TestType", "TestMG", "Test", "City", "State", "Strain"] if c in bad.columns]
    print(f"\n=== combined ({COMBINED.name}): {len(df):,} rows, {len(mat):,} Maturity rows ===")
    return _report("combined", bad, cols)


def audit_wide():
    if not WIDE.exists():
        print(f"  [wide] SKIP — {WIDE.name} not found")
        return 0
    df = pd.read_csv(WIDE, low_memory=False)
    df["_v"] = pd.to_numeric(df["Maturity"], errors="coerce")
    bad = df[df["_v"].notna() & ((df["_v"] < MAT_DOY_LO) | (df["_v"] > MAT_DOY_HI))]
    cols = [c for c in ["Year", "Experiment", "MG", "Location", "Strain"] if c in bad.columns]
    print(f"\n=== wide ({WIDE.name}): {len(df):,} rows, {df['_v'].notna().sum():,} non-null Maturity ===")
    return _report("wide", bad, cols)


def main():
    print("=" * 70)
    print("Maturity DOY physical-range gate  (window [%d, %d])" % (MAT_DOY_LO, MAT_DOY_HI))
    print("=" * 70)
    n = audit_combined() + audit_wide()
    print("\n" + "=" * 70)
    if n:
        print(f"GATE FAILED: {n} physically-impossible Maturity DOY value(s) present.")
        print("These are raw offsets / days-after-planting / garbled cells leaking into")
        print("the absolute-DOY Maturity field. Fix at source in 10_assemble_corpus.py")
        print("(fix_maturity_doy) and rebuild (10 → 11 → 12).")
        sys.exit(1)
    print("GATE PASSED: all Maturity values are physically-plausible DOY.")
    sys.exit(0)


if __name__ == "__main__":
    main()
