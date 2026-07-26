"""
08_extraction_accuracy.py
=========================
Compute extraction accuracy metrics for NUST historical years.

For each year with values-mode QC data, computes:

1. HUMAN OCR ACCURACY (%)
   The XLSX files in input_YYYY/ were OCR'd by humans from source PDFs.
   We extracted that XLSX via Claude API into combined_YYYY_phenotypesTable.csv,
   then validated → combined_YYYY_phenotypesTable_approved.csv (= total cells).
   Claude QC (`qc_pdf_vs_csv.py --mode values`) then compared each cell against
   the PDF. Each discrepancy = a cell where human OCR disagreed with PDF.

       OCR accuracy = (1 - discrepancies / total_cells) * 100

   not_found = strain present in CSV but absent in PDF (likely phantom OCR row);
   ambiguous = QC could not reliably determine. Reported separately.

2. CLAUDE AGENT FIX RATE (%)
   apply_patches_YYYY.py reads the QC discrepancies and auto-applies patches
   subject to thresholds (e.g., |Protein diff| >= 0.3) and skips (YieldRank).
   Patches successfully applied to the approved CSV / Files4Upload define
   what fraction of OCR errors the Claude agent corrected.

       Fix rate = patches_applied / discrepancies * 100

Outputs:
   analysis/data/extraction_accuracy_per_year.csv
   analysis/data/extraction_accuracy_report.md
"""
import sys, re, json
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent.parent
OUT_DIR = REPO / "analysis" / "data" / "_shared"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Phenotypes excluded from patching (matches apply_patches_*.py SKIP_PHENOTYPES)
SKIP_PHENOTYPES = {"YieldRank"}


def parse_patches_applied(log_path: Path) -> int:
    """Extract total cells updated from an apply_patches_YYYY.log.

    The log emits per-target lines like:
        QC patches applied: N cells updated, M misses
    Sum across both targets (combined + approved CSVs)."""
    if not log_path.exists():
        return -1
    total = 0
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.search(r"QC patches applied:\s+(\d+)\s+cells updated", line)
        if m:
            total += int(m.group(1))
    return total


def metrics_for_year(year: str) -> dict | None:
    approved = REPO / f"output_files/output_{year}/validated/combined_{year}_phenotypesTable_approved.csv"
    qc_csv   = REPO / f"output_files/output_{year}/qc/qc_{year}_values.csv"
    summary  = REPO / f"output_files/output_{year}/qc/qc_{year}_values_summary.json"
    patch_log = REPO / f"archive/logs_docs/logs/apply_patches_{year}.log"  # logs archived in reorg

    if not approved.exists() or not qc_csv.exists():
        return None

    df_approved = pd.read_csv(approved, dtype=str)
    total_cells = len(df_approved)

    df_qc = pd.read_csv(qc_csv, dtype=str)
    v_counts = df_qc["verdict"].value_counts().to_dict()
    n_disc   = v_counts.get("discrepancy", 0)
    n_nf     = v_counts.get("not_found", 0)
    n_amb    = v_counts.get("ambiguous", 0)

    # "Actionable" discrepancies = those that apply_patches would consider.
    # Excludes YieldRank phenotype and non-numeric PDF values.
    def _is_numeric(s):
        try:
            float(str(s).strip().rstrip("*").replace(",", "."))
            return True
        except (ValueError, TypeError):
            return False

    disc_df = df_qc[df_qc["verdict"] == "discrepancy"].copy()
    actionable = disc_df[
        (~disc_df["phenotype"].isin(SKIP_PHENOTYPES)) &
        disc_df["pdf_value"].apply(_is_numeric)
    ]
    n_actionable = len(actionable)

    # combos_checked: from summary if available
    combos = None
    if summary.exists():
        try:
            combos = json.loads(summary.read_text()).get("combos_checked")
        except Exception:
            pass

    # Patches applied — apply_patches script writes counts for BOTH targets
    # (combined and approved CSVs). We divide by 2 to get patches per CSV
    # (the per-CSV patch count is what corresponds to QC discrepancies).
    patches_total = parse_patches_applied(patch_log)
    patches_per_csv = patches_total // 2 if patches_total > 0 else patches_total

    ocr_accuracy_pct = (1.0 - n_disc / total_cells) * 100.0 if total_cells else None
    # Note: `total_cells` is the historical name; the value is the COUNT OF
    # ROWS in combined_YYYY_phenotypesTable_approved.csv (long format), i.e.
    # one row per (Test, Strain, City, Phenotype) measurement. The report
    # below renders this as "rows" for clarity, since a long-format row IS
    # the unit being QC'd against the PDF.
    fix_rate_pct = (patches_per_csv / n_disc * 100.0) if (n_disc > 0 and patches_per_csv >= 0) else None
    actionable_fix_rate_pct = (
        (patches_per_csv / n_actionable * 100.0) if (n_actionable > 0 and patches_per_csv >= 0) else None
    )

    return {
        "year": year,
        "total_cells": total_cells,
        "combos_checked": combos,
        "discrepancies": n_disc,
        "not_found": n_nf,
        "ambiguous": n_amb,
        "actionable_disc": n_actionable,
        "patches_applied_per_csv": patches_per_csv,
        "ocr_accuracy_pct": ocr_accuracy_pct,
        "fix_rate_pct": fix_rate_pct,
        "actionable_fix_rate_pct": actionable_fix_rate_pct,
    }


