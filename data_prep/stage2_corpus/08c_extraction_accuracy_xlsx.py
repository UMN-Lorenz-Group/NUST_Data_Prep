"""
08c_extraction_accuracy_xlsx.py
================================
Emit the NUST extraction accuracy + OCR accuracy by decade tables as a
single multi-sheet xlsx for slide / report use.

Output: analysis/data/extraction_accuracy_1941_1988.xlsx
Sheets:
  - Headline     1-row summary of overall + Claude fix rate
  - By Decade    5-row decade roll-up (1940s..1980s + All)
  - Per Year     46-row per-year detail
"""
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(r"C:\Users\vramasub\Desktop\UMN_GIT\NUST_Data_Prep")
DATA = REPO / "analysis" / "data" / "_shared"
SRC_YR = DATA / "extraction_accuracy_per_year.csv"
SRC_DC = DATA / "extraction_accuracy_by_decade.csv"
OUT = DATA / "extraction_accuracy_1941_1988.xlsx"


def main():
    if not SRC_YR.exists() or not SRC_DC.exists():
        sys.exit(
            "ERROR: missing per-year or by-decade CSV. Run "
            "analysis/08_extraction_accuracy.py then "
            "analysis/08b_extraction_accuracy_presentation.py first.")

    yr = pd.read_csv(SRC_YR)
    dc = pd.read_csv(SRC_DC)

    # --- Headline (1-row) ---------------------------------------------------
    total_cells = int(yr["total_cells"].sum())
    total_disc  = int(yr["discrepancies"].sum())
    total_actionable = int(yr["actionable_disc"].sum())
    patched = yr[yr["patches_applied_per_csv"] >= 0]
    n_patched_yrs = len(patched)
    patches_applied = int(patched["patches_applied_per_csv"].sum())
    patched_actionable = int(patched["actionable_disc"].sum())
    overall_ocr = (1 - total_disc / total_cells) * 100
    fix_rate = (patches_applied / patched_actionable * 100
                if patched_actionable else None)

    headline = pd.DataFrame([{
        "Metric": "Years covered",
        "Value": f"{len(yr)} (1941-1988)",
    }, {
        "Metric": "Total rows QC'd",
        "Value": f"{total_cells:,}  (one row per Test/Strain/City/Phenotype measurement)",
    }, {
        "Metric": "Discrepancies (CSV != PDF)",
        "Value": f"{total_disc:,}",
    }, {
        "Metric": "OCR accuracy",
        "Value": f"{overall_ocr:.2f}%",
    }, {
        "Metric": "Actionable discrepancies",
        "Value": f"{total_actionable:,}",
    }, {
        "Metric": "Claude patches applied",
        "Value": f"{patches_applied:,} (across {n_patched_yrs} years 1960-1974)",
    }, {
        "Metric": "Claude fix rate on actionable",
        "Value": f"{fix_rate:.1f}%" if fix_rate is not None else "N/A (see 09 pre/post resolved)",
    }])

    # --- By Decade (5+1 rows) ----------------------------------------------
    decade = dc.copy()
    # Rename for slide-readiness
    decade = decade.rename(columns={
        "decade": "Decade",
        "year_range": "Years",
        "years_n": "N years",
        "total_cells": "Rows QC'd",
        "discrepancies": "Discrepancies",
        "actionable_disc": "Actionable disc",
        "patched": "Patches applied",
        "patched_years": "Patched yrs",
        "ocr_accuracy_pct": "OCR accuracy %",
        "fix_pct_actionable": "Fix rate %",
    })
    # Reorder
    decade = decade[["Decade", "Years", "N years", "Rows QC'd",
                     "Discrepancies", "OCR accuracy %",
                     "Patched yrs", "Actionable disc",
                     "Patches applied", "Fix rate %"]]
    # Append total row
    total_row = pd.DataFrame([{
        "Decade":         "All",
        "Years":          "1941-1988",
        "N years":        len(yr),
        "Rows QC'd":     total_cells,
        "Discrepancies":  total_disc,
        "OCR accuracy %": overall_ocr,
        "Patched yrs":    n_patched_yrs,
        "Actionable disc": patched_actionable,
        "Patches applied": patches_applied,
        "Fix rate %":     fix_rate,
    }])
    decade_full = pd.concat([decade, total_row], ignore_index=True)
    # Format the % columns to 2dp
    decade_full["OCR accuracy %"] = decade_full["OCR accuracy %"].round(2)
    decade_full["Fix rate %"] = decade_full["Fix rate %"].round(1)

    # --- Per Year (46 rows) ------------------------------------------------
    per_year = yr.copy()
    per_year = per_year[[
        "year", "total_cells", "discrepancies", "not_found", "ambiguous",
        "actionable_disc", "patches_applied_per_csv",
        "ocr_accuracy_pct", "actionable_fix_rate_pct"
    ]].copy()
    per_year = per_year.rename(columns={
        "year": "Year",
        "total_cells": "Rows QC'd",
        "discrepancies": "Discrepancies",
        "not_found": "Not found",
        "ambiguous": "Ambiguous",
        "actionable_disc": "Actionable disc",
        "patches_applied_per_csv": "Patches applied",
        "ocr_accuracy_pct": "OCR accuracy %",
        "actionable_fix_rate_pct": "Fix rate % (actionable)",
    })
    per_year["OCR accuracy %"] = per_year["OCR accuracy %"].round(2)
    per_year["Fix rate % (actionable)"] = per_year["Fix rate % (actionable)"].round(1)
    # Replace -1 patches_applied (unpatched years) with blank
    per_year.loc[per_year["Patches applied"] < 0, "Patches applied"] = pd.NA

    # --- Write xlsx ---------------------------------------------------------
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        headline.to_excel(w, sheet_name="Headline", index=False)
        decade_full.to_excel(w, sheet_name="By Decade", index=False)
        per_year.to_excel(w, sheet_name="Per Year", index=False)
        # Set column widths
        for sheet_name, df_ in (("Headline", headline),
                                ("By Decade", decade_full),
                                ("Per Year", per_year)):
            ws = w.sheets[sheet_name]
            for i, col in enumerate(df_.columns):
                max_len = max(
                    len(str(col)),
                    df_[col].astype(str).str.len().max() if len(df_) else 0
                )
                ws.column_dimensions[chr(65 + i)].width = max_len + 2
    print(f"Wrote {OUT}")
    print(f"  Sheets: Headline (7 rows), By Decade ({len(decade_full)} rows), "
          f"Per Year ({len(per_year)} rows)")


if __name__ == "__main__":
    main()
