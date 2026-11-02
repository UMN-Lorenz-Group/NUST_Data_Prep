#!/usr/bin/env python
"""
extract_sojabone_anchors.py
============================
Extract Maturity reference-strain anchor dates from the API-extracted
Sojabone xlsx files at `input_files/input_{year}/{year}-Sojabone (*-* OR).xlsx`
(or `Sojabone-{year} (*-* OR).xlsx`).

The Sojabone files preserve the per-loc Maturity table footer triplet
(Date planted / X matured / Days to mature) for years 1951-1969. For
years 1970+ the doc-AI extraction template dropped these rows, so the
extractor will produce 0 anchors for those years. Years 1941-1950 lack
a Sojabone xlsx entirely.

Output: emits or merges into
`analysis/data/yellow_standardized/Sojabone-{year}_yellow_standardized.xlsx`
on the `anchors` sheet, with Tier=`A` (per-loc dates, same confidence
as Yellow extracts).

Algorithm:
  1. Walk the Sojabone xlsx Sheet1 row by row.
  2. Track "group number" â€” incremented every time col A is "tp2" (each
     group is one Test, mapped to test_code via the year's
     `{year}_done_test_map.json`).
  3. Within each group, scan for sub-sections starting with `tpN` where
     the section title contains 'Maturity' (typically tp7 or tp8).
  4. In each such sub-section:
     - Find the Strain header row (col 0 = "Strain", col 1+ = city
       names like "Ontario Ottawa", "Wisconsin Ashland").
     - Find the "X matured" row (col A regex-match `^.+ matured`,
       excluding "Days to mature"). The cells in col B+ are
       datetime.datetime objects (with arbitrary year â€” month-day is
       what matters). Extract DOY.
  5. Cross-reference with `test_map.json` group_number -> test_code
     to attribute each anchor to a Test.
  6. Emit anchors per (Test, canonical_city) -> DOY.

Usage:
    uv run python fixes/extract_sojabone_anchors.py --year 1968
    uv run python fixes/extract_sojabone_anchors.py --years 1955,1956,...
    uv run python fixes/extract_sojabone_anchors.py --all
        (walks input_* folders, processes every year with a Sojabone xlsx)
"""
import argparse
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import openpyxl
import pandas as pd

_FIXES_DIR = Path(__file__).parent
_REPO_ROOT = _FIXES_DIR.parent
sys.path.insert(0, str(_FIXES_DIR))

from apply_patches_corpus_maturity_doy import (  # type: ignore
    canonicalize_city,
    DOY_LO, DOY_HI,
)

# The input_files/input_{year} folders live in the MAIN repo (not the worktree), so
# resolve _REPO_ROOT to the main checkout by walking up past any .claude/
# worktree segment.
def _find_main_repo(start: Path) -> Path:
    """Walk up from `start` until we find a directory containing input_*
    folders. Falls back to start if none found."""
    cur = start.resolve()
    while True:
        if any(p.is_dir() and p.name.startswith("input_files/input_") for p in cur.glob("input_*")):
            return cur
        if cur.parent == cur:
            return start
        cur = cur.parent

# The main repo is the parent-of-parent of .claude/worktrees/*/ â€” but more
# robustly: walk up until we find input_* folders. From a worktree at
# `<main>/.claude/worktrees/X/`, this lands on `<main>/`.
_REPO_INPUT_ROOT_GUESS = _REPO_ROOT
if ".claude" in str(_REPO_ROOT):
    # Find the parent of .claude/
    parts = _REPO_ROOT.parts
    for i, p in enumerate(parts):
        if p == ".claude":
            _REPO_INPUT_ROOT_GUESS = Path(*parts[:i])
            break

REPO_INPUT_ROOT = _find_main_repo(_REPO_INPUT_ROOT_GUESS)
OUT_DIR_DEFAULT = _REPO_ROOT / "analysis" / "data" / "yellow_standardized"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# "X matured" footer-row label patterns. Accepts:
#   "Hawkeye matured"           (full)
#   "Shelby mat."               (abbreviated, 1959-era)
#   "Hawkeye mat"               (no period)
#   "Wabash mat."               (abbreviated)
#   "Hawkeye mature."           (3-letter variation)
#   "Mandarin (Ottawa) matured."(trailing period)
#   "Date Gibson Matured"       (1942 "Date <strain> matured" prefix)
#   "Date Illini matured"       (1942)
#   "Richland Natured"          (1943 OCR M->N)
#   "Date Hatured"              (1943 OCR M->H)
# Pattern: optional "Date " prefix, then "<strain>" then
# "mat[ured]/nat[ured]/hat[ured]" with optional period.
# Caller MUST also check _DAYS_TO_MATURE_RE.
_MATURED_RE = re.compile(
    r"^(?:Date\s+)?(.+?)\s+[mnh]at[a-z]*\.?$", re.IGNORECASE
)
# "Date Matured (Illini)" — 1944 pattern where strain is in parens after.
_DATE_MATURED_PARENS_RE = re.compile(
    r"^Date\s+[mnh]at[a-z]*\s*\(([^)]+)\)\.?$", re.IGNORECASE
)
# "Days to mature" / "Da. to mat." / "Da. to ma." / "Days to Nature" /
# "Days to Maturity" companion row.
_DAYS_TO_MATURE_RE = re.compile(
    r"^(days?|da\.)\s+to\s+(ma|na|ha)(?:t|tur|ture|turity|ture)?\.?$",
    re.IGNORECASE,
)
# "Date planted" / "Date pltd." companion row.
_DATE_PLANTED_RE = re.compile(
    r"^date\s+pl(?:anted|td\.?|t\.?)?$", re.IGNORECASE
)
_MD_TEXT_RE = re.compile(r"^(\d{1,2})[-/](\d{1,2})(?:\.\d+)?\*?\+?$")

# Day-Month text formats like '15-Sep', '15 Sep', '15-September'.
# These appear when openpyxl falls back to text (e.g., if the Claude API
# rendered date cells as plain text rather than datetime, or if a future
# re-extraction does so). The cells we've seen in 1985-86 Sojabone are
# datetime objects with number_format='d-mmm', but other extractions may
# yield text equivalents.
_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}
_DD_MON_RE = re.compile(
    r"^(\d{1,2})[-\s/]+([A-Za-z]{3,9})\.?\*?\+?$", re.IGNORECASE
)
_MON_DD_RE = re.compile(
    r"^([A-Za-z]{3,9})\.?[-\s/]+(\d{1,2})\*?\+?$", re.IGNORECASE
)


def _norm(v) -> str:
    """Collapse all whitespace (including embedded newlines like
    "Carbondale\nIll." that some 1959-era OCR cells use) to single
    spaces, then strip leading/trailing whitespace."""
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _planted_doy(v, year) -> int | None:
    """Like cell_to_doy but accepts any in-year DOY (no maturity-range
    filter). Used by the cross-validation fallback where the Date planted
    cell is a May/June date (DOY 100-180) that cell_to_doy would reject.

    `year` is required: converting through a fixed non-leap reference year (this used
    2001) puts every post-February date 1 day early in a leap year."""
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        try:
            return date(int(year),v.month, v.day).timetuple().tm_yday
        except (ValueError, AttributeError):
            return None
    s = str(v).strip().rstrip("*+")
    m = _MD_TEXT_RE.match(s)
    if m:
        try:
            mo, da = int(m.group(1)), int(m.group(2))
            if not (1 <= mo <= 12 and 1 <= da <= 31):
                return None
            return date(int(year),mo, da).timetuple().tm_yday
        except ValueError:
            return None
    m = _DD_MON_RE.match(s)
    if m:
        mo = _MONTH_ABBR.get(m.group(2).lower())
        da = int(m.group(1))
        if mo and 1 <= da <= 31:
            try:
                return date(int(year),mo, da).timetuple().tm_yday
            except ValueError:
                return None
    m = _MON_DD_RE.match(s)
    if m:
        mo = _MONTH_ABBR.get(m.group(1).lower())
        da = int(m.group(2))
        if mo and 1 <= da <= 31:
            try:
                return date(int(year),mo, da).timetuple().tm_yday
            except ValueError:
                return None
    return None


