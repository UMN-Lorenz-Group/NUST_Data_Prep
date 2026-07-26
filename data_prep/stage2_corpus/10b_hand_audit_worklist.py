"""
10b_hand_audit_worklist.py
==========================
Turn the "confirmed remaining errors" residue (from 09) into a categorized hand-audit
worklist. Separates the genuinely-auditable measured discrepancies from the artifacts:

  * MATURITY offset-vs-DOY: the QC pdf_value is a raw ± offset (|v|<100) while the corpus
    stores the reconstructed absolute DOY -> a representation mismatch, NOT a value error.
    Flagged 'maturity_offset_artifact' and EXCLUDED from the audit worklist.
  * still_OCR_error: corpus still == the OCR value AND pdf is a clean in-range number ->
    an auto-fix the QC patch missed (usually a strain-name OCR variant / supersede-timing
    mismatch). Category 'autofix_candidate'.
  * pdf_out_of_range: pdf_value outside the trait's sane range -> likely a PDF typo or a
    bad QC read; corpus may well be right. Category 'pdf_suspect'.
  * third_value: corpus != OCR and != pdf, pdf in range -> genuine 'HAND_AUDIT'.

Output: analysis/data/analysis_results/Extraction_Accuracy/hand_audit_worklist.csv
(with the QC `note` = PDF page cite for each, so the auditor can verify straight off it).
"""
import glob
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent.parent
CORPUS = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
OUT = REPO / "analysis" / "data" / "analysis_results" / "Extraction_Accuracy" / "hand_audit_worklist.csv"
TOL = 0.15
RANGES = {"YieldBuA": (0, 130), "Maturity": (200, 330), "Lodging": (1, 5), "Height": (3, 70),
          "SeedQuality": (1, 5), "SeedSize": (2, 50), "Protein": (24, 52), "Oil": (12, 30)}


def nm(s): return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())
def nc(s): return re.sub(r"[^a-z0-9]", "", str(s).lower())
def nt(t):
    t = str(t).upper().strip().replace("UPT-", "PT-").replace("UPT", "PT-")
    return re.sub(r"[^A-Z0-9-]", "", t)
def num(s):
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", str(s).replace(",", ".")); return float(m.group(1)) if m else None


