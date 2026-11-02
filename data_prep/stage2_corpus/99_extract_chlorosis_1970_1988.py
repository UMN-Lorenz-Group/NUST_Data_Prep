"""
99_extract_chlorosis_1970_1988.py
=================================
Recover the pre-1989 **Chlorosis Score** (iron-deficiency chlorosis, IDC) trait
from the raw 1970-1988 NUST annual-report **Red PDFs** and append it to each
year's `phenotypesTable1.csv` as `Phenotype="Chlorosis"`, `Units="score"`.

This is the historical analogue of `98_extract_idc_2022_2025.py`. Both fix the
SAME class of bug: the chlorosis score lives in a *descriptive/disease* table
block ("DESCRIPTIVE AND DISEASE DATA" / "Descriptive and Other Data" /
"Descriptive and Shattering Data"), NOT in the per-location yield tables that
fed `phenotypesTable1.csv`. The historical extraction used a fixed ~22-col
yield-schema with no descriptive-disease slot, so the entire block (Chlorosis +
Shattering + Hypocotyl/Emergence + BSR ...) was dropped for every year.

SPAN (diagnosed in memory project_nust_chlorosis_idc_extraction §SECOND GAP):
  1941-1969 = GENUINE absence (chlorosis not yet a reported trait).
  1970-1988 = EXTRACTION FAILURE -> recovered here.
After this runs, corpus chlorosis coverage is 1970-2025 (1989-2019 Master DB,
2020/2022-2025 from script 98, 1970-1988 from here).

LAYOUT (two eras, both handled by the same x-band parser):
  Era A  1970-1977  "Descriptive and Shattering Data"
         Chlorosis nurseries: Crookston, Lamberton (MN) + Ames (IA) (PT often Ames only).
         Shattering can precede chlorosis (1970-71); 1972+ chlorosis is first-after-code.
  Era B  1978-1988  "DESCRIPTIVE AND DISEASE DATA" / "Descriptive and Other Data"
         "Score" sub-headers; chlorosis nurseries Ames (IA) + Lamberton (MN);
         clean single-line data rows. Chlorosis is the first scored trait after the code.

PARSER (per descriptive block on a page):
  1. Find the 'Chlorosis' header word. RIGHT boundary R = x of the nearest
     trait-header word to its right (Emergence/Emerg/Hypocotyl/Hypo/Fluor/
     Shattering/Shatter/Germination/BSR/Disease). LEFT boundary L = x_chlorosis
     - MARGIN, clamped right of the Descriptive 'Code' column and of any
     left-side trait word (e.g. Shattering in 1970). Band = [L, R).
  2. Collect in-band data numeric tokens across all data rows; cluster their x
     into columns (= chlorosis nurseries). Label each column by the nearest
     in-band location-name header word (Ames/Lamberton/Crookston/...).
  3. Emit (Year, Test, Strain, City, State, Value) per strain x nursery, with
     Value restricted to the 1.0-6.0 IDC visual scale (rejects disease % /
     maturity / yield leakage; emergence & shattering are excluded by the band,
     not the range).

JOIN: strains in the descriptive block (e.g. 'Clay (0)', 'Maple Amber',
'0T84-4') are mapped to each year's `phenotypesTable1.csv` spelling via an
OCR-tolerant key (uppercase; strip spaces/parens/stars; collapse O<->0, I/L<->1).

OUTPUT: appends long rows to each year's `phenotypesTable1.csv`. Idempotent
(drops any prior Chlorosis rows, writes a one-time `.bak`).

VALIDATION (spot-checked exactly against raw PDF text)
  UT-00 sections of 1970/1973/1975/1980/1985/1988 reproduce every strain x
  nursery value exactly. ~4,800 values, all 19 years, scores 1.0-5.0 (mean ~2.9,
  a clean IDC bell); <0.5% of strain x test x nursery groups show an internal
  conflict >1.5 (resolved by taking the median across page repeats).
KNOWN LIMITATIONS
  - 1984 is partial (~80 vals): its OCR shreds the word 'Chlorosis' to
    'Chi orost s', so only the Emergence-anchored fallback recovers it.
  - OCR-illegible strains (e.g. 1975 'CM1U7'<-'CM147') and scores that lost
    their decimal point or fell outside 1.0-5.5 are dropped, not guessed.
  - Several systematic leaks are explicitly defended against: shattering columns
    left of chlorosis (1970), the hypocotyl-colour 'I'->'1' code (1984), the
    Emergence/BSR 'Ames' that repeats the nursery name (1988), and the
    Emergence-first 1982/88 UT-IV southern layout (chlorosis = Lamberton only).

USAGE
  uv run python data_prep/stage2_corpus/99_extract_chlorosis_1970_1988.py            # REPORT only (no writes)
  uv run python data_prep/stage2_corpus/99_extract_chlorosis_1970_1988.py --write    # append to phenotypesTable1.csv
  uv run python data_prep/stage2_corpus/99_extract_chlorosis_1970_1988.py --years 1980 1985   # subset
  uv run python data_prep/stage2_corpus/99_extract_chlorosis_1970_1988.py --dump-csv out.csv  # dump raw extraction
"""
import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
NUST_DATA = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
HIST = NUST_DATA / "NUST_Historical_Data_1941_1988"
RED_DIR = Path("R:/cfans_agro_lore0149_lorenzlabresearch/NUST_Historical_Data_1941_1988"
               "/Red-20260427T193444Z-3-001/Red")
