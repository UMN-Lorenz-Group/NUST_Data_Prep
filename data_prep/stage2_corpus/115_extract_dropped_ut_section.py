"""Re-extract a DROPPED Uniform-Test section (all traits) from the Red PDF — the sections the F4U
positional label-shift dropped (1985 UT-III, 1977 UT-III/UT-IV, 1988 UT-00; see
ut_pt_mislabel_audit_1941_1990.md). Handles the garbled-split-decimal, multi-location-group,
wrapped-city-header format that 112/109 return 0 on.

Approach per trait (spans ~3 pages, each a location GROUP; only the first page has the Mean column):
  * header: stitch wrapped city prefixes ("Man-"+"hattan"), read state line, keep column x-anchors;
  * data row: strain from x < first value column; values = fragment CELLS clustered by x-gap, each
    cell assigned to the nearest header column, then decimal-cleaned;
  * combine location groups by strain across pages; reconcile row-mean vs the printed "N Tests" Mean.

Usage: uv run python 115_extract_dropped_ut_section.py 1985 UT-III [--write out.csv]
"""
import sys, re, importlib
from collections import defaultdict
import pandas as pd, pdfplumber
sys.path.insert(0, "C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/data_prep/stage2_corpus")
O = importlib.import_module("114_extract_oil_perloc")

# (year, code) -> {trait: (units, [pages])}. Discover with the page-map scan; first page has Mean.
SECTION_PAGES = {
    (1985, "UT-III"): {
        "YieldBuA":    ("bu/a", [110, 111, 112]),
        "Maturity":    ("date", [113, 114, 115]),
        "Lodging":     ("score", [116, 117, 118]),
        "Height":      ("in", [119, 120, 121]),
        "SeedQuality": ("score", [122, 123, 124]),
        "SeedSize":    ("g/100", [125, 126, 127]),
        "Protein":     ("%", [128]),
        # Oil (129) already recovered -> oil_1985_UTIII_true.csv
    },
    (1977, "UT-III"): {   # dropped by the 1977 shift; single-year Mean page + 2 continuation pages
        "YieldBuA":    ("bu/a", [80, 81, 82]),
        "Maturity":    ("date", [86, 87, 88]),
        "Lodging":     ("score", [89, 90, 91]),
        "Height":      ("in", [92, 93, 94]),
        "SeedQuality": ("score", [95, 96, 97]),
        "SeedSize":    ("g/100", [98, 99, 100]),
        "Protein":     ("%", [101, 102]),
        "Oil":         ("%", [103, 104]),
    },
    (1977, "UT-IV"): {    # Height/Size/Oil are composite-only (regional summary), not per-location here
        "YieldBuA":    ("bu/a", [117, 118, 119]),
        "Maturity":    ("date", [120, 121, 122]),   # was mis-captioned "YIELD" (signed-value signature)
        "Lodging":     ("score", [123, 124, 125]),
        "SeedQuality": ("score", [126, 127, 128]),
        "Protein":     ("%", [129, 130]),
    },
    (1988, "UT-00"): {    # small test (13 strains), few pages
        "YieldBuA":    ("bu/a", [8, 9]),
        "Lodging":     ("score", [10]),
        "SeedQuality": ("score", [11]),
        "Protein":     ("%", [12]),
    },
    (1968, "UT-I"): {     # Phase-C recoverable single-trait gap: Height (F4U missed it). Others anchor roster.
        "YieldBuA":    ("bu/a", [36, 37]),
        "Maturity":    ("date", [38]),
        "Lodging":     ("score", [40]),
        "Height":      ("in", [41]),
        "Protein":     ("%", [44]),
    },
}
CELL_GAP = 24          # x-gap that separates two value cells
FOOTER = re.compile(r"Mean|LSD|L\.S\.D|C\.V|Reps?|Rows?|Average|Test|Row Sp|Date|Plant|Parentage", re.I)
# state token: 2-letter caps (1980s: PA IA) OR period-abbrev (1970s: Pa. N.J.) OR full/abbrev name
_ABBR = {"Ohio", "Iowa", "Ind", "Ill", "Mich", "Wis", "Wisc", "Minn", "Neb", "Nebr", "Kans", "Kan", "Mo",
         "Ky", "Tenn", "Va", "Ark", "Miss", "Ont", "Man", "Md", "Del", "Pa", "Cal", "Calif", "Penn"}
_FULLNAME = {"ohio", "iowa", "indiana", "illinois", "michigan", "wisconsin", "minnesota", "missouri",
             "nebraska", "kansas", "kentucky", "tennessee", "virginia", "maryland", "delaware",
             "pennsylvania", "arkansas", "mississippi", "ontario", "manitoba", "california", "georgia"}
