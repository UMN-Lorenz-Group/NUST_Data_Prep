"""Extract per-(Year, Test, Location) PlantingDate + MaturityDate (as DOY) from the
'MATURITY (date)' data tables in the NUST annual report PDFs, 2005-2015.

Each maturity table (one per test, sometimes 2 pages) prints, sharing column x:
  * a city header row + a state row (one state per location column),
  * an ANCHOR row (first strain = a check) with the ABSOLUTE maturity date per
    location (m/d)  -> MaturityDate,
  * a 'Date Planted' row (m/d per location)                 -> PlantingDate,
  * a 'Days to Mature' row (int per location) for validation (planting+days==anchor).
The leftmost 'Mean' column is skipped.

Output committed as reference/nust_planting_maturity_2005_2015.csv
  [Year, Test, State, Location, PlantingDOY, MaturityDOY, DaysToMature, days_check]

Report PDFs are NOT in the repo — download from USDA-ARS (see
reference_nust_report_pdf_source) into NUST_PDF_DIR (default below). The CSV is the
committed reproducible artifact consumed by build_nust_locations_table_2005_2025.py.

Run:  NUST_PDF_DIR=/path/to/pdfs uv run --with pymupdf python extract_dates_2005_2015.py [YEAR]
"""
import fitz, re, os, sys, csv
from pathlib import Path
from collections import defaultdict

SC = os.environ.get(
    "NUST_PDF_DIR",
    "C:/Users/vramasub/AppData/Local/Temp/claude/C--Users-vramasub-Desktop-UMN-GIT-NUST-Data-Prep--claude-worktrees-sad-proskuriakova-cd3106/b032cfbf-4a15-4437-8bb0-2e0355ac9b36/scratchpad/pdfs")
OUT_CSV = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/reference/nust_planting_maturity_2005_2015.csv")

STATES = {"IA","IL","IN","KS","KY","MI","MN","MO","ND","NE","NJ","OH","ONT","ON","QUE","QC",
          "SAS","SK","MAN","MB","SD","WI","DE","MD","PA","TX","VA","AL","AR","GA","TN","CO","WY","NC"}
MONTHS_CUM = {1:0,2:31,3:59,4:90,5:120,6:151,7:181,8:212,9:243,10:273,11:304,12:334}
MD = re.compile(r"^(\d{1,2})/(\d{1,2})$")

def to_doy(s):
    m = MD.match(str(s).strip())
    if not m: return None
    mo, da = int(m.group(1)), int(m.group(2))
    if not (1 <= mo <= 12 and 1 <= da <= 31): return None
    return MONTHS_CUM[mo] + da

def test_code(title):
    t = title.upper()
    m = re.search(r"(UNIFORM|PRELIMINARY)\s+TEST\s+([0IVAB]+)", t)
    if not m: return None
    code = ("UT" if m.group(1) == "UNIFORM" else "PT") + m.group(2)
    if "ROUNDUP" in t or "RR" in t.replace("PRELIMINARY", "").replace("UNIFORM", ""):
        code += "RR"
    return code

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

def nearest(x, centers):
    return min(range(len(centers)), key=lambda i: abs(centers[i] - x))

TITLEWORDS = {"MEAN", "TESTS", "STRAIN", "UNIFORM", "PRELIMINARY", "TEST", "MATURITY", "(DATE)"}