def main():
    c = pd.read_csv(CORPUS, low_memory=False)
    c["cv"] = pd.to_numeric(c.Value_num, errors="coerce"); c = c.dropna(subset=["cv"])
    c["tk"] = (c.Year.astype(str) + "|" + c.Test.map(nt) + "|" + c.Strain.map(nm) + "|"
               + c.City.map(nc) + "|" + c.Phenotype)
    rec_keys = set(c.loc[c.Source == "Recovered_1970_1988", "tk"])
    corp = c.drop_duplicates("tk").set_index("tk").cv
    sk = c.Year.astype(str) + "|" + c.Test.map(nt) + "|" + c.Strain.map(nm) + "|" + c.Phenotype
    fb = c.assign(sk=sk).groupby("sk")["cv"].apply(lambda s: sorted(set(s.round(2)))).to_dict()

    rows = []
    for f in sorted(glob.glob(str(REPO / "output_files/output_*/qc/qc_*_values.csv"))):
        yr = int(re.search(r"output_(\d+)", f).group(1))
        for r in pd.read_csv(f, dtype=str).query("verdict=='discrepancy'").itertuples():
            pv = num(r.pdf_value)
            if r.phenotype == "YieldRank" or pv is None:
                continue
            k = f"{yr}|{nt(r.Test)}|{nm(r.strain)}|{nc(r.City)}|{r.phenotype}"
            hit = corp.get(k)
            if hit is None:
                cand = fb.get(f"{yr}|{nt(r.Test)}|{nm(r.strain)}|{r.phenotype}")
                hit = cand[0] if (cand and len(cand) == 1) else None
            if hit is None or abs(hit - pv) < TOL:
                continue  # no-join or already resolved
            cvsv = num(r.csv_value)
            lo, hi = RANGES.get(r.phenotype, (-1e9, 1e9))
            # sibling-location values for the same strain/trait (for the column-misread test)
            sib = fb.get(f"{yr}|{nt(r.Test)}|{nm(r.strain)}|{r.phenotype}", [])
            dual_agree = cvsv is not None and abs(hit - cvsv) < TOL  # corpus == OCR (2 transcriptions)
            pv_is_sibling = any(abs(pv - o) < TOL for o in sib)     # pv == another location's value
            if r.phenotype == "Maturity" and abs(pv) < 100:
                cat = "maturity_offset_artifact"   # DOY vs offset -> not an error
            elif r.phenotype == "Maturity" and 200 <= pv <= 330 and abs(hit) < 100:
                cat = "maturity_doy_offset_repr"   # corpus stores printed rel-offset, QC read abs DOY -> repr, not error
            elif dual_agree and pv_is_sibling:
                # AUDITED 2026-07-13: both transcriptions agree AND the QC value is a neighbour
                # column -> QC column-misread in a dense per-location table; corpus is CORRECT.
                cat = "qc_column_misread"
            elif not (lo <= pv <= hi):
                cat = "pdf_suspect"                 # PDF value implausible -> PDF typo / bad QC read
            elif k in rec_keys:
                cat = "green_pdf_conflict"          # Green re-extraction agrees w/ OCR vs the PDF -> audit the PDF
            elif dual_agree:
                cat = "autofix_candidate"           # corpus still == OCR, clean PDF -> patch missed it
            else:
                cat = "HAND_AUDIT"                  # corpus != OCR and != PDF -> needs human eyes
            rows.append({"Year": yr, "Test": r.Test, "City": r.City, "State": r.State,
                         "Strain": r.strain, "Phenotype": r.phenotype,
                         "ocr_value": r.csv_value, "corpus_value": round(hit, 2),
                         "pdf_value": r.pdf_value, "abs_diff": round(abs(hit - pv), 2),
                         "category": cat, "qc_note": str(getattr(r, "note", ""))[:200]})
    df = pd.DataFrame(rows)
    # categories that are AUDITED/EXPLAINED, not open errors -> excluded from the manual worklist
    RESOLVED = {"maturity_offset_artifact", "maturity_doy_offset_repr", "qc_column_misread"}
    resolved = df[df.category.isin(RESOLVED)].sort_values(
        ["category", "Test", "Phenotype", "Year"]).reset_index(drop=True)
    resolved.to_csv(OUT.with_name("audit_resolved_evidence.csv"), index=False)
    # write only the actionable worklist (drop the resolved/explained categories, keep them counted)
    work = df[~df.category.isin(RESOLVED)].sort_values(
        ["category", "Phenotype", "Year"]).reset_index(drop=True)
    work.to_csv(OUT, index=False)

    print(f"residue (confirmed measured discrepancies): {len(df)}")
    print("  by category:")
    for cat, n in df.category.value_counts().items():
        tag = "  [RESOLVED]" if cat in RESOLVED else ""
        print(f"    {n:5d}  {cat}{tag}")
    print(f"\n  -> maturity_offset_artifact / maturity_doy_offset_repr = DOY<->offset representation (corpus faithful)")
    print(f"  -> qc_column_misread = audited: both transcriptions agree, QC read a neighbour column (corpus correct)")
    print(f"  -> audit_resolved_evidence.csv written ({len(resolved)} rows)")
    print(f"  -> worklist written ({len(work)} rows) to {OUT.name}:")
    print(work.category.value_counts().to_string())
    print("\n  HAND_AUDIT + autofix by phenotype:")
    print(work[work.category.isin(["HAND_AUDIT", "autofix_candidate"])]
          .groupby(["category", "Phenotype"]).size().to_string())


if __name__ == "__main__":
    main()
