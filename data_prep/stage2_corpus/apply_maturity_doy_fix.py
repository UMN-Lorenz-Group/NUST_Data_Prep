"""
apply_maturity_doy_fix.py
=========================
Apply the maturity DOY physical-validity fix (fix_maturity_doy in
10_assemble_corpus.py) to an already-assembled combined corpus, then re-emit the
combined + the subset aliases. Rebuild 11 (wide) and 12 (era) afterwards.

Why this exists (and is NOT a hand-patch of the wide CSV): the authoritative
source fix lives in 10_assemble_corpus.py::fix_maturity_doy and runs during a full
assembly. But the external source tree on this machine has been partially
dismantled since the canonical corpus (combined b943555b) was built — the 1990
F4U source directory is gone, the queryportal folder was renamed
(…_1993_2022_… → …_1993_2020_…), and 1976-1979 moved under the historical bucket —
so a from-scratch 10_assemble run can no longer reproduce b943555b. This script
therefore applies the *identical* fix_maturity_doy transform (imported from
10_assemble, single source of truth) to the intact combined, so the only change
from b943555b is the intended maturity correction. It patches the LONG corpus
(the input to 11_build_wide), never the wide CSV directly.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/apply_maturity_doy_fix.py \
        --in analysis/data/_shared/_restored_combined.csv
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
# Import the SIBLING 10_assemble_corpus.py (this script's own directory) so we pick
# up the edited fix_maturity_doy — not a stale copy under a hardcoded repo path.
ASSEMBLE = Path(__file__).resolve().parent / "10_assemble_corpus.py"


def load_assemble_module():
    """Import 10_assemble_corpus.py (name starts with a digit) for its fix_maturity_doy."""
    spec = importlib.util.spec_from_file_location("assemble10", ASSEMBLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(SHARED / "_restored_combined.csv"))
    args = ap.parse_args()

    mod = load_assemble_module()

    print(f"Loading {args.inp} ...", flush=True)
    df = pd.read_csv(args.inp, low_memory=False)
    print(f"  rows: {len(df):,}   cols: {list(df.columns)}")

    # Pre-fix signature (validates this is the expected corpus)
    mat = df["Phenotype"].astype(str).eq("Maturity")
    v = pd.to_numeric(df["Value_num"], errors="coerce")
    imp = mat & v.notna() & ((v < mod.MAT_DOY_LO) | (v > mod.MAT_DOY_HI))
    print(f"  PRE-FIX: {int(mat.sum()):,} Maturity rows, "
          f"{int(imp.sum())} physically-impossible (outside [{mod.MAT_DOY_LO},{mod.MAT_DOY_HI}])")

    # Apply the authoritative fix
    fixed = mod.fix_maturity_doy(df)
    print(f"  rows after fix: {len(fixed):,}  (removed {len(df) - len(fixed)})")

    # Post-fix signature
    matf = fixed["Phenotype"].astype(str).eq("Maturity")
    vf = pd.to_numeric(fixed["Value_num"], errors="coerce")
    impf = matf & vf.notna() & ((vf < mod.MAT_DOY_LO) | (vf > mod.MAT_DOY_HI))
    print(f"  POST-FIX: {int(matf.sum()):,} Maturity rows, {int(impf.sum())} impossible")
    assert int(impf.sum()) == 0, "impossible maturity values remain after fix!"

    # Emit combined + the aliases that downstream reads. Era splits are regenerated
    # by 12_split; wide by 11_build_wide (both read nust_1941_2025 / nust_1965_2025).
    for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
        out = SHARED / name
        fixed.to_csv(out, index=False)
        print(f"  wrote {out.name}: {len(fixed):,} rows")

    # Regenerate the era subsets 10_assemble writes from `full`, so every downstream
    # artifact is consistent with the fix.
    modern = fixed[fixed["Year"] >= 1993]
    for name in ("nust_1993_2025_combined.csv",):
        modern.to_csv(SHARED / name, index=False)
        print(f"  wrote {name}: {len(modern):,} rows")
    f4u_era = fixed[fixed["Year"] <= 1988]
    for name in ("nust_1941_1988_combined_f4u.csv",):
        f4u_era.to_csv(SHARED / name, index=False)
        print(f"  wrote {name}: {len(f4u_era):,} rows")

    print("\nDone. Next: rebuild 11 (wide) then 12 (era), then run the DOY gate.")


if __name__ == "__main__":
    main()
