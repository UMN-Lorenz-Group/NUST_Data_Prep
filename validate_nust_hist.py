"""
validate_nust_hist.py — Post-extraction validation for NUST historical CSV output.

Reads phenotypesTable CSV produced by extract_nust_xlsx.py and checks:
  1. Column schema matches R pipeline expectations
  2. Value range checks per phenotype
  3. All expected traits present per entry group
  4. Strain count consistent across traits within a group

Outputs:
  approved.csv      — rows passing all checks
  review_flagged.csv — rows failing at least one check (with Flag column)

Usage:
  python validate_nust_hist.py --input phenotypesTable_1980.csv --out_dir ./output/
  python validate_nust_hist.py --dir ./output/ --out_dir ./validated/
"""

import argparse
import os
import re
import sys
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# Expected schema
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = ["Strain", "Year", "Test", "City", "State", "Phenotype", "Value"]

# Range checks: phenotype name exactly as Claude outputs it -> (min, max)
# Maturity is stored as a date string (e.g. "2026-09-05 00:00:00") — skipped from numeric range check.
RANGE_CHECKS = {
    "YIELD (bu/a)":        (0.0,  120.0),
    "YIELD RANK":          (1.0,  200.0),
    "LODGING (score)":     (1.0,    5.0),
    "PLANT HEIGHT (inches)": (10.0, 80.0),
    "SEED QUALITY (score)": (1.0,   5.0),
    "SEED SIZE (g/100)":   (1.0,   30.0),
    "PROTEIN (%)":         (30.0,  55.0),
    "OIL (%)":             (15.0,  25.0),
}

# Traits with date/text values — numeric parsing skipped
DATE_OR_TEXT_TRAITS = {"MATURITY (date)"}

EXPECTED_TRAITS = set(RANGE_CHECKS.keys()) | DATE_OR_TEXT_TRAITS


