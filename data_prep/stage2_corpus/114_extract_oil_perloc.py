"""
114_extract_oil_perloc.py
=========================
Recover per-location OIL (% oil, dry basis as printed) from the Red PDFs across ALL eras.
Companion to 112 (which handles the combined per-location trait tables). The dedicated oil data
lives in tables whose caption 112 does NOT match, so the F4U pipeline missed them for whole
(year, test) cells (e.g. 1979 UT-00/I/II/IV; Preliminary Tests in many years).

Three source layouts (see the format survey):
  A. "OIL (%"  embedded column in the combined per-location trait table (1970-1988) -> already
      handled by 112; re-parsed here for completeness / gap-fill.
  B. "% OIL"   dedicated per-location oil block, percent BEFORE the word (1979-1980). Shares the
      page's location header with the % PROTEIN / SEED SIZE blocks above it.
  C. "Percentage of Oil"  sub-block inside a "Percentages of protein and oil, <Test>" table
      (1950s-1960s). The table carries its OWN multi-line State/City header at the top; the oil
      block sits below a "... Percentage of Oil" separator line.

Layouts A/B use a PAGE-level location header (detected here, independent of 112._page_header which
needs a "TRAIT (unit" caption that the "% OIL" pages lack). Layout C uses the table-top header.
All three reuse 112._parse_region (column x-clustering + fixed multi-line-header reconstruction +
ref-roster city/state repair) to turn a (band, header) into {strain: {(City,State): value}}.

Library: extract_oil_section(year, code) -> DataFrame
  {Year,TestType,TestMG,Test,Strain,City,State,Phenotype="Oil",Value_num,Units="%",Source="OilPDF"}.
"""
import sys
import re
import importlib
from collections import defaultdict, Counter
from pathlib import Path
import pandas as pd
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
P = importlib.import_module("112_extract_pdf_perloc")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = P.REPO
OIL_RANGE = (5.0, 30.0)                      # plausible % oil (dry basis)
MIN_X = 152                                  # data-column region (strains sit left, at cx<150)

# --------------------------------------------------------------------------- page-rotation correction
# Wide composition/oil tables in the older reports are printed SIDEWAYS (rotated 90/270 deg). pdfplumber
# reads them at the page's portrait orientation -> garbled fragments. Detect the dominant character
# transform matrix per page and, where rotated, rebuild a rotation-corrected copy of the PDF (via pypdf)
# so pdfplumber re-orients the text. Corrected PDFs are cached under the scratch dir, keyed by year.
_CORR_DIR = Path(REPO) / "data_prep" / "stage2_corpus" / "_oil_rotcorrected"
_CORR_CACHE = {}


def _rot_needed(page):
    """Degrees to add to make the page's dominant text upright (0/90/180/270)."""
    c = Counter((round(m[0]), round(m[1]), round(m[2]), round(m[3]))
                for ch in page.chars if (m := ch.get("matrix")))
    if not c:
        return 0
    return {(0, 1, -1, 0): 90, (0, -1, 1, 0): 270, (-1, 0, 0, -1): 180}.get(c.most_common(1)[0][0], 0)


def _corrected_pdf(year):
    """Path to a rotation-corrected copy of the year's PDF (or the raw path if no page needs it)."""
    if year in _CORR_CACHE:
        return _CORR_CACHE[year]
    raw = Path(REPO) / "input_files" / f"input_{year}" / f"{year}_done.pdf"
    if not raw.exists():
        _CORR_CACHE[year] = None
        return None
    with pdfplumber.open(raw) as pdf:
        rots = {i: _rot_needed(pg) for i, pg in enumerate(pdf.pages)}
    if not any(rots.values()):
        _CORR_CACHE[year] = str(raw)
        return str(raw)
    from pypdf import PdfReader, PdfWriter
    reader, writer = PdfReader(str(raw)), PdfWriter()
    for i, pg in enumerate(reader.pages):
        if rots.get(i):
            pg.rotate(rots[i])
        writer.add_page(pg)
    _CORR_DIR.mkdir(parents=True, exist_ok=True)
    out = _CORR_DIR / f"{year}_done_rotcorrected.pdf"
    with open(out, "wb") as f:
        writer.write(f)
    n = sum(1 for v in rots.values() if v)
    print(f"  [rotation] {year}: corrected {n} sideways page(s) -> {out.name}")
    _CORR_CACHE[year] = str(out)
    return str(out)


