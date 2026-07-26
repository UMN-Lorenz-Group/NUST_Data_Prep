"""
103_extract_pdf_tables.py
=========================
Local pdfplumber re-extraction of MISSING UT trait-tables from the Red PDFs, for the
dual-source recovery (cross-checked against the Green XLSX, script 104, by 105).
NO API — pdfplumber text/word layer only.

Independent re-extract of the manifest cells (102_recovery_manifest.csv). This first
cut handles the 1950s "Summary of data for Uniform Test, Group X, YYYY" STRAIN-MEAN
table (Table 13 style): one row per strain with positional columns
  Yield | Maturity(+/-) | Lodging | Height | SeedQuality | SeedWeight | Protein | Oil
(SeedWeight -> SeedSize; Protein/Oil get the x0.87 dry->13%mb correction). Per-location
yield matrices (Table 15) + the 1970s-80s "UNIFORM TEST X" formats are added next.

Output: data_prep/stage2_corpus/recovery_pdf_extract.csv
  Year, TestMG, Test, Strain, City, State, Phenotype, Value_num, Units, Source="PDF"
"""
import sys
import re
from collections import defaultdict
from pathlib import Path
import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
CORPUS = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
INPUT = REPO / "input_files"
OUT = REPO / "data_prep" / "stage2_corpus" / "recovery_pdf_extract.csv"
DRY_TO_13MC = 0.87

# Table-13 strain-mean column order (after the strain name), 1950s-60s layout.
SM_COLS = ["YieldBuA", "Maturity", "Lodging", "Height", "SeedQuality", "SeedSize", "Protein", "Oil"]
RANGES = {"YieldBuA": (5, 80), "Maturity": (-40, 40), "Lodging": (1, 5.5), "Height": (10, 60),
          "SeedQuality": (1, 5.5), "SeedSize": (8, 26), "Protein": (33, 50), "Oil": (14, 26)}
UNITS = {"YieldBuA": "bu/a", "Maturity": "rel_days", "Lodging": "score", "Height": "in",
         "SeedQuality": "score", "SeedSize": "g/100sd", "Protein": "%", "Oil": "%"}
FOOTER = re.compile(r"^(no\.|mean|coef|bu\.|row|mo\.|l\.?s\.?d|c\.?v|grand|range|table|"
                    r"\d{4}|days|brown|bacterial)", re.IGNORECASE)
NUMISH = re.compile(r"^[+\-^•]?\d[\d.,\-]*$")
MG_ROMAN = r"(0{1,2}|[IV]+)"


# --------------------------------------------------------------------------- helpers (from 101)
def strain_key(s, collapse=False):
    s = re.sub(r"\s*\([^)]*\)", "", str(s)).replace("*", "")
    s = re.sub(r"[\s.]+", "", s).upper()
    if collapse:
        s = s.replace("O", "0").replace("I", "1").replace("L", "1")
    return s


def build_strain_map(lo, hi):
    src = pd.read_csv(CORPUS, low_memory=False, usecols=["Year", "Strain"])
    src = src[src["Year"].between(lo, hi)]
    exact, collapsed = {}, {}
    for sp in sorted(set(str(x).strip() for x in src["Strain"].dropna())):
        if sp and sp.lower() != "strain":
            exact.setdefault(strain_key(sp), sp)
            collapsed.setdefault(strain_key(sp, collapse=True), sp)
    return exact, collapsed


def match_strain(raw, exact, collapsed):
    return exact.get(strain_key(raw)) or collapsed.get(strain_key(raw, collapse=True))


def match_prefix(tokens, exact, collapsed):
    for p in range(min(len(tokens), 4), 0, -1):
        cand = " ".join(tokens[:p])
        if re.search(r"[A-Za-z]", cand):
            m = match_strain(cand, exact, collapsed)
            if m:
                return m, p
    return None, 0


def cx(w):
    return (w["x0"] + w["x1"]) / 2.0


def words_by_line(page, tol=2.4):
    d = defaultdict(list)
    for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        d[round(w["top"] / tol) * tol].append(w)
    return [(t, sorted(d[t], key=lambda w: w["x0"])) for t in sorted(d)]


def clean_num(tok):
    t = tok.strip("^•*()").replace(",", ".")
    # keep a leading sign (maturity), turn stray internal dashes into dots
    sign = "-" if t[:1] == "-" else ""
    t = re.sub(r"[^0-9.]", ".", t.lstrip("+-"))
    t = re.sub(r"\.+", ".", t).strip(".")
    if not t:
        return None
    if t.count(".") > 1:
        a, b = t.split(".")[:2]
        t = f"{a}.{b}"
    try:
        return float(sign + t)
    except ValueError:
        return None


