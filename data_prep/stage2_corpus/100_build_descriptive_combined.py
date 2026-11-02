"""
100_build_descriptive_combined.py  — DEPRECATED / SUPERSEDED (2026-06-24)
=========================================================================
This script was a short-lived parallel build of the combined descriptive file.
It has been CONSOLIDATED into the canonical compiler
`16_compile_descriptive_disease.py`, which produces
`analysis/data/_shared/nust_descriptive_disease_1941_2025.csv` from the same
three feeds (production 99 for 1970-1988 Chlorosis, corpus for 1989-2020, and the
modern UTPT XLSX descriptive block for 2022-2025).

Do not run this. Use:
    uv run python data_prep/stage2_corpus/16_compile_descriptive_disease.py

The stale output `analysis/data/_shared/nust_descriptive_data_combined_1970_2025.csv`
is redundant with `nust_descriptive_disease_1941_2025.csv` and can be deleted.
"""
import sys

print(__doc__)
sys.exit("Deprecated: run 16_compile_descriptive_disease.py instead.")