def _oilnum(t):
    """clean_num hardened for messy 1940s cells: strip trailing dashes/OCR punctuation first."""
    s = re.sub(r"[\-–—•*·,.\s]+$", "", str(t).strip())
    return P.clean_num(s)

# any block caption that starts a data block (used to bound the shared page header from below)
BLOCK_RE = re.compile(r"%\s*OIL|OIL\s*\(\s*%|%\s*PROTEIN|PROTEIN\s*\(\s*%|SEED\s*SIZE|SEED\s*QUALITY|"
                      r"PLANT\s*HEIGHT|\bHEIGHT\b|MATURITY|LODGING|YIELD|SEED\s*WT", re.I)
OIL_CAP_RE = re.compile(r"%\s*OIL\b|\bOIL\s*\(\s*%", re.I)
# a line that ends a data block from below (next caption / rank / mean / year-range separator)
BOUND_RE = re.compile(r"RANK|\bMEAN\b|\bTESTS?\b|19\d\d\s*-|\bYEAR\b|%\s*OIL|OIL\s*\(\s*%|"
                      r"%\s*PROTEIN|PROTEIN\s*\(\s*%|SEED\s*SIZE|SEED\s*QUALITY|PLANT\s*HEIGHT|"
                      r"\bHEIGHT\b|MATURITY|LODGING|YIELD", re.I)


def _lines(page):
    W = page.extract_words(use_text_flow=False)
    d = defaultdict(list)
    for w in W:
        d[round(w["top"])].append(w)
    return W, d


def _ltext(lines, top):
    return " ".join(x["text"] for x in sorted(lines[top], key=lambda w: w["x0"]))


NUM_RE = re.compile(r"^[+\-^]?[\d.,]+$")
# column-label / caption tokens that are NOT locations (Mean/N-Tests cols, row labels, caption words
# that leak in when a wrapped table caption sits just above the State/City header).
HDR_JUNK = re.compile(r"^(mean|tests?|strain|no|rank|of|the|percentage|oil|protein|seed|"
                      r"size|quality|height|maturity|lodging|yield|uniform|preliminary|group|"
                      r"summary|table|for|in|strains|data|content|and|composite|locations|"
                      r"iodine|number|source|origin|agency|variety|varieties|"
                      r"i|ii|iii|iv|v|vi|vii)$", re.I)     # incl. roman-numeral MG from a wrapped caption
HDR_NUMISH = re.compile(r"^[\d.,+\-^–—:]+$")               # value tokens (incl. trailing-dash '20,6-')


def _hdr_words(lines, tops, lo, hi):
    return [w for row in tops if lo <= row <= hi for w in lines[row]
            if P.cx(w) > MIN_X and not HDR_NUMISH.match(w["text"])
            and not HDR_JUNK.match(re.sub(r"[^A-Za-z%]", "", w["text"]))]


def _state_top(hdr):
    """_parse_region skips its top header line as the STATE line. That is right only when the top
    line actually holds state names; many oil headers are pure wrapped city syllables with no state
    row (e.g. 1979 UT-IV: Eldo/Belle/Queens/Sulli), where skipping it would drop the first syllable.
    Return the real top when the top line has a state word, else just below it (skip nothing)."""
    if not hdr:
        return 0
    mn = min(w["top"] for w in hdr)
    top_line = [w for w in hdr if abs(w["top"] - mn) <= 3]
    return mn if any(P._state_of(w["text"]) for w in top_line) else mn - 6


def _page_top_header(lines, tops):
    """Shared header (title -> first data block), for pages where all blocks list the same locs."""
    title_top = max((min(w["top"] for w in lines[t]) for t in tops
                     if re.search(r"UNIFORM", _ltext(lines, t), re.I)
                     and min(w["top"] for w in lines[t]) < 130), default=60)
    block_tops = [t for t in tops if BLOCK_RE.search(_ltext(lines, t).upper())]
    if not block_tops:
        return [], 0
    hdr = _hdr_words(lines, tops, title_top + 6, min(block_tops) - 2)
    return hdr, _state_top(hdr)