def pdf_path(year):
    p = INPUT / f"input_{year}" / f"{year}_done.pdf"
    return p if p.exists() else None


# --------------------------------------------------------------------------- strain-mean table
def find_summary_pages(pdf, year, mg):
    """page indices whose text has 'summary of data for uniform test, group <mg>, <year>'
    (single-year, not 'two/three-year')."""
    want = mg.upper()
    out = []
    for i, pg in enumerate(pdf.pages):
        norm = re.sub(r"\s+", " ", (pg.extract_text() or "").lower())
        for m in re.finditer(r"(\w+[- ])?summary of data for uniform test,?\s*group\s+"
                             + r"(0{1,2}|[ivx]+),?\.?\s*(\d{4})?", norm):
            if m.group(1) and "year" in m.group(1):     # multi-year summary
                continue
            grp = m.group(2).upper()
            yr = m.group(3)
            if grp == want and (yr is None or yr == str(year)):
                out.append(i)
                break
    return out


def parse_summary(page, exact, collapsed):
    """Yield (strain, {trait: value}) from a Table-13 strain-mean summary. Groups each
    strain line with its wrapped numeric continuation lines, then positional-maps the
    8 SM_COLS (Yield..Oil)."""
    lines = words_by_line(page)
    rows, cur, started = [], None, False

    def flush():
        if not cur:
            return
        nums = [v for v in (clean_num(t) for t in cur["nums"]) if v is not None]
        vals = {}
        for col, v in zip(SM_COLS, nums):
            lo, hi = RANGES[col]
            if lo <= v <= hi:
                vals[col] = v
        if vals:
            rows.append((cur["strain"], vals))

    for top, ws in lines:
        toks = [w["text"] for w in ws]
        if not toks:
            continue
        first = toks[0].strip(".,")
        sp, n = match_prefix(toks, exact, collapsed)
        if sp is not None and not FOOTER.match(first):
            flush()
            cur = {"strain": sp, "nums": [t for t in toks[n:] if NUMISH.match(t)], "cont": 0}
            started = True
        elif started and cur is not None:
            if FOOTER.match(first):
                flush(); cur = None
                break
            nums = [t for t in toks if NUMISH.match(t)]
            if nums and len(nums) >= len(toks) - 1 and cur["cont"] < 2:
                cur["nums"].extend(nums); cur["cont"] += 1
            elif re.search(r"[A-Za-z]{3,}", " ".join(toks)):
                flush(); cur = None
                break
    flush()
    return rows


def main():
    exact, collapsed = build_strain_map(1941, 1990)
    print(f"strain map: {len(exact)} spellings (1941-1990)")
    man = pd.read_csv(REPO / "data_prep" / "stage2_corpus" / "recovery_manifest.csv")
    rows = []

    def emit(year, mg, strain, trait, val):
        if trait in ("Protein", "Oil"):
            val = round(val * DRY_TO_13MC, 2)
        rows.append({"Year": year, "TestMG": mg, "Test": f"UT-{mg}", "Strain": strain,
                     "City": "", "State": "", "Phenotype": trait,
                     "Value_num": round(val, 2), "Units": UNITS[trait], "Source": "PDF"})

    # FIRST CUT: the 1950s strain-mean summary, for the manifest cells <= 1969 (Table-13 era)
    targets = sorted(set((int(r.Year), str(r.TestMG)) for r in man.itertuples()
                         if r.Year <= 1969))
    by_year = defaultdict(list)
    for yr, mg in targets:
        by_year[yr].append(mg)

    for year, mgs in sorted(by_year.items()):
        pp = pdf_path(year)
        if pp is None:
            print(f"{year}: no PDF"); continue
        with pdfplumber.open(pp) as pdf:
            for mg in sorted(set(mgs)):
                pages = find_summary_pages(pdf, year, mg)
                n = 0
                for idx in pages:
                    for strain, vals in parse_summary(pdf.pages[idx], exact, collapsed):
                        for tr, v in vals.items():
                            emit(year, mg, strain, tr, v); n += 1
                print(f"  {year} MG {mg}: summary pages {pages} -> {n} vals")

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"\nWrote {OUT.name}: {len(df):,} rows")
    if len(df):
        print(df.groupby(["Year", "TestMG", "Phenotype"]).size().head(40).to_string())


if __name__ == "__main__":
    main()
