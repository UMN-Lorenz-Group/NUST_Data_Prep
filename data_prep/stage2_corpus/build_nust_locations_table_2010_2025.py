"""
build_nust_locations_table_2010_2025.py
=======================================
Derive NUST_Locations_Table_Combined_2010_2025.csv (a 2010-2025 subset of the
2005-2025 combined locations table) and report the MISSING fraction of each field
(Conductor, PlantingDate, MaturityDate, lat, lon) overall, by era, and by year.

Run: uv run python data_prep/stage2_corpus/build_nust_locations_table_2010_2025.py
(assumes NUST_Locations_Table_Combined_2005_2025.csv already built)
"""
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO   = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
QC_DIR = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"
SRC    = SHARED / "NUST_Locations_Table_Combined_2005_2025.csv"
OUT    = SHARED / "NUST_Locations_Table_Combined_2010_2025.csv"
MD     = QC_DIR / "NUST_Locations_Table_Combined_2010_2025_coverage.md"
FIELDS = ["lat", "lon", "Conductor", "PlantingDate", "MaturityDate"]

def miss(df, col):
    return df[col].isna().mean()

def main():
    t = pd.read_csv(SRC)
    d = t[(t["Year"] >= 2010) & (t["Year"] <= 2025)].copy().reset_index(drop=True)
    d.to_csv(OUT, index=False)

    L = [f"# NUST_Locations_Table_Combined_2010_2025 — missing-fraction estimate", "",
         f"- rows: **{len(d):,}**  |  years 2010–2025  |  one row per (Year, Test, Location)", ""]

    # overall
    L.append("## Overall missing fraction (2010–2025)")
    L.append("| Field | present | missing | % missing |")
    L.append("|---|---|---|---|")
    for c in FIELDS:
        m = int(d[c].isna().sum()); p = len(d) - m
        L.append(f"| {c} | {p:,} | {m:,} | **{m/len(d)*100:.1f}%** |")
    L.append("")

    # Conductor provenance
    if "Conductor_source" in d.columns:
        L.append("## Conductor provenance (`Conductor_source`)")
        L.append("| source | rows | meaning |")
        L.append("|---|---|---|")
        meanings = {"report": "from that location's own report grower / LocationsTable row",
                    "state_single": "within-(Year,State) single-conductor consensus fill (unambiguous)",
                    "state_majority": "within-(Year,State) plurality fill (a flagged guess)"}
        vc = d["Conductor_source"].value_counts(dropna=False)
        for k in ["report", "state_single", "state_majority"]:
            L.append(f"| {k} | {int(vc.get(k, 0)):,} | {meanings[k]} |")
        L.append(f"| (missing) | {int(d['Conductor'].isna().sum()):,} | tie between conductors, or none known that year |")
        L.append("")

    # by era — 2010-2015 (report-PDF-derived skeleton) vs 2016-2025 (portal/LocationsTable)
    L.append("## By era")
    L.append("| Field | 2010–2015 %missing | 2016–2025 %missing |")
    L.append("|---|---|---|")
    a = d[d.Year <= 2015]; b = d[d.Year >= 2016]
    for c in FIELDS:
        L.append(f"| {c} | {miss(a,c)*100:.1f}% | {miss(b,c)*100:.1f}% |")
    L.append("")
    L.append("*lat/lon are blank for 2010–2015 by design (no official station GPS in the reports "
             "before 2020; the SoyBase portal has no data before 2016).* ")
    L.append("")
    L.append("*Conductor is back-filled by within-year, within-state consensus (a state whose known "
             "locations all share ONE conductor fills its blank locations — e.g. Danvers MN 2010 = J. Orf). "
             "The residual missing are multi-conductor states that year (ambiguous, e.g. IA = Fehr + Cianzio) "
             "or states with no conductor extracted at all.*")
    L.append("")

    # per year
    L.append("## Per-year rows and % missing")
    L.append("| Year | rows | lat/lon | Conductor | PlantingDate | MaturityDate |")
    L.append("|---|---|---|---|---|---|")
    for yr, g in d.groupby("Year"):
        L.append(f"| {yr} | {len(g)} | {miss(g,'lat')*100:.0f}% | {miss(g,'Conductor')*100:.0f}% "
                 f"| {miss(g,'PlantingDate')*100:.0f}% | {miss(g,'MaturityDate')*100:.0f}% |")

    MD.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nWrote {OUT}  ({len(d):,} rows)")
    print(f"Wrote {MD}")

if __name__ == "__main__":
    main()