def _header_for_oil(lines, tops, oil_top):
    """Per-block header = the location line(s) within ~30px above the oil caption (state line +
    city line). If none (the block shares the page-top header), fall back to that."""
    for t in sorted((t for t in tops if oil_top - 30 < t < oil_top - 1), reverse=True):
        txt = _ltext(lines, t).upper()
        if OIL_CAP_RE.search(txt) or re.search(r"%\s*PROTEIN|SEED|HEIGHT|MATURITY|LODGING|YIELD", txt):
            continue
        loc = [w for w in lines[t] if P.cx(w) > MIN_X and re.search(r"[A-Za-z]", w["text"])
               and not NUM_RE.match(w["text"])
               and not HDR_JUNK.match(re.sub(r"[^A-Za-z%]", "", w["text"]))]
        if len(loc) >= 2:                                 # a real per-block location header
            hdr = _hdr_words(lines, tops, t - 14, t + 1)
            return hdr, min((w["top"] for w in hdr), default=t)
    return _page_top_header(lines, tops)                  # shared-header page


def _per_block_header(lines, tops, oil_top):
    """The header band = the CONSECUTIVE non-data lines directly above the oil caption (a state
    line + one or two wrapped city-syllable lines), stopping at the previous block's data rows or
    caption. Passing the full band lets _parse_region stitch wrapped/multi-line city names."""
    band = []
    for t in sorted((t for t in tops if t < oil_top - 1), reverse=True):
        if oil_top - t > 36:
            break
        txt = _ltext(lines, t).upper()
        if OIL_CAP_RE.search(txt) or re.search(r"%\s*PROTEIN|SEED|HEIGHT|MATURITY|LODGING|YIELD", txt):
            break                                         # previous block caption -> header ends
        ws = lines[t]
        nums = [w for w in ws if P.cx(w) > MIN_X and NUM_RE.match(w["text"])]
        alpha = [w for w in ws if P.cx(w) > MIN_X and re.search(r"[A-Za-z]", w["text"])
                 and not NUM_RE.match(w["text"])]
        if len(nums) >= 3 and len(alpha) < 2:
            break                                         # a data row -> header ends
        band.append(t)
    if not band:
        return None
    hdr = _hdr_words(lines, tops, min(band), max(band) + 1)
    loc = [w for w in hdr if re.search(r"[A-Za-z]", w["text"]) and not NUM_RE.match(w["text"])]
    if len(loc) < 2:
        return None
    return hdr, _state_top(hdr)


def _page_oil_bands(page):
    """For every oil block on the page yield (candidate_headers, top0, top1). Two candidate headers
    are offered — the shared page-top header and any per-block header — because pages are mixed:
    some blocks share the page header (UT-0), others carry their own location subset (UT-00). The
    caller parses with each and keeps whichever actually yields oil."""
    _, lines = _lines(page)
    tops = sorted(lines)
    bounds = [t for t in tops if BOUND_RE.search(_ltext(lines, t).upper())]
    pt = _page_top_header(lines, tops)
    out = []
    for t in tops:
        if OIL_CAP_RE.search(_ltext(lines, t).upper()):
            cands = []
            pb = _per_block_header(lines, tops, t)
            if pb and pb[0]:
                cands.append(pb)
            if pt and pt[0]:
                cands.append(pt)
            if not cands:
                continue
            nxt = [b for b in bounds if b > t + 6]
            out.append((cands, t + 4, (min(nxt) - 2) if nxt else 9999))
    return out