def _strip_to_numeric(val) -> float | None:
    """Strip trailing asterisks/annotations then try float conversion."""
    if val is None:
        return None
    s = re.sub(r"[*+\s]+$", "", str(val).strip())
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def check_schema(df: pd.DataFrame) -> list[str]:
    """Return list of missing required columns."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    return missing


def flag_range_violations(df: pd.DataFrame) -> pd.Series:
    """Return boolean Series: True where value is outside allowed range.
    Strips trailing asterisks/annotations before numeric comparison."""
    flags = pd.Series(False, index=df.index)
    for pheno, (lo, hi) in RANGE_CHECKS.items():
        mask = df["Phenotype"] == pheno
        if not mask.any():
            continue
        vals = df.loc[mask, "Value"].apply(_strip_to_numeric)
        out_of_range = mask & vals.notna() & ((vals < lo) | (vals > hi))
        flags |= out_of_range
    return flags


def flag_non_numeric(df: pd.DataFrame) -> pd.Series:
    """Flag rows where Value cannot be parsed as a number after stripping annotations.
    Excludes known text/date phenotypes."""
    skip_phenos = {"Parentage", "Source", "DescriptiveCode"} | DATE_OR_TEXT_TRAITS
    mask_numeric = df["Phenotype"].isin(RANGE_CHECKS.keys())
    numeric_vals = df.loc[mask_numeric, "Value"].apply(_strip_to_numeric)
    bad = mask_numeric & numeric_vals.isna() & df["Value"].notna() & (df["Value"].astype(str).str.strip() != "")
    return bad


def check_trait_completeness(df: pd.DataFrame) -> dict[str, list[str]]:
    """
    For each (Year, Test) group, check that all EXPECTED_TRAITS are present.
    Returns dict: {(Year, Test): [missing traits]}
    """
    issues = {}
    for (year, test), grp in df.groupby(["Year", "Test"]):
        present = set(grp["Phenotype"].unique())
        missing = EXPECTED_TRAITS - present
        if missing:
            issues[(str(year), str(test))] = sorted(missing)
    return issues


def check_strain_consistency(df: pd.DataFrame) -> dict[str, str]:
    """
    For each (Year, Test), check that strain count is consistent across traits.
    Returns dict: {(Year, Test): description of inconsistency}
    """
    issues = {}
    for (year, test), grp in df.groupby(["Year", "Test"]):
        trait_counts = grp.groupby("Phenotype")["Strain"].nunique()
        if trait_counts.empty:
            continue
        if trait_counts.max() - trait_counts.min() > 2:   # allow ±2 for missing values
            issues[(year, test)] = (
                f"Strain counts vary across traits: "
                f"min={trait_counts.min()} ({trait_counts.idxmin()}), "
                f"max={trait_counts.max()} ({trait_counts.idxmax()})"
            )
    return issues


# ---------------------------------------------------------------------------
# Main validation routine
# ---------------------------------------------------------------------------

def validate_file(input_path: str, out_dir: str) -> None:
    print(f"\n{'='*60}")
    print(f"Validating: {input_path}")
    print(f"{'='*60}")

    df = pd.read_csv(input_path)

    # 1. Schema check
    missing_cols = check_schema(df)
    if missing_cols:
        print(f"  [ERROR] Missing required columns: {missing_cols}")
        print("  Aborting validation — fix schema first.")
        return
    print(f"  [OK] Schema: all required columns present ({len(df)} rows)")

    # 2. Range violations
    range_flags = flag_range_violations(df)
    n_range = range_flags.sum()
    print(f"  [{'WARN' if n_range else 'OK'}] Range violations: {n_range} rows")

    # 3. Non-numeric values in numeric phenotypes
    numeric_flags = flag_non_numeric(df)
    n_numeric = numeric_flags.sum()
    print(f"  [{'WARN' if n_numeric else 'OK'}] Non-numeric values in numeric phenotypes: {n_numeric} rows")

    # 4. Trait completeness
    completeness_issues = check_trait_completeness(df)
    if completeness_issues:
        print(f"  [WARN] Missing traits in {len(completeness_issues)} (Year, Test) groups:")
        for k, v in completeness_issues.items():
            print(f"         Year={k[0]}, Test={k[1]}: missing {v}")
    else:
        print(f"  [OK] Trait completeness: all expected traits present in every group")

    # 5. Strain count consistency
    consistency_issues = check_strain_consistency(df)
    if consistency_issues:
        print(f"  [WARN] Strain count inconsistencies in {len(consistency_issues)} groups:")
        for k, v in consistency_issues.items():
            print(f"         Year={k[0]}, Test={k[1]}: {v}")
    else:
        print(f"  [OK] Strain count consistency: uniform across traits within each group")

    # ---------------------------------------------------------------------------
    # Build flag column and split into approved / flagged
    # ---------------------------------------------------------------------------
    flag_reasons = pd.Series("", index=df.index)
    flag_reasons[range_flags] += "RangeViolation;"
    flag_reasons[numeric_flags] += "NonNumeric;"

    flagged_mask = range_flags | numeric_flags
    df["Flag"] = flag_reasons.str.rstrip(";")

    approved = df[~flagged_mask].drop(columns=["Flag"])
    flagged  = df[flagged_mask]

    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(input_path))[0]

    approved_path = os.path.join(out_dir, f"{base}_approved.csv")
    flagged_path  = os.path.join(out_dir, f"{base}_review_flagged.csv")

    approved.to_csv(approved_path, index=False)
    flagged.to_csv(flagged_path, index=False)

    print(f"\n  Approved rows : {len(approved):>6}  -> {approved_path}")
    print(f"  Flagged rows  : {len(flagged):>6}  -> {flagged_path}")

    # Summary stats
    print(f"\n  --- Summary ---")
    if not df.empty:
        print(f"  Years   : {sorted(df['Year'].unique())}")
        print(f"  Tests   : {sorted(df['Test'].unique())}")
        print(f"  Traits  : {sorted(df['Phenotype'].unique())}")
        print(f"  Strains : {df['Strain'].nunique()} unique")
        print(f"  Cities  : {df['City'].nunique()} unique")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate NUST historical phenotype CSVs extracted by extract_nust_xlsx.py"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="Path to a single phenotypesTable CSV")
    group.add_argument("--dir",   help="Directory of CSVs to validate (processes all *phenotypesTable*.csv files)")
    parser.add_argument(
        "--out_dir",
        default="./validated",
        help="Output directory for approved.csv and review_flagged.csv (default: ./validated)"
    )
    args = parser.parse_args()

    if args.input:
        if not os.path.isfile(args.input):
            print(f"Error: file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        validate_file(args.input, args.out_dir)
    else:
        csv_files = [
            os.path.join(args.dir, f)
            for f in os.listdir(args.dir)
            if f.endswith(".csv") and "phenotypesTable" in f
        ]
        if not csv_files:
            print(f"No phenotypesTable*.csv files found in {args.dir}", file=sys.stderr)
            sys.exit(1)
        for csv_path in sorted(csv_files):
            validate_file(csv_path, args.out_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