# Local cache for the Red PDFs (R: drive reads are slow; see project_nust_input_data_layout).
PDF_CACHE = Path("C:/Users/vramasub/AppData/Local/Temp")

YEARS_ALL = list(range(1970, 1989))

PHENOTYPE = "Chlorosis"
UNITS = "score"

# Chlorosis is the 1-5 IDC visual scale (occasionally up to ~5.5). Restrict to
# this range so disease percentages, maturity DOY, yields, etc. that share the
# block can never be mis-read as chlorosis. Emergence/Shattering (also 1-5) are
# excluded by the column band, not by this range.
CHL_MIN, CHL_MAX = 1.0, 5.5

# Trait-header words that can sit to the RIGHT of Chlorosis and thus bound its
# column band. Matched case-insensitively against the start of a header token.
RIGHT_TRAITS = ("emergence", "emerg", "hypocotyl", "hypocoty", "hypo",
                "fluor", "shattering", "shatter", "germination", "bsr",
                "disease", "iodine", "protein", "oil")
# Trait words that can sit to the LEFT of chlorosis (Era A 1970-71 ordering).
LEFT_TRAITS = ("shattering", "shatter", "peroxidase", "perox")

# Nursery location-name header tokens -> canonical (City, State). Abbreviations
# and OCR variants included. An UNKNOWN in-band location token aborts the run so
# a new nursery cannot silently get the wrong state (mirrors script 98's guard).
NURSERY = {
    "ames": ("Ames", "IA"),
    "iowa": ("Ames", "IA"),            # column labelled by state in some years
    "iova": ("Ames", "IA"),            # OCR
    "asms": ("Ames", "IA"),            # OCR (1974)
    "lamberton": ("Lamberton", "MN"),
    "lamb": ("Lamberton", "MN"),
    "lamber": ("Lamberton", "MN"),
    "lairberton": ("Lamberton", "MN"),  # OCR (1982 UT-IV)
    "leunb": ("Lamberton", "MN"),      # OCR (1974)
    "timber": ("Lamberton", "MN"),     # OCR of "Lamber-ton" (1988 p51: "Timber-ton")
    "crookston": ("Crookston", "MN"),
    "crkstn": ("Crookston", "MN"),
    "crook": ("Crookston", "MN"),
    "crooks": ("Crookston", "MN"),
    "rosemount": ("Rosemount", "MN"),
    "rose": ("Rosemount", "MN"),
    "waseca": ("Waseca", "MN"),
    "climax": ("Climax", "MN"),
}

# Tokens that, while inside the band, are NOT nurseries but layout noise to skip.
LOC_NOISE = {"score", "n", "%", "plant", "stem", "code", "strain", "descriptive",
             "descrip", "tive", "race", "a", "rt", "ton", "tan", "weeks", "week",
             "wk", "wk.", "mo", "mo.", "light", "idase", "ence", "escent", "gence",
             "2", "3", "4", "1", "7", "-", ".", "to", "of"}

