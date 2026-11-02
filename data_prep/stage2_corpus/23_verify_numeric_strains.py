"""
23_verify_numeric_strains.py
============================
Deep-search the `numeric_only_possible_line_no` Strains (QC audit, script 13) that are NOT
the 1941 PIs (handled separately) against the original source ORIGIN tables, and SAVE evidence
images that show the dropped prefix. Like the PI/short-code work (script 22), the yield DATA
tables list these by a bare number while the strain-ORIGIN table carries the full prefixed
breeding-line code. The dropped prefixes are state-program series with OCR letter->digit
confusions:
  C### = Purdue (Indiana)     A3-/A4- = Iowa            L6-/L7-/L3-/L75- = Illinois (L->1)
  S### / S32- = Missouri (S->3)   H##-461 = Ohio (H->1)   plus A->4 / A->1, '.' for L75->1.75

For each (corpus_strain, year) the script locates the origin row in the year's PDF and crops a
horizontal band (code | originating agency | origin) at 200 dpi into Corpus_QC/
numeric_strain_evidence/<year>_<strain>.png, and writes a mapping CSV/MD. Tentative/unresolved
rows are flagged for manual review (no over-correction).

Read-only over the sources. Output:
  analysis/data/analysis_results/Corpus_QC/numeric_strain_source_verification.{csv,md}
  analysis/data/analysis_results/Corpus_QC/numeric_strain_evidence/*.png
"""
import sys
import re
from pathlib import Path
import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
INPUT = REPO / "input_files"
OUTDIR = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"
IMGDIR = OUTDIR / "numeric_strain_evidence"

# (corpus_strain, year, MG, origin_code, originator, origin/pedigree, search_tokens, status)
# search_tokens = distinctive strings that survive OCR, used to locate the origin row on the PDF.
MAP = [
    # --- CONFIRMED: digit string matches origin code by prefix-drop or one consistent OCR sub
    ("56",         1942, "III", "C56",        "Purdue Agr.Exp.Sta.",  "Sel. from X331 (Illini x Mandell)", ["C56", "X331"], "confirmed"),
    ("16-700",     1942, "II",  "L6-700",     "Illinois Agr.Exp.Sta.", "Sel. from (Mandarin x Manchu)",    ["L6-700"], "confirmed"),       # L->1
    ("17-1160",    1942, "IV",  "L7-1160",    "Illinois Agr.Exp.Sta.", "Sel. from LX157 (Illini x T148)",  ["1160", "T148"], "confirmed"), # L->1 (src OCR 'LV-1160')
    ("332-11",     1942, "IV",  "S32-11",     "Missouri Agr.Exp.Sta.", "Sel. from (P.I.37062 x Illini)",   ["S32-11", "37062"], "confirmed"),# S->3
    ("13-2015-28", 1944, "II",  "A3-2015-28", "Iowa A.E.S. & U.S.R.S.L.", "Sel. from Ontario x Richland",  ["2015-28"], "confirmed"),       # A->1
    ("43-2015-28", 1944, "II",  "A3-2015-28", "Iowa A.E.S. & U.S.R.S.L.", "Sel. from Ontario x Richland",  ["2015-28"], "confirmed"),       # A->4
    ("43-1411-47", 1944, "III", "A3-1411-47", "Iowa A.E.S. & U.S.R.S.L.", "Sel. from Mukden x Dunfield",   ["1411-47"], "confirmed"),       # A->4
    ("3-107",      1946, "II",  "A3-107",     "Iowa Agr.Exp.Sta. & U.S.R.S.L.", "Sel. from Mukden x Richland", ["A3-107"], "confirmed"),
    ("3-108",      1946, "II",  "A3-108",     "Iowa Agr.Exp.Sta. & U.S.R.S.L.", "Sel. from Mukden x Richland", ["A3-108"], "confirmed"),
    ("425",        1946, "IV",  "C425",       "Purdue Agr.Exp.Sta. & U.S.R.S.L.", "Sel. from T117 x Mansoy", ["C425", "T117"], "confirmed"),
    ("44-1715-32", 1946, "I",   "A4-1715-32", "Iowa Agr.Exp.Sta. & U.S.R.S.L.", "Sel. from Mandarin x Richland", ["1715-32"], "confirmed"), # A->4
    ("490",        1947, "IV",  "C490",       "Purdue A.E.S. & U.S.R.S.L.", "Sel. from Patoka x X531-468-3-3-2", ["C490"], "confirmed"),
    ("13-2926",    1947, "IV",  "L3-2926",    "Illinois Agr.Exp.Sta. & U.S.R.S.L.", "Sel. from Dunfield x T117", ["L3-2926", "2926"], "confirmed"), # L->1
    ("35-41",      1948, "IV",  "S5-41",      "Missouri Agr.Exp.Sta.", "Sel. from Lincoln x Patoka",       ["S5-41"], "confirmed"),          # S->3
    ("739",        1949, "II",  "C739",       "Purdue A.E.S. & U.S.R.S.L.", "Sel. from Lincoln x (Linc. x Rich.)", ["C739"], "confirmed"),
    ("1.75-8234",  1978, "III", "L75-8234",   "Illinois (U.S.R.S.L.)", "Williams x L70-2450",              ["L75-8234", "8234"], "confirmed"), # L->1.
    # --- CONFIRMED via OCR-twin co-presence (clean code present SAME year + SAME MG), even
    #     though the digit string needs a less-common sub (H->1 / S->3).
    ("129-461",    1946, "II",  "H29-461",    "Ohio Agr.Exp.Sta. & U.S.R.S.L.", "Sel. from Scioto x Mandarin", ["H29-461"], "confirmed"),    # H->1; clean H29-461 co-present 1946 MG II (460r)
    ("3100",       1946, "IV",  "S100",       "Missouri Agr.Exp.Sta.", "Rogue in Illini",                  ["S100"], "confirmed"),            # S->3; clean S100 co-present 1946 MG IV (380r)
    # --- CONFIRMED via OCR anchor + orphaned single-trait fragment: 16-390 carries ONLY the 7
    #     Lodging notes (Table 21) at the same 7 locations as L3-700 (which is unambiguously
    #     L6-700, 700=700). Same OCR (L->1, 6->3) -> 16-390 = L6-690 (the real origin-table line;
    #     no L6-390 exists). The lodging values are L6-690's, orphaned by the Table-21 code garble.
    ("16-390",     1942, "III", "L6-690", "Illinois Agr.Exp.Sta.", "Sel. from (Mandarin x Manchu)", ["L6-690"], "confirmed"), # L->1, 6->3 (anchored by L3-700=L6-700)
    # --- CONFIRMED by table POSITION + exact value match (user catch): in Table 34 (plant height)
    #     the row order is ...C149, C6, Gibson, C160, L7-923, L7-1160... — C160 sits exactly where
    #     '250' sits (between Gibson and L7-923), and 250's 9 Height values match C160's Table-34 row
    #     EXACTLY (Carrollton 26 / Clayton 50 / Columbia 36 / Elsberry 36 / Evansville 50 / Freeburg 51
    #     / North Vernon 33 / Urbana 50 / Wheatland 41). C160 has 0 non-null Height elsewhere (orphaned
    #     as '250'). Evidence: 1942_grpIV_height_p39_for_250.png.
    ("250",        1942, "IV",  "C160", "Purdue Agr.Exp.Sta.", "Sel. from X331 (Illini x Mandell)", ["C160"], "confirmed"),
]


