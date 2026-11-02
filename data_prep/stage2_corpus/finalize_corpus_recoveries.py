"""
finalize_corpus_recoveries.py  --  canonical post-assembly recovery orchestrator
================================================================================
Re-applies EVERY session recovery to the combined corpus in one idempotent pass, then rebuilds
the wide + era splits. This is the DURABILITY mechanism: the recoveries below are post-assembly
FOLDS (they modify the gitignored combined), and past experience showed that concurrent surgical
rebuilds each applied only a SUBSET, silently clobbering the rest. Running this ONE script after
any (re)assembly guarantees the corpus carries all of them.

Every step is idempotent (each strips/reclassifies its own contribution before re-applying), so
this is safe to run repeatedly and in any starting state.

Order (recoveries are on disjoint cells, but fixed for reproducibility):
  1. UT<->PT dropped-section recovery   1985 UT-III, 1977 UT-III+IV   (apply_ut_pt_recovery)
  2. 1988 early-block PDF-grounded split UT-00/UT-0 + restore UT-I     (apply_1988_utpt_relabel)
  3. P1 oil  location-composite fold     22 cells 1941-56             (apply_oil_composite_fold)
  4. P1 oil  per-location recovery       10 cells 1962-87             (apply_oil_perloc_recovery)
  5. P1 protein location-composite fold  14 cells 1947-58             (apply_protein_composite_fold)
  6. rebuild wide (11) + era splits (12)
  7. rebuild the plot-only agronomic composite diamond files (oil + protein) -- standalone CSVs
     script 32 reads directly; not in the corpus, but regenerated here for completeness.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/finalize_corpus_recoveries.py
    (add --skip-wide to only re-fold the combined without rebuilding 11/12)
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
PY = [sys.executable]

FOLDS = [
    ("UT<->PT recovery 1985/1977", ["apply_ut_pt_recovery.py", "1985", "1977"]),
    ("1988 early-block split",      ["apply_1988_utpt_relabel.py"]),
    ("oil location-composite fold", ["apply_oil_composite_fold.py"]),
    ("oil per-location recovery",   ["apply_oil_perloc_recovery.py"]),
    ("protein composite fold",      ["apply_protein_composite_fold.py"]),
    # 1972 UT-III city-label repair MUST precede the maturity fixes below, because the leap
    # batch (leap_1972_fixes.csv) targets the corrected city names (Adelphia, Quantico, ...).
    ("1972 UT-III label repair",    ["fix_1972_utiii_labels.py", "--apply"]),
    ("maturity anchor + leap re-anchor (PDF-oracle batch + 1972 leap)",
     ["fix_maturity_anchor.py", "--apply"]),
]
WIDE = [
    ("rebuild wide (11)",  ["11_build_wide_1941_2025.py"]),
    ("era splits (12)",    ["12_split_combined_by_era.py"]),
]
DIAMONDS = [
    ("oil agronomic diamonds",     ["build_oil_agronomic_composite.py"]),
    ("protein agronomic diamonds", ["build_protein_agronomic_composite.py"]),
]


def run(label, argv):
    print(f"\n{'='*72}\n>>> {label}: {argv[0]}\n{'='*72}", flush=True)
    r = subprocess.run(PY + [str(HERE / argv[0])] + argv[1:], cwd=HERE.parent.parent)
    if r.returncode != 0:
        sys.exit(f"FAILED at {argv[0]} (exit {r.returncode})")


def main():
    skip_wide = "--skip-wide" in sys.argv
    for label, argv in FOLDS:
        run(label, argv)
    if not skip_wide:
        for label, argv in WIDE:
            run(label, argv)
    for label, argv in DIAMONDS:
        run(label, argv)
    print("\n" + "=" * 72)
    print("ALL RECOVERIES RE-APPLIED. Corpus + wide + era splits + diamond files are current.")
    print("Next (optional): regenerate plots — analysis/scripts/P2_raw_trends/"
          "32_secondary_trait_boxplots_per_mg_1941_2025.py")


if __name__ == "__main__":
    main()
