"""
112_extract_pdf_perloc.py
=========================
Local pdfplumber per-location extractor for the 1970s-80s "UNIFORM TEST X, YYYY"
Red-PDF format (NO API). Completes the gap campaign for the PDF-ONLY sections the Green
Sojabone XLSX never digitized:
  * 1977 UT-IV (whole section, absent from Green),
  * 1972 UT-III (no Green file at all),
and provides an independent PDF ground-truth to ARBITRATE the scattered 1977 UT-00..III
Green-vs-corpus diffs.

Per section, each trait is a per-location table captioned like "N Tests 1977 YIELD (bu/a)",
"MATURITY (relative data)", "PLANT HEIGHT (inches)", ... spanning 1-2 pages (page-1 carries
a Mean column + the main locations; page-2 the Iowa/ND/SD/Neb locations, no Mean). Data rows
WRAP (a strain's values land on the baseline just above its name) and carry OCR noise
("16.,4"); we band-merge numeric words within +/-7px of the strain baseline and assign them
to columns by x-coordinate clustering, mapping columns to locations reconstructed from the
multi-line header. Multi-year "X-YEAR MEAN" tables are skipped. Maturity is reconstructed to
DOY from the anchor (dated) row + per-strain offsets (DOY window 200-330), matching 109.

STATUS (2026-06-30): FIRST-PAGE proven across traits; SECOND-PAGE is the remaining blocker.
  WORKS (0-diff vs the proven Green, 1977 UT-0): wrapped-row x-coord extraction, table bounding,
  OCR cleanup, page-level shared header (fixes STACKED multi-trait pages), split-caption units
  (SEED SIZE / (g/100)), footer-row + state-word exclusion. YieldBuA/Height/Protein/SeedQuality
  extract EXACTLY at full coverage on the main (page-1) locations.
  VALUE->STRAIN ASSIGNMENT (2026-06-30): wrapped values sit on the strain baseline or just ABOVE it,
  so each value is assigned to the nearest strain baseline at/below it (window [t-2, t+10]) — robust
  on DENSE pages where a symmetric band grabbed an adjacent row. Coverage ~doubled; UT-0 = 2 diffs,
  UT-I/UT-II ~96% (780/1080 merged, ~50 diffs).
  REMAINING BLOCKER: the diffs concentrate in the FIRST ~4 strains of a dense page (the wrap line
  above the top strain is the caption, not a previous data row -> top-row wrap edge case). Until that
  is 100%, recovery would inject ~4% wrong cells, so it is NOT yet wired into the corpus.
  TODO: top-of-page wrap handling; Oil caption (PROTEIN+OIL share a page); maturity-DOY parity; THEN
  integration (1977 UT-IV, 1972 UT-III, PDF-arbitrate the 1977 UT-00..III diffs).

Library: extract_pdf_section(year, code) -> DataFrame {Year,TestType,TestMG,Test,Strain,
City,State,Phenotype,Value_num,Units,Source="PDF"}.
"""
import sys
import re
import datetime as dt
from collections import defaultdict
from pathlib import Path
import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")

# Per-location caption TRAIT -> (Phenotype, Units). Units in the caption are REQUIRED so the
# Regional Summary column-header row ("Strain Yield Rank ... Protein Oil", no inline units) is
# NOT mistaken for a per-location table.
TRAIT_CAP = [
    (r"YIELD\s*\(BU", "YieldBuA", "bu/a"),
    (r"MATURITY\s*\((REL|DAT)", "Maturity", "date"),
    (r"HEIGHT\s*\(IN", "Height", "inches"),
    (r"LODGING\s*\(SC", "Lodging", "score"),
    (r"SEED\s*QUALITY\s*\(SC", "SeedQuality", "score"),
    (r"SEED\s*SIZE\s*\(G", "SeedSize", "g/100"),
    (r"PROTEIN\s*\(%", "Protein", "%"),
    (r"OIL\s*\(%", "Oil", "%"),
]
STATE_HINTS = {"ONT": "ONT", "ONTARIO": "ONT", "MICH": "MI", "MICHIGAN": "MI", "WIS": "WI",
               "WISCONSIN": "WI", "MINN": "MN", "MINNESOTA": "MN", "IND": "IN", "INDIANA": "IN",
               "ILL": "IL", "ILLINOIS": "IL", "IOWA": "IA", "OHIO": "OH", "NEB": "NE",
               "NEBRASKA": "NE", "ND": "ND", "SD": "SD", "NJ": "NJ", "MO": "MO", "KANSAS": "KS",
               "KAN": "KS", "DEL": "DE", "VA": "VA", "MD": "MD"}