def cell_to_doy(v, year) -> int | None:
    """Extract DOY from a cell that may be:
    - datetime.datetime / datetime.date (openpyxl native; covers cells
      formatted with 'd-mmm', 'm/d/yyyy', etc.)
    - 'M-D' / 'M/D' / 'M-D.f' string  (e.g., '9-15', '10-1.5')
    - 'DD-Mon' / 'DD Mon' / 'DD-Month' string (e.g., '15-Sep', '15 September')
    - 'Mon-DD' / 'Mon DD' / 'Month-DD' string (e.g., 'Sep-15')
    Returns None if not parseable or out of plausible range (200..330).
    """
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        try:
            doy = date(int(year),v.month, v.day).timetuple().tm_yday
        except (ValueError, AttributeError):
            return None
        return doy if DOY_LO <= doy <= DOY_HI else None
    s = str(v).strip().rstrip("*+")
    # M-D / M/D numeric
    m = _MD_TEXT_RE.match(s)
    if m:
        try:
            mo, da = int(m.group(1)), int(m.group(2))
            if not (1 <= mo <= 12 and 1 <= da <= 31):
                return None
            doy = date(int(year),mo, da).timetuple().tm_yday
        except ValueError:
            return None
        return doy if DOY_LO <= doy <= DOY_HI else None
    # DD-Mon text (e.g., '15-Sep', '15 September')
    m = _DD_MON_RE.match(s)
    if m:
        mo = _MONTH_ABBR.get(m.group(2).lower())
        da = int(m.group(1))
        if mo and 1 <= da <= 31:
            try:
                doy = date(int(year),mo, da).timetuple().tm_yday
            except ValueError:
                return None
            return doy if DOY_LO <= doy <= DOY_HI else None
    # Mon-DD text (e.g., 'Sep-15', 'September 15')
    m = _MON_DD_RE.match(s)
    if m:
        mo = _MONTH_ABBR.get(m.group(1).lower())
        da = int(m.group(2))
        if mo and 1 <= da <= 31:
            try:
                doy = date(int(year),mo, da).timetuple().tm_yday
            except ValueError:
                return None
            return doy if DOY_LO <= doy <= DOY_HI else None
    return None


def cell_to_md(v) -> str:
    """Render a cell as M-D string (for the AnchorDate_MD column)."""
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return f"{v.month}-{v.day}"
    s = str(v).strip().rstrip("*+")
    m = _MD_TEXT_RE.match(s)
    if m:
        return f"{int(m.group(1))}-{int(m.group(2))}"
    # DD-Mon
    m = _DD_MON_RE.match(s)
    if m:
        mo = _MONTH_ABBR.get(m.group(2).lower())
        if mo:
            return f"{mo}-{int(m.group(1))}"
    # Mon-DD
    m = _MON_DD_RE.match(s)
    if m:
        mo = _MONTH_ABBR.get(m.group(1).lower())
        if mo:
            return f"{mo}-{int(m.group(2))}"
    return ""


def looks_like_city(s: str) -> bool:
    """Reject Mean/Tests/blank/numeric headers + phenotype-label-prefixed
    cells. Accept compound state-city strings like 'Ontario Ottawa',
    'Wisconsin Ashland'."""
    if not s:
        return False
    s = s.strip()
    low = s.lower()
    # Reject summary columns
    if low.startswith("mean") or low in ("rank", "strain"):
        return False
    # Reject phenotype-label-prefixed cells. OCR sometimes merges a
    # phenotype column header ("Maturity") with the city name in the same
    # cell, producing junk like "Maturity Madison Wis" that would otherwise
    # canonicalize to "maturitymadison" — a non-existent F4U city.
    PHENO_PREFIXES = ("maturity ", "yield ", "lodging ", "height ",
                      "protein ", "oil ", "seed quality ", "seed size ",
                      "seed weight ")
    if any(low.startswith(p) for p in PHENO_PREFIXES):
        return False
    if re.match(r"^\d", s):
        return False
    # Must contain at least one letter
    return bool(re.search(r"[A-Za-z]{2,}", s))


_KNOWN_STATES = [
    "Alabama", "Arkansas", "California", "Colorado", "Delaware",
    "Florida", "Georgia", "Illinois", "Indiana", "Iowa", "Kansas",
    "Kentucky", "Louisiana", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Nebraska", "Nevada",
    "New Jersey", "New Mexico", "New York", "North Carolina",
    "North Dakota", "Ohio", "Oklahoma", "Pennsylvania", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Vermont", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming",
    "Oregon",  # was missing — 1959 "Ontario, Oregon" hit the gap
    "Idaho",   # 1946 "Aberdeen Idaho" was canonicalizing to 'aberdeenidaho'
    "Canada",  # 1946 "Ottawa Canada" was canonicalizing to 'ottawacanada'
              # ("Canada" used as the state when the city is in Ontario)
    "Can.", "Can",  # 1946 OCR may render "Ottawa Can." or "Ottawa Can"
    "Ont",          # 1965-era OCR may drop the period after "Ont."
    "Ontario", "Manitoba", "Quebec", "Saskatchewan", "Alberta",
    # Abbreviations and common partials (longest first matters)
    "Calif.", "Mass.", "Conn.", "Mich.", "Minn.", "Wisc.",
    "S. Dakota", "N. Dakota", "S Dakota", "N Dakota",
    "Cal.", "Cal",   # 1966 "Davis Cal.", "Five Points Cal." (California abbrev)
    "Wis.", "Ill.", "Ind.", "Neb.", "Iowa", "Mo.", "Pa.",
    "S.D.", "N.D.", "N.J.", "N.Y.", "N.C.", "S.C.",
    # Spaced variants: 1961 R1655 has "Jamesburg N. J." (space between
    # N. and J.). Without these the suffix-strip falls through.
    "N. J.", "N. J", "S. J.", "S. J",
    "N. Y.", "N. Y", "N. C.", "N. C", "S. C.", "S. C",
    "N. M.", "N. M", "N. H.", "N. H",
    "W. Va.", "W. Va",
    "Ont.", "Man.", "Sask.",
    # 1947-1969 era full state names + abbreviations the older formats use:
    "Del.", "Maine", "Mich.", "Ariz.", "Ark.", "Colo.", "Fla.", "Ga.",
    "Hawaii", "Ida.", "Kans.", "Kan.", "Ky.", "La.", "Md.", "Me.",
    "Miss.", "Mont.", "Nev.", "N.H.", "N.M.", "Okla.", "Ore.", "R.I.",
    "Tenn.", "Tex.", "Va.", "Vt.", "Wash.", "W.Va.", "Wyo.",
    "Ala.",
    # 4-letter abbreviations seen in 1953-1965 era (longer abbrevs that
    # the user-found "Lincoln Nebr." pattern revealed):
    "Nebr.", "Nebr", "Kans", "Mich", "Minn", "Wisc", "Wash", "Mass",
    "Conn", "Tenn", "Tex", "Okla", "Mont",
    "Ala", "Ariz", "Ark", "Colo", "Fla",
    "Iowa", "Iowa.",
    # 1943-era OCR errors in state abbreviations (user-flagged):
    # M -> N: "No." for "Mo." (Missouri), "Nass." for "Mass."
    # W -> V: "Vis." / "Vis" for "Wis." (Wisconsin)
    # M -> H: less common but observed
    "No.",                # "Columbia No." for Columbia Mo.
    "Vis.", "Vis",        # "Madison Vis." for Madison Wis.
    "Nass.", "Hass.",     # OCR variants for Mass.
    "Hich.", "Nich.",     # OCR variants for Mich.
    "Hinn.", "Ninn.",     # OCR variants for Minn.
    "Nebr,",              # comma typo
    # 1944 state patterns (user-flagged): "N. D" (space, no period),
    # "S.Dak.", "Dakota" full-word, "Iown" OCR variant.
    "N. D", "N. D.", "S. D", "S. D.", "S.Dak.", "N.Dak.", "S.Dak", "N.Dak",
    "Dakota", "Iown",
    # 1942/43 OCR variants of state names
    "Iova", "Iov", "Chio", "F.D.", "F. D.", "F. D", "Febr.",
    "Lo.", "Lio.",  # 1942/43 OCR for "Mo." (M -> L)
    # Parenthesized state spelling occasionally appears (e.g.
    # "Lincoln (Nebraska)" — defensive)
]
_KNOWN_STATES.sort(key=len, reverse=True)