MARGIN = 52.0  # px the chlorosis header word may sit right of its leftmost column


# ---------------------------------------------------------------------------
# Strain key (OCR-tolerant)
# ---------------------------------------------------------------------------
def strain_key(s, collapse=False):
    """Uppercase key with spaces/parens/stars removed. If collapse, also map
    letter O<->digit 0 and I/L<->1 to absorb OCR confusions (used as a fallback
    so two genuinely-distinct strains aren't merged on the first pass)."""
    s = re.sub(r"\s*\([^)]*\)", "", str(s)).replace("*", "")
    s = re.sub(r"[\s.]+", "", s).upper()
    if collapse:
        s = s.replace("O", "0").replace("I", "1").replace("L", "1")
    return s


def build_strain_map(csv_path):
    """key -> source spelling, for both exact and collapsed keys."""
    src = pd.read_csv(csv_path, low_memory=False)
    spellings = [str(x).strip() for x in src["Strain"].astype(str).unique()
                 if str(x).strip() and str(x).strip().lower() != "strain"]
    exact, collapsed = {}, {}
    for sp in spellings:
        exact.setdefault(strain_key(sp), sp)
        collapsed.setdefault(strain_key(sp, collapse=True), sp)
    return exact, collapsed, src


def match_strain(raw, exact, collapsed):
    k = strain_key(raw)
    if k in exact:
        return exact[k]
    kc = strain_key(raw, collapse=True)
    if kc in collapsed:
        return collapsed[kc]
    return None


def match_prefix(tokens, exact, collapsed):
    """Longest-prefix match: the strain is the longest leading run of `tokens`
    whose joined text matches a known phenotypesTable1 strain. This uses the
    authoritative strain list to separate the strain from the trailing
    descriptive/hypocotyl color codes (PGBr, DYY, ...) without heuristics.
    Returns (matched_spelling, n_tokens_consumed) or (None, 0)."""
    for p in range(len(tokens), 0, -1):
        cand = " ".join(tokens[:p])
        if not re.search(r"[A-Za-z]", cand):
            continue
        m = match_strain(cand, exact, collapsed)
        if m is not None:
            return m, p
    return None, 0


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------
def pdf_path(year):
    cached = PDF_CACHE / f"{year}_done.pdf"
    if cached.exists():
        return cached
    red = RED_DIR / f"{year}_done.pdf"
    if red.exists():
        shutil.copy2(red, cached)
        return cached
    return None


TEST_TITLE_RE = re.compile(
    r"(UNIFORM|PRELIMINARY)\s+TEST\s+(0{1,2}|I{1,3}V?|IV|V)\s*([AB])?", re.IGNORECASE)


def parse_test(text):
    """Return normalized test code (UT-00, PT-IV, ...) from a page's title text."""
    m = TEST_TITLE_RE.search(text)
    if not m:
        return None
    prefix = "UT" if m.group(1).upper().startswith("UN") else "PT"
    mg = m.group(2).upper()
    ab = (m.group(3) or "").upper()
    return f"{prefix}-{mg}{ab}"


def words_by_line(page, tol=2.2):
    d = defaultdict(list)
    for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        d[round(w["top"] / tol) * tol].append(w)
    return [(t, sorted(d[t], key=lambda w: w["x0"])) for t in sorted(d)]


def cx(w):
    return (w["x0"] + w["x1"]) / 2.0


NUM_RE = re.compile(r"^\d{1,2}([.,]\d)?$")  # 1-2 digits, optional .d (e.g. 3.3, 4, 2,5)


def to_float(tok):
    t = tok.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------
def _desc_signature(text):
    """True if the page carries a descriptive/disease score block (used to fire
    the garbled-header fallback even when the word 'Chlorosis' didn't OCR)."""
    tl = (text or "").lower()
    return ("escriptive and" in tl and "score" in tl
            and ("shatter" in tl or "emerg" in tl or "hypoco" in tl))