def extract_oil_section(year, code):
    tt = "PT" if code.startswith("PT") else "UT"
    mg = re.sub(r"^(UT|PT)-", "", code)
    pdf_path = _corrected_pdf(year)
    if not pdf_path:
        return pd.DataFrame()
    per = defaultdict(dict)                   # strain -> {(city,state): oil%}
    with pdfplumber.open(pdf_path) as pdf:
        pages = P.section_pages(pdf, year, code)
        for i in pages:
            pg = pdf.pages[i]
            for cands, top0, top1 in _page_oil_bands(pg):
                # parse the band with each candidate header; keep the one giving the most oil
                # cells whose LOCATION is CLEAN (in the ref roster or a clean single-name city).
                # Scoring on clean-loc count rejects a mismatched header that stitches fragments
                # ("town"/"van"/"ville") even when it produces many raw cells.
                def clean_loc(loc):
                    return P._in_ref(loc[0], loc[1]) or P._clean_city(loc[0])
                best, best_score = {}, -1
                for hdr, state_top in cands:
                    region = P._parse_region(pg, top0, top1, hdr, state_top)
                    got = {}
                    for strain, cells in region.items():
                        for loc, w in cells.items():
                            v = _oilnum(w["text"] if isinstance(w, dict) else w)
                            if v is not None and OIL_RANGE[0] <= v <= OIL_RANGE[1]:
                                got.setdefault(strain, {})[loc] = round(v, 2)
                    score = sum(1 for d in got.values() for loc in d if clean_loc(loc))
                    if score > best_score:
                        best, best_score = got, score
                for strain, cells in best.items():
                    for loc, v in cells.items():
                        per[strain].setdefault(loc, v)
    rows = [(strain, loc[0], loc[1], "Oil", v, "%")
            for strain, cells in per.items() for loc, v in cells.items()]
    df = pd.DataFrame(rows, columns=["Strain", "City", "State", "Phenotype", "Value_num", "Units"])
    if len(df):
        df.insert(0, "Year", year); df.insert(1, "TestType", tt)
        df.insert(2, "TestMG", mg); df.insert(3, "Test", code)
        df["Source"] = "OilPDF"
    return df


# --------------------------------------------------------------------------- 1950s-1960s format C
# "Percentages of protein and oil, <Test>" / "Summary of (height data and) percentage of oil ...".
# One table with a multi-line State/City header at the TOP; oil is either the whole table (standalone
# "summary of percentage of oil") or a sub-block below a "... Percentage of Oil" separator line
# (combined protein+oil / height+oil). The top header is SHARED by all sub-blocks.
def _is_data_row(row_words):
    left = [w for w in row_words if P.cx(w) < 160 and re.match(r"^[A-Za-z$]", w["text"])]
    nums = [w for w in row_words if P.cx(w) > MIN_X and NUM_RE.match(w["text"])]
    return bool(left) and len(nums) >= 3


# the "... Percentage of Oil" sub-block separator (also matches the no-"of" 1940s wording)
PCTOIL_SEP_RE = re.compile(r"percentage\s*(of\s+|the\s+)*oil", re.I)


def _cap_window(lines, tops, cap):
    """Caption text joined across the caption line + the next up-to-2 lines (older captions wrap:
    'Summary of the percentage oil ... Uniform' / 'Test, Group III, 1943.')."""
    idx = tops.index(cap)
    return " ".join(_ltext(lines, t) for t in tops[idx:idx + 3])


def _cap_matches(txt, tt, mg):
    tl = txt.lower()
    if "oil" not in tl or "percentage" not in tl:
        return False
    if re.search(r"\d\s*-\s*year|two-?year|three-?year|four-?year|five-?year|year summary", tl):
        return False                                      # skip multi-year summaries
    kind = "preliminary" if tt == "PT" else "uniform"
    if kind not in tl:
        return False
    return bool(re.search(rf"(test|group)\s*,?\s*{re.escape(mg.lower())}\b", tl))