# 2-letter postal abbreviations â€” used to detect/strip "City, ST" and
# "City ST" formats common in 1984+ Sojabone outputs.
_STATE_ABBR_2 = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "ON", "MB", "QC", "SK", "AB", "BC",  # Canadian provinces
}


_YEAR_PREFIX_RE = re.compile(r"^(\d{4})\s+(.+)$")


def parse_year_prefix(s: str) -> tuple[int | None, str]:
    """Detect '1947 Worthington Ind.' style year-prefix headers used in
    multi-year-comparison Sojabone summary tables. Returns (year, rest_of_city).
    If no year prefix, returns (None, s)."""
    if not s:
        return None, s
    m = _YEAR_PREFIX_RE.match(s.strip())
    if m:
        try:
            yr = int(m.group(1))
            if 1900 <= yr <= 2100:
                return yr, m.group(2).strip()
        except ValueError:
            pass
    return None, s


def parse_compound_city(s: str) -> str:
    """Strip state prefix or suffix from a compound city label.

    Examples:
        'Ontario Ottawa' -> 'Ottawa'             (state-first, 1965-69)
        'Ottawa Ontario' -> 'Ottawa'             (state-suffix, 1951-64)
        'Spooner Wis.'   -> 'Spooner'
        'Crookston, MN'  -> 'Crookston'          (comma + abbrev, 1984+)
        'Adelphia, NJ'   -> 'Adelphia'
        'Arlington WI'   -> 'Arlington'          (space + abbrev)
        'Manitoba Portage la P' -> 'Portage la P'
        'Carbondale\\nIll.' -> 'Carbondale'       (newline-separated, 1959 OCR)
        '1947 Worthington Ind.' -> 'Worthington'  (year-prefix multi-year, 1947)
        'Mean of 7 Tests' -> 'Mean of 7 Tests' (caller's looks_like_city
        rejects this)
    """
    # Collapse embedded newlines + multiple spaces (some 1959-era OCR
    # cells store "City\nState" with a literal newline character).
    s = re.sub(r"\s+", " ", s).strip()
    # Strip leading year ("1947 Worthington Ind." -> "Worthington Ind.")
    _, s = parse_year_prefix(s)
    # Strip parenthesized state-name suffix ("Lincoln (Nebraska)" -> "Lincoln")
    s = re.sub(r"\s*\([^)]+\)\s*$", "", s).strip()
    # Strip trailing footnote digit on city headers — 1966 R97 etc. uses
    # "Concord Nebr.1", "Davis Cal.1", "Five Points Cal.1" where the
    # ".1" / " 1" is a footnote indicator, not part of the city name.
    # Be conservative: only strip a single digit at the very end, with
    # an optional leading space or directly after a period.
    s = re.sub(r"(?:(?<=\.)|(?<= ))\d$", "", s).strip()
    # Normalize comma+state to space+state ("Prosser, Wash." ->
    # "Prosser Wash.") so the multi-char state-suffix logic below catches
    # 3-4-5-letter abbreviations. The 2-letter comma case is handled
    # directly by the regex below.
    s_no_comma = re.sub(r",\s+", " ", s).strip().rstrip(",").strip()

    # Merged-cell detection: OCR sometimes runs two city headers into a
    # single cell, e.g. 1947 Block 1 R380 col 4 = "Columbus Ohio St. Paul
    # Minn." (Columbus Ohio + St. Paul Minn. merged). Detect by finding
    # the FIRST known state-suffix match — if there's still another state
    # word after it in the remainder, the cell has multiple cities; keep
    # only the leading city.
    def _first_state_split(text: str) -> str | None:
        for sp in _KNOWN_STATES:
            for sep in (" " + sp + " ", " " + sp + ". "):
                idx = text.find(sep)
                if idx > 0:
                    rest = text[idx + len(sep):]
                    # If rest also contains a state suffix => merged cell
                    for sp2 in _KNOWN_STATES:
                        if (rest.endswith(" " + sp2) or rest.endswith(" " + sp2 + ".")
                                or (" " + sp2 + " ") in rest or (" " + sp2 + ". ") in rest):
                            return text[:idx].strip()
        return None
    _split = _first_state_split(s)
    if _split:
        # Recurse on the first-city portion to strip its trailing state
        return parse_compound_city(_split)

    # Drop trailing 2-letter state abbreviation (with or without comma):
    # "Crookston, MN", "Arlington WI", "Adelphia, NJ"
    m = re.match(r"^(.+?)[,\s]+([A-Z]{2})\.?\s*$", s)
    if m and m.group(2) in _STATE_ABBR_2:
        return m.group(1).strip().rstrip(",")

    # Try suffix strip â€” known state names (1951-64 era).
    # Use the comma-normalized form so "Prosser, Wash." -> "Prosser Wash."
    # -> matches " Wash." suffix. Also rstrip comma from result.
    def _clean(out: str) -> str:
        return out.strip().rstrip(",").rstrip(".").strip()
    for sp in _KNOWN_STATES:
        for cand in (s_no_comma, s):
            if cand.endswith(" " + sp):
                return _clean(cand[:-(len(sp) + 1)])
            if cand.endswith(" " + sp + "."):
                return _clean(cand[:-(len(sp) + 2)])
    # Then prefix strip (1965-69 era format)
    for sp in _KNOWN_STATES:
        if s.startswith(sp + " "):
            return _clean(s[len(sp):])
        if s.startswith(sp + "."):
            return _clean(s[len(sp) + 1:])
    return s


def _normalize_test_code(t: str) -> str:
    """Normalize a Test code to the canonical form used in F4U
    phenotypesTable1.csv.

    The 1957-1962 test_maps used 'UPT-' (Uniform Preliminary Test) but the
    F4U pipeline normalizes these to plain 'PT-'. Also strip whitespace and
    uppercase MG portion."""
    if not t:
        return ""
    t = t.strip()
    # 'UPT-XYZ' -> 'PT-XYZ'
    if t.upper().startswith("UPT-"):
        t = "PT-" + t[4:]
    return t


def _f4u_test_list(year: int) -> list[str]:
    """Return the F4U-derived Test list for a year, sorted in canonical
    NUST publication order: by MG ascending, with UT before PT within
    each MG (matching the order tests appear in the printed bulletin)."""
    f4u = REPO_INPUT_ROOT / f"output_files/output_{year}" / f"combined_{year}_phenotypesTable.csv"
    if not f4u.exists():
        return []
    try:
        df = pd.read_csv(f4u, dtype=str, usecols=["Test"])
    except Exception:
        return []
    tests = df["Test"].dropna().unique().tolist()
    # Sort by (MG_order, kind_order, name). MG order goes 00 < 0 < I < II < III < IV.
    # Within a MG, UT (0) before PT (1). Suffixed variants (IIA < IIB, IIIA < IIIB)
    # follow the parent.
    MG_ORDER = {"00": 0.0, "0": 1.0,
                "I":   2.0, "IA": 2.1, "IB": 2.2,
                "II":  3.0, "IIA": 3.1, "IIB": 3.2,
                "III": 4.0, "IIIA": 4.1, "IIIB": 4.2,
                "IV":  5.0, "IVA": 5.1, "IVB": 5.2}
    KIND_ORDER = {"UT": 0, "PT": 1, "Group": 2}
    def sort_key(t):
        m = re.match(r"^(UT|PT|Group)[-_](.+)$", t)
        if not m:
            return (99, 99, t)
        kind = m.group(1)
        mg = m.group(2)
        return (MG_ORDER.get(mg, 99), KIND_ORDER.get(kind, 99), t)
    tests.sort(key=sort_key)
    return tests


def load_test_map(year: int) -> list[dict]:
    """Load `input_files/input_{year}/{year}_done_test_map.json` and return groups list,
    or [] if missing/malformed. Test codes are normalized via
    _normalize_test_code() to match the F4U convention.

    Fallback: if the JSON is missing OR has fewer entries than the F4U has
    distinct Tests, derive the list from F4U sorted by MG ascending with
    UT before PT within each MG (matches NUST publication group order).
    The F4U-derived list is more complete than many test_map.json files
    which historically omitted Preliminary Tests.
    """
    f4u_tests = _f4u_test_list(year)

    f = REPO_INPUT_ROOT / f"input_files/input_{year}" / f"{year}_done_test_map.json"
    json_groups: list[dict] = []
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for g in data.get("groups", []):
                g["test_code"] = _normalize_test_code(g.get("test_code", ""))
                json_groups.append(g)
        except Exception:
            pass

    # Prefer F4U fallback if it has more Tests than the test_map (which is
    # common â€” e.g. 1955 test_map has 4 UTs but F4U has 4 UTs + 2 PTs).
    if json_groups and len(json_groups) >= len(f4u_tests):
        return json_groups
    if not f4u_tests:
        return json_groups  # nothing better than the JSON, use it as-is
    return [{"group_number": i + 1, "test_code": t} for i, t in enumerate(f4u_tests)]


