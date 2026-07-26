"""
extract_hand_audit_pages.py
===========================
For every HAND_AUDIT cell in
  analysis/data/analysis_results/Extraction_Accuracy/hand_audit_worklist.csv
locate the source-PDF page that holds the relevant trait table and render it to a PNG in an
R: review folder, so the pages can be checked without opening the full year PDFs.

Page match score per page (era-agnostic; strain is the strongest locator):
  +4 strain (normalised alnum core) present     +2 trait marker present
  +2 test header matches                        +1 city present
Ties -> keep all pages within 1 pt of the best (captures multi-page trait tables).

Outputs (to R: folder):
  <year>_p<NNN>_<Test>_<Phenotype>.png      (one per matched page; multiple cells may share)
  hand_audit_pages_manifest.csv             (cell -> matched page(s) + values + qc_note)
  _UNMATCHED.csv                            (cells where no confident page was found)

Usage:
  uv run --with pymupdf python data_prep/stage2_corpus/extract_hand_audit_pages.py --check   # match only, no render
  uv run --with pymupdf python data_prep/stage2_corpus/extract_hand_audit_pages.py --render  # render PNGs to R:
"""
import re
import sys
from pathlib import Path
import pandas as pd
import fitz

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(__file__).resolve().parent.parent.parent
WORK = REPO / "analysis" / "data" / "analysis_results" / "Extraction_Accuracy" / "hand_audit_worklist.csv"
RED = Path("R:/cfans_agro_lore0149_lorenzlabresearch/NUST_Data/NUST_Data/"
           "NUST_Historical_Data_1941_1988/Red-20260427T193444Z-3-001/Red")
OUT = Path("R:/cfans_agro_lore0149_lorenzlabresearch/NUST_Data/NUST_Data/"
           "NUST_Historical_Data_1941_1988/hand_audit_review_pages")

TRAIT_MARK = {
    "YieldBuA": ["YIELD"], "Height": ["HEIGHT"], "Lodging": ["LODGING"], "Maturity": ["MATURITY"],
    "SeedQuality": ["SEED QUALITY", "QUALITY"],
    "SeedSize": ["SEED SIZE", "SEED WEIGHT", "SEED WT", "100 SEED", "SEED WGT",
                 "/100", "/IQQ", "/I QQ", "IQQ)", "/1QQ", "/IOO", "G/10"],  # incl. OCR-garbled g/100 unit
    "Protein": ["PROTEIN"], "Oil": ["OIL"],
}


