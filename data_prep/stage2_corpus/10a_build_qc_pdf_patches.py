"""
10a_build_qc_pdf_patches.py
===========================
Build a targeted patch of the CONFIDENTLY-fixable OCR errors surfaced by the per-year
QC (`qc_YYYY_values.csv`, CSV-vs-PDF discrepancies) that still survive in the corpus.

A cell is patched only when ALL hold (maximize *accurate* recovery, never inject a PDF typo):
  * verdict == discrepancy and phenotype != YieldRank (a derived rank, not a value error)
  * pdf_value parses to a clean number IN the trait's sane range
  * the CURRENT corpus value still equals the original OCR (csv_value) -> confidently wrong
    AND differs from the PDF -> there IS a correction to make
  * we do NOT touch 'third_value' cells (corpus != csv and != pdf): those are ambiguous
    (often a later re-extraction that is right while the PDF has a typo) -> leave them.

Output: data_prep/stage2_corpus/qc_pdf_patches.csv  (Source=QC_PDF_patch), superseding the
F4U cell for the same (Year,Test,City,State,Strain,Phenotype). Protein/Oil values are DRY
basis (the report value), consistent with the F4U years (11_build_wide applies ×0.87).

Usage:
    uv run python data_prep/stage2_corpus/10a_build_qc_pdf_patches.py
"""
import glob
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent.parent
# Build from the PRE-patch corpus state so the raw F4U OCR values (and their Source) are visible
# -- the live corpus has already superseded them with QC_PDF_patch rows. The backup is the full
# corpus (all other fixes applied) minus only the QC patch.
_SHARED = REPO / "analysis" / "data" / "_shared"
CORPUS = (_SHARED / "nust_1941_2025_combined.csv.bak_pre_qcpatch"
          if (_SHARED / "nust_1941_2025_combined.csv.bak_pre_qcpatch").exists()
          else _SHARED / "nust_1941_2025_combined.csv")
OUT = REPO / "data_prep" / "stage2_corpus" / "qc_pdf_patches.csv"

# per-trait sane ranges (Protein/Oil are DRY basis for these F4U years)
RANGES = {
    "YieldBuA": (0, 130), "Maturity": (200, 330), "Lodging": (1, 5),
    "Height": (3, 70), "SeedQuality": (1, 5), "SeedSize": (2, 50),
    "Protein": (24, 52), "Oil": (12, 30),
}
TOL = 0.15


def nm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())


def nc(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def nt(t):
    t = str(t).upper().strip().replace("UPT-", "PT-").replace("UPT", "PT-")
    return re.sub(r"[^A-Z0-9-]", "", t)


def num(s):
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", str(s).replace(",", "."))
    return float(m.group(1)) if m else None


def main():
    c = pd.read_csv(CORPUS, low_memory=False)
    c["tk"] = (c.Year.astype(str) + "|" + c.Test.map(nt) + "|" + c.Strain.map(nm)
               + "|" + c.City.map(nc) + "|" + c.Phenotype)
    c["cv"] = pd.to_numeric(c.Value_num, errors="coerce")
    # keep full rows for the winning source cell so we emit corpus-consistent Test/City/State/Strain
    cc = c.dropna(subset=["cv"]).drop_duplicates("tk")
    corp = cc.set_index("tk")

    rows = []
    from collections import Counter
    by_ph = Counter()
    for f in sorted(glob.glob(str(REPO / "output_files/output_*/qc/qc_*_values.csv"))):
        yr = int(re.search(r"output_(\d+)", f).group(1))
        q = pd.read_csv(f, dtype=str)
        d = q[q.verdict == "discrepancy"]
        for r in d.itertuples():
            ph = r.phenotype
            if ph == "YieldRank" or ph not in RANGES:
                continue
            pv, cvsv = num(r.pdf_value), num(r.csv_value)
            if pv is None or cvsv is None:
                continue
            lo, hi = RANGES[ph]
            if not (lo <= pv <= hi):
                continue
            k = f"{yr}|{nt(r.Test)}|{nm(r.strain)}|{nc(r.City)}|{ph}"
            if k not in corp.index:
                continue
            # ONLY override raw OCR (F4U) cells. If the current value comes from a validated
            # recovery (Green re-extraction) or any other source, a second independent transcription
            # already corroborates it against the PDF -> that's a Green-vs-PDF CONFLICT for hand-audit,
            # not a confident OCR error. Skip it.
            if corp.at[k, "Source"] != "F4U_1941_1988":
                continue
            v = float(corp.at[k, "cv"])
            # confidently wrong: corpus == OCR error, and a real correction exists
            if abs(v - cvsv) < TOL and abs(v - pv) >= TOL:
                row = corp.loc[k]
                rows.append({
                    "Year": yr, "Test": row["Test"], "City": row["City"],
                    "State": row["State"], "Strain": row["Strain"], "Phenotype": ph,
                    "Value_num": pv, "Units": row.get("Units", ""),
                    "old_value": v, "Source": "QC_PDF_patch",
                    "note": str(getattr(r, "note", ""))[:180],
                })
                by_ph[ph] += 1
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f"Wrote {OUT.name}: {len(out)} confirmed OCR-error patches")
    print("  by phenotype:", dict(by_ph.most_common()))
    print("  by year (top):", dict(out["Year"].value_counts().head(8)) if len(out) else {})
    if len(out):
        print("\n  sample:")
        print(out[["Year", "Test", "City", "Strain", "Phenotype", "old_value", "Value_num"]]
              .head(10).to_string(index=False))


if __name__ == "__main__":
    main()
