"""
111_crosscheck_recover.py
=========================
Phase 2 cross-check + recovery builder for the F4U "extraction-skipped trait-table"
gaps (1970-1988). Uses the Green per-location extractor (109) plus the user-approved
ROBUST HYBRID validation (the 1970s PDF per-location tables are too OCR-noisy for a
strict cell-level Green==PDF check):

  * PARTIAL sections (the F4U already has some traits, e.g. 1984 UT-II yield+maturity):
    validate the Green parse by EXACT overlap against the existing corpus values for the
    shared traits. If they agree, fold the Green-recovered traits (the ones the F4U
    skipped) into recovery_confirmed.csv.
  * WHOLE-missing sections (no F4U baseline, e.g. 1977 UT-IV): validate the Green parser
    on a SIBLING same-year section that DOES have full F4U data; if the parser is exact
    on the sibling, trust the section's Green extraction and fold it.
  * PDF-ONLY sections (no Green XLSX, e.g. 1972 UT-III): cannot Green-extract -> recorded
    in recovery_review.csv as HELD (per the user decision; needs manual PDF extraction).

Outputs:
  recovery_confirmed.csv  -> folded by the Phase-6 loader in 10_assemble_corpus.py
  recovery_review.csv     -> held items (PDF-only / failed validation / disagreements)
Source tag on recovered rows: "Recovered_1970_1988". NO API.
"""
import sys
import re
import importlib
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
green = importlib.import_module("109_extract_green_section")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
NUST = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
CORPUS = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
OUT_CONF = REPO / "data_prep" / "stage2_corpus" / "recovery_confirmed.csv"
OUT_REV = REPO / "data_prep" / "stage2_corpus" / "recovery_review.csv"

TOL = {"YieldBuA": 0.05, "Maturity": 1.0, "Height": 0.5, "Lodging": 0.1,
       "Protein": 0.1, "Oil": 0.1, "SeedSize": 0.1, "SeedQuality": 0.1}

# Targets: (year, test_code, kind). kind = partial | whole | pdf_only
TARGETS = [
    (1984, "UT-II", "partial"),
    (1977, "UT-IV", "whole"),
    (1972, "UT-III", "pdf_only"),
]
SIBLING = {1977: "UT-I"}     # full-F4U same-year section to validate the parser for "whole" cases


