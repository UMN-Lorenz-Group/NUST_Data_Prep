"""Red-PDF test-caption parser — the LABEL ORACLE for the test map.

Every NUST test section is headed by its own code: `UNIFORM TEST III, 1984` (1960+) or
`UNIFORM TEST, GROUP III` (the 1941-1959 dialect). The Green XLSX carries clean structure but NO
labels, and `combine_nust_outputs.TEST_MAPS` assigns them POSITIONALLY (Nth tp2 marker -> Nth code),
which is what scrambles whole years. The PDF caption is the only source that states the label
directly, so it arbitrates between the Green and TEST_MAPS.

There are 11+ independent caption regexes in this repo and none of them is shared; this module is the
consolidation of the best parts of each:
  * OCR-tolerant MG alternation + `_MG_NORM`   <- stage1_processing/apply_patches_corpus_maturity_doy_via_ocr.py
  * despaced-header matching + extension guard <- extract_hand_audit_pages.test_patterns
    (OCR splits romans: 'III' -> 'I I I', so we strip whitespace before matching)
  * `GROUP` dialect                            <- 110_relabel_year.pdf_group_rosters
  * caption carry-forward across trait pages   <- analysis/scripts/Corpus_QC/verify_label_shift.pdf_sections
  * multi-year-summary rejection               <- 112_extract_pdf_perloc / 114

Measured caption yield (fraction of pages carrying a parseable caption):
    1970-1988  83-98%  (standard dialect)
    1960-1969  43-66%  (standard dialect + carry-forward)
    1941-1959   0%     with the standard regex -> ~40-56% with the GROUP dialect
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- caption grammar
# Matched against an UPPERCASED, WHITESPACE-STRIPPED header (OCR splits romans).
# MG alternation covers OCR corruption: 1/11/111 -> I/II/III, 1V/TV -> IV, O/OO -> 0/00.
# The trailing guard forbids only roman/subclass EXTENSION chars, so 'II' cannot match 'III'/'IIA'
# and '0' cannot match '00', while a trait word may still follow directly ('TESTIIASEEDSIZE').
# The trailing guard forbids BOTH extension chars (so 'II' != 'III'/'IIA', '0' != '00') AND any
# further letter. The letter half is essential: without it the front-matter line "IDENTIFICATION OF
# PARENT STRAINS ... Uniform Testing" despaces to 'UNIFORMTESTING' and matches TEST + MG 'I' (the
# 'NG' was allowed), inventing a phantom UT-I section on page 0 of 1971/1973/1974; likewise
# "APPENDIX: UNIFORM TEST I AND II" matched UT-I via 'AND'. A real caption is always followed by a
# separator or the year, never by more letters.
# The kind word is itself OCR-damaged in the worst years (1969 prints 'Frelininary Test 00' -> F for P,
# M read as N), so match it through the standard confusion classes rather than literally.
_UNI = r"UN[IL1]F[O0][RB][MN]"
_PRE = r"[PF][RB]E[L1I][IL1][MN][IL1][MN]ARY"
_CAP = re.compile(
    rf"(?:(?P<both>{_UNI}AND{_PRE})|(?P<pt>{_PRE})|(?P<ut>{_UNI}))"
    rf"(?:{_UNI})?"                              # 1944 phrasing 'PRELIMINARY UNIFORM TEST, GROUP IV'
    r"(?:SOYBEAN)?(?:TESTS?|GROUP)[.,]?"
    r"(?:GROUP)?[.,]?"
    r"(?:C[-.]?)?"                               # 1947 'GROUP C-IV' preliminary sub-series prefix
    r"(?P<mg>0{1,2}|1{1,3}[VY]?|I[VY]|[IV]+|TV|OO|O)(?P<sub>[AB]?)"
    r"(?![A-Z0-9])"
)
# GROUP-dialect fallback (1941-1959). The title line often runs straight into a descriptive sentence
# ("UNIFORM TEST. GROUP IV The Group IV test consisted...") so the strict `(?![A-Z0-9])` guard above
# rejects the real caption; and the preliminary sub-series prints "GROUP C-IV" where the dash is an
# em/en-dash the `C[-.]?` class misses (1947 PT-IV pg62/65). This pattern REQUIRES an explicit GROUP
# anchor (so the 'UNIFORMTESTING'/'UNIFORMTESTI' phantom, which has no GROUP, can never match it) and
# then guards only against MG-EXTENSION chars (I/V/Y/A/B/0), allowing a trailing descriptive word.
_DASH = r"[-.‐-―]"                     # hyphen, period, and the unicode dash block (‐‑‒–—―)
_CAP_GROUP = re.compile(
    rf"(?:(?P<both>{_UNI}AND{_PRE})|(?P<pt>{_PRE})|(?P<ut>{_UNI}))"
    rf"(?:{_UNI})?(?:SOYBEAN)?(?:TESTS?)?[.,]?"
    r"GROUP[.,]?"
    rf"(?:C{_DASH}?)?"
    r"(?P<mg>0{1,2}|1{1,3}[VY]?|I[VY]|[IV]+|TV|OO|O)(?P<sub>[AB]?)"
    r"(?![IVYAB0])"
)
# Appendix / cross-test summary pages carry a caption but are not their own test section.
_NOT_SECTION = re.compile(r"APPENDIX|BOTH TESTS|TESTS\s+[IVX]+\s+AND", re.I)
_MG_NORM = {
    "0": "0", "00": "00", "I": "I", "II": "II", "III": "III", "IV": "IV",
    "1": "I", "11": "II", "111": "III", "1V": "IV",
    "TV": "IV", "O": "0", "OO": "00", "IY": "IV", "1Y": "IV",  # OCR: V read as Y
}
VALID_MG = {"00", "0", "I", "II", "III", "IV"}
# A page that is a multi-year mean/summary is NOT its own test section. Covers digit ('2-year') and
# WORD ('Three year') counts, and year ranges whose dash OCR'd to */~/en/em/period ('1943*45', the 1945
# 'Three year sunmary, 1943*45' page that otherwise mis-parses as a phantom PT-IV under the GROUP
# fallback). A real section opener says "consisted of", never "N year summary".
_MULTIYEAR = re.compile(
    r"\b\d+\s*-?\s*YEARS?\b"
    r"|\b(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)[\s-]*YEARS?\b"
    r"|\b(19\d\d)\s*[-*~–—.]\s*(19\d\d|\d\d)\b",
    re.I)
# canonical NUST publication order: MG ascending, UT before PT within an MG
_MG_ORDER = {"00": 0.0, "0": 1.0, "I": 2.0, "II": 3.0, "III": 4.0, "IV": 5.0}
_KIND_ORDER = {"UT": 0, "PT": 1}


def canon_code(kind, mg, sub=""):
    return f"{kind}-{mg}{sub}"


def sort_key(code):
    m = re.match(r"^(UT|PT)-(00|0|I{1,3}V?|IV)([AB]?)$", code)
    if not m:
        return (99, 99, "")
    kind, mg, sub = m.groups()
    return (_MG_ORDER.get(mg, 9), _KIND_ORDER.get(kind, 9), sub)


def parse_caption(text):
    """First 3 lines of a page -> (code, sub) or None. Rejects multi-year-mean pages."""
    head = "\n".join(str(text or "").split("\n")[:3])
    if _MULTIYEAR.search(head) or _NOT_SECTION.search(head):
        return None
    ns = re.sub(r"\s+", "", head.upper())
    m = _CAP.search(ns)
    if not m or _MG_NORM.get(m.group("mg").upper()) not in VALID_MG:
        m = _CAP_GROUP.search(ns)   # GROUP-dialect fallback (trailing descriptive word / em-dash C-IV)
    if not m:
        return None
    mg = _MG_NORM.get(m.group("mg").upper())
    if mg is None or mg not in VALID_MG:
        return None            # OCR junk (e.g. 'XII', 'XV') -> not a caption
    if m.group("both"):
        # 1950s format: preliminary strains are reported in a combined "UNIFORM AND PRELIMINARY
        # TESTS, GROUP <mg>" table (1955 pp.38/59), which FOLLOWS that group's plain "UNIFORM TEST
        # GROUP <mg>". TEST_MAPS labels this section PT-<mg>, so that is the single code to emit.
        # (Post-1960 has no such combined caption, so this branch never fires there — no regression.)
        return canon_code("PT", mg, m.group("sub"))
    kind = "PT" if m.group("pt") else "UT"
    return canon_code(kind, mg, m.group("sub"))


# ---------------------------------------------------------------- roster
# leftmost name token before the first number (verify_label_shift.pdf_sections L37)
_ROW = re.compile(r"^\s*([A-Z][\w\-]*\d[\w\-]*|[A-Z][a-z]+[\w ]*?)\s+\d")


# Table footers look exactly like strain rows to _ROW ("Reps 4 4 3", "Date planted 5-19 ..."), so they
# leak into the roster and poison the overlap (1984 UT-I's PDF-vs-Green intersection was literally
# just {'REPS'}). Matched AFTER norm-folding, hence the 0/1 substitutions.
_FOOT = {"MEAN", "REPS", "R0WSP", "R0WSP1AT", "R0WSP1TT", "DATEP1ANTED", "DAYST0MATURE", "CV",
         "1SD", "LSD", "STRA1N", "AVERAGE", "RANGE", "GRAND", "C0EF", "TESTS", "R0WS", "P1AT"}


def norm_strain(s, strip_rank=True):
    s = re.sub(r"\s*\([^)]*\)", "", str(s))
    if strip_rank:
        # the Green (and some PDF pages) prefix the roster with a rank: "1. Elgin", "5. A80-149020".
        # 109.norm does NOT strip it, so 'Elgin' -> '1E1G1N' and the roster fails to match.
        s = re.sub(r"^\s*\d+\s*[.)]\s*", "", s)
    s = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return s.replace("O", "0").replace("L", "1").replace("I", "1")


def match_key(k):
    """Fold an ALREADY-normed key for roster COMPARISON only (never for identity): drop a leading
    digit-run left over from a rank prefix. Applied symmetrically to both sides."""
    return re.sub(r"^\d+", "", str(k)) or str(k)


def page_roster(text):
    out = set()
    for ln in str(text or "").split("\n"):
        m = _ROW.match(ln)
        if not m:
            continue
        n = norm_strain(m.group(1))
        if len(n) >= 4 and n not in _FOOT:
            out.add(n)
    return out


# ---------------------------------------------------------------- sections
def caption_sections(year, pdf_path=None):
    """-> ordered [{code, pages:[i..], roster:set, n_caption_pages}] for one year.

    Carry-forward: a trait page whose own caption OCR-failed inherits the last seen code (that is why
    43-66% caption yield still resolves a whole year). A run ENDS when a different code appears; a
    later re-appearance of the same code opens a NEW run, which the caller can then judge (a genuine
    repeat, e.g. 1957's two PT-IV blocks, vs OCR noise).
    """
    p = Path(pdf_path) if pdf_path else REPO / "input_files" / f"input_{year}" / f"{year}_done.pdf"
    if not p.exists():
        return []
    runs = []
    cur = None
    with pdfplumber.open(p) as pdf:
        for i, pg in enumerate(pdf.pages):
            t = pg.extract_text() or ""
            code = parse_caption(t)
            if code is not None:
                cur = code
                if not runs or runs[-1]["code"] != code:
                    runs.append({"code": code, "pages": [], "roster": set(), "n_caption_pages": 0})
                runs[-1]["n_caption_pages"] += 1
            if cur is None:
                continue                       # front matter before the first caption
            if not runs or runs[-1]["code"] != cur:
                runs.append({"code": cur, "pages": [], "roster": set(), "n_caption_pages": 0})
            runs[-1]["pages"].append(i)
            runs[-1]["roster"] |= page_roster(t)
    return runs


def _collapse_same(runs):
    out = []
    for r in runs:
        if out and out[-1]["code"] == r["code"]:
            out[-1]["pages"] += r["pages"]
            out[-1]["roster"] |= r["roster"]
            out[-1]["n_caption_pages"] += r["n_caption_pages"]
        else:
            out.append(dict(r))
    return out


def merge_noise_runs(runs, min_pages=1):
    """Collapse adjacent same-code runs, then drop runs whose code BREAKS canonical publication order
    on thin evidence -- those are caption misreads, not tests.

    NUST publishes strictly MG-ascending, UT before PT. So a code that goes BACKWARDS mid-sequence is
    impossible. 1969 is the case that forces this: its PT-00 captions are OCR-destroyed
    ('Frelininary Test 00', 'pezlix;::a?.y test cc') and one page prints 'Preliminary Test 11' -- an
    OCR of '00' that _MG_NORM legitimately reads as roman 'II' (the arabic->roman mapping is
    genuinely ambiguous here), inventing a PT-II between UT-00 and UT-0 in a year that has no PT-II.
    A single-page run that regresses the order loses to its neighbours.
    """
    runs = _collapse_same(runs)
    # A run carrying (almost) NO strains is a section's front matter (parentage/descriptive pages), not
    # a test -- it identifies nothing, since alignment is by roster. Fold those away FIRST: otherwise a
    # single misread page can SPLIT a real section in two and the LIS then prefers the junk. 1985:
    #   PT-IIA 68-70 (roster 1) | PT-II 71 (roster 1) | PT-IIA 72-86 (roster 35)
    # -> the real PT-IIA is 72-86; dropping the two roster-1 runs lets the halves rejoin, taking 1985
    # from a non-canonical 15 to the correct 13. A genuinely small test still has a real roster
    # (1984 UT-00 = 5, 1985 UT-00 = 13), so the threshold is safe.
    thin = []
    for r in runs:
        if len(r["roster"]) < 3 and thin:
            thin[-1]["pages"] += r["pages"]
            continue
        thin.append(dict(r))
    runs = _collapse_same(thin)
    # SANDWICH: one misread page inside a section splits it into `X | junk | X`. Absorb a short
    # intruder that sits between two runs of the SAME code. 1981:
    #   PT-IIIA 118-121 | PT-III 122 (1 captioned) | PT-IIIA 123-136
    # pages 118-136 are all PT-IIIA; p122's caption lost its 'A'. Without this the LIS actually
    # prefers the junk (PT-III then PT-IIIA is a longer increasing run than one PT-IIIA), keeping the
    # split and yielding 14 sections instead of 12.
    i = 0
    while i + 2 < len(runs):
        if runs[i]["code"] == runs[i + 2]["code"] and runs[i + 1]["n_caption_pages"] <= 1:
            runs[i]["pages"] += runs[i + 1]["pages"] + runs[i + 2]["pages"]
            runs[i]["roster"] |= runs[i + 1]["roster"] | runs[i + 2]["roster"]
            runs[i]["n_caption_pages"] += runs[i + 2]["n_caption_pages"]
            del runs[i + 1:i + 3]
            continue
        i += 1
    # Identify the intruders as the runs OUTSIDE the longest canonically-increasing subsequence.
    # A simple running-max test blames the wrong run: 1969's phantom PT-II jumps FORWARD, so every
    # genuine section after it (UT-0, PT-0, ...) looks like the regression instead.
    n = len(runs)
    keys = [sort_key(r["code"]) for r in runs]
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if keys[j] < keys[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(n), key=lambda x: best[x]) if n else -1
    lis = set()
    while i >= 0:
        lis.add(i)
        i = prev[i]
    keep = []
    for idx, r in enumerate(runs):
        if idx not in lis and r["n_caption_pages"] <= 1:
            if keep:                       # weakly-evidenced intruder -> fold into the previous run
                keep[-1]["pages"] += r["pages"]
                keep[-1]["roster"] |= r["roster"]
            continue
        keep.append(r)
    return [r for r in _collapse_same(keep) if len(r["pages"]) >= min_pages]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    years = [int(a) for a in sys.argv[1:]] or [1984]
    for y in years:
        runs = merge_noise_runs(caption_sections(y))
        codes = [r["code"] for r in runs]
        dup = [c for c in set(codes) if codes.count(c) > 1]
        order_ok = codes == sorted(codes, key=sort_key)
        print(f"\n=== {y}: {len(runs)} caption sections ===")
        for r in runs:
            print(f"   {r['code']:8} pages {r['pages'][0]:3}-{r['pages'][-1]:3} "
                  f"({len(r['pages']):2}p, {r['n_caption_pages']:2} captioned)  roster={len(r['roster'])}")
        print(f"   canonical order: {order_ok}   repeated codes: {dup if dup else 'none'}")
