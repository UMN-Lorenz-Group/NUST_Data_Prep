"""
fix_2004_beresford_ag2801_maturity.py
=====================================
Correct one confirmed SOURCE-REPORT maturity typo in the 1993-2020 queryportal data.

Cell: 2004, UNIFORM TEST II Roundup-Ready (corpus Test=UT-II / Variant=Traited),
      Beresford SD, AG2801 (a check), Phenotype=Maturity.
  stored DOY = 309  ->  corrected DOY = 269

Why: the 2004 USDA NUST report (p.283 of the PDF; "UNIFORM TEST II Roundup-Ready,
MATURITY (date)") prints AG2801's Beresford maturity OFFSET as "46" — verified at the
glyph level (single token '46' in the Beresford column, anchor AG2302 = 9/19 = DOY 262)
and by an 8x render. Anchor 262 + 46 = DOY 308 (~309 as stored). An offset of +46 days
is agronomically impossible for an MG II variety whose column-mates are +2/+4/+6, so the
report itself contains a data-entry slip (intended a single digit ~+4..+6). The queryportal
transcribed the erroneous report value faithfully; this is NOT a pipeline error.

Corrected value = 269, NOT nulled: AG2801 at the SAME Beresford site+year in the
PRELIMINARY TEST II RR reads 269, and at adjacent Brookings SD reads 266 — a
high-confidence cross-test/same-environment value, so we retain the check's data point
rather than leaving a gap. (Its DOY 309 sits INSIDE the [175,340] physical-window gate,
so audit_maturity_doy_range.py does not catch it; it was surfaced by the standalone
maturity-adjusted yield estimator's within-cell outlier flag.)

Idempotent: only rewrites cells whose current value rounds to 309, so re-running is a no-op.
Applies to the built combined + wide corpus (the established modern-maturity-fix pattern,
cf. fix_2020_portageville_maturity_pipeline.py / fix_2025_maturity_doy.py). Should be folded
into 10_assemble_corpus.py::fix_maturity_doy (as an in-window context correction) at the next
clean rebuild so it survives rebuilds.

Run:
  uv run python data_prep/stage2_corpus/fix_2004_beresford_ag2801_maturity.py
"""
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO   = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
OLD, NEW = 309.0, 269.0

def _norm(s):
    return str(s).strip().lower()

def fix_combined(fp: Path) -> int:
    df = pd.read_csv(fp, low_memory=False)
    need = {"Year", "Test", "City", "State", "Strain", "Phenotype", "Value_num"}
    if not need.issubset(df.columns):
        return 0  # intermediate with a different schema (e.g. Location not City) — skip
    v = pd.to_numeric(df["Value_num"], errors="coerce")
    mask = (
        (df["Year"] == 2004)
        & (df["Test"].map(_norm) == "ut-ii")
        & (df["City"].map(_norm) == "beresford")
        & (df["State"].map(_norm) == "sd")
        & (df["Strain"].map(_norm) == "ag2801")
        & (df["Phenotype"] == "Maturity")
        & (v.round() == OLD)
    )
    n = int(mask.sum())
    if n:
        df.loc[mask, "Value_num"] = NEW
        df.to_csv(fp, index=False)
    return n

def fix_wide(fp: Path) -> int:
    df = pd.read_csv(fp, low_memory=False)
    m = pd.to_numeric(df["Maturity"], errors="coerce")
    mask = (
        (df["Year"] == 2004)
        & (df["Experiment"].map(_norm) == "utii")
        & (df["Location"].map(_norm) == "beresford_sd")
        & (df["Strain"].map(_norm) == "ag2801")
        & (m.round() == OLD)
    )
    n = int(mask.sum())
    if n:
        df.loc[mask, "Maturity"] = NEW
        df.to_csv(fp, index=False)
    return n

def main():
    combined_files = [
        SHARED / "nust_1941_2025_combined.csv",
        SHARED / "nust_1965_2025_combined.csv",
        SHARED / "nust_1993_2025_combined.csv",
    ]
    total = 0
    for fp in combined_files:
        if fp.exists():
            n = fix_combined(fp)
            total += n
            print(f"  combined {fp.name}: {n} cell(s) 309->269")
    wp = SHARED / "NUST_1941_2025_data_wide.csv"
    if wp.exists():
        n = fix_wide(wp)
        total += n
        print(f"  wide {wp.name}: {n} cell(s) 309->269")
    print(f"Done. {'applied' if total else 'no-op (already corrected)'}.")

if __name__ == "__main__":
    main()