def _composite_header(rows: list, hdr_idx: int) -> list[str]:
    """Build a per-column header by merging hdr_idx and hdr_idx+1.

    1947-style summary tables put 'Strain' in col 0 of one row and the
    city names (Walkerton Ind., Spooner Wis., etc.) in the NEXT row
    under each non-strain column. Merging them gives us the city per
    column. If a column has values in both rows, the later (city) one
    wins for non-col-0 positions; col 0 stays "Strain".
    """
    if hdr_idx < 0 or hdr_idx >= len(rows):
        return []
    r0 = rows[hdr_idx] or ()
    r1 = rows[hdr_idx + 1] if hdr_idx + 1 < len(rows) else ()
    r1 = r1 or ()
    n = max(len(r0), len(r1))
    out = []
    for c in range(n):
        v0 = _norm(r0[c]) if c < len(r0) and r0[c] is not None else ""
        v1 = _norm(r1[c]) if c < len(r1) and r1[c] is not None else ""
        # For col 0: keep "Strain" if present
        if c == 0:
            out.append(v0 if v0 else v1)
            continue
        # For other cols: prefer the one that looks like a city
        if v1 and (not v0 or looks_like_city(v1)):
            out.append(v1)
        elif v0:
            out.append(v0)
        else:
            out.append(v1)
    return out


# Strain-name abbreviation aliases. Sojabone matured-row labels often
# abbreviate strain names (e.g., "Hawk. mat." for "Hawkeye matured" in
# 1958 R781). Map abbreviated canonical -> full canonical so the
# strain_to_tests lookup can find a match.
_STRAIN_ALIASES = {
    "hawk":      "hawkeye",     # "Hawk. mat." (1958)
    "linc":      "lincoln",
    "rich":      "richland",
    "wab":       "wabash",
    "gib":       "gibson",
    "mand":      "mandarin",
    # Mandarin (Ottawa) is a distinct variety from plain Mandarin. The
    # ref row often uses "Mandarin (Ott.)" while the matured row uses
    # "Mand. (Ott.) matured" -- after paren+space+dot stripping these
    # would land at different canonical keys; fold them all into one.
    "mandott":         "mandarinottawa",   # "Mand. (Ott.)"
    "mandotta":        "mandarinottawa",
    "mandottawa":      "mandarinottawa",   # "Mand. (Ottawa)"
    "mandarinott":     "mandarinottawa",   # "Mandarin (Ott.)" (1947+1948+1949)
    "mandarinotta":    "mandarinottawa",   # OCR variant
    "mandarinott awa": "mandarinottawa",   # defensive against OCR spaces
    "chipp":     "chippewa",
    "chip":      "chippewa",
    "cors":      "corsoy",
    "corsoy79":  "corsoy",
    "elgin87":   "elgin",
    "clark63":   "clark",
    "harosoy63": "harosoy",       # "Harosoy 63" (1964+)
    "har63":     "harosoy",       # "Har. 63 mat." (1964 Block 1, 1967 Block 1)
    "chippewa64": "chippewa",     # "Chippewa 64" (1966 Block 2)
    "chip64":    "chippewa",      # "Chip. 64 mat." (1966 Block 1)
    "fortage":   "portage",       # 1969 Block 3 OCR P->F in matured row
    "meritt":    "merit",         # 1970 R549 OCR "Meritt" (double t)
    "hodgson78": "hodgson",
    "cutler71":  "cutler",
}


def _canon_strain(s: str) -> str:
    """Canonicalize a strain name for cross-source matching.
    Strips: parenthetical MG annotation, leading "N. " enumeration,
    spaces, punctuation, hyphens, " matured" suffix, case-folds.
    Applies _STRAIN_ALIASES to map abbreviations to full forms.
    Examples:
        'Hodgson 78 (I)' -> 'hodgson78' -> 'hodgson'
        'Mand. (Ott.)' -> 'mandott' -> 'mandarinottawa'
        'Hawk.' -> 'hawk' -> 'hawkeye'
        'Mandarin(Ottawa)' -> 'mandarinottawa'
    """
    if not s:
        return ""
    s = re.sub(r"\bmatured?\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\d+\.\s*", "", s)  # strip "3. " enum
    s = re.sub(r"[^A-Za-z0-9]", "", s)
    s = s.lower()
    return _STRAIN_ALIASES.get(s, s)


def _build_f4u_ref_strain_map(year: int) -> dict[str, str]:
    """Read F4U Maturity rows; for each Test, find the Strain whose
    Maturity Value == '0' most often (the reference strain). Returns
    {test_code: strain_name}. Used to attribute Sojabone matured rows
    to the correct Test independent of group_idx ordering.

    User-observed pattern (1947): "the only '0' valued row under the
    Maturity column points to the check". The strain with the most
    '0' cells per Test is the reference.
    """
    f4u_path = REPO_INPUT_ROOT / f"output_files/output_{year}" / f"combined_{year}_phenotypesTable.csv"
    if not f4u_path.exists():
        return {}
    try:
        df = pd.read_csv(f4u_path, dtype=str,
                         usecols=["Test", "Strain", "Phenotype", "Value"])
    except Exception:
        return {}
    mat = df[df["Phenotype"] == "Maturity"]
    if mat.empty:
        return {}
    # Count '0' cells per (Test, Strain)
    zero_counts: dict[tuple[str, str], int] = {}
    for _, row in mat.iterrows():
        v = row["Value"]
        if v is None or pd.isna(v):
            continue
        sv = str(v).strip()
        if sv in ("0", "0.0", "0.00", ".0"):
            t = str(row["Test"]).strip()
            s = str(row["Strain"]).strip()
            zero_counts[(t, s)] = zero_counts.get((t, s), 0) + 1
    # For each Test, pick the Strain with the most '0' cells, but only
    # commit to it if the lead is UNAMBIGUOUS. User caution flag (1982
    # tp8 R1909-1931): multiple strains can have several '0' cells when
    # non-ref strains happen to mature on the same date as the ref at
    # several cities. Heuristic:
    #   - Leader must have >= 3 '0' cells, AND
    #   - Leader must have strictly more than 2x the runner-up's count
    # Otherwise leave the Test unmapped, so Pass 1 falls back to
    # group_idx attribution.
    by_test: dict[str, list[tuple[str, int]]] = {}
    for (t, s), n in zero_counts.items():
        by_test.setdefault(t, []).append((s, n))
    test_to_ref: dict[str, str] = {}
    for t, candidates in by_test.items():
        candidates.sort(key=lambda x: -x[1])
        if not candidates or candidates[0][1] < 3:
            continue
        if len(candidates) > 1 and candidates[1][1] * 2 >= candidates[0][1]:
            continue
        test_to_ref[t] = candidates[0][0]
    return test_to_ref


def find_sojabone_xlsx(year: int) -> Path | None:
    """Return the FIRST Sojabone xlsx for a year (back-compat single-file
    callers). Prefer find_sojabone_xlsx_all() to get all files."""
    paths = find_sojabone_xlsx_all(year)
    return paths[0] if paths else None