def is_state(t):
    return bool(re.fullmatch(r"[A-Z]{2,3}", t) and t not in ("III", "II", "UT", "PT")) \
        or bool(re.fullmatch(r"[A-Z]\.[A-Z]\.?", t)) \
        or bool(re.fullmatch(r"[A-Z][a-z]{1,5}\.?", t) and t.rstrip(".") in _ABBR) \
        or t.strip("_.").lower() in _FULLNAME

def clean_cell(words, mode="decimal"):
    t = "".join(w["text"] for w in sorted(words, key=lambda w: w["x0"]))
    if mode == "signed":                    # Maturity relative offsets: +9, -8, -4.4, "+ 5.0"
        m = re.search(r"([+-]?)\s*(\d{1,2})(?:\.(\d))?", t)
        if not m:
            return None
        sign = -1 if m.group(1) == "-" else 1
        return sign * (float(f"{m.group(2)}.{m.group(3)}") if m.group(3) else float(m.group(2)))
    digs = re.findall(r"\d", t)
    if len(digs) < 2:
        return None
    return float(f"{digs[0]}{digs[1]}.{digs[-1]}") if len(digs) >= 3 else float(f"{digs[0]}.{digs[1]}")

def parse_header(ws):
    """-> ([(city,state,x0)], has_mean). Column order left->right; Mean (if present) is col 0."""
    meanw = [w for w in ws if w["text"] == "Mean"]
    has_mean = bool(meanw)
    # header row = the row with the most state codes just below a city line
    states = [w for w in ws if is_state(w["text"])]
    if not states:
        return [], has_mean, 150
    from statistics import mode
    st_top = mode([round(w["top"]) for w in states])
    states = sorted([w for w in states if abs(w["top"] - st_top) < 4], key=lambda w: w["x0"])
    mean_x = meanw[0]["x0"] if has_mean else (min(w["x0"] for w in states) - 40)
    # real city words: right of Mean, >=4 letters, on a line 3-20px above the state line (reject junk)
    cityw = sorted([w for w in ws if w["x0"] > mean_x + 12 and 3 < st_top - w["top"] < 20
                    and len(re.sub(r"[^A-Za-z]", "", w["text"])) >= 4 and not w["text"].endswith("-")],
                   key=lambda w: w["x0"])
    prefw = [w for w in ws if 3 < st_top - w["top"] < 24 and w["text"].endswith("-")]
    cols = []
    if has_mean:
        cols.append(("Mean", "", mean_x))
    for j, st in enumerate(states):
        cw = min(cityw, key=lambda w: abs(w["x0"] - st["x0"])) if cityw else None
        # only accept the city word if it's reasonably close to this state column, else placeholder
        name = cw["text"] if (cw and abs(cw["x0"] - st["x0"]) < 60) else f"col{j}"
        anchor = cw["x0"] if (cw and abs(cw["x0"] - st["x0"]) < 60) else st["x0"]
        if cw:
            pre = [p for p in prefw if abs(p["x0"] - cw["x0"]) < 22]
            if pre:
                name = pre[0]["text"].rstrip("-") + name
        cols.append((name, st["text"], anchor))
    return cols, has_mean, st_top

def _row_cells(wl, first_val_x):
    """value words in a row -> list of (center_x, [words]) cells clustered by x-gap."""
    vw = sorted([w for w in wl if w["x0"] >= first_val_x], key=lambda w: w["x0"])
    cells, cell = [], []
    for w in vw:
        if cell and w["x0"] - cell[-1]["x1"] > CELL_GAP:
            cells.append(cell); cell = []
        cell.append(w)
    if cell:
        cells.append(cell)
    return [(sum((w["x0"] + w["x1"]) / 2 for w in c) / len(c), c) for c in cells]

def _cluster_columns(centers, n_expected):
    """1D cluster of cell-centers -> column anchor x's (split at the largest gaps)."""
    xs = sorted(centers)
    if not xs:
        return []
    gaps = sorted(((xs[i + 1] - xs[i], i) for i in range(len(xs) - 1)), reverse=True)
    cuts = sorted(i for _, i in gaps[:max(0, n_expected - 1)] if _ > 15)
    cols, start = [], 0
    for cut in cuts + [len(xs) - 1]:
        seg = xs[start:cut + 1]
        cols.append(sum(seg) / len(seg)); start = cut + 1
    return cols

