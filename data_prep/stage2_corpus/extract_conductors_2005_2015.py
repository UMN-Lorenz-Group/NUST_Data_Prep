"""Extract per-location Conductor (cooperator) from the 'Uniform and Preliminary
Test Location(s)' table in the NUST annual report PDFs, 2005-2015. The grower/
cooperator table exists in the reports from 1989 on (GPS coords only from 2020).

Output: reference/nust_conductors_2005_2015.csv  [Year, State, Location, Conductor]

Report PDFs are NOT in the repo (gitignored / large). Download them from USDA-ARS
(see memory reference_nust_report_pdf_source): pattern
  https://www.ars.usda.gov/ARSUserFiles/50200500/UST/<YEAR>.PDF   (2003+ upper-case)
  https://www.ars.usda.gov/ARSUserFiles/50200500/ust/<year>.pdf   (2000-2002 lower-case)
into a directory and set NUST_PDF_DIR to it (default below). The extracted CSV is the
committed, reproducible artifact consumed by build_nust_locations_table_2005_2025.py.

Run:  NUST_PDF_DIR=/path/to/pdfs uv run --with pymupdf python extract_conductors_2005_2015.py
"""
import fitz, re, os, sys, csv
from pathlib import Path
from collections import defaultdict

SC = os.environ.get(
    "NUST_PDF_DIR",
    "C:/Users/vramasub/AppData/Local/Temp/claude/C--Users-vramasub-Desktop-UMN-GIT-NUST-Data-Prep--claude-worktrees-sad-proskuriakova-cd3106/b032cfbf-4a15-4437-8bb0-2e0355ac9b36/scratchpad/pdfs")
OUT_CSV = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/reference/nust_conductors_2005_2015.csv")
STATES = {"IA","IL","IN","KS","KY","MI","MN","MO","ND","NE","NJ","OH","ONT","ON","QUE","QC",
          "SAS","SK","MAN","Man","SD","WI","DE","MD","PA","TX","VA","AL","AR","GA","TN","CO","WY"}
INITIAL = re.compile(r"^[A-Z][A-Z.\-]{0,3}\.")     # 'W.' / 'W.Fehr' / 'G-L.' / 'G.L.' (initials incl. hyphenated)

def is_x(tok):
    return tok in ("X", "X1", "x")

def rows_by_y(words, tol=4):
    rows = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        for r in rows:
            if abs(r["y"] - w[1]) <= tol:
                r["w"].append(w); break
        else:
            rows.append({"y": w[1], "w": [w]})
    for r in rows:
        r["w"].sort(key=lambda w: w[0])
    return rows

def parse_page(pg):
    words = pg.get_text("words")
    if not words:
        return []
    rows = rows_by_y(words)
    out = []           # (state, location, conductor)
    cur_state = None
    pending_loc = None       # location text with no conductor yet (wrapped)
    for r in rows:
        toks = [(w[0], w[4]) for w in r["w"]]
        txts = [t[1] for t in toks]
        # x of first X-mark → right boundary of the name region
        xs = [x for x, t in toks if is_x(t)]
        first_x = min(xs) if xs else None
        # name region = tokens left of first X (or all if no X)
        name_toks = [(x, t) for x, t in toks if (first_x is None or x < first_x - 1)]
        if not name_toks:
            continue
        nt = [t for _, t in name_toks]
        # strip a leading state code
        state_here = None
        if nt and nt[0] in STATES:
            state_here = nt[0]; cur_state = nt[0]; nt = nt[1:]; name_toks = name_toks[1:]
        # skip header/footer noise
        joined = " ".join(nt)
        if not nt or re.match(r"^\d+$", joined) or "LOCATIONS" in joined.upper() \
           or "Tests" in joined or "Location" in joined or "By:" in joined or "Conducted" in joined:
            continue
        # find conductor start = first token matching an INITIAL
        gi = next((j for j, t in enumerate(nt) if INITIAL.match(t)), None)
        if gi is None:
            # no conductor on this line: either a wrapped LOCATION (pair with next conductor)
            # or a location whose conductor is same as previous (blank). Treat as pending location.
            pending_loc = joined
            continue
        loc = " ".join(nt[:gi]).strip()
        cond = " ".join(nt[gi:]).strip()
        if not loc and pending_loc:      # conductor line whose location wrapped above/below
            loc = pending_loc
        pending_loc = None
        if not loc:
            continue
        st = state_here or cur_state
        out.append((st, loc, cond))
    return out

def find_pages(doc):
    """A locations table page = header mentions 'PRELIMINARY TEST LOCATION' (singular or
    plural, any casing) AND the page actually has the X-mark grid (excludes TOC/title pages)."""
    out = []
    for i, pg in enumerate(doc):
        t = pg.get_text() or ""
        u = t.upper()
        if "PRELIMINARY TEST LOCATION" not in u:
            continue
        n_x = sum(1 for w in pg.get_text("words") if w[4] in ("X", "X1"))
        if n_x >= 12:
            out.append(i)
    return out

def surname_clean(g):
    # keep as-is but tidy: collapse spaces
    return re.sub(r"\s+", " ", g).strip()

def run(year):
    doc = fitz.open(f"{SC}/{year}.pdf")
    pages = find_pages(doc)
    rows = []
    for i in pages:
        rows += parse_page(doc[i])
    # dedup by (state, location) keep first
    seen = {}
    for st, loc, cond in rows:
        k = (st, loc)
        if k not in seen:
            seen[k] = surname_clean(cond)
    return pages, seen

if __name__ == "__main__":
    if len(sys.argv) > 1:                       # single-year debug print
        yr = sys.argv[1]
        pages, seen = run(yr)
        print(f"{yr}: pages {pages} -> {len(seen)} conductor rows")
        for (st, loc), cond in sorted(seen.items()):
            print(f"  {st:4} {loc:28} {cond}")
    else:                                       # full 2005-2015 -> reference CSV
        allrows = []
        for yr in range(2005, 2016):
            try:
                pages, seen = run(str(yr))
            except Exception as e:
                print(f"{yr}: ERROR {e}"); continue
            print(f"{yr}: pages {pages} -> {len(seen)} locations")
            allrows += [(yr, st, loc, cond) for (st, loc), cond in seen.items()]
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["Year", "State", "Location", "Conductor"]); w.writerows(allrows)
        print(f"Wrote {OUT_CSV}  ({len(allrows)} rows)")