def extract_pctoil_section(year, code):
    tt = "PT" if code.startswith("PT") else "UT"
    mg = re.sub(r"^(UT|PT)-", "", code)
    pdf_path = _corrected_pdf(year)
    if not pdf_path:
        return pd.DataFrame()
    per = defaultdict(dict)
    with pdfplumber.open(pdf_path) as pdf:
        for pg in pdf.pages:
            _, lines = _lines(pg)
            tops = sorted(lines)
            for cap in tops:
                if not _cap_matches(_cap_window(lines, tops, cap), tt, mg):
                    continue
                data_tops = [t for t in tops if t > cap and _is_data_row(lines[t])]
                if not data_tops:
                    continue
                first_data = min(data_tops)
                ends = [t for t in tops if t > cap + 2 and re.match(r"TABLE\s+\d", _ltext(lines, t).upper())]
                tbl_end = min(ends) if ends else 9999
                hdr = _hdr_words(lines, tops, cap + 1, first_data - 1)
                if len([w for w in hdr if re.search(r"[A-Za-z]", w["text"])]) < 2:
                    continue
                seps = [t for t in tops if cap < t < tbl_end
                        and PCTOIL_SEP_RE.search(_ltext(lines, t))]
                oil0 = (min(seps) + 4) if seps else (first_data - 1)
                region = P._parse_region(pg, oil0, tbl_end - 1, hdr, _state_top(hdr))
                for strain, cells in region.items():
                    for loc, w in cells.items():
                        v = _oilnum(w["text"] if isinstance(w, dict) else w)
                        if v is not None and OIL_RANGE[0] <= v <= OIL_RANGE[1]:
                            per[strain].setdefault(loc, round(v, 2))
    rows = [(strain, loc[0], loc[1], "Oil", v, "%")
            for strain, cells in per.items() for loc, v in cells.items()]
    df = pd.DataFrame(rows, columns=["Strain", "City", "State", "Phenotype", "Value_num", "Units"])
    if len(df):
        df.insert(0, "Year", year); df.insert(1, "TestType", tt)
        df.insert(2, "TestMG", mg); df.insert(3, "Test", code)
        df["Source"] = "OilPDF"
    return df


def extract_oil(year, code):
    """Union of the modern (% OIL / OIL(%) and the 1950s-60s (Percentage of Oil) extractors,
    de-duplicated on (Strain, City, State) keeping the first value seen."""
    parts = [d for d in (extract_oil_section(year, code), extract_pctoil_section(year, code)) if len(d)]
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    return df.drop_duplicates(["Strain", "City", "State"]).reset_index(drop=True)


TITLE_RE = re.compile(r"\b(UNIFORM|PRELIMINARY)\s+TEST\s+(0{1,2}|IV|I{1,3})\b", re.I)
CAP_CODE_RE = re.compile(r"(test|group)\s*,?\s*(0{1,2}|iv|i{1,3})\b", re.I)


def _code_from_title(text):
    m = TITLE_RE.search(re.sub(r"\s+", " ", text))
    if not m:
        return None
    tt = "PT" if m.group(1).upper().startswith("PREL") else "UT"
    return f"{tt}-{m.group(2).upper()}"


def _code_from_caption(txt):
    tl = txt.lower()
    if "oil" not in tl or "percentage" not in tl:
        return None
    if re.search(r"\d\s*-\s*year|two-?year|three-?year|four-?year|five-?year|year summary", tl):
        return None
    tt = "PT" if "preliminary" in tl else ("UT" if "uniform" in tl else None)
    m = CAP_CODE_RE.search(tl)
    return f"{tt}-{m.group(2).upper()}" if (tt and m) else None


def _collect_modern(pg, per_code, cur):
    """Modern % OIL / OIL(% bands on this page -> assigned to the running test code `cur`."""
    if not cur:
        return
    for cands, top0, top1 in _page_oil_bands(pg):
        best, best_score = {}, -1
        for hdr, state_top in cands:
            region = P._parse_region(pg, top0, top1, hdr, state_top)
            got = {}
            for strain, cells in region.items():
                for loc, w in cells.items():
                    v = _oilnum(w["text"] if isinstance(w, dict) else w)
                    if v is not None and OIL_RANGE[0] <= v <= OIL_RANGE[1]:
                        got.setdefault(strain, {})[loc] = round(v, 2)
            score = sum(1 for d in got.values() for loc in d
                        if P._in_ref(loc[0], loc[1]) or P._clean_city(loc[0]))
            if score > best_score:
                best, best_score = got, score
        for strain, cells in best.items():
            for loc, v in cells.items():
                per_code[cur][strain].setdefault(loc, v)