def parse_page(pdf, i, mode="decimal"):
    ws = pdf.pages[i].extract_words()
    cols_hdr, has_mean, st_top = parse_header(ws)
    if not cols_hdr:
        return None, has_mean
    mean_x = cols_hdr[0][2] if has_mean else min(c[2] for c in cols_hdr)
    n_loc = len([c for c in cols_hdr if c[0] != "Mean"])
    first_val_x = mean_x - 22
    body_top = st_top + 11
    rows = defaultdict(list)
    for w in ws:
        if w["top"] > body_top:
            rows[round(w["top"])].append(w)
    tops = sorted(rows)
    merged, cur = [], []
    for t in tops:
        if cur and t - cur[-1] > 6:
            merged.append(cur); cur = []
        cur.append(t)
    if cur:
        merged.append(cur)
    anchors = [c[2] for c in cols_hdr]
    out = {}
    for grp in merged:
        wl = [w for t in grp for w in rows[t]]
        strain = re.sub(r"\s+", " ", " ".join(w["text"] for w in sorted(wl, key=lambda w: w["x0"])
                                              if w["x0"] < first_val_x)).strip()
        strain = re.sub(r"^[^A-Za-z]+", "", strain)
        if not re.match(r"^[A-Za-z]", strain) or FOOTER.search(strain):
            continue
        rowvals = {}
        for cx, cl in _row_cells(wl, first_val_x):
            ci = min(range(len(anchors)), key=lambda k: abs(cx - anchors[k]))
            v = clean_cell(cl, mode)
            if v is not None:
                rowvals[ci] = v
        out[strain] = (cols_hdr, rowvals, has_mean)
    return out, has_mean

def norm(s):
    return re.sub(r"\s*\([^)]*\)", "", re.sub(r"[^A-Za-z0-9 ]", "", s)).strip().lower()

def extract_trait(pdf, pages, mode="decimal"):
    combined = defaultdict(dict)   # strain_norm -> {(city,state): value}
    meancol, disp = {}, {}
    for i in pages:
        res, has_mean = parse_page(pdf, i, mode)
        if not res:
            continue
        for strain, (cols, rowvals, hm) in res.items():
            k = norm(strain)
            if not k:
                continue
            disp.setdefault(k, strain)
            for ci, v in rowvals.items():
                city, st, _ = cols[ci]
                if city == "Mean":
                    meancol.setdefault(k, v)
                else:
                    combined[k][(city, st)] = v
    return combined, meancol, disp

def main():
    year, code = int(sys.argv[1]), sys.argv[2]
    write = sys.argv[sys.argv.index("--write") + 1] if "--write" in sys.argv else None
    traits = SECTION_PAGES[(year, code)]
    mg = re.sub(r"^(UT|PT)-", "", code)
    path = O._corrected_pdf(year)
    allrows = []
    with pdfplumber.open(path) as pdf:
        per_trait = {t: extract_trait(pdf, p, "signed" if t == "Maturity" else "decimal")
                     for t, (u, p) in traits.items()}
        # ROSTER: the clean strain set = strains seen in >=2 traits (drops footer junk that appears once)
        from collections import Counter
        seen = Counter(k for combined, _, _ in per_trait.values() for k in combined)
        roster = {k for k, n in seen.items() if n >= 2}
        for trait, (units, pages) in traits.items():
            combined, meancol, disp = per_trait[trait]
            ok = tot = 0
            for k, locs in combined.items():
                if k not in roster:
                    continue
                vals = list(locs.values())
                rm = round(sum(vals) / len(vals), 1) if vals else None
                mc = meancol.get(k)
                good = mc is not None and rm is not None and abs(rm - mc) <= (2.0 if trait == "YieldBuA" else 1.0)
                tot += 1; ok += good
                for (city, st), v in locs.items():
                    allrows.append((year, "UT", mg, code, disp[k], city, st, trait, v, units,
                                    "PDFdropUT_115", round(mc, 1) if mc else None, "OK" if good else "x"))
            nloc = len(set(l for s, lv in combined.items() if s in roster for l in lv))
            print(f"  {trait:12} {tot:2} strains x {nloc:2} locs; reconcile {ok}/{tot}")
    df = pd.DataFrame(allrows, columns=["Year", "TestType", "TestMG", "Test", "Strain", "City", "State",
                                        "Phenotype", "Value_num", "Units", "Source", "MeanCol", "reconcile"])
    print(f"roster (strains in >=2 traits): {len(roster)}")
    if write:
        df.to_csv(write, index=False)
        print(f"wrote {len(df)} rows -> {write}")
    return df

if __name__ == "__main__":
    main()