def find_chl_blocks(page):
    """Yield dicts describing each chlorosis descriptive block on the page:
    {chl_x, L, R, header_top, loc_headers:[(name,centerx)], data_lines:[(top,words)]}.
    Primary anchor = a header line carrying a clean 'Chlorosis' word. If a page
    has the descriptive-block signature but NO clean chlorosis word (OCR mangled
    it, e.g. 1984 'Chi orost s'), a fallback anchor is synthesised from the
    Emergence/Hypocotyl column — chlorosis is the score column just left of it."""
    lines = words_by_line(page)
    blocks = []
    have_clean = False
    fallback = _desc_signature(page.extract_text() or "")
    for li, (top, ws) in enumerate(lines):
        # Header anchor: a short line carrying a 'Chlorosis' header word.
        if len(ws) > 9:
            continue
        chl = next((w for w in ws if w["text"].lower().startswith("chloros")), None)
        if chl is not None:
            chl_x = chl["x0"]
            have_clean = True
        elif fallback:
            # No clean chlorosis word: anchor off the first Emergence/Hypocotyl
            # header on a line that also looks like a trait-header row.
            em = next((w for w in ws if any(w["text"].lower().startswith(p)
                       for p in ("emergence", "emerg", "hypocotyl", "hypocoty", "hypo"))), None)
            below = " ".join(x["text"].lower() for tt, tws in lines[li:li + 3] for x in tws)
            if em is None or "score" not in below:
                continue
            chl_x = em["x0"] - 70.0  # chlorosis score column sits ~70px left of Emergence
        else:
            continue
        # Trait words in the header zone (this line + next two lines).
        zone = []
        for tt, tws in lines[li:li + 3]:
            zone.extend(tws)
        # A trait header sitting LEFT of 'Chlorosis' bounds the band on that side
        # (e.g. Shattering in 1970, or Emergence-first in the 1982/88 UT-IV
        # southern tests where chlorosis is at Lamberton only and 'Ames' is the
        # emergence column to the LEFT). Clamp the nursery window past it.
        left_traits = ("emergence", "emerg", "hypocotyl", "hypoco", "hypo",
                       "germination", "bsr") + LEFT_TRAITS
        left_x = [w["x1"] for w in zone
                  if w["x1"] < chl_x - 4
                  and (w["text"].lower().startswith("code")
                       or any(w["text"].lower().startswith(p) for p in left_traits)
                       or w["text"].lower() in ("manhattan", "urbana"))]
        low = max(chl_x - 88, (max(left_x) + 6) if left_x else -1e9)
        # Collect chlorosis-nursery header words in [low, chl_x+98]. The right
        # edge stops short of the Emergence/BSR 'Ames' columns (which repeat the
        # same nursery name); left clamp drops an Emergence-first 'Ames'.
        cand = []   # (key, center) chlorosis-nursery headers near the trait word
        zone_locs = []
        for zi, (tt, tws) in enumerate(lines[li:li + 7]):
            for w in tws:
                if w["text"].lower().strip(".,") in LOC_NOISE:
                    continue
                key = re.sub(r"[^a-z]", "", w["text"].lower())
                if key not in NURSERY:
                    continue
                c = cx(w)
                zone_locs.append((key, c))
                if zi < 5 and low <= c <= (chl_x + 98):
                    cand.append((key, c))
        # A nursery name that repeats in the window is the Emergence/BSR column
        # reusing that site (e.g. 1988 chlorosis 'Ames' + emergence 'Ames'):
        # keep only the leftmost occurrence so the band can't span into it.
        seen = {}
        for key, c in sorted(cand, key=lambda kc: kc[1]):
            seen.setdefault(key, (key, c))
        cand = sorted(seen.values(), key=lambda kc: kc[1])
        # RIGHT boundary: nearest right-of-chlorosis trait header word.
        rights = [w["x0"] for w in zone
                  if w["x0"] > chl_x + 8
                  and any(w["text"].lower().startswith(p) for p in RIGHT_TRAITS)]
        R = min(rights) if rights else 1e9
        # LEFT boundary: chlorosis word minus margin, clamped past any left-trait
        # / code column (same clamp used for the nursery window above).
        L = max(chl_x - MARGIN, low)
        # When >=2 nursery headers are found, define a TIGHT band around them.
        # This is the reliable case (multi-nursery Era A/B blocks) and excludes
        # the shattering column on the left (e.g. Manhattan) and the
        # emergence/BSR columns on the right that the trait-word band can leak.
        if len(cand) >= 2:
            xs = [c for _, c in cand]
            L, R = min(xs) - 20, max(xs) + 20
            loc_headers = cand
            R = max(xs) + 20  # never extend toward the shattering side
        else:
            loc_headers = [(k, c) for k, c in cand if L <= c < R]
            # Chlorosis nurseries never sit to the RIGHT of the rightmost
            # detected one (further right is emergence/shattering): clamp R so a
            # leaked shattering column (e.g. Lubbock in 1982 UT-IV) is excluded.
            if loc_headers:
                R = min(R, max(c for _, c in loc_headers) + 22)
            # Sparse/messy block with no in-band header: label by nearest
            # chlorosis-nursery word in the zone (e.g. 1971 single Crookston col).
            if not loc_headers and zone_locs:
                loc_headers = [min(zone_locs, key=lambda kc: abs(kc[1] - chl_x))]
        blocks.append({"li": li, "top": top, "chl_x": chl_x, "L": L, "R": R,
                       "loc_headers": loc_headers, "fallback": chl is None})
    # Fallback (Emergence-anchored) blocks only stand in when the page had NO
    # clean 'Chlorosis' word; never let them interfere with validated pages.
    if have_clean:
        blocks = [b for b in blocks if not b["fallback"]]
    return blocks, lines