def cx(w):
    return (w["x0"] + w["x1"]) / 2.0


def clean_num(t):
    t = t.strip("^•*+ ").replace(",", ".")
    t = re.sub(r"\.\.+", ".", t).strip(".")
    if not t:
        return None
    m = re.match(r"^[+\-]?\d+(\.\d+)?$", t)
    return float(t) if m else None


def cell_doy(t, year):
    """Date cell -> DOY. `year` is REQUIRED and must be the real report year.

    This previously converted through a fixed reference year (1977, non-leap), which made
    every date from Mar 1 on 1 day early in a leap year. `year` is deliberately positional
    and required so that a missed call site raises instead of silently mis-converting.
    """
    s = str(t).strip()
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})$", s)
    if not m:
        return None
    mo, dy = int(m.group(1)), int(m.group(2))
    try:
        d = dt.date(int(year), mo, dy).timetuple().tm_yday
        return d if 200 <= d <= 330 else None
    except ValueError:
        return None


def norm(s):
    s = re.sub(r"\s*\([^)]*\)", "", str(s))
    s = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return s.replace("O", "0").replace("L", "1").replace("I", "1")


# --------------------------------------------------------------------------- section / page map
def section_pages(pdf, year, code):
    """Page indices belonging to the 'UNIFORM TEST <mg>, <year>' section (until the next
    UNIFORM (PRELIMINARY) TEST header)."""
    mg = re.sub(r"^(UT|PT)-", "", code)
    pref = "PRELIMINARY " if code.startswith("PT") else ""
    hdr = re.compile(rf"uniform {pref}test\s+{re.escape(mg)}\b[, ]\s*{year}", re.I)
    anyhdr = re.compile(r"uniform (preliminary )?test\s+(0{1,2}|[ivx]+)\b", re.I)
    # The section is the CONTIGUOUS run from its first header page until the next DIFFERENT-section
    # header. We must NOT re-enter on a later page that repeats this section's header (those are
    # multi-year summaries placed inside a later section's page range, whose shared check varieties
    # would otherwise overwrite the real single-year values).
    pages, state = [], "before"
    for i, pg in enumerate(pdf.pages):
        t = re.sub(r"\s+", " ", (pg.extract_text() or ""))
        is_self = bool(hdr.search(t))
        m = anyhdr.search(t)
        is_other = bool(m) and m.group(2).upper() != mg.upper() and not is_self
        if state == "before":
            if is_self:
                state = "inside"
                pages.append(i)
        elif state == "inside":
            if is_other:
                state = "after"
            else:
                pages.append(i)
    return pages