def main():
    years = sorted({
        p.stem.replace("qc_", "").replace("_values", "")
        for p in REPO.glob("output_files/output_*/qc/qc_*_values.csv")
    })

    rows = []
    for y in years:
        m = metrics_for_year(y)
        if m is None:
            continue
        rows.append(m)

    df = pd.DataFrame(rows)
    if df.empty:
        print("No QC data found. Run qc_pdf_vs_csv.py --mode values for at least one year.")
        return

    # Per-year detailed CSV
    out_csv = OUT_DIR / "extraction_accuracy_per_year.csv"
    df.to_csv(out_csv, index=False)
    print(f"Wrote {out_csv} ({len(df)} years)")

    # Aggregate accuracy across ALL years
    agg = {
        "total_cells": df["total_cells"].sum(),
        "discrepancies": df["discrepancies"].sum(),
        "not_found": df["not_found"].sum(),
        "ambiguous": df["ambiguous"].sum(),
        "actionable_disc": df["actionable_disc"].sum(),
    }
    agg["ocr_accuracy_pct"] = (1 - agg["discrepancies"] / agg["total_cells"]) * 100

    # Fix rate only meaningful for years with apply_patches log
    df_patched = df[df["patches_applied_per_csv"] >= 0].copy()
    if not df_patched.empty:
        agg["patched_years"] = df_patched["year"].tolist()
        agg["patched_disc_total"]       = int(df_patched["discrepancies"].sum())
        agg["patched_actionable_total"] = int(df_patched["actionable_disc"].sum())
        agg["patches_applied"]          = int(df_patched["patches_applied_per_csv"].sum())
        agg["fix_rate_pct"] = (
            agg["patches_applied"] / agg["patched_disc_total"] * 100
        ) if agg["patched_disc_total"] else None
        agg["actionable_fix_rate_pct"] = (
            agg["patches_applied"] / agg["patched_actionable_total"] * 100
        ) if agg["patched_actionable_total"] else None
    else:
        agg["patched_years"] = []
        agg["patches_applied"] = 0
        agg["fix_rate_pct"] = None
        agg["actionable_fix_rate_pct"] = None

    # Markdown report
    md_path = OUT_DIR / "extraction_accuracy_report.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# NUST Extraction Accuracy Report\n\n")
        f.write("## Methodology\n\n")
        f.write("- **OCR accuracy** = (1 − discrepancies / total_rows) × 100. "
                "Total rows = rows in `combined_YYYY_phenotypesTable_approved.csv` "
                "(long format: one row per (Test, Strain, City, Phenotype) "
                "measurement). Discrepancies = rows where Claude QC (values mode) "
                "found CSV ≠ PDF.\n")
        f.write("- **Claude fix rate** = patches_applied / discrepancies × 100. Patches are "
                "auto-applied by `fixes/apply_patches_YYYY.py` from the QC discrepancy CSV, "
                "subject to thresholds (e.g., |Protein diff| ≥ 0.3) and SKIP_PHENOTYPES={YieldRank}.\n")
        f.write("- **Actionable discrepancies** = discrepancies excluding YieldRank and "
                "non-numeric PDF values (the subset patchable programmatically).\n")
        f.write("- `not_found` = strain present in CSV but absent in PDF (likely phantom OCR row).\n")
        f.write("- `ambiguous` = QC could not determine. Excluded from accuracy denominator.\n\n")

        f.write("## Aggregate — OCR accuracy across all years\n\n")
        f.write(f"- Years included: {', '.join(df['year'].tolist())}\n")
        f.write(f"- Total rows QC'd: **{agg['total_cells']:,}** "
                f"(one row per Test/Strain/City/Phenotype measurement)\n")
        f.write(f"- Total discrepancies: **{agg['discrepancies']:,}**\n")
        f.write(f"- `not_found`: {agg['not_found']:,}  |  `ambiguous`: {agg['ambiguous']:,}\n")
        f.write(f"- Actionable discrepancies: {agg['actionable_disc']:,}\n\n")
        f.write(f"**Human OCR accuracy: {agg['ocr_accuracy_pct']:.2f}%**\n\n")

        f.write("## Aggregate — Claude agent fix rate (years with apply_patches log only)\n\n")
        f.write(f"- Patched years: {', '.join(agg['patched_years'])}\n")
        if agg['patches_applied']:
            f.write(f"- Discrepancies in patched years: {agg['patched_disc_total']:,}\n")
            f.write(f"- Actionable discrepancies in patched years: {agg['patched_actionable_total']:,}\n")
            f.write(f"- Patches applied by Claude agent: {agg['patches_applied']:,}\n\n")
            f.write(f"**Claude fix rate (of all discrepancies): {agg['fix_rate_pct']:.1f}%**\n\n")
            f.write(f"**Claude fix rate (of actionable discrepancies): {agg['actionable_fix_rate_pct']:.1f}%**\n\n")
        else:
            f.write("(no apply_patches logs found — fix rate unavailable)\n\n")

        f.write("## Per-year breakdown\n\n")
        f.write("| Year | Rows | Disc | Not-found | Amb | Actionable | Patched | OCR acc % | Fix % (actionable) |\n")
        f.write("|------|------:|-----:|----------:|----:|-----------:|--------:|----------:|-------------------:|\n")
        for _, r in df.iterrows():
            patched_cell = (int(r['patches_applied_per_csv'])
                            if r['patches_applied_per_csv'] >= 0 else "—")
            fix_cell = (f"{r['actionable_fix_rate_pct']:.1f}%"
                        if pd.notna(r['actionable_fix_rate_pct']) else "—")
            f.write(
                f"| {r['year']} "
                f"| {r['total_cells']:,} "
                f"| {r['discrepancies']:,} "
                f"| {r['not_found']} "
                f"| {r['ambiguous']} "
                f"| {r['actionable_disc']} "
                f"| {patched_cell} "
                f"| {r['ocr_accuracy_pct']:.2f}% "
                f"| {fix_cell} |\n"
            )

        f.write("\n## Caveats\n\n")
        f.write("- QC compares against the source PDF; accuracy is relative to the PDF "
                "(considered ground truth). PDF itself may have typos.\n")
        f.write("- `not_found` rows in 1972 reflect dropped GlobalParentage data; in 1974 "
                "they reflect dropped PT-IV section-header phantoms; in 1971 they reflect "
                "dropped `unknown_row*` placeholders. These were filtered by apply_patches, "
                "not in the OCR accuracy denominator.\n")
        f.write("- The `fix_rate_pct` of actionable discrepancies should approach 100% — "
                "lower values indicate apply_patches misses (city-spelling variants, "
                "strain-name normalization issues). The full discrepancy fix rate (not just "
                "actionable) is lower because YieldRank and date-string Maturity values are "
                "deliberately skipped.\n")
        f.write("- 1965-1970 years are transitional/early-modern era with severe OCR damage "
                "in some sections (e.g., 1969 'QUALITY TOO POOR TO EDIT' notes in source XLSX). "
                "Their OCR accuracy reflects historical scanning limitations of mid-1960s reports.\n")

    print(f"Wrote {md_path}")
    print()
    print(f"Aggregate: OCR accuracy = {agg['ocr_accuracy_pct']:.2f}% across "
          f"{len(df)} years ({agg['total_cells']:,} rows, {agg['discrepancies']:,} discrepancies).")
    if agg['actionable_fix_rate_pct'] is not None:
        print(f"           Claude fix rate (actionable) = {agg['actionable_fix_rate_pct']:.1f}% "
              f"({agg['patches_applied']:,}/{agg['patched_actionable_total']:,} patches applied "
              f"across {len(agg['patched_years'])} patched years: {','.join(agg['patched_years'])})")


if __name__ == "__main__":
    main()