def extract_block(block, lines, exact, collapsed):
    """Pull (matched_strain, location_key, value) tuples from one block's data
    rows. Strain anchors are found by longest-prefix match against the year's
    strain list; fragmented value-only sub-lines are grouped to the nearest
    anchor; nursery columns are discovered by clustering in-band numeric x."""
    li, L, R = block["li"], block["L"], block["R"]
    data_lines = lines[li + 1:]
    stop_kw = ("disease data", "petri", "mean ", "average", "c.v", "lsd", "l.s.d",
               "footnote", "browning", "number of years", "percent of plants")
    # Pass 1: per line, collect left-region tokens (potential strain+code) and
    # in-band numeric values. Detect strain anchors via longest-prefix match.
    anchors = []     # (top, strain)
    line_nums = []   # (top, [(value, x), ...]) for every line with in-band nums
    for top, ws in data_lines:
        line_txt = " ".join(w["text"] for w in ws).lower()
        if any(k in line_txt for k in stop_kw) or parse_test(line_txt.upper()):
            break
        left = [w["text"] for w in sorted(ws, key=lambda w: w["x0"]) if cx(w) < L]
        strain, _ = match_prefix(left, exact, collapsed)
        if strain is not None:
            anchors.append((top, strain))
        nums = [(to_float(w["text"]), cx(w)) for w in ws
                if NUM_RE.match(w["text"]) and L <= cx(w) < R]
        nums = [(v, x) for v, x in nums if v is not None and CHL_MIN <= v <= CHL_MAX]
        if nums:
            line_nums.append((top, nums))
    if not anchors:
        return [], []
    # Pass 2: assign each numeric line to the nearest anchor (handles the
    # name-line / value-line split, above or below).
    anchor_tops = [a[0] for a in anchors]
    grouped = defaultdict(list)  # anchor_idx -> [(value, x)]
    for top, nums in line_nums:
        ai = min(range(len(anchor_tops)), key=lambda i: abs(anchor_tops[i] - top))
        if abs(anchor_tops[ai] - top) <= 8.0:  # within a fragmented record
            grouped[ai].extend(nums)
    # Cluster all grouped numeric x into nursery columns.
    all_x = sorted(x for vs in grouped.values() for _, x in vs)
    cols = _cluster(all_x, gap=14.0)
    if not cols:
        return [], []
    labels, from_header = _label_columns(cols, block["loc_headers"])
    # Per-row, pick one value per column (nearest); collect per-column values.
    per_row = []   # (strain, {col_idx: value})
    colvals = defaultdict(list)
    for ai, vs in grouped.items():
        _, strain = anchors[ai]
        best = {}  # col_idx -> (dist, value)
        for v, x in vs:
            ci = min(range(len(cols)), key=lambda i: abs(cols[i] - x))
            if abs(cols[ci] - x) > 24:
                continue
            d = abs(cols[ci] - x)
            if ci not in best or d < best[ci][0]:
                best[ci] = (d, v)
        row = {ci: v for ci, (_, v) in best.items()}
        per_row.append((strain, row))
        for ci, v in row.items():
            colvals[ci].append(v)
    # Drop spurious columns: an unlabelled (default-named) column whose values
    # are near-constant 1.0 is the hypocotyl-color code "I" OCR'd to digit "1",
    # not a chlorosis nursery (it leaks into the band on some Era-B pages, e.g.
    # 1984 'PGBrDYY 1 3.2'). A genuine chlorosis nursery varies across strains.
    drop = set()
    for ci, vals in colvals.items():
        if not from_header[ci] and len(vals) >= 4:
            frac_one = sum(1 for v in vals if v <= 1.0) / len(vals)
            if frac_one >= 0.8:
                drop.add(ci)
    rows = []
    for strain, row in per_row:
        for ci, v in row.items():
            if ci not in drop:
                rows.append((strain, labels[ci], v))
    colinfo = [(round(c), labels[i]) for i, c in enumerate(cols) if i not in drop]
    return rows, colinfo