def year_pdf(year):
    p = INPUT / f"input_{year}" / f"{year}_done.pdf"
    if p.exists():
        return p
    cand = list((INPUT / f"input_{year}").glob("*.pdf"))
    return cand[0] if cand else None


def find_and_crop(pdf_path, tokens, out_png):
    """Locate the origin row by any search token (joined per text-row), crop a band, save PNG.
    Returns the 1-based page number, or None if not located."""
    norm = lambda s: re.sub(r"\s+", "", s).lower()
    toks = [norm(t) for t in tokens]
    with pdfplumber.open(pdf_path) as doc:
        for i, pg in enumerate(doc.pages):
            words = pg.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            # group words into rows by rounded vertical position
            rows = {}
            for w in words:
                rows.setdefault(round(w["top"] / 3), []).append(w)
            for _, ws in rows.items():
                line = norm("".join(w["text"] for w in sorted(ws, key=lambda x: x["x0"])))
                if any(t and t in line for t in toks):
                    top = min(w["top"] for w in ws) - 6
                    bot = max(w["bottom"] for w in ws) + 6
                    bbox = (0, max(0, top), pg.width, min(pg.height, bot))
                    pg.crop(bbox).to_image(resolution=200).save(str(out_png))
                    return i + 1
    return None


def main():
    IMGDIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for strain, year, mg, code, orig, ped, tokens, status in MAP:
        page, img = None, ""
        if tokens:
            pdf = year_pdf(year)
            out_png = IMGDIR / f"{year}_{re.sub(r'[^A-Za-z0-9.-]', '_', strain)}.png"
            if pdf:
                page = find_and_crop(pdf, tokens, out_png)
                if page:
                    img = out_png.name
        rows.append({"corpus_strain": strain, "year": year, "MG": mg,
                     "source_code": code, "originator": orig, "origin_pedigree": ped,
                     "status": status, "evidence_pdf_page": page or "", "evidence_img": img})
        flag = "OK" if img else ("no-img" if status != "unresolved" else "UNRESOLVED")
        print(f"  {strain:11s} {year} {mg:3s} -> {code or '???':12s} [{status:10s}] "
              f"{'p'+str(page) if page else flag}")

    out = pd.DataFrame(rows)
    out.to_csv(OUTDIR / "numeric_strain_source_verification.csv", index=False)
    L = ["# Numeric-only Strain source verification (origin-table prefix recovery)\n",
         f"{len(out)} numeric Strains (non-1941). Status: "
         f"{out.status.value_counts().to_dict()}. Evidence crops in numeric_strain_evidence/.\n",
         "The yield DATA tables list these by a bare number; the strain-ORIGIN table carries the "
         "full prefixed code (C=Purdue, A=Iowa, L=Illinois, S=Missouri, H=Ohio) with OCR "
         "letter->digit confusions (L->1, A->4/1, S->3, H->1).\n",
         "| corpus_strain | year | MG | source_code | originator | origin / pedigree | status | pg |",
         "|------|----|----|------|-----------|-------------------|--------|----|"]
    for _, r in out.iterrows():
        L.append(f"| {r.corpus_strain} | {r.year} | {r.MG} | {r.source_code} | {r.originator} "
                 f"| {r.origin_pedigree} | {r.status} | {r.evidence_pdf_page} |")
    (OUTDIR / "numeric_strain_source_verification.md").write_text("\n".join(L), encoding="utf-8")

    n_img = sum(1 for r in rows if r["evidence_img"])
    print(f"\nstatus: {out.status.value_counts().to_dict()}; evidence images saved: {n_img}")
    print(f"Wrote numeric_strain_source_verification.csv + .md + {n_img} crops to {IMGDIR.name}/")


if __name__ == "__main__":
    main()
