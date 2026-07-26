"""
gen_f4u_1989_1992_composition.py
================================
Extract the PROTEIN (%) and OIL (%) per-location tables for 1989/1991/1992 from the
report PDFs (NUST_Data_1989_1992/{year}.pdf). These composition traits are NOT in the
per-test report CSVs (only agronomic is) -- they live only in the PDF (and Master).

Output schema matches the agronomic F4U (Strain, Year, Test, City, State, Phenotype,
Value, Units) so the two can be concatenated into one phenotypesTable1.csv per year.

Table layout (clean text, few locations = the composition subset):
  PROTEIN (%)
  <frag?>            Crook- ...            <- optional fragment header row
  Mean  Crookston  Shelly  Elora          <- city row (Mean = the N-tests mean col)
  Strain  3 Tests  MN  MN  Ont.           <- state row (col0='Strain')
  CLAY (0)  41.3  39.2  41.7  42.9         <- strain + Mean + per-loc values
  ...
  OIL (%)   <same locations>

Parsed via pdfplumber word x-positions (the city headers are fragmented / multi-word,
so plain-text splitting fails). Reuses helpers from gen_f4u_1989_1992_agronomic.

Usage:
    uv run --with pdfplumber python data_prep/stage2_corpus/gen_f4u_1989_1992_composition.py         # report
    uv run --with pdfplumber python data_prep/stage2_corpus/gen_f4u_1989_1992_composition.py --write  # write CSVs
"""
import argparse
import csv
import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_spec = importlib.util.spec_from_file_location(
    "agro", Path(__file__).with_name("gen_f4u_1989_1992_agronomic.py"))
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

SRC = A.SRC
YEARS = [1989, 1991, 1992]
# header may be 'UNIFORM TEST X', 'UNIFORM PRELIMINARY TEST X' (1989), or just
# 'PRELIMINARY TEST X' (1991/92 drop the UNIFORM prefix on preliminary tests)
HDR = re.compile(r"(UNIFORM PRELIMINARY|PRELIMINARY|UNIFORM)\s+TEST\s+(00|0|[IVX]+[AB]?)", re.I)
NUM = re.compile(r"^-?\d+(\.\d+)?$")
# OCR-tolerant block markers ('(' misread as '<'/'[', etc.)
PROT_RE = re.compile(r"PROTEIN\s*[(<\[{]?\s*%")
OIL_RE = re.compile(r"\bOIL\s*[(<\[{]?\s*%")


def looks_numeric(s):
    """True if the cell is a (possibly OCR-garbled) number, e.g. '42.,4', '43..1', '19'."""
    t = re.sub(r"[.,\s\-]", "", str(s))
    return len(t) > 0 and t.isdigit()


def clean_num(s):
    """Parse an OCR-noisy numeric cell: '41.,7'->'41.7', '43..1'->'43.1'. Returns the
    cleaned numeric string or None. Composition values are ~15-45 (%), so guard the range."""
    s = re.sub(r"[^0-9.\-]", "", str(s).strip())
    s = re.sub(r"\.{2,}", ".", s).strip(".")
    if not NUM.match(s):
        return None
    try:
        if 5 <= float(s) <= 60:   # plausible protein/oil %
            return s
    except ValueError:
        pass
    return None


def test_name(m):
    pre = "PRELIMINARY" in m.group(1).upper()
    mg = m.group(2).upper()
    return (f"PT-{mg}" if pre else f"UT-{mg}")


def xc(w):
    return (float(w["x0"]) + float(w["x1"])) / 2


def build_grid(words):
    """Words (y-windowed) -> (list of row-cell-lists, column centers). Rows are
    clustered by top with a tolerance (a strain label and its values can sit at
    slightly different baselines; a fixed bucket would split them)."""
    centers = []
    for x in sorted(xc(w) for w in words):
        if centers and x - centers[-1][-1] <= 12:
            centers[-1].append(x)
        else:
            centers.append([x])
    cen = [sum(c) / len(c) for c in centers]

    def col_of(w):
        return min(range(len(cen)), key=lambda i: abs(cen[i] - xc(w)))

    # cluster row baselines within TOL px
    TOL = 4.0
    tops = sorted(float(w["top"]) for w in words)
    groups = []
    for t in tops:
        if groups and t - groups[-1] <= TOL:
            continue
        groups.append(t)

    def row_of(w):
        t = float(w["top"])
        return min(range(len(groups)), key=lambda i: abs(groups[i] - t))

    rows = [["" for _ in cen] for _ in groups]
    for w in words:
        r, c = row_of(w), col_of(w)
        rows[r][c] = (rows[r][c] + " " + w["text"]).strip()
    return rows, cen