def parse_page(pg, test):
    words = pg.get_text("words")
    if not words: return []
    rows = rows_by_y(words)
    plant_row = days_row = anchor_row = None
    for r in rows:
        txt = " ".join(w[4] for w in r["w"])
        if plant_row is None and "Planted" in txt:
            plant_row = r
        if days_row is None and "Days" in txt and "Mature" in txt:
            days_row = r
    # anchor row = first row whose values are mostly m/d dates (the check with absolute dates)
    for r in rows:
        vals = [w for w in r["w"] if MD.match(w[4])]
        if len(vals) >= 3:
            anchor_row = r; break
    # column centers = x of the Date Planted m/d values (present for EVERY location incl Mean);
    # fall back to the anchor row if Date Planted is missing.
    def md_xs(r):
        return [w[0] for w in r["w"] if MD.match(w[4])] if r else []
    centers = md_xs(plant_row) or md_xs(anchor_row)
    if len(centers) < 2:
        return []
    anchor_y = anchor_row["y"] if anchor_row else min(centers)  # header band = above the anchor row
    ay = anchor_row["y"] if anchor_row else 1e9
    # state per column: nearest state token found anywhere above the anchor row
    st_toks = [(w[0], w[4]) for r in rows if r["y"] < ay for w in r["w"] if w[4] in STATES]
    states = [None] * len(centers)
    for x, s in st_toks:
        ci = nearest(x, centers)
        if abs(centers[ci] - x) <= 30 and states[ci] is None:
            states[ci] = s
    # city per column: stitch non-title/non-state header tokens (above anchor) by nearest center
    cities = [""] * len(centers)
    buckets = defaultdict(list)
    for r in sorted((r for r in rows if r["y"] < ay), key=lambda r: r["y"]):
        for w in r["w"]:
            tok = w[4]
            if tok.upper() in TITLEWORDS or tok in STATES or re.match(r"^[\dIVXAB]+,?$", tok):
                continue
            ci = nearest(w[0], centers)
            if abs(centers[ci] - w[0]) <= 34:
                buckets[ci].append((r["y"], w[0], tok))
    for ci, toks in buckets.items():
        cities[ci] = " ".join(t for _, _, t in sorted(toks))
    def col_vals(r):
        v = [None] * len(centers)
        if not r: return v
        for w in r["w"]:
            if MD.match(w[4]) or re.match(r"^\d{1,3}(\.\d)?$", w[4]):
                ci = nearest(w[0], centers)
                if abs(centers[ci] - w[0]) <= 20:
                    v[ci] = w[4]
        return v
    plant = col_vals(plant_row); days = col_vals(days_row); anchor = col_vals(anchor_row)
    out = []
    for i in range(len(centers)):
        if states[i] is None:          # the Mean column (no state) -> skip
            continue
        pl = to_doy(plant[i]) if plant[i] else None
        an = to_doy(anchor[i]) if anchor[i] else None
        dd = int(days[i]) if (days[i] and re.match(r"^\d{1,3}$", str(days[i]))) else None
        mat = (pl + dd) if (pl is not None and dd is not None) else an
        chk = (pl is not None and dd is not None and an is not None and abs((pl + dd) - an) <= 1)
        out.append((test, states[i], cities[i], pl, mat, dd, chk))
    return out

def find_maturity_pages(doc):
    """A maturity DATA table = a 'MATURITY (date)' title anywhere on the page AND a
    'Date Planted' row (its definitive signature — excludes regional-summary/yield pages)."""
    out = []
    for i, pg in enumerate(doc):
        t = pg.get_text() or ""
        if re.search(r"MATURITY\s*\(date\)", t, re.I) and "Planted" in t and re.search(r"(UNIFORM|PRELIMINARY)\s+TEST", t.upper()):
            out.append(i)
    return out

def title_of(pg):
    for l in (pg.get_text() or "").split("\n"):
        if re.search(r"(UNIFORM|PRELIMINARY)\s+TEST", l.upper()):
            return l.strip()
    return ""

def run(year):
    doc = fitz.open(f"{SC}/{year}.pdf")
    rows = []
    for i in find_maturity_pages(doc):
        tc = test_code(title_of(doc[i]))
        if tc is None: continue
        for r in parse_page(doc[i], tc):
            rows.append((int(year),) + r)
    return rows

if __name__ == "__main__":
    if len(sys.argv) > 1:
        rows = run(sys.argv[1])
        print(f"{sys.argv[1]}: {len(rows)} (test,location) rows")
        ok = sum(1 for r in rows if r[6])
        print(f"  planting+days==anchor: {ok}/{sum(1 for r in rows if r[3] and r[5])}")
        for r in rows[:40]:
            print("  ", r)
    else:
        allrows = []
        for y in range(2005, 2016):
            try:
                rr = run(str(y)); allrows += rr
                ok = sum(1 for r in rr if r[6])
                print(f"{y}: {len(rr)} rows, planting+days==anchor {ok}")
            except Exception as e:
                print(f"{y}: ERROR {e}")
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Year","Test","State","Location","PlantingDOY","MaturityDOY","DaysToMature","days_check"])
            w.writerows(allrows)
        print(f"Wrote {OUT_CSV}  ({len(allrows)} rows)")
