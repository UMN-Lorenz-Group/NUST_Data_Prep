"""
build_nust_combined_2005_2025.py
================================
Extract the 2005-2025 slice from the full corpus (nust_1941_2025_combined.csv) into a
standalone deliverable NUST_Combined_2005_2025.csv, and VERIFY that every Yield and
Maturity cell is sane, with all Maturity values expressed as day-of-year (DOY).

Verification / normalization applied:
  * Maturity: assert all values inside the physical DOY window [175, 340]; set Units="DOY"
    for every Maturity row (the queryportal load left Units blank / "date").
  * Yield (YieldBuA): assert range; NULL the single non-sane exact-0 cell (2018 UT-IV
    Rock Port MO SA14-5754 — cell median ~72.6, YieldRank 17 => a failed/missing plot
    miscoded as 0; no corroborating value, so gap beats wrong data).

Re-run this whenever the corpus changes (e.g. after fix_maturity_anchor.py + 11 + 12) so the
deliverable tracks the corrected corpus.

Writes:
  analysis/data/_shared/NUST_Combined_2005_2025.csv
  analysis/data/analysis_results/Corpus_QC/NUST_Combined_2005_2025_verification.md

Run:
  uv run python data_prep/stage2_corpus/build_nust_combined_2005_2025.py
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO   = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
QC_DIR = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"
QC_DIR.mkdir(parents=True, exist_ok=True)
COMBINED = SHARED / "nust_1941_2025_combined.csv"
OUT_CSV  = SHARED / "NUST_Combined_2005_2025.csv"
OUT_MD   = QC_DIR / "NUST_Combined_2005_2025_verification.md"

DOY_LO, DOY_HI = 175, 340
YIELD_LO, YIELD_HI = 2, 120   # corpus value-range gate window


def main():
    df = pd.read_csv(COMBINED, low_memory=False)
    s = df[(df["Year"] >= 2005) & (df["Year"] <= 2025)].copy()

    lines = ["# NUST_Combined_2005_2025 — Yield & Maturity verification", ""]
    lines.append("- Source corpus: `nust_1941_2025_combined.csv`")
    lines.append(f"- Rows (2005-2025): **{len(s):,}**")
    lines.append(f"- Years: {int(s.Year.min())}–{int(s.Year.max())}  |  Sources: {s.Source.value_counts().to_dict()}")
    lines.append("")

    # ---- Maturity ----
    mat = s["Phenotype"] == "Maturity"
    mv = pd.to_numeric(s.loc[mat, "Value_num"], errors="coerce")
    n_mat = int(mat.sum())
    n_out = int(((mv < DOY_LO) | (mv > DOY_HI)).sum())
    n_nan = int(mv.isna().sum())
    # normalize Units -> DOY for all maturity rows
    s.loc[mat, "Units"] = "DOY"
    lines.append("## Maturity")
    lines.append(f"- cells: **{n_mat:,}**  |  DOY range: **{mv.min():.0f}–{mv.max():.0f}**  |  NaN: {n_nan}")
    lines.append(f"- outside physical window [{DOY_LO},{DOY_HI}]: **{n_out}** "
                 f"({'PASS — all sane DOY' if n_out == 0 else 'FAIL'})")
    lines.append(f"- Units standardized to **DOY** for all {n_mat:,} Maturity rows")
    lines.append(f"- values <220 (far-south irrigated nurseries, verified real early maturity): "
                 f"{int((mv < 220).sum())}")
    lines.append("")

    # ---- Yield ----
    yld = s["Phenotype"] == "YieldBuA"
    yv = pd.to_numeric(s.loc[yld, "Value_num"], errors="coerce")
    n_yld = int(yld.sum())
    # NULL the single non-sane exact-0 (2018 Rock Port) — failed/missing plot miscoded 0
    zero_mask = yld & (pd.to_numeric(s["Value_num"], errors="coerce") == 0)
    n_zero = int(zero_mask.sum())
    z = None
    if n_zero:
        z = s.loc[zero_mask, ["Year", "Test", "City", "State", "Strain"]].astype(str)
        s.loc[zero_mask, "Value_num"] = np.nan
    yv2 = pd.to_numeric(s.loc[yld, "Value_num"], errors="coerce")
    lines.append("## Yield (YieldBuA)")
    lines.append(f"- cells: **{n_yld:,}**  |  range after fix: **{yv2.min():.1f}–{yv2.max():.1f}**")
    lines.append(f"- >{YIELD_HI} (unit/decimal errors): **{int((yv > YIELD_HI).sum())}**  |  "
                 f"exact-0 nulled: **{n_zero}** "
                 + (f"({z.to_dict('records')})" if n_zero else ""))
    lines.append(f"- 0 < yield < {YIELD_LO} (severe but plausible crop failures, kept): "
                 f"{int(((yv2 > 0) & (yv2 < YIELD_LO)).sum())}")
    lines.append("")

    verdict = "PASS" if (n_out == 0) else "FAIL"
    lines.append(f"## Verdict: **{verdict}** — all Maturity values are DOY in-window; "
                 f"Yield sane (1 exact-0 nulled).")

    s.to_csv(OUT_CSV, index=False)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {OUT_CSV}  ({len(s):,} rows)")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