def _loc_cols_from(grid, i, cen):
    """Given a state row at index i, build {loc_col: (city, state)} + mean_col."""
    r = grid[i]
    name_row = grid[i - 1] if i >= 1 else [""] * len(cen)
    frag_row = grid[i - 2] if i >= 2 else [""] * len(cen)
    loc_cols = {}
    base = ""
    for c in range(len(r)):
        st = A.norm_state(r[c])
        if st not in A.VALID_STATES:
            continue
        fc = frag_row[c] if c < len(frag_row) else ""
        nc = name_row[c] if c < len(name_row) else ""
        if nc.strip("*").lower() in A.SOIL:
            b = A.clean_city(fc, "") or base
            city = f"{b}-{nc.strip('*').title()}"
            base = b
        else:
            city = A.clean_city(fc, nc)
            if city:
                base = city
        if city:
            loc_cols[c] = (A.canon_city(city, st), st)
    return loc_cols


def parse_page(grid, cen, year, test, carry=None):
    """Walk a whole composition page grid, tracking the current phenotype (set by the
    PROTEIN(%)/OIL(%) marker rows) and the current location columns (set by each header
    state row; same-page OIL with no header reuses the preceding PROTEIN columns; a
    separate OIL page with no header reuses `carry` from the prior page). Returns
    (rows, last_loc_cols)."""
    out = []
    pheno = None
    loc_cols, mean_col = (carry or {}), (min(carry) - 1 if carry else 0)
    for i, r in enumerate(grid):
        c0, u = r[0].strip(), r[0].strip().upper()
        line = re.sub(r"\s+", " ", " ".join(r)).upper()
        if PROT_RE.search(line):
            pheno = "Protein"; continue
        if OIL_RE.search(line):
            pheno = "Oil"; continue
        # header state row?
        if sum(1 for x in r if A.norm_state(x) in A.VALID_STATES) >= 2:
            lc = _loc_cols_from(grid, i, cen)
            if lc:
                loc_cols, mean_col = lc, min(lc) - 1
            continue
        if pheno is None or not loc_cols:
            continue
        if not c0 or c0 == "_" or u.startswith(("MEAN", "C.V", "L.S", "STRAIN", "NO.")) or "UNIFORM" in u:
            continue
        # strain = the non-numeric label cells left of the first location column
        # (excludes the numeric Mean-value column that sits between strain and locations)
        first_loc = min(loc_cols)
        strain = A.clean_strain(" ".join(
            r[c] for c in range(first_loc) if r[c] and not looks_numeric(r[c])))
        if not strain or strain.upper() in ("STRAIN", "MEAN"):
            continue
        for c, (city, st) in loc_cols.items():
            v = clean_num(r[c]) if c < len(r) else None
            if v:
                out.append((strain, year, test, city, st, pheno, v, "%"))
    return out, loc_cols


def extract_year(year, pdf):
    out = []
    last_test = None
    carry = None
    for pi, page in enumerate(pdf.pages):
        t = page.extract_text() or ""
        tu = t.upper()
        if not PROT_RE.search(tu) and not OIL_RE.search(tu):
            carry = None
            continue
        m = HDR.search(t)
        test = test_name(m) if m else last_test
        if test is None:
            continue
        words = page.extract_words(x_tolerance=1.5, y_tolerance=1.5)
        y0 = min((float(w["top"]) for w in words
                  if w["text"].upper().startswith(("PROTEIN", "OIL"))), default=None)
        if y0 is None:
            continue
        # left margin = the 'Strain' header column; OCR speckle to its left ('MB','fc','|pUi')
        # shifts rows, so drop anything clearly left of it.
        sx = min((float(w["x0"]) for w in words if w["text"].strip().lower() == "strain"), default=0)
        sec = [w for w in words if float(w["top"]) >= y0 - 2 and float(w["x1"]) >= sx - 3]
        grid, cen = build_grid(sec)
        use_carry = carry if test == last_test else None
        rows, last_lc = parse_page(grid, cen, year, test, use_carry)
        out.extend(rows)
        carry, last_test = last_lc, test
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    import pdfplumber
    from collections import Counter
    for year in YEARS:
        with pdfplumber.open(SRC / f"{year}.pdf") as pdf:
            rows = extract_year(year, pdf)
        print(f"{year}: {len(rows):,} composition rows | {dict(Counter(r[5] for r in rows))} | tests {sorted(set(r[2] for r in rows))}")
        if args.write:
            out = SRC / str(year) / f"{year}_Processing" / "Files4Upload" / "phenotypesTable1_composition.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Strain", "Year", "Test", "City", "State", "Phenotype", "Value", "Units"])
                w.writerows(rows)
            print(f"   wrote {out.name}")


if __name__ == "__main__":
    main()