def k_strain(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def k_city(c):
    return re.sub(r"[^a-z0-9]", "", str(c).lower())


def corpus_section(corpus, year, test_code, traits=None):
    c = corpus[(corpus.Year == year) & (corpus.Test == test_code) & corpus.Value_num.notna()]
    if traits:
        c = c[c.Phenotype.isin(traits)]
    return c


def overlap_agreement(g, c, trait):
    """fraction of shared (strain,city) cells where Green==corpus within tolerance."""
    G = g[g.Phenotype == trait].copy()
    C = c[c.Phenotype == trait].copy()
    if not len(G) or not len(C):
        return None, 0
    G["k"] = G.Strain.map(k_strain) + "|" + G.City.map(k_city)
    C["k"] = C.Strain.map(k_strain) + "|" + C.City.map(k_city)
    M = G.merge(C, on="k", suffixes=("_g", "_c"))
    M = M[M.Value_num_g.notna() & M.Value_num_c.notna()]
    if not len(M):
        return None, 0
    agree = (abs(M.Value_num_g - M.Value_num_c) <= TOL.get(trait, 0.1)).sum()
    return agree / len(M), len(M)


def parser_validated(g, c):
    """True if every trait shared between Green and corpus agrees >=99%."""
    shared = sorted(set(g.Phenotype) & set(c.Phenotype))
    if not shared:
        return False, {}
    rates = {}
    for tr in shared:
        rate, n = overlap_agreement(g, c, tr)
        rates[tr] = (round(rate, 3) if rate is not None else None, n)
    ok = all(r is not None and r >= 0.99 for r, n in rates.values())
    return ok, rates


def main():
    corpus = pd.read_csv(CORPUS, low_memory=False)
    confirmed, review = [], []
    for year, code, kind in TARGETS:
        print(f"\n=== {year} {code} ({kind}) ===")
        if kind == "pdf_only":
            review.append({"Year": year, "Test": code, "kind": kind,
                           "reason": "PDF-only (no Green XLSX); held per user decision — needs manual PDF extraction"})
            print("  HELD (PDF-only).")
            continue

        roster = green._roster_from_f4u_or_pdf(year, code)
        if not roster and kind == "whole":
            roster = pdf_roster_whole(year, code)
        if not roster:
            review.append({"Year": year, "Test": code, "kind": kind, "reason": "no roster found"})
            print("  HELD (no roster).")
            continue
        g = green.extract_section(year, code, roster)
        if not len(g):
            review.append({"Year": year, "Test": code, "kind": kind, "reason": "Green extract empty"})
            print("  HELD (empty Green extract).")
            continue

        if kind == "partial":
            c = corpus_section(corpus, year, code)
            ok, rates = parser_validated(g, c)
            print(f"  overlap validation: {rates}  -> {'VALIDATED' if ok else 'FAILED'}")
            present = set(c.Phenotype)
            recovered = g[~g.Phenotype.isin(present)]
        else:  # whole
            sib = SIBLING.get(year)
            gs = green.extract_section(year, sib, green._roster_from_f4u_or_pdf(year, sib)) if sib else g.iloc[0:0]
            cs = corpus_section(corpus, year, sib) if sib else c
            ok, rates = parser_validated(gs, cs)
            print(f"  sibling {sib} parser validation: {rates}  -> {'VALIDATED' if ok else 'FAILED'}")
            recovered = g  # whole section: everything is new

        recovered = recovered[recovered.Value_num.notna()]
        if ok and len(recovered):
            confirmed.append(recovered)
            print(f"  CONFIRMED {len(recovered)} rows across {sorted(set(recovered.Phenotype))}")
        else:
            review.append({"Year": year, "Test": code, "kind": kind,
                           "reason": f"parser not validated ({rates})" if not ok else "no recovered rows"})
            print("  HELD (validation failed / nothing to recover).")

    conf = pd.concat(confirmed, ignore_index=True) if confirmed else pd.DataFrame()
    if len(conf):
        conf["Source"] = "Recovered_1970_1988"
        conf = conf[["Year", "TestType", "TestMG", "Test", "Strain", "City", "State",
                     "Phenotype", "Value_num", "Units", "Source"]]
        conf.to_csv(OUT_CONF, index=False)
    pd.DataFrame(review).to_csv(OUT_REV, index=False)
    print(f"\nrecovery_confirmed.csv: {len(conf)} rows  ({conf.groupby(['Year','Test']).size().to_dict() if len(conf) else '{}'})")
    print(f"recovery_review.csv: {len(review)} held items")


def pdf_roster_whole(year, code):
    """Roster for a whole-missing section, from the PDF 'UNIFORM TEST X' parentage page."""
    import pdfplumber
    from collections import defaultdict
    mg = re.sub(r"^(UT|PT)-", "", code)
    p = REPO / "input_files" / f"input_{year}" / f"{year}_done.pdf"
    want = re.compile(rf"uniform test\s+{re.escape(mg)}\b", re.I)
    ros = set()
    with pdfplumber.open(p) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            tl = re.sub(r"\s+", " ", t.lower())
            if not want.search(tl) or "previous generat" not in tl and "parentage" not in tl:
                continue
            for line in t.splitlines():
                mm = re.match(r"^\s*\d+\.?\s+([A-Z][A-Za-z0-9()\-]+)", line)
                if mm:
                    ros.add(green.norm(mm.group(1)))
            if len(ros) >= 4:
                break
    return ros


if __name__ == "__main__":
    main()