# --------------------------------------------------------------------------- one table on a page
def _captions(page):
    """(targets, boundaries). targets = [(top, Phenotype, Units)] single-year per-location trait
    tables. boundaries = sorted tops of ANY caption/header row (trait / RANK / MEAN / N Tests /
    year-range) used to bound each table from below (so a table never swallows the rank or the
    multi-year-mean sub-table that follows it on the same page)."""
    W = page.extract_words(use_text_flow=False)
    lines = defaultdict(list)
    for w in W:
        lines[round(w["top"])].append(w)
    tops = sorted(lines)

    def ltext(top):
        return " ".join(x["text"] for x in sorted(lines[top], key=lambda w: w["x0"])).upper()

    targets, boundaries = [], []
    for top in tops:
        txt = ltext(top)
        if re.search(r"RANK|MEAN|\bTESTS?\b|19\d\d\s*-|YEAR|YIELD|MATURITY|HEIGHT|"
                     r"LODGING|SEED|PROTEIN|OIL", txt):
            boundaries.append(top)
        if "RANK" in txt or "YEAR" in txt or "MEAN" in txt or re.search(r"19\d\d\s*-", txt):
            continue
        # split captions put the units on an adjacent line ("SEED SIZE" / "(g/100)") -> check a
        # small vertical window for the unit pattern.
        win = " ".join(ltext(t) for t in tops if abs(t - top) <= 4)
        for pat, ph, un in TRAIT_CAP:
            if re.search(pat, win) and re.search(pat.split("\\s*")[0], txt):
                targets.append((top, ph, un))
                break
    return targets, sorted(set(boundaries))


_STATE_EXACT = dict(STATE_HINTS, **{
    "WISCONS": "WI", "WISCON": "WI", "ONTARI": "ONT", "MINNESOT": "MN", "MICHIGA": "MI",
    "NEBR": "NE", "ILLINOI": "IL", "INDIAN": "IN", "MISS": "MO", "KANSA": "KS"})


def _state_of(text):
    """Exact state-name/abbrev/OCR-fragment match ONLY (no loose prefixing, so cities like
    Morris/Mead are never mistaken for a state)."""
    key = re.sub(r"[^A-Za-z]", "", text).upper()
    return _STATE_EXACT.get(key, "")


# Reference roster for OCR-fragment repair: {STATE: {alpha_normkey: canonical_city}} from the
# geocoded NUST site list. The stacked multi-line headers OCR-merge adjacent columns' first
# syllables into one wide token, so a column can be left with only its tail ("phia" for Adelphia,
# "ville" for Landisville). After the column's syllables are stitched, if the (still-partial)
# string uniquely matches a ref city for the column's (reliably-read) state, we adopt the
# canonical spelling. Conservative: exact key wins; otherwise a UNIQUE substring match either
# direction; else keep the assembled string (never worse than before).
_REF_ROSTER = None


def _ref_roster():
    global _REF_ROSTER
    if _REF_ROSTER is None:
        _REF_ROSTER = defaultdict(dict)
        try:
            ref = pd.read_csv(REPO / "reference" / "nust_locations_ref.csv")
            for c, s in zip(ref["City"].astype(str), ref["State"].astype(str)):
                st, key = s.strip().upper(), re.sub(r"[^a-z]", "", c.lower())
                if st and key:
                    _REF_ROSTER[st][key] = c.strip()
        except Exception:
            pass
    return _REF_ROSTER


def _match_roster(a, roster):
    """Best canonical for normalized-key `a` within one roster dict: exact key, else a UNIQUE
    substring match either direction (soil sub-plots Portageville/-Clay/-Loam collapse to the
    shortest base). Returns None if nothing unambiguous."""
    if a in roster:
        return roster[a]
    hits = sorted({canon for key, canon in roster.items() if a in key or key in a}, key=len)
    if not hits:
        return None
    base = re.sub(r"[^a-z]", "", hits[0].lower())
    if len(hits) == 1 or all(base in re.sub(r"[^a-z]", "", h.lower()) for h in hits):
        return hits[0]
    return None