def find_sojabone_xlsx_all(year: int) -> list[Path]:
    """Find ALL Sojabone xlsx files for a year. Many years (1972, 73,
    74, 77-86) split the bulletin into two halves (e.g.
    "Sojabone-1982 (1-115 OR).xlsx" + "Sojabone-1982 (116-211 OR).xlsx").
    Returns the list sorted by page-range start so order is deterministic.
    1941-1950 use a nested `input_files/input_{year}/{year}/` subfolder."""
    folder = REPO_INPUT_ROOT / f"input_files/input_{year}"
    if not folder.exists():
        return []
    found: list[Path] = []
    for search_dir in (folder, folder / str(year)):
        if not search_dir.exists():
            continue
        for p in search_dir.glob("*.xlsx"):
            if p.name.endswith(".orig_extra_tp2"):
                continue
            # Skip supplemental injury/disease files (e.g.
            # "Sojabone-1977 (138-143 OR)_Soybean Injury.xlsx" â€” has no
            # standard tp1/tp2 main-table layout, just descriptive text).
            if "_" in p.stem.split(" ")[-1] or "injury" in p.name.lower():
                continue
            found.append(p)
    # Sort by first page-range start. Filename format:
    # "Sojabone-YYYY (start-end OR).xlsx" or "YYYY-Sojabone (start-end OR).xlsx"
    def _page_start(p: Path) -> int:
        m = re.search(r"\((\d+)\s*-\s*\d+\s*OR\)", p.name)
        return int(m.group(1)) if m else 0
    found.sort(key=_page_start)
    return found


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def extract_anchors_from_sojabone(year: int) -> list[dict]:
    """Walk the Sojabone xlsx(s) for year; emit anchor rows.

    Many years (1972, 73, 74, 77-86) split the bulletin into two
    Sojabone xlsx files (e.g. pages 1-115 and 116-211). All files are
    processed in page order with continuous group_idx counting across
    file boundaries.

    Strategy: find every "X matured" row directly. For each one, look
    UPWARD (within ~100 rows) for the most recent "Strain" header row
    that gives the city columns. Group attribution: count tp2 markers
    that appeared before this matured row â€” that's the group_idx.

    This avoids fragile dependence on tp marker labels (e.g., 1951's
    tp8 markers lack a "Maturity" sub-label).
    """
    xps = find_sojabone_xlsx_all(year)
    if not xps:
        print(f"  {year}: no Sojabone xlsx")
        return []
    groups = load_test_map(year)
    if not groups:
        print(f"  {year}: no test_map.json; cannot attribute Tests")
        return []

    # Load all Sojabone files in page-range order and concatenate their
    # Sheet1 rows. Track which source file each row came from for the
    # anchor's `Source` field.
    rows: list = []
    file_of_row: list[str] = []
    for xp in xps:
        try:
            wb = openpyxl.load_workbook(xp, data_only=True, read_only=True)
            ws = wb["Sheet1"]
            file_rows = list(ws.iter_rows(values_only=True))
            wb.close()
        except Exception as e:
            print(f"  {year}: cannot read {xp.name}: {e}")
            continue
        rows.extend(file_rows)
        file_of_row.extend([xp.name] * len(file_rows))
    if not rows:
        return []
    xp = xps[0]  # for the default Source label when file_of_row is short

    # Pre-compute group_idx for each row: count "tp2" markers up to and
    # including this row (minus 1 since group_idx is 0-based).
    group_idx_at: list[int] = []
    g = -1
    for r in rows:
        if r and r[0] is not None and _norm(str(r[0])).startswith("tp2"):
            g += 1
        group_idx_at.append(g)

    # Pre-compute most recent "Strain" header row idx before each row idx.
    # A Strain header has col A == "Strain" (exactly) and at least 3 non-empty
    # subsequent cells.
    last_strain_at: list[int] = []
    last = -1
    for i, r in enumerate(rows):
        if r and r[0] is not None and _norm(str(r[0])).lower() == "strain":
            n_non_empty = sum(1 for c in r[1:] if c is not None and _norm(c))
            if n_non_empty >= 2:
                last = i
        last_strain_at.append(last)

    # Pre-compute which rows are "tp8 MATURITY" markers (or close variants)
    # so we know which tp-sections to look inside. For older formats with no
    # tp label, the tp_section boundary is just every tp marker; we'll
    # check each strain row in those sections too.
    tp_rows = []  # list of (i, label) for every "tpN..." marker
    for i, r in enumerate(rows):
        if r and r[0] is not None:
            a0 = _norm(str(r[0]))
            if re.match(r"^tp\d+[a-z]?", a0):
                label = _norm(r[1] if len(r) > 1 and r[1] is not None else "")
                tp_rows.append((i, label))
    # tp_label_at[i] = the label of the tp section that row i is inside
    tp_label_at = [""] * len(rows)
    for j, (tp_i, tp_label) in enumerate(tp_rows):
        end = tp_rows[j + 1][0] if j + 1 < len(tp_rows) else len(rows)
        for k in range(tp_i, end):
            tp_label_at[k] = tp_label

    # F4U-based reference-strain map: (Test, RefStrain) pairs identified
    # by searching the F4U for Maturity Value == "0". The strain with the
    # most '0' cells in a Test is its reference. Used to attribute matured
    # rows to the correct Test when group_idx-based attribution is
    # ambiguous (e.g. 1947 has 4 Sojabone groups all named "Mand. (Ott.)
    # matured" but they belong to UT-0, PT-0, UT-I, PT-I per F4U).
    f4u_ref_strains = _build_f4u_ref_strain_map(year)
    # Inverse: canonical_strain_name -> set of Tests that use it
    strain_to_tests: dict[str, set[str]] = {}
    for tc, ref in f4u_ref_strains.items():
        strain_to_tests.setdefault(_canon_strain(ref), set()).add(tc)

    # MG-sibling broadcast: if a ref strain is mapped to UT-X, also map
    # it to PT-X / UPT-X (same maturity group). Closes 1969 Block 3-era
    # gap where _build_f4u_ref_strain_map's ambiguity filter dropped
    # PT-00 (because PT-00's zero-cell candidates were close in count)
    # while UT-00 was confidently mapped to Portage. By broadcasting
    # across MG siblings, the Portage matured-row anchors flow to PT-00
    # too -- safe because UT/PT/UPT siblings share planting sites by
    # convention so the calendar dates are interchangeable.
    #
    # Fallback: when test_map.json has MG=None (e.g. 1963 has it as
    # None for every test), derive MG from the test_code suffix
    # (UT-00 -> "00", PT-IV -> "IV", etc.). Without this, 1963 PT-00
    # Acme matured anchors stayed siloed in UT-00 only.
    def _mg_from_tc(tc: str | None) -> str | None:
        if not tc:
            return None
        m = re.search(r"-([0O]+|I+V?|VI*|[A-Z]+)\s*$", str(tc).upper())
        return m.group(1) if m else None
    mg_of_test = {g.get("test_code"): (g.get("maturity_group")
                                        or _mg_from_tc(g.get("test_code")))
                  for g in groups if g.get("test_code")}
    mg_to_tests: dict[str, set[str]] = {}
    for tc, mg in mg_of_test.items():
        if mg:
            mg_to_tests.setdefault(str(mg), set()).add(tc)
    for canon, tests in list(strain_to_tests.items()):
        siblings: set[str] = set()
        for t in tests:
            mg = mg_of_test.get(t)
            if mg:
                siblings |= mg_to_tests.get(str(mg), set())
        strain_to_tests[canon] |= siblings

    anchors: list[dict] = []
    # --- Pass 1: "X matured" footer row (1951-1969 format) ---
    # Now uses F4U-derived strain-to-test map for attribution (more
    # accurate than group_idx for years where multiple groups share the
    # same reference strain).
    seen_tier_a_pass1: set[tuple[str, str]] = set()
    for i, r in enumerate(rows):
        if not r or r[0] is None:
            continue
        a0 = _norm(str(r[0]))
        # Try "Date Matured (X)" pattern FIRST — extracts strain from
        # parens. Otherwise fall through to the standard "<strain> matured"
        # regex.
        pm = _DATE_MATURED_PARENS_RE.match(a0)
        if pm:
            ref_strain = pm.group(1).strip()
        else:
            m = _MATURED_RE.match(a0)
            if not m:
                continue
            if _DAYS_TO_MATURE_RE.match(a0):
                continue
            if _DATE_PLANTED_RE.match(a0):
                continue
            ref_strain = m.group(1).strip()
            # Strip a leading "Date " if the regex picked it up via the
            # optional prefix — defensive: regex usually consumes it.
            if ref_strain.lower().startswith("date "):
                ref_strain = ref_strain[5:].strip()
            # Skip degenerate "Date matured" / "Days matured" rows that
            # have no actual strain name (the regex falls back to treating
            # "Date" as the strain). Real strains shouldn't be just
            # "Date" / "Days" / "Day".
            if ref_strain.lower() in {"date", "days", "day"}:
                continue
        # Try F4U-strain mapping FIRST (handles cross-MG comparator usage).
        ref_canon = _canon_strain(ref_strain)
        target_tests = list(strain_to_tests.get(ref_canon, set()))
        # ALSO union in the block's own test via group_idx AND its
        # MG-siblings — covers the case where _build_f4u_ref_strain_map
        # ambiguity-filtered or omitted the block's Test entirely (e.g.
        # 1963 PT-00 / UT-00 weren't in the F4U ref map at all because
        # the F4U had its Maturity=0 cells patched in earlier rounds;
        # without MG-sibling broadcast on the group_idx fallback, Acme
        # matured anchors only went to one test instead of UT-00+PT-00).
        gidx = group_idx_at[i]
        if 0 <= gidx < len(groups):
            tc = groups[gidx].get("test_code", "")
            if tc and tc not in target_tests:
                target_tests.append(tc)
            # Add MG-siblings of the block's test
            mg_self = mg_of_test.get(tc) if tc else None
            if mg_self:
                for sib in mg_to_tests.get(str(mg_self), set()):
                    if sib not in target_tests:
                        target_tests.append(sib)
        if not target_tests:
            continue
        hdr_idx = last_strain_at[i]
        # Allow up to 100 rows between Strain header and matured-row /
        # ref-strain-row. 1947-style summary tables have 40-50 strain rows
        # between header and footer. Stricter limit caused false negatives
        # for PT-0 / PT-I attribution. Still constrained to same tp2 group.
        if hdr_idx < 0 or i - hdr_idx > 100:
            continue
        # Header must be inside the same group (tp2-bounded)
        if group_idx_at[hdr_idx] != group_idx_at[i]:
            continue
        header = _composite_header(rows, hdr_idx)
        n_cols = min(len(r), len(header))
        # Cross-validation fallback: find the Date planted row above + the
        # Days to mature row below within this same block, in case any
        # matured-row cell fails to parse (e.g. 1946 R1713 col 8 has
        # literal '9/31' — Sept 31 doesn't exist; the original PDF entry
        # is a transcription typo. planted 5/23 + 121 days = 9/21).
        planted_idx_xv = -1
        days_idx_xv = -1
        for j in range(i - 1, max(i - 30, -1), -1):
            if group_idx_at[j] != group_idx_at[i]:
                break
            rj = rows[j]
            if not rj or rj[0] is None:
                continue
            aj = str(rj[0]).strip()
            if _DATE_PLANTED_RE.match(aj):
                planted_idx_xv = j
                break
        for j in range(i + 1, min(i + 30, len(rows))):
            if group_idx_at[j] != group_idx_at[i]:
                break
            rj = rows[j]
            if not rj or rj[0] is None:
                continue
            aj = str(rj[0]).strip()
            if _DAYS_TO_MATURE_RE.match(aj):
                days_idx_xv = j
                break

        for c in range(1, n_cols):
            city_raw = header[c]
            if not looks_like_city(city_raw):
                continue
            # Year-prefix filter: cells like "1946 Worthington Ind." in a
            # 1947 Sojabone summary table are HISTORICAL comparison cells,
            # not 1947 single-year data. Skip if prefix year != current year.
            cell_year, _city_stripped = parse_year_prefix(city_raw)
            if cell_year is not None and cell_year != year:
                continue
            doy = cell_to_doy(r[c], year)
            xv_used = False
            if doy is None:
                # Cross-validation: planted_doy + days_to_mature == matured_doy
                # Only fires when the matured cell is missing/garbled but
                # both planted and days values are present and sane.
                # (e.g. 1946 R1713 col 8 has literal '9/31' transcription
                # typo; planted=5/23 + days=121 -> matured=9/21.)
                if (planted_idx_xv >= 0 and days_idx_xv >= 0
                        and c < len(rows[planted_idx_xv])
                        and c < len(rows[days_idx_xv])):
                    pd_cell = rows[planted_idx_xv][c]
                    days_cell = rows[days_idx_xv][c]
                    planted_doy = _planted_doy(pd_cell, year)  # accepts May/June dates
                    days_val = None
                    if days_cell is not None:
                        try:
                            days_val = int(float(str(days_cell).strip()))
                        except (ValueError, TypeError):
                            days_val = None
                    if (planted_doy is not None and days_val is not None
                            and 60 <= days_val <= 200):
                        cand = planted_doy + days_val
                        if DOY_LO <= cand <= DOY_HI:
                            doy = cand
                            xv_used = True
            if doy is None:
                continue
            city_clean = parse_compound_city(city_raw)
            city_canon = canonicalize_city(city_clean)
            # Dual-emit: when the Sojabone city has a "Mt." / "Mt " prefix
            # (e.g. 1943 R Mt. Morris Ill.), ALSO emit under the stripped
            # canon so the F4U cell (which may have dropped the "Mt."
            # prefix in some years) still matches.
            secondary_canon = None
            _stripped = re.sub(r"^[Mm]t\.?\s+", "", city_clean).strip()
            if _stripped and _stripped != city_clean:
                _sec = canonicalize_city(_stripped)
                if _sec and _sec != city_canon:
                    secondary_canon = _sec
            for test_code in target_tests:
                for cc_emit in (city_canon,) + ((secondary_canon,) if secondary_canon else ()):
                    key = (test_code, cc_emit)
                    if key in seen_tier_a_pass1:
                        continue
                    seen_tier_a_pass1.add(key)
                    anchor_md = cell_to_md(r[c]) if not xv_used else ""
                    if xv_used:
                        # Compute the M-D form from the recovered DOY for the
                        # AnchorDate_MD field (so the standardized xlsx records
                        # the corrected calendar date, not the typo).
                        from datetime import date as _d, timedelta as _td
                        _dt = _d(year, 1, 1) + _td(days=doy - 1)
                        anchor_md = f"{_dt.month}-{_dt.day}"
                    anchors.append({
                        "Test": test_code,
                        "City": city_clean,
                        "City_canon": cc_emit,
                        "State": "",
                        "RefStrain": ref_strain,
                        "AnchorDate_MD": anchor_md,
                        "AnchorDOY": int(doy),
                        "Tier": "A",
                        "Source": (f"Sojabone-xv:{file_of_row[i] if i < len(file_of_row) else xp.name}"
                                   if xv_used else
                                   f"Sojabone:{file_of_row[i] if i < len(file_of_row) else xp.name}"),
                    })

    # --- Pass 2: in-table reference strain row (1981-1988 format) ---
    # In tp8 MATURITY sections, the reference strain row has its col B+
    # filled with datetime objects (absolute dates) while other strain rows
    # have integer offsets. We detect any strain row where >=3 cells in
    # col B+ are datetime/date instances (or M-D text), and use it as
    # the reference.
    for i, r in enumerate(rows):
        if not r or r[0] is None:
            continue
        a0 = _norm(str(r[0]))
        # Skip if this row is itself a tp/header/footer marker, or
        # blank-strain, or already a matured row.
        if not a0 or a0.startswith("tp") or a0.lower() == "strain":
            continue
        if _MATURED_RE.match(a0) or _DAYS_TO_MATURE_RE.match(a0):
            continue
        if _DATE_PLANTED_RE.match(a0):
            continue
        # Only consider rows inside a tp section whose label contains
        # "maturity" (case-insensitive). For old years with unlabeled tp,
        # be permissive: also accept empty labels but only if the row's
        # col B+ has at least 3 datetime cells in the Sept-Oct range.
        tp_lab = tp_label_at[i].lower()
        has_mat_label = "maturity" in tp_lab or "matured" in tp_lab
        # Count date cells in col B+. A cell qualifies if it's:
        # (a) datetime.datetime/date with month 7-12, OR
        # (b) 'M-D' / 'M/D' text with month 7-12, OR
        # (c) 'DD-Mon' / 'Mon-DD' text where Mon is Jul-Dec
        # Sanity-check: month 7-12 (July-December) to exclude May/June
        # "Date planted" rows.
        n_date = 0
        for c in r[1:]:
            if isinstance(c, (datetime, date)):
                if 7 <= c.month <= 12:
                    n_date += 1
                continue
            if c is None:
                continue
            s = str(c).strip().rstrip("*+")
            mo = None
            mm = _MD_TEXT_RE.match(s)
            if mm:
                mo = int(mm.group(1))
            else:
                mm = _DD_MON_RE.match(s)
                if mm:
                    mo = _MONTH_ABBR.get(mm.group(2).lower())
                else:
                    mm = _MON_DD_RE.match(s)
                    if mm:
                        mo = _MONTH_ABBR.get(mm.group(1).lower())
            if mo is not None and 7 <= mo <= 12:
                n_date += 1
        if n_date < 3:
            continue
        if not has_mat_label:
            # For unlabeled tp sections, also require that at least one OTHER
            # strain row in the same section contains integer offsets (a
            # quick proxy that this is a Maturity table, not a Yield table
            # with calendar headers).
            # We skip this check for now; trust the Sept-Oct heuristic.
            pass
        ref_strain = a0
        gidx = group_idx_at[i]
        if gidx < 0 or gidx >= len(groups):
            continue
        test_code = groups[gidx].get("test_code", "")
        if not test_code:
            continue
        # MG-sibling broadcast: the in-row-date pattern (1970-era and
        # 1981-1988) attributes via group_idx -> single test, but UT-X
        # and PT-X share planting sites. Broadcast the anchors to all
        # tests sharing this test's maturity_group so PT-00 gets the
        # same anchors as UT-00 (e.g. 1970 R198 Portage UT-00 dates
        # also apply to PT-00).
        target_tests_p2 = {test_code}
        mg_self = mg_of_test.get(test_code)
        if mg_self:
            target_tests_p2 |= mg_to_tests.get(str(mg_self), set())
        hdr_idx = last_strain_at[i]
        # Allow up to 100 rows between Strain header and matured-row /
        # ref-strain-row. 1947-style summary tables have 40-50 strain rows
        # between header and footer. Stricter limit caused false negatives
        # for PT-0 / PT-I attribution. Still constrained to same tp2 group.
        if hdr_idx < 0 or i - hdr_idx > 100:
            continue
        # Header must be inside the same group (tp2-bounded)
        if group_idx_at[hdr_idx] != group_idx_at[i]:
            continue
        header = _composite_header(rows, hdr_idx)
        n_cols = min(len(r), len(header))
        # Cross-validation fallback: find Date plt. / Days to mat. rows
        # in this block so any in-row cell with garbled date can be
        # recovered via planted_doy + days_to_mature. Unlike Pass 1 (where
        # the matured row is at the END of the block so planted is above
        # and days is below), Pass 2's ref-strain row is near the TOP of
        # the block -- both companion rows are typically BELOW. So we
        # search both directions for both labels and take the closest.
        def _find_label_near(i_anchor, regex):
            best = -1
            best_dist = 999
            for j in range(max(i_anchor - 50, 0), min(i_anchor + 50, len(rows))):
                if group_idx_at[j] != group_idx_at[i_anchor]:
                    continue
                rj = rows[j]
                if not rj or rj[0] is None:
                    continue
                if regex.match(str(rj[0]).strip()):
                    dist = abs(j - i_anchor)
                    if dist < best_dist:
                        best, best_dist = j, dist
            return best
        planted_idx_p2 = _find_label_near(i, _DATE_PLANTED_RE)
        days_idx_p2 = _find_label_near(i, _DAYS_TO_MATURE_RE)

        for c in range(1, n_cols):
            city_raw = header[c]
            if not looks_like_city(city_raw):
                continue
            # Year-prefix filter: cells like "1946 Worthington Ind." in a
            # 1947 Sojabone summary table are HISTORICAL comparison cells,
            # not 1947 single-year data. Skip if prefix year != current year.
            cell_year, _city_stripped = parse_year_prefix(city_raw)
            if cell_year is not None and cell_year != year:
                continue
            doy = cell_to_doy(r[c], year)
            xv_used = False
            if doy is None:
                # Cross-validation fallback (planted + days = matured),
                # same heuristic as Pass 1. Useful for 1970 Block 1 where
                # individual Meritt-row cells may be garbled in OCR.
                if (planted_idx_p2 >= 0 and days_idx_p2 >= 0
                        and c < len(rows[planted_idx_p2])
                        and c < len(rows[days_idx_p2])):
                    pd_cell = rows[planted_idx_p2][c]
                    days_cell = rows[days_idx_p2][c]
                    planted_doy = _planted_doy(pd_cell, year)
                    days_val = None
                    if days_cell is not None:
                        try:
                            days_val = int(float(str(days_cell).strip()))
                        except (ValueError, TypeError):
                            days_val = None
                    if (planted_doy is not None and days_val is not None
                            and 60 <= days_val <= 200):
                        cand = planted_doy + days_val
                        if DOY_LO <= cand <= DOY_HI:
                            doy = cand
                            xv_used = True
            if doy is None:
                continue
            city_clean = parse_compound_city(city_raw)
            anchor_md = cell_to_md(r[c]) if not xv_used else ""
            if xv_used:
                from datetime import date as _d, timedelta as _td
                _dt = _d(year, 1, 1) + _td(days=doy - 1)
                anchor_md = f"{_dt.month}-{_dt.day}"
            for tc_emit in target_tests_p2:
                anchors.append({
                    "Test": tc_emit,
                    "City": city_clean,
                    "City_canon": canonicalize_city(city_clean),
                    "State": "",
                    "RefStrain": ref_strain,
                    "AnchorDate_MD": anchor_md,
                    "AnchorDOY": int(doy),
                    "Tier": "A",
                    "Source": (f"Sojabone-xv:{file_of_row[i] if i < len(file_of_row) else xp.name}"
                               if xv_used else
                               f"Sojabone:{file_of_row[i] if i < len(file_of_row) else xp.name}"),
                })

    # --- Pass 3: Tier B test-mean anchor in "Mean N Tests" column ---
    # 1981+ Sojabone tp5/tp6 (multi-year + Yield Rank summary) sections have
    # one row per strain. For the reference strain row, the "Mean N Tests"
    # column (typically col 3) holds the test-mean Maturity date formatted as
    # M-D*, M-D.f*, M/D*, DD-Mon, etc. â€” same format the Yellow Regional
    # Summary tables use but stored in the Sojabone aggregated xlsx.
    # We emit these as Tier B anchors (City="_test_mean_") so the patcher
    # broadcasts to all F4U cities of that Test lacking a Tier A direct.
    #
    # Tier B is broadcast to ALL F4U Tests matching the ref-strain's MG
    # annotation (e.g., "Hodgson 78 (I)" -> UT-I AND PT-I; "Elgin (II)" ->
    # UT-II AND PT-IIA AND PT-IIB; "Wayne" -> UT-III AND PT-III variants).
    # For 1981+ Sojabones with 5-7 tp2 groups but 13 F4U Tests, this is the
    # only way to cover sub-tests within an MG bracket.

    # Build MG -> list of F4U Tests map.
    # Order matters: must check LONGEST canonical MG first so that "II" /
    # "III" / "IV" don't get mis-bucketed into "I" by the prefix-match
    # fallback. "IV" / "III" must be checked before "II"/"I"; "00" before
    # "0".
    f4u_tests = _f4u_test_list(year)
    mg_to_tests: dict[str, list[str]] = {}
    CANON_ORDER = ("IV", "III", "II", "I", "00", "0")
    for t in f4u_tests:
        m = re.match(r"^(UT|PT)[-_](.+)$", t)
        if not m:
            continue
        mg = m.group(2)
        for canon_mg in CANON_ORDER:
            if mg == canon_mg or mg.startswith(canon_mg):
                mg_to_tests.setdefault(canon_mg, []).append(t)
                break

    # Map common ref-strain names -> MG (used when annotation is missing
    # or unparseable). Derived from NUST history.
    REF_STRAIN_TO_MG = {
        "portage": "00", "mccall": "00", "altona": "00", "flambeau": "00",
        "mand.": "0", "mandarin": "0", "merit": "0", "swift": "0",
        "evans": "0", "clay": "0", "dawson": "0", "chico": "00",
        "acme": "00",  # Used as MG 00 ref through 1959
        "crest": "00",
        "chippewa": "I", "hark": "I", "corsoy": "II", "hodgson": "I",
        "steele": "I", "sibley": "I", "elgin": "II", "hardin": "I",
        "amsoy": "II", "harosoy": "II", "lakota": "I",
        "hawkeye": "II", "richland": "II", "lincoln": "III",
        "wayne": "III", "williams": "III", "woodworth": "III",
        "calland": "III", "pella": "III", "zane": "III", "century": "III",
        "shelby": "III", "ford": "III",
        "cutler": "IV", "kent": "IV", "clark": "IV",  # Clark 63, Clark
        "wabash": "IV", "gibson": "IV", "morgan": "IV",
        "essex": "IV", "forrest": "V", "lee": "V",
        "harper": "III", "resnik": "III", "union": "IV", "spencer": "IV",
        "pixie": "III",
    }

    def _ref_strain_to_mg(ref: str) -> str | None:
        """Parse MG from ref-strain string.
        Examples: 'Hodgson 78 (I)' -> 'I', 'Elgin (II)' -> 'II',
        'Wayne' -> 'III' (via REF_STRAIN_TO_MG fallback)."""
        # First try parenthetical annotation
        m = re.search(r"\(\s*(0{1,2}|[IVivlxLX]+|[12345])\s*\)", ref)
        if m:
            raw = m.group(1).upper()
            # Normalize: "1V"/"1V" -> "IV", "11" -> "II", "1" -> "I"
            ANN_NORM = {"00": "00", "0": "0",
                        "1": "I", "I": "I",
                        "11": "II", "II": "II",
                        "111": "III", "III": "III",
                        "1V": "IV", "IV": "IV", "TV": "IV",
                        "V": "V", "2": "II", "3": "III", "4": "IV", "5": "V"}
            return ANN_NORM.get(raw)
        # Fallback to strain-name map
        ref_lower = ref.lower().strip()
        # Strip leading "N. " or "N." enumeration ("3. Hodgson 78")
        ref_lower = re.sub(r"^\d+\.\s*", "", ref_lower)
        for key, mg in REF_STRAIN_TO_MG.items():
            if key in ref_lower:
                return mg
        return None

    seen_tier_b: set[str] = set()  # avoid duplicate Tier B per test
    for i, r in enumerate(rows):
        if not r or r[0] is None or len(r) < 4:
            continue
        a0 = _norm(str(r[0]))
        if not a0:
            continue
        if a0.startswith("tp") or a0.lower() == "strain":
            continue
        if _MATURED_RE.match(a0) or _DAYS_TO_MATURE_RE.match(a0):
            continue
        if _DATE_PLANTED_RE.match(a0):
            continue
        # Mean column candidates: cols 1, 2, 3 (different formats have it at
        # different positions). Find the first one that parses as M-D*-style
        # date with month 7-12.
        mean_doy = None
        mean_cell = None
        for cand_col in (1, 2, 3):
            if cand_col >= len(r):
                break
            c = r[cand_col]
            if c is None:
                continue
            if isinstance(c, (datetime, date)):
                # Skip â€” that's already handled by Pass 2 for per-loc tables
                continue
            s = str(c).strip()
            # Must contain a date marker. M-D pattern with possible trailing
            # asterisk (test-mean marker).
            if not re.search(r"\d{1,2}[-/]\d", s) and not re.search(
                r"\d{1,2}[-\s][A-Za-z]{3}", s
            ):
                continue
            doy = cell_to_doy(s, year)
            if doy is None:
                continue
            # Confirm month is 7-12 (avoid May/June Date Planted confusion)
            md = cell_to_md(s)
            if md and 1 <= int(md.split("-")[0]) <= 6:
                continue
            mean_doy = doy
            mean_cell = s
            break
        if mean_doy is None:
            continue
        # Determine which Tests to attribute this Tier B anchor to.
        # Priority 1: MG annotation in ref-strain ("Hodgson 78 (I)" -> all
        # MG I F4U tests). Priority 2: group_idx fallback (one Test).
        ref_clean = re.sub(r"\s*\([^)]+\)\s*$", "", a0).strip()
        ref_clean = re.sub(r"^\d+\.\s*", "", ref_clean)  # strip "3. " enum prefix
        target_tests = []
        mg = _ref_strain_to_mg(a0)
        if mg and mg in mg_to_tests:
            target_tests = list(mg_to_tests[mg])
        else:
            # Fall back to group_idx mapping
            gidx = group_idx_at[i]
            if 0 <= gidx < len(groups):
                tc = groups[gidx].get("test_code", "")
                if tc:
                    target_tests = [tc]
        if not target_tests:
            continue
        # Emit one Tier B anchor per target test (skip if already seen for
        # that test from a higher-priority pass).
        for tc in target_tests:
            if tc in seen_tier_b:
                continue
            seen_tier_b.add(tc)
            anchors.append({
                "Test": tc,
                "City": "_test_mean_",
                "City_canon": "_test_mean_",
                "State": "",
                "RefStrain": ref_clean,
                "AnchorDate_MD": cell_to_md(mean_cell),
                "AnchorDOY": int(mean_doy),
                "Tier": "B",
                "Source": f"Sojabone:{file_of_row[i] if i < len(file_of_row) else xp.name}",
            })
    return anchors