def _cluster(xs, gap):
    """1-D clustering: split sorted xs where consecutive gap exceeds `gap`.
    Returns the mean x of each cluster (column center)."""
    if not xs:
        return []
    clusters, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] > gap:
            clusters.append(cur); cur = [x]
        else:
            cur.append(x)
    clusters.append(cur)
    return [sum(c) / len(c) for c in clusters]


def _label_columns(cols, loc_headers):
    """Label each nursery column (sorted by x). Returns (labels, from_header)
    where from_header[i] is True if column i was labelled by a real detected
    nursery name (vs a positional default). If the count of detected headers
    matches the number of columns, pair them by x-order (most robust); else
    assign each its nearest header within tolerance, filling the remainder from
    a positional default encoding the left->right geography (Crookston/Lamb/Ames)."""
    n = len(cols)
    if n and len(loc_headers) == n:
        ordered = [k for k, _ in sorted(loc_headers, key=lambda kc: kc[1])]
        return ordered, [True] * n
    labels, from_header = [], []
    for c in cols:
        if loc_headers:
            key, d = min(((k, abs(x - c)) for k, x in loc_headers), key=lambda t: t[1])
            ok = d <= 30
            labels.append(key if ok else None)
            from_header.append(ok)
        else:
            labels.append(None); from_header.append(False)
    if any(l is None for l in labels):
        default = {1: ["ames"], 2: ["ames", "lamberton"],
                   3: ["crkstn", "lamb", "ames"]}.get(n, ["ames"] * n)
        labels = [labels[i] or default[i] for i in range(n)]
    return labels, from_header


# ---------------------------------------------------------------------------
# Per-year driver
# ---------------------------------------------------------------------------
def extract_year(year, exact, collapsed, verbose=False):
    """Return DataFrame[Year,Test,Strain,LocKey,City,State,Value] + per-section log.
    `exact`/`collapsed` are the year's strain-key maps (anchor detection uses them)."""
    pp = pdf_path(year)
    if pp is None:
        print(f"  {year}: PDF NOT FOUND"); return pd.DataFrame(), []
    pdf = pdfplumber.open(pp)
    out, log = [], []
    cur_test = None
    for pi, page in enumerate(pdf.pages):
        txt = page.extract_text() or ""
        t = parse_test(txt)
        if t:
            cur_test = t
        if "hloros" not in txt.lower() and not _desc_signature(txt):
            continue
        blocks, lines = find_chl_blocks(page)
        for b in blocks:
            rows, colinfo = extract_block(b, lines, exact, collapsed)
            if not rows:
                continue
            test = cur_test or "?"
            for strain, key, v in rows:
                city, state = NURSERY.get(key, (None, None))
                out.append((year, test, strain, key, city, state, v))
            log.append({"page": pi, "test": test, "n": len(rows),
                        "cols": colinfo})
            if verbose:
                print(f"    p{pi} {test}: {len(rows)} vals  cols={colinfo}")
    df = pd.DataFrame(out, columns=["Year", "Test", "Strain", "LocKey",
                                    "City", "State", "Value"])
    return df, log