def _collect_pctoil(pg, lines, tops, per_code):
    """1950s-60s Percentage-of-Oil tables on this page -> assigned to the caption's own test."""
    for cap in tops:
        code = _code_from_caption(_cap_window(lines, tops, cap))
        if not code:
            continue
        data_tops = [t for t in tops if t > cap and _is_data_row(lines[t])]
        if not data_tops:
            continue
        first_data = min(data_tops)
        ends = [t for t in tops if t > cap + 2 and re.match(r"TABLE\s+\d", _ltext(lines, t).upper())]
        tbl_end = min(ends) if ends else 9999
        hdr = _hdr_words(lines, tops, cap + 1, first_data - 1)
        if len([w for w in hdr if re.search(r"[A-Za-z]", w["text"])]) < 2:
            continue
        seps = [t for t in tops if cap < t < tbl_end
                and PCTOIL_SEP_RE.search(_ltext(lines, t))]
        oil0 = (min(seps) + 4) if seps else (first_data - 1)
        region = P._parse_region(pg, oil0, tbl_end - 1, hdr, _state_top(hdr))
        for strain, cells in region.items():
            for loc, w in cells.items():
                v = _oilnum(w["text"] if isinstance(w, dict) else w)
                if v is not None and OIL_RANGE[0] <= v <= OIL_RANGE[1]:
                    per_code[code][strain].setdefault(loc, round(v, 2))


def extract_oil_year(year):
    """Single-pass over the year's PDF: recover per-location Oil for ALL tests at once (modern +
    1950s-60s formats). ~12x fewer PDF scans than calling extract_oil per code."""
    pdf_path = _corrected_pdf(year)
    if not pdf_path:
        return pd.DataFrame()
    per_code = defaultdict(lambda: defaultdict(dict))     # code -> strain -> {(city,state): oil}
    with pdfplumber.open(pdf_path) as pdf:
        cur = None
        for pg in pdf.pages:
            try:
                text = pg.extract_text() or ""
            except Exception:
                continue
            c = _code_from_title(text)
            if c:
                cur = c
            _collect_modern(pg, per_code, cur)
            _, lines = _lines(pg)
            _collect_pctoil(pg, lines, sorted(lines), per_code)
    rows = []
    for code, strains in per_code.items():
        tt = "PT" if code.startswith("PT") else "UT"
        mg = code.split("-")[1]
        for strain, cells in strains.items():
            for loc, v in cells.items():
                rows.append((year, tt, mg, code, strain, loc[0], loc[1], "Oil", v, "%", "OilPDF"))
    return pd.DataFrame(rows, columns=["Year", "TestType", "TestMG", "Test", "Strain",
                                       "City", "State", "Phenotype", "Value_num", "Units", "Source"])


# --------------------------------------------------------------------------- Table-65 per-loc composite
# "Chemical composition of soybean seed grown at each Uniform Test location ... composite/mean of all
# strains" (1941-1956). One OIL value per (Group, Location) = composite over strains, single-year. Used to
# fill cells that have no full strain x location oil table. Rows: Strain="Composite", Aggregation flag.
_T65_GUARD = re.compile(r"protein\s+oil|at each of the .{0,20}location", re.I)
# composite-block header ("Group III (composite of 16 strains)" / "Group 0 of 16 strains in 1945" /
# "Group I (Mean of ...)") — NOT the agronomic per-strain header "Group IV strains."
_T65_BLK = re.compile(r"group\s+(0{1,2}|iv|i{1,3}|v)\b[^\n]{0,45}"
                      r"(composite|mean\s+of|of\s+\d+\s+strains)", re.I)
_T65_STOP = re.compile(r"^\s*(table\s+\d|group\s)", re.I)
_T65_ST = {"del": "DE", "md": "MD", "ind": "IN", "indiana": "IN", "ill": "IL", "illinois": "IL",
           "ohio": "OH", "iowa": "IA", "mo": "MO", "nebr": "NE", "neb": "NE", "mich": "MI",
           "wis": "WI", "minn": "MN", "nd": "ND", "sd": "SD", "ont": "ONT", "va": "VA", "kansas": "KS",
           "kan": "KS", "tex": "TX", "texas": "TX", "ore": "OR", "man": "MB", "penn": "PA", "pa": "PA"}


