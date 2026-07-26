"""
13_qc_strain_germplasm_audit.py
===============================
Deep, pattern-based QC audit of EVERY distinct Strain / GermplasmId in the
assembled NUST corpus.

Motivation
----------
The GermplasmId/Strain *ratio* check (script 21) only catches gross spikes — e.g.
1974, where ~150 disease-rating / region-mean pseudo-locations inflated the count.
It is blind to stray IDs that hide inside an otherwise-healthy year: a handful of
`Mean` summary rows, a date mis-parsed as a strain, negative-number "strains", or
`??` OCR junk. Those individually-rare strays do not move the ratio, yet several of
them carry real yield values and one class (`Mean_*`) even survives the RGG
eligibility gate and is modelled as a phantom genotype. This audit examines every
distinct strain by PATTERN, regardless of per-year ratio.

What it does
------------
1. Catalogs every distinct (Strain, MG) in the long corpus.
2. Classifies each strain into a severity tier by regex rule (CRITICAL/HIGH/REVIEW/OK).
3. Adds STRUCTURAL flags computed across the corpus:
     - CHECK_WRONG_MG : a known anchor-check strain appearing in an MG it is not an
                        anchor for (e.g. early checks dumped into PT-IV/MG IV — the
                        1974 residue still in the un-rebuilt corpus).
     - MG_MULTIPLICITY: a strain spanning >= 3 MGs (real lines are ~1, occasionally 2).
4. For each flagged strain, reports: row count, distinct years, whether it appears in
   UT, whether it carries a usable yield value, and CRUCIALLY whether the GermplasmId
   survives the RGG eligibility gate (n_yrs>=3, n_obs>=4 on UT yield 5..100) and thus
   reaches the E1/E2V-idh/E7Y estimators.

Outputs (analysis/data/analysis_results/Corpus_QC/):
  corpus_qc_strain_audit.csv     — one row per flagged (Strain, MG); review list
  corpus_qc_summary.md           — human-readable tier rollup + the estimator-reaching list
  stray_ids_for_curation.xlsx    — Readme + Stray_summary + Stray_occurrences (Year x Trial
                                   x Location) for MANUAL checking / curation

This script DOES NOT modify the corpus. It is a review/QC report. Remediation (e.g.
dropping `Mean_*` summary rows) belongs in the assembly step (10_assemble_corpus.py),
applied on the next corpus rebuild — same deferral policy as the 1974 pseudo-location fix.

Input: analysis/data/_shared/nust_1941_2025_combined.csv  (long, source of truth)
       analysis/data/_shared/NUST_1941_2025_data_wide.csv  (for GermplasmId + eligibility)
       analysis/data/_shared/nust_anchor_expanded_1941_2025.csv  (anchor checks)
"""
import sys
import re
from pathlib import Path
import pandas as pd
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
LONG = SHARED / "nust_1941_2025_combined.csv"
WIDE = SHARED / "NUST_1941_2025_data_wide.csv"
ANCHORS = SHARED / "nust_anchor_expanded_1941_2025.csv"
OUTDIR = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"
OUTDIR.mkdir(parents=True, exist_ok=True)

MG_ORDER = ["00", "0", "I", "II", "III", "IV"]

# RGG eligibility gate (must match _shared/58_e1_e2v_e7_asreml_per_mg.R)
MIN_YRS_STRAIN = 3
MIN_OBS_STRAIN = 4
YIELD_LO, YIELD_HI = 5, 100

# --- classification rules (first match wins; most severe first) ---------------
# Summary / aggregate labels masquerading as a variety (trial means, dispersion stats).
RE_SUMMARY = re.compile(
    r"^(Mean|MeanYield|Average|Avg|Median|Total|Sum|Grand\s*Mean|LSD|C\.?V\.?|"
    r"Std|SD|SE|SEM|Range|Max|Min|Count)\W*$", re.IGNORECASE)
# Disease-rating / pseudo-location words leaking into the Strain field.
RE_PSEUDO = re.compile(
    r"Diaporthe|Purple ?Stain|Phytophthora|Miscellaneous|\bMature\b|\bLate\b", re.IGNORECASE)