# ---------------------------------------------------------------------------
# Output: merge into Sojabone-{year}_yellow_standardized.xlsx
# ---------------------------------------------------------------------------

def merge_into_standardized(year: int, new_anchors: list[dict], out_dir: Path) -> dict:
    if not new_anchors:
        return {"year": year, "added": 0, "merged": 0}
    out_path = out_dir / f"Sojabone-{year}_yellow_standardized.xlsx"
    # Load existing anchors sheet if present
    existing_df = None
    if out_path.exists():
        try:
            existing_df = pd.read_excel(out_path, sheet_name="anchors")
        except Exception:
            existing_df = None
    new_df = pd.DataFrame(new_anchors)
    # Drop self-duplicates within the new batch
    new_df = new_df.drop_duplicates(subset=["Test", "City_canon"], keep="first")
    if existing_df is not None and not existing_df.empty:
        existing_keys = set(zip(existing_df["Test"], existing_df["City_canon"]))
        new_df_filtered = new_df[~new_df.apply(
            lambda r: (r["Test"], r["City_canon"]) in existing_keys, axis=1
        )]
        merged_df = pd.concat([existing_df, new_df_filtered], ignore_index=True)
        added = len(new_df_filtered)
    else:
        merged_df = new_df
        added = len(new_df)
    # Write back (preserve qc sheet if present by reading it first)
    qc_df = None
    if out_path.exists():
        try:
            qc_df = pd.read_excel(out_path, sheet_name="qc")
        except Exception:
            qc_df = None
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        merged_df.to_excel(w, sheet_name="anchors", index=False)
        if qc_df is not None and not qc_df.empty:
            qc_df.to_excel(w, sheet_name="qc", index=False)
    return {"year": year, "added": added, "merged": len(merged_df)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--year", type=int)
    grp.add_argument("--years", type=str, help="Comma-separated list")
    grp.add_argument("--all", action="store_true",
                     help="Walk every input_YYYY folder with a Sojabone xlsx")
    ap.add_argument("--out_dir", default=str(OUT_DIR_DEFAULT))
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't write standardized xlsx; just print anchor counts")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.year:
        years = [args.year]
    elif args.years:
        years = [int(y) for y in args.years.split(",")]
    else:  # --all
        years = []
        for d in REPO_INPUT_ROOT.glob("input_*"):
            if not d.is_dir():
                continue
            m = re.match(r"input_(\d{4})$", d.name)
            if m:
                y = int(m.group(1))
                if y == 1975:
                    continue  # already complete per user
                if y >= 1989:
                    continue  # outside Yellow-era target
                years.append(y)
        years.sort()

    print(f"Processing {len(years)} year(s): {years}")
    summary_rows = []
    for year in years:
        print(f"\n=== {year} ===")
        anchors = extract_anchors_from_sojabone(year)
        unique = {(a["Test"], a["City_canon"]) for a in anchors}
        print(f"  raw anchor rows: {len(anchors)}  unique (Test, City): {len(unique)}")
        if args.dry_run:
            for a in anchors[:5]:
                print(f"    {a}")
            summary_rows.append({"year": year, "raw": len(anchors), "unique": len(unique), "added": 0})
            continue
        m = merge_into_standardized(year, anchors, out_dir)
        print(f"  merged: added {m['added']} new -> total {m['merged']} in xlsx")
        summary_rows.append({"year": year, "raw": len(anchors), "unique": len(unique), "added": m["added"]})

    print(f"\n=== Summary ===")
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