def _t65_loc(txt):
    toks = re.findall(r"[A-Za-z.]+", txt)
    st = ""
    for t in list(reversed(toks)):
        if re.sub(r"[^a-z]", "", t.lower()) in _T65_ST:
            st = _T65_ST[re.sub(r"[^a-z]", "", t.lower())]
            toks.remove(t)
            break
    city = re.sub(r"\s+", " ", " ".join(toks)).strip(" .,;")
    return city, st


def extract_table65_composite(year):
    """Per-location COMPOSITE oil (mean of all strains per location) from the Table-65 chemical-
    composition tables. Returns rows tagged Strain='Composite', Aggregation='location_composite'."""
    path = _corrected_pdf(year)
    if not path:
        return pd.DataFrame()
    out = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if not _T65_GUARD.search(t):
                continue
            lines = t.splitlines(); i = 0; mg = None
            while i < len(lines):
                m = _T65_BLK.search(lines[i])
                if m:
                    mg = m.group(1).upper(); i += 1; continue
                if mg and _T65_STOP.match(lines[i]):
                    mg = None
                if mg:
                    ln = lines[i].strip()
                    nm = re.search(r"\d", ln)
                    if nm and nm.start() >= 3:
                        nums = [float(x) for x in re.findall(r"\d+\.\d+", ln[nm.start():])]
                        if len(nums) >= 2 and 28 <= nums[0] <= 52 and 5 <= nums[1] <= 30:
                            city, st = _t65_loc(ln[:nm.start()])
                            if len(re.sub(r"[^A-Za-z]", "", city)) >= 3:
                                out.append((year, "UT", mg, f"UT-{mg}", city, st,
                                            "Composite", "Oil", round(nums[1], 2), "%",
                                            "OilComposite_T65", "location_composite"))
                i += 1
    df = pd.DataFrame(out, columns=["Year", "TestType", "TestMG", "Test", "City", "State", "Strain",
                                    "Phenotype", "Value_num", "Units", "Source", "Aggregation"])
    return df.drop_duplicates(["Year", "Test", "City", "State"])


_AGRO_GRP = re.compile(r"group\s+(0{1,2}|iv|i{1,3}|v)\b", re.I)
_AGRO_TRIPLET = re.compile(r"(\d{2}\.\d)\s+(\d{2}\.\d)\s+(\d{2,3}\.?\d?)\s*$")   # ...Protein Oil Iodine


def extract_agronomic_oil(year, mg):
    """Per-STRAIN oil from the agronomic/chemical summary tables (rows end in Protein Oil Iodine),
    used only as a fallback for cells with no Table-65 per-location composite. Returns oil values
    (dry basis) for the given group. Multi-year means where the table is a multi-year summary."""
    path = _corrected_pdf(year)
    if not path:
        return []
    vals = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if "protein" not in t.lower() or "oil" not in t.lower():
                continue
            cur = None
            for ln in t.splitlines():
                g = _AGRO_GRP.search(ln)
                if g:
                    cur = g.group(1).upper()
                if cur != mg or not re.match(r"^[A-Za-z]", ln.strip()):
                    continue
                m = _AGRO_TRIPLET.search(ln.strip())
                if m:
                    prot, oil, iod = float(m.group(1)), float(m.group(2)), float(m.group(3))
                    if 30 <= prot <= 52 and 5 <= oil <= 30 and 100 <= iod <= 160:
                        vals.append(round(oil, 2))
    return vals


def main():
    if len(sys.argv) == 2:                                # year-batch mode
        year = int(sys.argv[1])
        df = extract_oil_year(year)
        print(f"{year}: {len(df)} oil rows across {df.Test.nunique() if len(df) else 0} tests")
        if len(df):
            print(df.groupby("Test").agg(rows=("Value_num", "size"),
                                         locs=("City", "nunique")).to_string())
        return
    year, code = int(sys.argv[1]), sys.argv[2]
    df = extract_oil(year, code)
    print(f"{year} {code}: {len(df)} oil rows, "
          f"{df[['City','State']].drop_duplicates().shape[0] if len(df) else 0} locs")
    if len(df):
        print(df.groupby(["City", "State"]).size().to_string())


if __name__ == "__main__":
    main()