def _repair_city(assembled, state):
    """Return (canonical_city, canonical_state). The ref roster repairs OCR-fragment city names AND
    corrects the geometry-guessed state: the stacked headers put a KS site (Manhattan) physically
    under the Neb. header etc., so a city that resolves to a UNIQUE ref (city, state) adopts that
    authoritative state. Same-name-different-state cities (Arlington WI/SD) keep the parser's state
    to disambiguate; unknown cities keep the assembled name + parser state (never worse than before)."""
    a = re.sub(r"[^a-z]", "", str(assembled).lower())
    if len(a) < 3:
        return assembled, state
    # 1) the parser's own state gives a confident ref match -> trust it (disambiguates same-name sites)
    if state:
        hit = _match_roster(a, _ref_roster().get(state.upper(), {}))
        if hit:
            return hit, state
    # 2) resolve against the whole roster; if it names ONE city, adopt its ref state when unique.
    if len(a) >= 4:
        matches = [(st, hit) for st, r in _ref_roster().items()
                   if (hit := _match_roster(a, r))]
        canons = {re.sub(r"[^a-z]", "", c.lower()) for _, c in matches}
        if matches and len(canons) == 1:
            states = {st for st, _ in matches}
            return min((c for _, c in matches), key=len), (states.pop() if len(states) == 1 else state)
    return assembled, state


def _in_ref(city, state):
    a = re.sub(r"[^a-z]", "", str(city).lower())
    return bool(a) and a in _ref_roster().get(str(state).upper(), {})


def _clean_city(city):
    """A 'clean' single-location name: one Capitalized token (Adelphia, Quantico), or a
    directional/abbrev two-word name (East Lansing, Mt.Vernon, Elk Point). REJECTS CamelCase
    run-on merges of several cities' syllables (EdinaColumbia, ColHoytBluffvilleumbuston)."""
    if re.search(r"\d", city):
        return False
    segs = re.findall(r"[A-Z][a-z]+", city)
    if len(segs) <= 1:
        return len(re.sub(r"[^A-Za-z]", "", city)) >= 3
    if len(segs) == 2 and re.match(r"^(Mt|St|Ft|New|East|West|North|South|Elk|[ENSW])\.?\s*[A-Z]",
                                   city):
        return True
    return False


def _page_header(page):
    """(hdr_words, state_top): the location-header band shared by ALL tables on the page —
    the lines between the 'UNIFORM TEST X' title and the first trait caption. Restricted to the
    data-column region (x>195) to drop left-margin OCR junk."""
    W = page.extract_words(use_text_flow=False)
    title_top = max((w["top"] for w in W if re.search(r"UNIFORM", w["text"], re.I)
                     and w["top"] < 110), default=70)
    caps, _ = _captions(page)
    if not caps:
        return [], 0
    first = min(c[0] for c in caps)
    hdr = [w for w in W if title_top + 6 < w["top"] < first - 2 and cx(w) > 195]
    state_top = min((w["top"] for w in hdr), default=first)
    return hdr, state_top