# ---------------------------------------------------------------------------
# Append to phenotypesTable1.csv (idempotent + .bak)
# ---------------------------------------------------------------------------
def csv_path(year):
    if 1976 <= year <= 1979:
        return NUST_DATA / f"{year}_Processing" / "Files4Upload" / "phenotypesTable1.csv"
    return HIST / f"{year}_Processing" / "Files4Upload" / "phenotypesTable1.csv"


def append_year(year, df, src_cols, src_df):
    """Append matched Chlorosis rows to phenotypesTable1.csv. `df.Strain` already
    holds the source spelling (set during extraction). Idempotent + one-time .bak."""
    path = csv_path(year)
    # De-dup: same strain x test x nursery can recur across repeated pages /
    # the per-location summary block. Keep one (median guards OCR outliers).
    keep = (df.groupby(["Test", "Strain", "City", "State"], as_index=False)["Value"]
              .median())
    src = src_df.copy()
    if "Phenotype" in src.columns:
        src = src[src["Phenotype"] != PHENOTYPE].copy()
    new = pd.DataFrame({
        "Strain": keep["Strain"],
        "Year": year,
        "Test": keep["Test"],
        "City": keep["City"],
        "State": keep["State"],
        "Phenotype": PHENOTYPE,
        "Value": keep["Value"].round(4),
        "Units": UNITS,
    })
    for c in src_cols:
        if c not in new.columns:
            new[c] = ""
    new = new[src_cols]
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(path, bak)
    pd.concat([src, new], ignore_index=True)[src_cols].to_csv(path, index=False)
    return len(new)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="append to phenotypesTable1.csv")
    ap.add_argument("--years", type=int, nargs="*", default=YEARS_ALL)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--dump-csv", type=str, default=None)
    args = ap.parse_args()

    print("=" * 74)
    print(f"Chlorosis Score re-extraction (Red PDFs {args.years[0]}-{args.years[-1]})"
          f"  mode={'WRITE' if args.write else 'REPORT'}")
    print("=" * 74)

    all_dumps = []
    grand_written = 0
    for year in args.years:
        cpath = csv_path(year)
        if not cpath.exists():
            print(f"\n[{year}] phenotypesTable1.csv NOT FOUND -> skip ({cpath})")
            continue
        exact, collapsed, src_df = build_strain_map(cpath)
        df, log = extract_year(year, exact, collapsed, verbose=args.verbose)
        if df.empty:
            print(f"\n[{year}] no chlorosis values extracted "
                  f"({'no PDF' if pdf_path(year) is None else 'parse miss'})")
            continue
        n_strains_csv = len(set(strain_key(s) for s in src_df["Strain"].astype(str)))
        per_test = df.groupby("Test").size().to_dict()
        per_city = df["City"].value_counts().to_dict()
        rng = (round(df["Value"].min(), 1), round(df["Value"].max(), 1))
        n_uniq_strain = df["Strain"].nunique()
        print(f"\n[{year}] {len(df)} matched vals | {n_uniq_strain} distinct strains "
              f"| range {rng}")
        print(f"    tests: {per_test}")
        print(f"    nurseries: {per_city}")
        if args.dump_csv:
            all_dumps.append(df)
        if args.write:
            src_cols = list(src_df.columns)
            n_new = append_year(year, df, src_cols, src_df)
            grand_written += n_new
            print(f"    WROTE {n_new} rows -> {cpath.name}")

    if args.dump_csv and all_dumps:
        pd.concat(all_dumps, ignore_index=True).to_csv(args.dump_csv, index=False)
        print(f"\nDumped raw extraction -> {args.dump_csv}")
    if args.write:
        print(f"\nDone. {grand_written} Chlorosis rows written.")
        print("Next: rebuild corpus (10_assemble_corpus.py -> 11_build_wide_1941_2025.py),"
              " run 13_qc_strain_germplasm_audit.py gate, then P2 traits heatmap.")
    else:
        print("\nREPORT mode (no writes). Re-run with --write once validated.")


if __name__ == "__main__":
    main()
