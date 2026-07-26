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

REQUIRED_COLUMNS = ["id", "Year", "Test", "City", "State", "Strain", "Phenotype", "Value", "Units"]

# Range checks: Rex DB phenotype names -> (min, max)
# Thresholds confirmed against 1980 source PDF QC (2026-04-27).
RANGE_CHECKS = {
    "YieldBuA":    (0.0,  120.0),
    "YieldRank":   (1.0,  200.0),
    "Lodging":     (1.0,    5.0),
    "Height":      (9.0,   80.0),   # floor 9.0: confirmed HC76 very-short determinates
    "SeedQuality": (1.0,    5.0),
    "SeedSize":    (1.0,   30.0),
    "Protein":     (30.0,  55.0),
    "Oil":         (14.0,  25.0),   # floor 14.0: confirmed low-oil values at MD/MO sites
}

# Traits with date/text values — numeric parsing skipped
DATE_OR_TEXT_TRAITS = {"Maturity"}

EXPECTED_TRAITS = set(RANGE_CHECKS.keys()) | DATE_OR_TEXT_TRAITS

# Known trait omissions confirmed against source PDFs — suppress WARN for these.
# Format: {test_pattern: {traits_not_reported}}
# test_pattern is matched as a prefix (e.g. "PT-" covers PT-I through PT-IV).
KNOWN_TRAIT_OMISSIONS = {
    # Preliminary Tests never assigned yield ranks in the historical NUST era.
    "PT-":    {"YieldRank"},
    # PT-III (MG III prelim) also did not report maturity dates.
    "PT-III": {"YieldRank", "Maturity"},
    # UT-0 and UT-III did not include yield ranks — confirmed vs 1980 source PDF.
    "UT-0":   {"YieldRank"},
    "UT-III": {"YieldRank"},
}


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
    """Return list of missing required columns. 'id' is optional (added by R bridge)."""
    required = [c for c in REQUIRED_COLUMNS if c != "id"]
    missing = [c for c in required if c not in df.columns]
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
    Skips traits listed in KNOWN_TRAIT_OMISSIONS for matching test codes.
    Returns dict: {(Year, Test): [missing traits]}
    """
    issues = {}
    for (year, test), grp in df.groupby(["Year", "Test"]):
        present = set(grp["Phenotype"].unique())
        # Build expected set minus confirmed omissions for this test
        allowed_missing: set[str] = set()
        for pattern, omitted in KNOWN_TRAIT_OMISSIONS.items():
            if str(test).startswith(pattern):
                allowed_missing |= omitted
        missing = EXPECTED_TRAITS - present - allowed_missing
        if missing:
            issues[(str(year), str(test))] = sorted(missing)
    return issues


# ---------------------------------------------------------------------------
# Strain name OCR pattern table
# Each entry: (compiled regex, category label, correction function or None)
# correction fn receives the full strain name string and returns a suggestion.
# ---------------------------------------------------------------------------
_STRAIN_OCR_PATTERNS = [
    (
        # "1.27" → "L27", "1.77-8079" → "L77-8079"
        # Capital L (or I) misread as "1." by scanner/OCR.
        re.compile(r'^\d+\.'),
        "DecimalPrefix",
        lambda s: re.sub(r'^\d+\.', 'L', s),
    ),
    (
        # "57073" → "U57073", "59218" → "U59218"
        # Letter prefix dropped entirely during digitisation.
        re.compile(r'^\d+$'),
        "IntegerOnly",
        None,   # can't infer missing prefix without context
    ),
    (
        # "78-122028" → "A78-122028"
        # Letter prefix dropped before a hyphenated line designation.
        re.compile(r'^\d+-\d'),
        "DigitHyphenStart",
        None,
    ),
    (
        # "Corsoy 79 (11)" → "Corsoy 79 (II)", "Pella (111)" → "Pella (III)"
        # Roman numeral I misread as digit 1.
        # Excludes legitimate MG designations (0) and (00).
        re.compile(r'\([1-9]\d*\)\s*$'),
        "DigitMGCode",
        lambda s: re.sub(
            r'\((\d+)\)\s*$',
            lambda m: '(' + m.group(1).replace('1', 'I') + ')',
            s,
        ),
    ),
]


def flag_suspicious_strain_names(df: pd.DataFrame) -> pd.Series:
    """
    Return a string Series: empty = OK, non-empty = semicolon-joined reason codes.

    Pattern classes:
      DecimalPrefix    — "1.27"          → likely "L27"         (L → 1.)
      IntegerOnly      — "57073"         → likely "U57073"      (prefix dropped)
      DigitHyphenStart — "78-122028"     → likely "A78-122028"  (prefix dropped)
      DigitMGCode      — "Pella (111)"   → likely "Pella (III)" (I → 1)
                         excludes legitimate (0) and (00) MG codes
    """
    s = df["Strain"].astype(str).str.strip()
    reasons = pd.Series("", index=df.index)
    for pat, label, _ in _STRAIN_OCR_PATTERNS:
        hit = s.apply(lambda v, p=pat: bool(p.search(v)))
        reasons[hit] = reasons[hit].where(reasons[hit] == "", reasons[hit] + ";") + label
    return reasons


def suggest_strain_correction(name: str, reasons: str) -> str:
    """Best-guess corrected name given the semicolon-joined reason codes."""
    result = name
    for _, label, fn in _STRAIN_OCR_PATTERNS:
        if fn and label in reasons:
            result = fn(result)
    return result if result != name else "?"


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
        if trait_counts.max() - trait_counts.min() > 5:   # allow ±5: quality traits can have fewer strains than yield
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

    # 6. Suspicious strain names (OCR/digitisation artefacts)
    strain_reasons = flag_suspicious_strain_names(df)
    strain_flags   = strain_reasons != ""
    n_strain = strain_flags.sum()
    if n_strain:
        print(f"  [WARN] Suspicious strain names: {n_strain} rows across "
              f"{df.loc[strain_flags, 'Strain'].nunique()} unique strains")
        summary = (
            df.loc[strain_flags, ["Strain", "Test"]]
            .assign(Reason=strain_reasons[strain_flags].values)
            .drop_duplicates("Strain")
            .sort_values("Strain")
        )
        summary["Suggested"] = summary.apply(
            lambda r: suggest_strain_correction(r["Strain"], r["Reason"]), axis=1
        )
        for _, row in summary.iterrows():
            print(f"         {row['Strain']:<22} [{row['Reason']:<20}]  "
                  f"→ {row['Suggested']}  (Test: {row['Test']})")
        print(f"         Cross-check source XLSX; add corrections to fixes/fix_strain_ocr_{{year}}.py")
    else:
        print(f"  [OK] Strain names: no suspicious OCR patterns detected")

    # ---------------------------------------------------------------------------
    # Build flag column and split into approved / flagged
    # ---------------------------------------------------------------------------
    flag_reasons = pd.Series("", index=df.index)
    flag_reasons[range_flags]  += "RangeViolation;"
    flag_reasons[numeric_flags] += "NonNumeric;"
    flag_reasons[strain_flags]  += strain_reasons[strain_flags].apply(
        lambda r: f"SuspiciousStrainName({r});"
    )

    flagged_mask = range_flags | numeric_flags | strain_flags
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