def _parse_region(page, top0, top1, hdr, state_top):
    """{strain: {(City,State): value}} for the table band (top0,top1). Data columns by x-cluster;
    each column's location is stitched from the shared page header `hdr` (anchored on the column
    x-center, skipping the top state line — which avoids state-name bleed)."""
    W = page.extract_words(use_text_flow=False)
    nums = [w for w in W if re.match(r"^[+\-^]?\d[\d.,]*$", w["text"]) and top0 < w["top"] < top1]
    if len(nums) < 4:
        return {}
    xs = sorted(cx(w) for w in nums)
    cols = []
    for x in xs:
        if cols and x - cols[-1][-1] < 12:
            cols[-1].append(x)
        else:
            cols.append([x])
    centers = [sum(c) / len(c) for c in cols]
    # A city syllable is assigned to its NEAREST data column, but only within a cap (~half the
    # column spacing) so a header word with no detected data column (sparse trait table) is DROPPED
    # rather than piled onto an edge column. An OCR-merged first-syllable RUN spanning >1 column
    # ("Landis-Adel-Clarks-Queens-Quan") is split on hyphens/space and its parts distributed across
    # its own x-extent, so each column recovers its own first syllable before stitching.
    gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    med_gap = sorted(gaps)[len(gaps) // 2] if gaps else 40.0
    cap = min(18.0, 0.5 * med_gap)

    def assign(x):
        ci = min(range(len(centers)), key=lambda i: abs(centers[i] - x))
        return ci if abs(centers[ci] - x) <= cap else None

    state_words = [(cx(w), _state_of(w["text"])) for w in hdr
                   if _state_of(w["text"]) and w["top"] <= state_top + 6]
    HSPLIT = r"[­‐-—\s\-]+"              # any dash/soft-hyphen/space
    HSTRIP = r"[­‐-—:\-]+$"              # trailing dash/colon
    NOISE = re.compile(r"^[(\[]?[A-Za-z][)\]]?$|^[•■*.]+$")   # single letters, (A)/(B), bullets
    lo_x, hi_x = centers[0] - cap, centers[-1] + cap
    syll = []                                          # (col_index, top, x, text)
    for w in hdr:
        if w["top"] <= state_top + 4:                  # top line = states / region labels (Central)
            continue
        parts = [p for p in re.split(HSPLIT, w["text"]) if p]
        if w["x1"] > w["x0"] + 1 and len(parts) >= 2 and (w["x1"] - w["x0"]) > 1.4 * med_gap:
            span = w["x1"] - w["x0"]                    # merged multi-column run -> distribute parts
            items = [(w["x0"] + (k + 0.5) / len(parts) * span, p) for k, p in enumerate(parts)]
        else:
            items = [(cx(w), w["text"])]
        for x, t in items:
            ci = assign(x)
            if ci is not None:
                syll.append((ci, w["top"], x, t))
    locs = {}
    for ci in range(len(centers)):
        toks = sorted((top, x, t) for c2, top, x, t in syll if c2 == ci)
        parts = [re.sub(HSTRIP, "", t) for _, _, t in toks if not NOISE.match(t)]
        city = re.sub(r"\s+", "", "".join(parts)).strip(" .,")
        st = min(state_words, key=lambda sw: abs(sw[0] - centers[ci]))[1] if state_words else ""
        locs[ci] = _repair_city(city, st)
    # SAFETY NET: keep a column only if its city is authoritative (in the ref roster for its state)
    # or unambiguously clean (a single capitalized token, or a directional/abbrev two-word name).
    # This drops any residual OCR fragment ("phia", "town"), digit/mean/rank bleed, and CamelCase
    # run-on merges ("EdinaColumbia", "ColHoytBluff...") — never fabricating a wrong location.
    keep = [i for i in range(len(centers))
            if locs[i][0] and len(locs[i][0]) >= 3
            and not re.search(r"mean|strain|average|rank|year|\d", locs[i][0], re.I)
            and (_in_ref(locs[i][0], locs[i][1]) or _clean_city(locs[i][0]))]
    # strain rows: leftmost alpha token, excluding footer/stat rows.
    FOOTER = re.compile(r"^(C\.?V|L\.?S\.?D|Row|Rep|Coef|Mean|Grand|Range|Bu|No\.|Days|us|sp|"
                        r"vsr|sar|VT|SrfSf|urar|oar)", re.I)
    strain_tops = sorted((w["top"], w["text"]) for w in W
                         if top0 < w["top"] < top1 and re.match(r"^[A-Za-z$]", w["text"])
                         and cx(w) < 150 and not FOOTER.match(w["text"]))
    if not strain_tops or not keep:
        return {}
    # Assign each value word to its OWNING strain: wrapped values sit on the strain's baseline or
    # just ABOVE it, so the owner is the nearest strain baseline at/below the value (T in [t-2, t+10]).
    # This is robust on DENSE pages where a symmetric band would grab an adjacent row's value.
    # Route each value to its geometrically NEAREST column among ALL columns (independent of the
    # city-label quality), then emit only if that column survived the keep filter. Routing must not
    # depend on `keep`, or dropping a junk-labelled column would misroute ITS values onto a real
    # neighbour and corrupt it; here a junk column's values are simply dropped with the column.
    keep_set = set(keep)
    out = defaultdict(dict)
    for w in W:
        t = w["top"]
        if not (top0 < t < top1 and cx(w) > 150 and re.match(r"^[+\-^]?\d", w["text"])):
            continue
        owner = next((nm for T, nm in strain_tops if t - 2 <= T <= t + 10), None)
        if owner is None:
            continue
        ci = min(range(len(centers)), key=lambda i: abs(centers[i] - cx(w)))
        if ci in keep_set and abs(centers[ci] - cx(w)) < 13:
            out[owner].setdefault(locs[ci], w)
    return {s: dict(d) for s, d in out.items()}


def extract_pdf_section(year, code):
    """Per-location long rows for (year, code) from the Red PDF."""
    tt = "PT" if code.startswith("PT") else "UT"
    mg = re.sub(r"^(UT|PT)-", "", code)
    pdf_path = REPO / "input_files" / f"input_{year}" / f"{year}_done.pdf"
    per = defaultdict(lambda: defaultdict(dict))   # trait -> strain -> {(city,state): word}
    with pdfplumber.open(pdf_path) as pdf:
        pages = section_pages(pdf, year, code)
        for i in pages:
            pg = pdf.pages[i]
            caps, bounds = _captions(pg)
            hdr, state_top = _page_header(pg)
            for top, ph, un in caps:
                nxt = [b for b in bounds if b > top + 2]
                top1 = (nxt[0] - 4) if nxt else 9999
                region = _parse_region(pg, top + 4, top1, hdr, state_top)
                for strain, cells in region.items():
                    for loc, w in cells.items():
                        # keep the FIRST value seen for a cell: single-year tables precede the
                        # multi-year-mean tables (lower page numbers), so first == single-year.
                        per[ph][strain].setdefault(loc, w["text"])
    rows = []
    for ph, strains in per.items():
        if ph == "Maturity":
            for strain, cells in strains.items():
                anchor = {loc: cell_doy(t, year) for loc, t in cells.items()
                          if cell_doy(t, year) is not None}
            # anchor row = the strain with the most date-like cells
            anchor_by_loc = {}
            for strain, cells in strains.items():
                ds = {loc: cell_doy(t, year) for loc, t in cells.items()
                      if cell_doy(t, year) is not None}
                if len(ds) > len(anchor_by_loc):
                    anchor_by_loc = ds
            for strain, cells in strains.items():
                for loc, t in cells.items():
                    d = cell_doy(t, year)
                    if d is None:
                        off = clean_num(t)
                        if off is None or loc not in anchor_by_loc:
                            continue
                        d = int(anchor_by_loc[loc] + off)
                    rows.append((strain, loc[0], loc[1], "Maturity", float(d), "date"))
        else:
            un = next(u for p, _, u in [(pat, ph2, un2) for pat, ph2, un2 in TRAIT_CAP] if _ == ph) \
                if False else dict((p, u) for _, p, u in TRAIT_CAP)[ph]
            for strain, cells in strains.items():
                for loc, t in cells.items():
                    v = clean_num(t)
                    if v is not None:
                        rows.append((strain, loc[0], loc[1], ph, round(v, 2), un))
    df = pd.DataFrame(rows, columns=["Strain", "City", "State", "Phenotype", "Value_num", "Units"])
    if len(df):
        df.insert(0, "Year", year)
        df.insert(1, "TestType", tt)
        df.insert(2, "TestMG", mg)
        df.insert(3, "Test", code)
        df["Source"] = "PDF"
    return df


def main():
    year, code = int(sys.argv[1]), sys.argv[2]
    df = extract_pdf_section(year, code)
    print(f"{year} {code}: {len(df)} rows")
    if len(df):
        print(df.groupby("Phenotype").agg(n=("Value_num", "size"), locs=("City", "nunique")).to_string())


if __name__ == "__main__":
    main()