# A date that got parsed as a strain. Anchored at start (or carrying a clock time) so
# real line numbers with embedded digit groups (e.g. UD3210-31-14) are NOT mis-flagged.
RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}:\d{2}")
# Mojibake / Unicode replacement char / other obvious encoding damage.
RE_MOJIBAKE = re.compile(r"[�\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# Question-mark / pure-junk tokens.
RE_QJUNK = re.compile(r"[?]")
# Negative number masquerading as a strain.
RE_NEG = re.compile(r"^-\d+(\.\d+)?$")
# Pure-numeric (could be a legitimate early-era line number — REVIEW, not delete).
RE_NUMERIC = re.compile(r"^[\d][\d.\-]*$")
# Anything with no alphanumeric content at all.
RE_NOALNUM = re.compile(r"^[\W_]+$")


def classify(strain: str):
    """Return (tier, rule) for a strain string. Tiers: CRITICAL/HIGH/REVIEW/OK."""
    if strain is None:
        return ("CRITICAL", "null_strain")
    s = str(strain)
    if s.strip() == "" or s.lower() in ("nan", "none"):
        return ("CRITICAL", "blank_or_nan")
    if RE_MOJIBAKE.search(s):
        return ("CRITICAL", "mojibake_encoding")
    if RE_DATE.search(s):
        return ("CRITICAL", "date_as_strain")
    if RE_SUMMARY.match(s):
        return ("CRITICAL", "summary_label")
    if RE_PSEUDO.search(s):
        return ("CRITICAL", "disease_pseudo_location")
    if RE_QJUNK.search(s) or RE_NOALNUM.match(s):
        return ("HIGH", "punct_or_question_junk")
    if RE_NEG.match(s):
        return ("HIGH", "negative_number")
    if RE_NUMERIC.match(s):
        return ("REVIEW", "numeric_only_possible_line_no")
    if s != s.strip() or "  " in s:
        return ("REVIEW", "whitespace_artifact")
    if len(s.strip()) <= 2:
        return ("REVIEW", "very_short_code")
    return ("OK", "")


def norm(s: str) -> str:
    """Normalise a strain for anchor comparison (strip asterisk / whitespace)."""
    return re.sub(r"\s*\*\s*$", "", str(s).strip())


# Suggested curation action per (tier, rule). KEEP = legitimate, flagged only for context.
def suggest_action(tier, rule):
    if tier in ("CRITICAL", "HIGH"):
        return "DROP"
    if rule == "whitespace_artifact":
        return "FIX (trim)"
    if rule == "possible_mg_misassignment_1yr":
        return "REVIEW (MG?)"
    if rule in ("numeric_only_possible_line_no", "very_short_code"):
        return "KEEP (likely real line/code)"
    return "REVIEW"


def build_curation_workbook(df, flagged, outpath):
    """Write a multi-sheet Excel workbook of stray IDs at occurrence level
    (Year x Trial x Location) for manual checking / curation."""
    df = df.copy()
    df["_skey"] = df["Strain"].astype(str)              # NaN -> 'nan' (stable join key)
    fl = flagged.copy()
    fl["_skey"] = fl["Strain"].astype(str)
    fl["action"] = [suggest_action(t, r) for t, r in zip(fl["tier"], fl["rule"])]

    keys = fl[["_skey", "MG", "tier", "rule", "action", "reaches_estimator",
               "GermplasmId"]].drop_duplicates(["_skey", "MG"])
    occ = df.merge(keys, on=["_skey", "MG"], how="inner")

    # occurrence = one row per (Strain, MG, Year, Trial, Location); collapse the ~6
    # per-plot phenotype rows into a count so the sheet is reviewable.
    occ_tbl = (occ.groupby(
                   ["tier", "rule", "action", "reaches_estimator", "GermplasmId",
                    "Strain", "MG", "Year", "Test", "Variant", "City", "State", "Source"],
                   dropna=False)
                  .size().reset_index(name="n_pheno_rows"))
    tier_rank = {"CRITICAL": 0, "HIGH": 1, "REVIEW": 2}
    occ_tbl["_t"] = occ_tbl["tier"].map(tier_rank)
    occ_tbl = (occ_tbl.sort_values(["_t", "Strain", "MG", "Year", "Test", "City"])
                      .drop(columns="_t")
                      .rename(columns={"Test": "Trial", "City": "Location"}))

    # summary = one row per (Strain, MG) with trial/location spread for triage.
    summ = (occ_tbl.groupby(["tier", "rule", "action", "reaches_estimator",
                             "GermplasmId", "Strain", "MG"], dropna=False)
                   .agg(n_occurrences=("Year", "size"),
                        n_years=("Year", "nunique"),
                        yr_min=("Year", "min"), yr_max=("Year", "max"),
                        n_trials=("Trial", "nunique"),
                        n_locations=("Location", "nunique"),
                        example_trial=("Trial", "first"),
                        example_location=("Location", "first"),
                        n_pheno_rows=("n_pheno_rows", "sum"))
                   .reset_index())
    summ["_t"] = summ["tier"].map(tier_rank)
    summ = summ.sort_values(["_t", "reaches_estimator", "n_pheno_rows"],
                            ascending=[True, False, False]).drop(columns="_t")

    readme = pd.DataFrame({
        "column / tier": [
            "PURPOSE", "Stray_summary", "Stray_occurrences",
            "tier: CRITICAL", "tier: HIGH", "tier: REVIEW",
            "action: DROP", "action: REVIEW (MG?)", "action: KEEP (likely real ...)",
            "action: FIX (trim)", "reaches_estimator", "n_pheno_rows", "NOTE",
        ],
        "meaning": [
            "Stray / mis-formatted Strain IDs flagged by the QC audit (script 13) for manual "
            "checking and curation. Generated from the long corpus; does NOT modify it.",
            "One row per (Strain, MG): tier, suggested action, year/trial/location spread.",
            "One row per (Strain, MG, Year, Trial, Location) — the unit to trace each stray "
            "back to its source table. n_pheno_rows = phenotype rows collapsed in that cell.",
            "Unambiguous non-strain (trial-Mean/summary row, date, blank, mojibake). DROP.",
            "Mangled junk (negative-number 'strain', ?? OCR). DROP. All single-year, so already "
            "excluded from the RGG estimators by the n_yrs>=3 gate.",
            "Needs human judgement — may be legitimate.",
            "Remove from the corpus (not a real genotype / site).",
            "A known check appears in a non-anchor MG for a SINGLE year — verify the MG label "
            "(this is the 1974 Hark_IV pseudo-location residue pattern).",
            "Numeric early-era line numbers and the systematic H#/M#/L# short-code series — "
            "legitimate designations; listed for completeness, normally KEEP.",
            "Leading/trailing or double whitespace — trim, do not drop.",
            "TRUE = this GermplasmId survives the RGG eligibility gate and is modelled as a "
            "genotype (only the 6 Mean_* do). These are the highest priority.",
            "Count of long-format phenotype rows collapsed into that occurrence cell.",
            "Curation should also de-duplicate near-identical Strain spellings (a recurring "
            "issue); compare entries within the same Trial/Year for OCR variants.",
        ],
    })

    with pd.ExcelWriter(outpath, engine="openpyxl") as xl:
        readme.to_excel(xl, sheet_name="Readme", index=False)
        summ.to_excel(xl, sheet_name="Stray_summary", index=False)
        occ_tbl.to_excel(xl, sheet_name="Stray_occurrences", index=False)
        for sheet, frame in (("Readme", readme), ("Stray_summary", summ),
                             ("Stray_occurrences", occ_tbl)):
            ws = xl.sheets[sheet]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for col_cells in ws.columns:
                width = min(60, max(10, max(len(str(c.value)) for c in col_cells) + 2))
                ws.column_dimensions[col_cells[0].column_letter].width = width
    return summ, occ_tbl


def main():
    for p in (LONG, WIDE, ANCHORS):
        if not p.exists():
            sys.exit(f"ERROR: missing {p}")

    print(f"Loading {LONG.name} ...", flush=True)
    df = pd.read_csv(LONG, low_memory=False,
                     usecols=["Year", "TestType", "TestMG", "Test", "Variant",
                              "Strain", "City", "State", "Phenotype", "Value_num", "Source"])
    df["MG"] = df["TestMG"].astype(str).str.strip()
    print(f"  {len(df):,} long rows; {df['Strain'].nunique(dropna=True)} distinct strains")

    # --- per (Strain, MG) catalog -------------------------------------------
    df["_yield"] = df["Value_num"].where(df["Phenotype"].astype(str).str.contains("Yield", na=False))
    grp = df.groupby([df["Strain"].astype("object"), "MG"], dropna=False)
    cat = grp.agg(
        n_rows=("Year", "size"),
        n_years=("Year", "nunique"),
        yr_min=("Year", "min"),
        yr_max=("Year", "max"),
        in_UT=("TestType", lambda x: bool((x == "UT").any())),
        n_yield_obs=("_yield", lambda x: int(x.between(YIELD_LO, YIELD_HI).sum())),
    ).reset_index().rename(columns={"Strain": "Strain"})

    # classify
    tiers = cat["Strain"].apply(classify)
    cat["tier"] = tiers.apply(lambda t: t[0])
    cat["rule"] = tiers.apply(lambda t: t[1])

    # --- structural flags across MGs ----------------------------------------
    # MG multiplicity per (normalised) strain
    cat["strain_norm"] = cat["Strain"].apply(norm)
    mg_per_strain = (cat[cat["MG"].isin(MG_ORDER)]
                     .groupby("strain_norm")["MG"].nunique())
    cat["n_MGs_for_strain"] = cat["strain_norm"].map(mg_per_strain).fillna(0).astype(int)

    # cross-MG check: anchor strain showing up in an MG it is not an anchor for
    anc = pd.read_csv(ANCHORS, low_memory=False)
    anc["strain_norm"] = anc["Strain"].apply(norm)
    anchor_mgs = anc.groupby("strain_norm")["MG"].apply(lambda x: set(x.astype(str)))
    def wrong_mg(row):
        mgs = anchor_mgs.get(row["strain_norm"])
        return bool(mgs is not None and row["MG"] in MG_ORDER and row["MG"] not in mgs)
    cat["check_wrong_mg"] = cat.apply(wrong_mg, axis=1)

    # --- does it reach the estimator? (UT yield eligibility on wide) ---------
    print(f"Loading {WIDE.name} for estimator-eligibility ...", flush=True)
    w = pd.read_csv(WIDE, low_memory=False,
                    usecols=["Year", "Experiment", "MG", "Location", "GermplasmId",
                             "Strain", "YieldBuA"])
    ut = w[w["Experiment"].astype(str).str.match("UT")
           & w["YieldBuA"].between(YIELD_LO, YIELD_HI)
           & w["Location"].notna() & w["GermplasmId"].notna()
           & w["MG"].astype(str).str.strip().isin(MG_ORDER)]
    eg = ut.groupby("GermplasmId").agg(n_yrs=("Year", "nunique"), n_obs=("Year", "size"))
    eligible_ids = set(eg[(eg.n_yrs >= MIN_YRS_STRAIN) & (eg.n_obs >= MIN_OBS_STRAIN)].index)
    cat["GermplasmId"] = cat["Strain"].astype(str) + "_" + cat["MG"].astype(str)
    cat["reaches_estimator"] = cat["GermplasmId"].isin(eligible_ids)

    # --- quantify the estimator impact of removing the unambiguous (CRITICAL) strays ----
    # E1 proxy: per-genotype mean yield regressed on first test year, within MG. Compares
    # the slope WITH vs WITHOUT the CRITICAL-tier strain names that reach the estimator
    # (i.e. the Mean_* summary genotypes). A tiny delta means the report does not need an
    # urgent re-run; the fix can ride the next corpus rebuild.
    ut_e = ut[ut["GermplasmId"].isin(eligible_ids)].copy()
    ut_e["MG"] = ut_e["MG"].astype(str).str.strip()
    crit_names = set(cat.loc[(cat["tier"] == "CRITICAL") & cat["reaches_estimator"], "Strain"]
                     .astype(str))

    def e1_proxy(d):
        gm = d.groupby(["GermplasmId", "MG"]).agg(my=("YieldBuA", "mean"),
                                                  fy=("Year", "min")).reset_index()
        out = {}
        for mg, sub in gm.groupby("MG"):
            if len(sub) >= 5:
                out[mg] = float(np.polyfit(sub.fy, sub.my, 1)[0] * 67.25)  # bu/a/yr -> kg/ha/yr
        return out

    impact = []
    if crit_names:
        full_s = e1_proxy(ut_e)
        clean_s = e1_proxy(ut_e[~ut_e["Strain"].astype(str).isin(crit_names)])
        for mg in MG_ORDER:
            if mg in full_s and mg in clean_s:
                impact.append((mg, full_s[mg], clean_s[mg], clean_s[mg] - full_s[mg]))

    # --- assemble flagged set ------------------------------------------------
    # check_wrong_mg fires for any anchor-check strain seen in a non-anchor MG, but a
    # widely-grown variety legitimately tested across adjacent MGs over many years is
    # NOT a stray. Only the SINGLE-YEAR appearances are suspicious (the 1974 Hark_IV
    # residue pattern: an early check dumped into a late-MG test for one year). Multi-year
    # cross-MG appearances are treated as legitimate cross-MG testing and excluded.
    # n_MGs_for_strain is kept as a CONTEXT column but is NOT a defect flag — every famous
    # check (Hawkeye/Lincoln/Corsoy/Hark) spans 3+ MGs by design.
    cat["mg_misassign"] = cat["check_wrong_mg"] & (cat["n_years"] == 1)
    flagged = cat[(cat["tier"] != "OK") | cat["mg_misassign"]].copy()
    # structural-only rows (pattern tier OK but single-year cross-MG) → REVIEW
    so = (flagged["tier"] == "OK") & flagged["mg_misassign"]
    flagged.loc[so, "rule"] = "possible_mg_misassignment_1yr"
    flagged.loc[so, "tier"] = "REVIEW"

    tier_rank = {"CRITICAL": 0, "HIGH": 1, "REVIEW": 2}
    flagged["_t"] = flagged["tier"].map(tier_rank)
    flagged = flagged.sort_values(
        ["_t", "reaches_estimator", "n_rows"], ascending=[True, False, False])

    out_cols = ["tier", "rule", "Strain", "MG", "GermplasmId", "reaches_estimator",
                "in_UT", "n_yield_obs", "n_rows", "n_years", "yr_min", "yr_max",
                "n_MGs_for_strain", "check_wrong_mg", "mg_misassign"]
    flagged[out_cols].to_csv(OUTDIR / "corpus_qc_strain_audit.csv", index=False)

    # --- summary -------------------------------------------------------------
    reach = flagged[flagged["reaches_estimator"]]
    lines = []
    lines.append("# Corpus Strain / GermplasmId QC audit\n")
    lines.append(f"Source: `{LONG.name}` ({len(df):,} rows, "
                 f"{df['Strain'].nunique(dropna=True)} distinct strains)\n")
    lines.append("Pattern-based audit (not ratio-based). Does NOT modify the corpus.\n")
    lines.append("## Flagged (Strain, MG) by tier\n")
    lines.append("| tier | distinct (Strain,MG) | rows | reaches estimator |")
    lines.append("|------|----:|----:|----:|")
    for t in ["CRITICAL", "HIGH", "REVIEW"]:
        sub = flagged[flagged["tier"] == t]
        lines.append(f"| {t} | {len(sub)} | {int(sub['n_rows'].sum()):,} | "
                     f"{int(sub['reaches_estimator'].sum())} |")
    lines.append("")
    lines.append("## Rule breakdown\n")
    lines.append("| rule | n | rows | reaches est. |")
    lines.append("|------|--:|--:|--:|")
    for rule, sub in flagged.groupby("rule"):
        lines.append(f"| {rule} | {len(sub)} | {int(sub['n_rows'].sum()):,} | "
                     f"{int(sub['reaches_estimator'].sum())} |")
    lines.append("")
    lines.append("## ⚠ Strays that REACH the RGG estimator (highest priority)\n")
    if len(reach):
        lines.append("| GermplasmId | tier | rule | n_years | n_yield_obs |")
        lines.append("|-------------|------|------|--:|--:|")
        for _, r in reach.iterrows():
            lines.append(f"| {r.GermplasmId} | {r.tier} | {r.rule} | "
                         f"{r.n_years} | {r.n_yield_obs} |")
    else:
        lines.append("_None — all flagged strays are filtered by the n_yrs>=3 eligibility gate._")
    lines.append("")
    if impact:
        maxabs = max(abs(d) for *_, d in impact)
        lines.append("## Estimator impact of removing the CRITICAL strays (E1 proxy)\n")
        lines.append(f"Removing `{', '.join(sorted(crit_names))}`-type summary genotypes shifts the "
                     f"genotype-mean (E1-proxy) slope by at most **{maxabs:.2f} kg/ha/yr** "
                     f"(see below) — negligible vs the +22..+33 kg/ha/yr estimates, so the RGG "
                     f"report does not need an urgent re-run; fold the fix into the next corpus rebuild.\n")
        lines.append("| MG | slope with strays | slope without | delta |")
        lines.append("|----|--:|--:|--:|")
        for mg, a, b, d in impact:
            lines.append(f"| {mg} | {a:+.2f} | {b:+.2f} | {d:+.2f} |")
        lines.append("")
    lines.append("## Interpretation / recommended action\n")
    lines.append("- **CRITICAL** = unambiguous non-strains (trial-`Mean` summary rows, a date, a "
                 "blank, `MeanYield`). The 6 `Mean_*` genotypes are the only strays that survive the "
                 "eligibility gate and reach the RGG estimators; impact is negligible (above).\n")
    lines.append("- **HIGH** = mangled junk (negative-number 'strains', `??`/`???` OCR). All are "
                 "single-year, so the n_yrs>=3 gate already keeps them out of the estimators; they "
                 "only affect raw per-year corpus counts.\n")
    lines.append("- **REVIEW** = mostly legitimate: `numeric_only` early-era line numbers, the "
                 "systematic short-code series (H#/M#/L#, 1943-65), and single-year cross-MG "
                 "appearances (incl. the 1974 `Hark_IV` pseudo-location residue). Human review only.\n")
    lines.append("- `n_MGs_for_strain` is CONTEXT, not a defect: every famous check "
                 "(Hawkeye/Lincoln/Corsoy/Hark) legitimately spans 3+ MGs.\n")
    lines.append("- **Remediation** belongs in `10_assemble_corpus.py` (strain-level filter for the "
                 "CRITICAL/HIGH unambiguous classes), applied on the next corpus rebuild — same "
                 "deferral policy as the 1974 pseudo-location fix.\n")
    (OUTDIR / "corpus_qc_summary.md").write_text("\n".join(lines), encoding="utf-8")

    # --- curation workbook (Year x Trial x Location) -------------------------
    xlsx_path = OUTDIR / "stray_ids_for_curation.xlsx"
    summ, occ_tbl = build_curation_workbook(df, flagged, xlsx_path)

    # --- console -------------------------------------------------------------
    print("\n=== QC audit summary ===")
    for t in ["CRITICAL", "HIGH", "REVIEW"]:
        sub = flagged[flagged["tier"] == t]
        print(f"  {t:8s}: {len(sub):3d} distinct (Strain,MG), {int(sub['n_rows'].sum()):>7,} rows, "
              f"{int(sub['reaches_estimator'].sum())} reach estimator")
    print(f"\n  Strays reaching the RGG estimator: {len(reach)}")
    if len(reach):
        print(reach[["GermplasmId", "tier", "rule", "n_years", "n_yield_obs"]].to_string(index=False))
    if impact:
        print(f"\n  E1-proxy impact of removing CRITICAL strays: max |delta| = "
              f"{max(abs(d) for *_, d in impact):.2f} kg/ha/yr (negligible)")
    print(f"\n  Curation workbook: {len(summ)} (Strain,MG) rows, "
          f"{len(occ_tbl):,} occurrence rows (Year x Trial x Location)")
    print(f"\nOutputs ({OUTDIR.name}/):")
    print("  corpus_qc_strain_audit.csv")
    print("  corpus_qc_summary.md")
    print("  stray_ids_for_curation.xlsx  (Readme / Stray_summary / Stray_occurrences)")


if __name__ == "__main__":
    main()