def alnum(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def strain_tokens(strain):
    """distinctive tokens: alpha runs >=4 chars + numeric runs >=3 digits + full alnum code.
    order-independent so 'Harper (III)' matches '(III) Harper', 'Corsoy 79 (II)' etc."""
    s = str(strain).upper()
    toks = re.findall(r"[A-Z]{4,}", s) + re.findall(r"\d{3,}", s)
    core = alnum(re.sub(r"\([^)]*\)", "", s))          # full code minus MG paren
    if len(core) >= 4:
        toks.append(core)
    # dedupe, longest first
    return sorted(set(toks), key=len, reverse=True)


def test_patterns(test):
    """pattern for a SPACE-STRIPPED header (OCR splits romans: 'III'->'I I I', 'IIA'->'I I A').
    Early reports (1941-1950s) label tests 'GROUP I/II/III/IV' instead of 'TEST III'."""
    t = str(test).upper().strip()
    mg = t.replace("UT-", "").replace("PT-", "")
    # forbid only roman/subclass EXTENSION chars (so 'II'!='III'/'IIA'; '0'!='00'), but allow a
    # trait word to follow directly in the despaced header ('TESTIIASEEDSIZE' must still match IIA)
    mg_re = re.escape(mg) + r"(?![IVXAB0-9])"
    if t.startswith("PT"):
        kind = r"(?:PRELIMINARYTEST|PRELIMINARYGROUP)"
    else:
        kind = r"(?:(?<!PRELIMINARY)TEST|(?<!PRELIMINARY)GROUP)"
    return re.compile(kind + mg_re)


def has_trait(U, pheno):
    return any(m in U for m in TRAIT_MARK.get(pheno, []))


def table_hint(qc_note):
    m = re.search(r"[Tt]able\s*(\d+)", str(qc_note))
    return int(m.group(1)) if m else None


def find_table_pages(pages, tno):
    """pages whose text has a 'TABLE <n>' heading (captures the (CONTINUED) 2nd page)."""
    pat = re.compile(r"TABLE\s*" + str(tno) + r"\b")
    return sorted(p[0] for p in pages if pat.search(p[1]))


def score_page(U, Ualnum, head_ns, toks, city, tpat):
    """score a candidate page (trait already confirmed present). strain + city + test pin it."""
    s = 0
    if toks and toks[0] in Ualnum:
        s += 4                                          # primary strain token
        for t in toks[1:]:
            if t in Ualnum:
                s += 1                                  # corroborating tokens
    elif any(t in Ualnum for t in toks):
        s += 2                                          # only a secondary token
    if tpat.search(head_ns):
        s += 2                                          # correct test (despaced header)
    if city and str(city).upper().replace(".", "") in U.replace(".", ""):
        s += 3                                          # city pins the location-split page
    return s


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    w = pd.read_csv(WORK)
    h = w[w.category == "HAND_AUDIT"].copy()
    docs, manifest, unmatched = {}, [], []
    for yr, grp in h.groupby("Year"):
        pdf = RED / f"{yr}_done.pdf"
        if not pdf.exists():
            for r in grp.itertuples():
                unmatched.append({**r._asdict(), "reason": "no PDF"})
            continue
        if yr not in docs:
            doc = fitz.open(pdf)
            pages = []
            for i, p in enumerate(doc):
                t = p.get_text(); U = t.upper()
                head_ns = re.sub(r"\s+", "", U[:300])   # despaced header (OCR splits romans)
                pages.append((i, U, re.sub(r"[^A-Z0-9]", "", U), head_ns))
            docs[yr] = (doc, pages)
        doc, pages = docs[yr]
        # propagate a Table-N hint across each (Test,Phenotype) group (early-era table cells)
        grp_tab = {}
        for (tst, ph), sub in grp.groupby(["Test", "Phenotype"]):
            tnos = [table_hint(n) for n in sub.qc_note]
            tnos = [t for t in tnos if t]
            grp_tab[(tst, ph)] = max(set(tnos), key=tnos.count) if tnos else None
        for r in grp.itertuples():
            tpat = test_patterns(r.Test)
            toks = strain_tokens(r.Strain)
            tno = grp_tab.get((r.Test, r.Phenotype))
            method, best = "trait_scan", None
            if tno is not None:
                hits = find_table_pages(pages, tno)[:4]
                method = "table_hint"
            else:
                hits = []
            if not hits:  # trait-filtered strain/city/test scoring
                method = "trait_scan"
                block = [p[0] for p in pages if tpat.search(p[3])]   # this test's page block
                trait_in_block = [i for i in block if has_trait(pages[i][1], r.Phenotype)]
                if block:
                    # stay INSIDE the right test: trait pages if the title survived OCR, else the block
                    cand_ix = trait_in_block if trait_in_block else block
                    method = "trait_scan" if trait_in_block else "test_block"  # flag garbled-title case
                else:
                    cand_ix = [i for i, U, Ua, hns in pages if has_trait(U, r.Phenotype)]
                if not cand_ix:
                    unmatched.append({"Year": yr, "Test": r.Test, "Phenotype": r.Phenotype,
                                      "City": r.City, "Strain": r.Strain, "reason": "no trait page / test block"})
                    continue
                cand = [(score_page(pages[i][1], pages[i][2], pages[i][3], toks, r.City, tpat), i)
                        for i in cand_ix]
                best = max(s for s, _ in cand)
                hits = sorted(i for s, i in cand if s == best)
                hits = hits[:6] if (method == "test_block" and best == 0) else hits[:4]
            manifest.append({"Year": yr, "Test": r.Test, "Phenotype": r.Phenotype, "City": r.City,
                             "State": r.State, "Strain": r.Strain, "ocr_value": r.ocr_value,
                             "corpus_value": r.corpus_value, "pdf_value": r.pdf_value,
                             "method": method, "score": ("tbl" if best is None else best),
                             "confident": (method == "table_hint") or (best is not None and best >= 5),
                             "pdf_pages_1based": ",".join(str(i + 1) for i in hits),
                             "qc_note": r.qc_note})
    md = pd.DataFrame(manifest)
    nlow = int((~md["confident"]).sum()) if len(md) else 0
    print(f"HAND_AUDIT cells: {len(h)} | matched: {len(md)} (low-confidence: {nlow}) | unmatched: {len(unmatched)}")
    if len(md):
        print(md[["Year", "Test", "Phenotype", "Strain", "method", "score", "confident",
                  "pdf_pages_1based"]].to_string(index=False))
    if unmatched:
        print("\nUNMATCHED:")
        print(pd.DataFrame(unmatched)[["Year", "Test", "Phenotype", "Strain"]].to_string(index=False))

    if mode == "--render":
        OUT.mkdir(parents=True, exist_ok=True)
        # unique (year, page) -> tag with tests/traits that need it
        need = {}
        for row in manifest:
            for pg in row["pdf_pages_1based"].split(","):
                need.setdefault((row["Year"], int(pg)), set()).add(f"{row['Test']}_{row['Phenotype']}")
        for (yr, pg), tags in sorted(need.items()):
            doc = docs[yr][0]
            tag = "_".join(sorted(tags))[:60]
            fn = OUT / f"{yr}_p{pg:03d}_{re.sub(r'[^A-Za-z0-9_-]', '', tag)}.png"
            doc[pg - 1].get_pixmap(matrix=fitz.Matrix(2.6, 2.6)).save(str(fn))
        md.to_csv(OUT / "hand_audit_pages_manifest.csv", index=False)
        if unmatched:
            pd.DataFrame(unmatched).to_csv(OUT / "_UNMATCHED.csv", index=False)
        print(f"\nrendered {len(need)} unique pages -> {OUT}")


if __name__ == "__main__":
    main()
