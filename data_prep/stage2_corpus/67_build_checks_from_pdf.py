"""
67_build_checks_from_pdf.py
============================
Extract check variety designations from NUST Red PDF annual reports.

Step 1 — zero API cost:
    pdfplumber extract_words() with FULLY DYNAMIC column detection.
    Three format eras are handled:

    ERA A: 1941–1955
      Header:   "UNIFORM TEST, GROUP X"  (no year in header)
      Columns:  Strain | Source or Originating Agency | Origin
      Trigger:  "Originating Agency" keyword (no "Parentage")
      Check ID: paragraph count only (no Previous Testing column)

    ERA B: 1956–1965
      Header:   "UNIFORM TEST, GROUP XX, YEAR" (1956-1959)
                "UNIFORM TEST XX[.,]YEAR"       (1960-1965)
                OCR typo: "I" misread as "1" in years (e.g. I960, I963)
      Columns:  Strain | Originating Agency | Origin | Generation Composited
      Trigger:  "Originating Agency" keyword
      Check ID: paragraph count only (no Previous Testing column)

    ERA C: 1966–1991
      Header:   "UNIFORM TEST MG, YEAR"
      Columns:  Strain | Parentage | [Line/Generation] | Previous Testing*
                (column order varies by year: see original docstring)
      Trigger:  "Parentage" keyword
      Check ID: Previous Testing heuristic + paragraph count

Step 2 — manual only:
    Low-confidence cells (confidence < 2) get needs_review=True.
    No automatic API call.

Usage:
    uv run python analysis/67_build_checks_from_pdf.py            # all years
    uv run python analysis/67_build_checks_from_pdf.py --year 1972
    uv run python analysis/67_build_checks_from_pdf.py --year 1972 --verbose
"""

import re
import sys
import argparse
from collections import defaultdict
from pathlib import Path

import pdfplumber
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Paths — checks both local input_XXXX/ and R: drive Red folder
# ---------------------------------------------------------------------------
REPO    = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
RED_DIR = Path(
    r"R:\cfans_agro_lore0149_lorenzlabresearch"
    r"\NUST_Historical_Data_1941_1988"
    r"\Red-20260427T193444Z-3-001\Red"
)
OUT_DIR        = REPO / "analysis/data/_shared"
OUT_STRAINS    = OUT_DIR / "nust_checks_from_pdf_1941_1991.csv"
OUT_VALIDATION = OUT_DIR / "nust_checks_from_pdf_validation.csv"

MG_ORDER = ["00", "0", "I", "II", "III", "IV"]


def find_pdf(year):
    """Return path to the year's PDF, preferring local copy."""
    local = REPO / f"input_files/input_{year}" / f"{year}_done.pdf"
    if local.exists():
        return local
    remote = RED_DIR / f"{year}_done.pdf"
    if remote.exists():
        return remote
    return None


# ---------------------------------------------------------------------------
# Regex helpers — era-aware
# ---------------------------------------------------------------------------

def make_header_re(year):
    """ERA C (1966+): 'UNIFORM TEST MG, YEAR' with MG code."""
    return re.compile(
        rf"UNIFORM\s+TEST\s+(0{{1,2}}|[IV]+)\s*[,.]?\s*{year}",
        re.IGNORECASE,
    )

# ERA A (1941-1955): no year in header; match "UNIFORM TEST, GROUP X"
ERA_A_HEADER_RE = re.compile(
    r"UNIFORM\s+TEST[,.]?\s+GROUP\s+(0{1,2}|[IV]+)",
    re.IGNORECASE,
)

def make_header_re_era_b(year):
    """
    ERA B (1956-1965): year present but OCR may mis-read '1' as 'I'.
    Handles both 'UNIFORM TEST, GROUP X, YEAR' and 'UNIFORM TEST X[.,]YEAR'.
    Allows '196X' or 'I96X'.
    """
    yr = str(year)
    # Allow first digit to be OCR-garbled: '1' <-> 'I'
    yr_pat = "[1I]" + yr[1:]
    return re.compile(
        rf"UNIFORM\s+TEST[,.]?\s+(?:GROUP\s+)?(0{{1,2}}|[IV]+)\s*[,.\-]\s*{yr_pat}",
        re.IGNORECASE,
    )

# Entry-list page triggers
PARENTAGE_RE = re.compile(r"Parentage", re.IGNORECASE)
AGENCY_RE    = re.compile(r"Originating\s+Agency|Source\s+or\s+Originating", re.IGNORECASE)

FOOTNOTE_RE  = re.compile(r"^\*\s*Number\s+of\s+years", re.IGNORECASE)

WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
COUNT_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(?:named|check)\s+variet",
    re.IGNORECASE,
)
# Also catch "Three of the named/check varieties" and
# "three check/named varieties" already covered above
# Additional: "three of the varieties have been in the test" (no "named")
COUNT_RE2 = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(?:of\s+the\s+)?(?:named\s+|check\s+)?variet",
    re.IGNORECASE,
)

# Keywords that identify column headers
PREV_KWS   = {"previous", "testing"}
LINE_KWS   = {"line", "generation", "composited"}
ORIGIN_KWS = {"originating", "agency", "origin"}   # pre-1966 parentage proxy
ALL_HDR_KWS = PREV_KWS | LINE_KWS | {"strain", "parentage"} | ORIGIN_KWS

# ---------------------------------------------------------------------------
# Phase A: Locate entry-list pages
# ---------------------------------------------------------------------------

def find_entry_pages(pdf_path, year, verbose=False):
    """
    Era-aware scan for UNIFORM TEST entry-list pages.

    ERA A (1941-1955): header has no year; uses "GROUP X" format;
                       entry trigger = "Originating Agency"
    ERA B (1956-1965): year present but may have OCR typos ("I960");
                       entry trigger = "Originating Agency"
    ERA C (1966+):     standard format; entry trigger = "Parentage"

    Returns {mg: (page_index_0based, raw_text)}.  First match per MG kept.
    """
    if year <= 1955:
        header_re  = ERA_A_HEADER_RE
        entry_re   = AGENCY_RE
    elif year <= 1965:
        header_re  = make_header_re_era_b(year)
        entry_re   = AGENCY_RE
    else:
        header_re  = make_header_re(year)
        entry_re   = PARENTAGE_RE

    found = {}
    with pdfplumber.open(pdf_path) as pdf:
        if verbose:
            print(f"  PDF pages: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages):
            txt = page.extract_text() or ""
            lines = [ln.strip() for ln in txt.strip().splitlines() if ln.strip()]
            header_block = " ".join(lines[:5])
            m = header_re.search(header_block)
            if not m:
                continue
            mg = m.group(1).upper()
            if mg in found:
                continue
            if entry_re.search(txt):
                found[mg] = (i, txt)
                if verbose:
                    print(f"    MG {mg}: entry-list at PDF page {i+1}")
    return found


# ---------------------------------------------------------------------------
# Step 1: Fully dynamic column boundary detection
# ---------------------------------------------------------------------------

def get_words_clean(page):
    """Extract words, filtering out binding-mark artefacts at left margin."""
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    # Binding marks: short (1-2 char), far left (x0 < 15pt)
    return [w for w in words if not (float(w["x0"]) < 15 and len(w["text"]) <= 2)]


def detect_column_bounds(words, page_width, verbose=False):
    """
    Fully dynamic column detection — works for any NUST column order.

    Algorithm:
      1. Bucket words into rows (8pt tolerance for OCR y-jitter).
      2. Collect the first x0 occurrence of each column-header keyword.
      3. Group right-side keywords by approximate x-position (±12pt = same col).
      4. Identify which group is "prev_testing" (contains 'previous'/'testing').
      5. Identify which group is "line/gen" (contains 'line'/'generation'/'composited').
      6. Set column boundaries accordingly — order may vary by year.

    Returns dict with at minimum:
        strain_num   -> (0, parentage_x - PAD)
        parentage    -> (parentage_x - PAD, prev_testing_left - PAD)   [or wider]
        prev_testing -> (prev_testing_left - PAD, prev_testing_right)
        line_gen     -> (prev_testing_right, page_width + 50)  [optional]
    """
    PAD = 2.0
    CLUSTER_TOL = 12.0   # pt — keywords within this x-distance = same column

    # Bucket words into rows
    row_buckets = defaultdict(list)
    for w in words:
        rk = round(float(w["top"]) / 8) * 8
        row_buckets[rk].append(w)

    # Collect first x0 for each header keyword
    kw_pos = {}   # keyword -> x0 (first occurrence)
    for rk in sorted(row_buckets.keys()):
        rw = sorted(row_buckets[rk], key=lambda w: float(w["x0"]))
        for w in rw:
            t = w["text"].lower().rstrip("*,.")
            if t in ALL_HDR_KWS and t not in kw_pos:
                kw_pos[t] = float(w["x0"])

    # Find the "parentage" boundary.
    # For 1966+ (ERA C): use x0 of the "parentage" keyword.
    # For pre-1966 (ERA A/B): use x0 of "originating"/"agency" BUT only from the
    #   column-header row (a row that contains BOTH a strain/variety word AND an
    #   agency word at the same time). This avoids false matches from body text
    #   where "origin" appears in sentences ("The origin of the strains...").
    if "parentage" in kw_pos:
        parentage_x = kw_pos["parentage"]
    else:
        # Search for the HEADER ZONE — rows within 12pt of each other that
        # together contain both a "strain"/"variety" word AND "originating"/"agency".
        # Uses a wider 12pt window because some years have 2-row headers where
        # "Strain" and "Originating" differ by ~1pt in top, falling in different 8pt buckets.
        STRAIN_HDR = {"strain", "variety"}
        AGENCY_HDR = {"originating", "agency"}
        sorted_rks = sorted(row_buckets.keys())
        parentage_x = None
        for rk in sorted_rks:
            # Build a combined word map across this bucket ± 12pt
            combined = {}
            for rk2 in sorted_rks:
                if abs(rk2 - rk) <= 12:
                    for w in row_buckets[rk2]:
                        t = w["text"].lower().rstrip("*,.")
                        if t not in combined:   # first occurrence wins (leftmost)
                            combined[t] = float(w["x0"])
            if combined.keys() & STRAIN_HDR and combined.keys() & AGENCY_HDR:
                for kw in ("originating", "agency"):
                    if kw in combined:
                        parentage_x = combined[kw]
                        break
                if verbose:
                    print(f"      Using '{kw}' header zone as parentage proxy at x={parentage_x:.0f}")
                break
        if parentage_x is None:
            if verbose:
                print("      WARNING: No parentage/agency header found — using fallbacks")
            return {
                "strain_num":   (0,          119 - PAD),
                "parentage":    (119 - PAD,  430 - PAD),
                "prev_testing": (430 - PAD,  page_width + 50),
            }

    # Right-side keywords: anything to the right of parentage
    right_kws = {k: v for k, v in kw_pos.items()
                 if k not in ("strain",) and v > parentage_x}

    if not right_kws:
        if verbose:
            print("      WARNING: No right-side column headers found")
        return {
            "strain_num":   (0,               parentage_x - PAD),
            "parentage":    (parentage_x - PAD, page_width * 0.80),
            "prev_testing": (page_width * 0.80, page_width + 50),
        }

    # Cluster right-side keywords by x-position
    # Each cluster = one column
    clusters = []   # list of {"x": float, "kws": set}
    for kw, x in sorted(right_kws.items(), key=lambda kv: kv[1]):
        placed = False
        for c in clusters:
            if abs(x - c["x"]) <= CLUSTER_TOL:
                c["kws"].add(kw)
                c["x"] = min(c["x"], x)   # leftmost x in cluster
                placed = True
                break
        if not placed:
            clusters.append({"x": x, "kws": {kw}})

    # Sort clusters left to right
    clusters.sort(key=lambda c: c["x"])

    # Identify prev_testing cluster and line/gen cluster
    prev_cluster  = None
    linegen_cluster = None
    for c in clusters:
        if c["kws"] & PREV_KWS:
            prev_cluster = c
        if c["kws"] & LINE_KWS:
            linegen_cluster = c

    if verbose:
        for c in clusters:
            print(f"      cluster x={c['x']:.0f}: {c['kws']}")

    # Case 1: Both clusters identified
    if prev_cluster and linegen_cluster:
        p_x  = prev_cluster["x"]
        lg_x = linegen_cluster["x"]

        if p_x < lg_x:
            # 1976+ format: prev_testing BEFORE line/gen
            bounds = {
                "strain_num":   (0,             parentage_x - PAD),
                "parentage":    (parentage_x - PAD, p_x - PAD),
                "prev_testing": (p_x - PAD,     lg_x - PAD),
                "line_gen":     (lg_x - PAD,    page_width + 50),
            }
        else:
            # 1968-1975 format: line/gen BEFORE prev_testing
            bounds = {
                "strain_num":   (0,             parentage_x - PAD),
                "parentage":    (parentage_x - PAD, lg_x - PAD),
                "line_gen":     (lg_x - PAD,    p_x - PAD),
                "prev_testing": (p_x - PAD,     page_width + 50),
            }

    # Case 2: Only prev_testing cluster found (no line/gen header detected)
    elif prev_cluster:
        p_x = prev_cluster["x"]
        bounds = {
            "strain_num":   (0,             parentage_x - PAD),
            "parentage":    (parentage_x - PAD, p_x - PAD),
            "prev_testing": (p_x - PAD,     page_width + 50),
        }

    # Case 3: Only line/gen cluster found (prev_testing header not detected)
    # Treat the rightmost cluster as prev_testing (fallback)
    else:
        last_x = clusters[-1]["x"] if clusters else page_width * 0.80
        bounds = {
            "strain_num":   (0,             parentage_x - PAD),
            "parentage":    (parentage_x - PAD, last_x - PAD),
            "prev_testing": (last_x - PAD,  page_width + 50),
        }

    if verbose:
        print("      col_bounds: " + " | ".join(
            f"{k}=[{int(lo)},{int(hi)}]" for k, (lo, hi) in bounds.items()))

    return bounds


def assign_column(x0, col_bounds):
    for col, (lo, hi) in col_bounds.items():
        if lo <= x0 < hi:
            return col
    return "prev_testing"


# ---------------------------------------------------------------------------
# Entry table extraction
# ---------------------------------------------------------------------------

NUM_PREFIX_RE = re.compile(r"^(\d+)\.?\s*(.*)", re.DOTALL)
GEN_RE = re.compile(r"^[Ff][\d\s,«♦\.\-]+$")   # generation codes: F5, F7 etc.

# Parentage-contamination patterns — truncate strain name at first match.
# Conservative: only strip OBVIOUS parentage bleed (column calibration handles
# most cases; this is a safety net for when calibration returns fallback width).
#   - "0-52-903" style codes starting with DIGIT (not letter): r"\s+[0-9][0-9]*-"
#   - Cross-in-parens like "(Amsoy X" (multi-char in parens, followed by cross)
# Intentionally does NOT strip:
#   - "M 65-217" (letter-prefixed strain codes)
#   - "(0)" / "(O)" / "(00)" MG-indicator parentheticals
STRAIN_STOP_RE = re.compile(
    r"\s+[0-9]+-[0-9]+-[0-9]"            # 3-part digit code: "0-52-903" (2 dashes)
    r"|\s+\(\s*[A-Z][a-z]{2,}\s+[xX×]"  # cross in parens: "(Amsoy X" (3+ char word)
)


def clean_strain(raw):
    """Strip parentage/agency contamination and OCR artefacts from a strain name."""
    # Remove leading punctuation artefacts (e.g. ". Beeson" from table border OCR)
    raw = re.sub(r"^[\.\s\-]+", "", raw).strip()
    # Truncate at obvious parentage bleed (digit-leading cross codes, paren crosses)
    m = STRAIN_STOP_RE.search(raw)
    if m:
        raw = raw[:m.start()].strip()
    # Truncate at agency/institutional keywords that bleed from pre-1966 format
    # e.g. "Earlyana Purdue Agr. Exp. Sta." → "Earlyana"
    AGENCY_STOP_RE = re.compile(
        r"\s+(?:Agr\.\s|Exp\.\s|Sta\.\s|U\.S\.\s|\bSel\.\b|"
        r"\bSelection\b|\bStation\b|Originating|Purdue|Wisconsin|Illinois|Iowa|"
        r"Central\s+Exp)",
        re.IGNORECASE,
    )
    m2 = AGENCY_STOP_RE.search(raw)
    if m2:
        raw = raw[:m2.start()].strip()
    return raw.strip().rstrip(".")


def calibrate_strain_boundary(rows, approx_parentage_x, prev_testing_x):
    """
    Scan first 3 numbered entry rows to find the actual strain/parentage gap.
    Returns a refined x-boundary to use instead of header-derived parentage_x.

    In some years (e.g. 1978) the 'Parentage' header is shifted right of where
    parentage DATA actually starts, causing bleeding.  The gap between the last
    strain word and first parentage word is the true column boundary.
    """
    MIN_GAP = 15.0
    boundaries = []

    for rk, row_words in sorted(rows.items()):
        rw = sorted(row_words, key=lambda w: float(w["x0"]))
        if not rw:
            continue
        m = re.match(r"^\d+\.?$", rw[0]["text"].strip())
        if not m:
            continue

        # Find gaps between consecutive words in the region left of prev_testing
        for i in range(len(rw) - 1):
            x0_curr = float(rw[i]["x0"])
            x1_curr = float(rw[i]["x1"])
            x0_next = float(rw[i + 1]["x0"])

            # Only look at gaps in the "strain+parentage" region
            if x0_curr < 50:          # skip entry number
                continue
            if x0_next > prev_testing_x - 30:  # stop before prev_testing col
                break

            gap = x0_next - x1_curr
            if gap >= MIN_GAP:
                # First significant gap after the entry number = strain/parentage boundary
                mid = (x1_curr + x0_next) / 2
                boundaries.append(mid)
                break   # only first gap per row

        if len(boundaries) >= 3:
            break

    if not boundaries:
        return approx_parentage_x

    refined = sorted(boundaries)[len(boundaries) // 2]   # median
    # Only use refined if it's meaningfully different from header position
    # and makes sense (should be well left of prev_testing)
    if refined < approx_parentage_x - 5 and refined < prev_testing_x - 50:
        return refined
    return approx_parentage_x


# Para-end patterns that signal end of un-numbered entry table (pre-1966)
PRE66_STOP_RE = re.compile(
    r"^(Identification\s+of\s+Parent|Table\s+\d+|"
    r"Data\s+for\s+|Data\s+were\s+|The\s+test\s+|This\s+test\s+|"
    r"The\s+origin\s+|The\s+group\s+|Only\s+two\s+|Only\s+one\s+|"
    r"No\s+new\s+|Regional\s+test|Yield\s+level|"
    r"[A-Z][a-z].*\s+\d+\s+bushel)",   # "X bushels" sentence
    re.IGNORECASE,
)


def extract_entry_table_pre1966(page, col_bounds, rows, verbose=False):
    """
    Parse UN-NUMBERED entry rows for pre-1966 format.

    Pre-1966 layout:
      [header row] Strain  Originating Agency  Origin  Generation Composited
      [entry rows] Acme    Central Exp. Farm   Sel...  F8
                   Flambeau ...

    Strategy: find the column-header row (contains "Strain" at far left),
    then collect all subsequent rows that have a word in the strain column
    (x0 ≤ agency_x) until a stop condition is hit.
    """
    # Find the LAST header row before entries begin.
    # Some years (e.g. 1947) have a 2-row header:
    #   Row 1: "Variety  Source or  Origin"
    #   Row 2: "or Strain  Originating Agency"
    # We detect the header ZONE (all rows within 16pt of the first header row)
    # and set header_rk to the LAST row in the zone.
    STRAIN_HDR = {"strain", "variety"}
    HEADER_KWS = STRAIN_HDR | {"originating", "agency", "source", "origin",
                                "generation", "composited", "testing", "previous"}
    sorted_rks  = sorted(rows.keys())
    header_zone_start = None

    for rk in sorted_rks:
        rw = rows[rk]
        for w in rw:
            if w["text"].lower().rstrip("*,.") in STRAIN_HDR and float(w["x0"]) < 100:
                header_zone_start = rk
                break
        if header_zone_start is not None:
            break

    if header_zone_start is None:
        if verbose:
            print("      pre-1966: no 'Strain' header row found")
        return []

    # Advance header_rk through any additional header rows within 20pt
    header_rk = header_zone_start
    for rk in sorted_rks:
        if rk <= header_zone_start:
            continue
        if rk - header_zone_start > 20:
            break
        rw = rows[rk]
        row_texts = {w["text"].lower().rstrip("*,.") for w in rw}
        if row_texts & HEADER_KWS:
            header_rk = rk   # extend header zone

    if header_rk is None:
        if verbose:
            print("      pre-1966: no 'Strain' header row found")
        return []

    entries = []
    for rk in sorted(rows.keys()):
        if rk <= header_rk:
            continue

        row_words = rows[rk]
        full_line = " ".join(w["text"] for w in row_words).strip()

        # Stop conditions
        if not full_line:
            continue
        if PRE66_STOP_RE.match(full_line):
            break
        # Long sentence starting with paragraph-like words = stop
        if len(full_line) > 75 and not row_words[0]["text"][0].isdigit():
            # Look for sentence-like structure (multiple common words)
            if re.search(r"\b(the|this|of|in|and|was|for|were|has|have)\b",
                         full_line, re.I):
                break

        # Assign words to columns
        cells = defaultdict(list)
        for w in row_words:
            col = assign_column(float(w["x0"]), col_bounds)
            cells[col].append(w["text"])
        row_text = {col: " ".join(tokens) for col, tokens in cells.items()}

        strain_raw  = row_text.get("strain_num", "").strip()
        strain_str  = clean_strain(strain_raw) if strain_raw else ""

        # Valid entry: strain column has content, not just generation codes
        if strain_str and len(strain_str) >= 2 and not GEN_RE.match(strain_str):
            prev_raw = row_text.get("prev_testing", "").strip()
            line_raw = row_text.get("line_gen", "").strip()
            # Promote line_gen → prev_testing if it has numbers (same logic as 1966+)
            if not prev_raw and line_raw and not GEN_RE.match(line_raw):
                if re.search(r"\d", line_raw):
                    prev_raw = line_raw
            entries.append({
                "num":          len(entries) + 1,
                "strain":       strain_str,
                "parentage":    row_text.get("parentage", "").strip(),
                "prev_testing": prev_raw,
            })

    if verbose:
        for e in entries:
            print(f"      {e['num']:2d}. strain='{e['strain']}'  "
                  f"prev='{e['prev_testing']}'")

    return entries


def extract_entry_table(page, verbose=False, year=None):
    """
    Parse the entry-list table using fully dynamic column bounds.
    Dispatches to era-specific parser based on year.

    Returns (list of dicts, col_bounds).
    """
    words = get_words_clean(page)
    if not words:
        return [], {}

    col_bounds = detect_column_bounds(words, page.width, verbose=verbose)

    # Bucket words into rows (8pt)
    rows_raw = defaultdict(list)
    for w in words:
        rk = round(float(w["top"]) / 8) * 8
        rows_raw[rk].append(w)
    rows = {k: sorted(v, key=lambda w: float(w["x0"]))
            for k, v in sorted(rows_raw.items())}

    # ── Dispatch: pre-1966 un-numbered format ─────────────────────────────
    if year is not None and year <= 1965:
        entries = extract_entry_table_pre1966(page, col_bounds, rows, verbose=verbose)
        return entries, col_bounds

    # ── 1966+ numbered format (original logic) ────────────────────────────

    # Calibrate strain/parentage boundary from actual data gaps
    prev_x = col_bounds.get("prev_testing", (page.width * 0.7, page.width + 50))[0]
    approx_par_x = col_bounds["strain_num"][1]  # current right edge of strain_num
    refined_par_x = calibrate_strain_boundary(rows, approx_par_x, prev_x)
    if refined_par_x != approx_par_x:
        if verbose:
            print(f"      calibrated parentage_x: {approx_par_x:.0f} -> {refined_par_x:.0f}")
        PAD = 2.0
        # Rebuild col_bounds with refined boundary
        col_bounds["strain_num"] = (0, refined_par_x)
        col_bounds["parentage"]  = (refined_par_x, col_bounds["parentage"][1])

    entries = []
    for rk in sorted(rows.keys()):
        row_words = rows[rk]
        full_line = " ".join(w["text"] for w in row_words).strip()

        if FOOTNOTE_RE.match(full_line):
            break

        # Assign words to columns
        cells = defaultdict(list)
        for w in row_words:
            col = assign_column(float(w["x0"]), col_bounds)
            cells[col].append(w["text"])
        row_text = {col: " ".join(tokens) for col, tokens in cells.items()}

        strain_num_raw = row_text.get("strain_num", "").strip()
        m = NUM_PREFIX_RE.match(strain_num_raw)

        if not m:
            if len(full_line) > 70:
                break   # paragraph started
            continue

        entry_num  = int(m.group(1))
        strain_str = clean_strain(m.group(2).strip())

        if entry_num > 25:
            continue   # page number artefact

        prev_raw = row_text.get("prev_testing", "").strip()
        line_raw = row_text.get("line_gen", "").strip()

        # If prev_testing empty but line_gen has numeric/P content, promote it
        if not prev_raw and line_raw and not GEN_RE.match(line_raw):
            if re.search(r"\d", line_raw) or re.match(r"^[PpUu\-–]\b", line_raw):
                prev_raw = line_raw
                line_raw = ""

        entries.append({
            "num":          entry_num,
            "strain":       strain_str,
            "parentage":    row_text.get("parentage", "").strip(),
            "prev_testing": prev_raw,
        })

    # Gap-fill: some PDFs place the prev_testing number on a slightly
    # different y-position than the rest of the entry row (OCR jitter > 8pt).
    # Scan ±12pt around each entry's row key to fill missing prev_testing values.
    if entries:
        prev_bounds = col_bounds.get("prev_testing")
        if prev_bounds:
            prev_lo, prev_hi = prev_bounds
            # Build: entry_num -> row_key
            entry_rks = {}
            for rk, rw in rows.items():
                first_txt = rw[0]["text"].strip() if rw else ""
                m2 = re.match(r"^(\d+)\.?$", first_txt)
                if m2:
                    n = int(m2.group(1))
                    if 1 <= n <= 25:
                        entry_rks[n] = rk
            for e in entries:
                if e["prev_testing"] or e["num"] not in entry_rks:
                    continue
                erk = entry_rks[e["num"]]
                for rk2, rw2 in rows.items():
                    if rk2 == erk or abs(rk2 - erk) > 12:
                        continue
                    for w in sorted(rw2, key=lambda w: float(w["x0"])):
                        if prev_lo <= float(w["x0"]) < prev_hi:
                            e["prev_testing"] = w["text"]
                            break
                    if e["prev_testing"]:
                        break

    if verbose:
        for e in entries:
            print(f"      {e['num']:2d}. strain='{e['strain']}'  "
                  f"prev='{e['prev_testing']}'")

    return entries, col_bounds


# ---------------------------------------------------------------------------
# Previous-testing heuristic
# ---------------------------------------------------------------------------

def prev_is_established(prev_raw):
    """
    True if Previous Testing value indicates >= 3 years in the Uniform Test.
    "P XX", "U XX" = advanced from another test → not established.
    Dash "–" or "-" = brand new → not established.
    """
    s = (prev_raw or "").strip().lstrip("0")
    if not s or s in ("-", "–", "—"):
        return False
    if re.match(r"^[PpUu]\b", s):
        return False
    nums = re.findall(r"\d+", s)
    if nums:
        return int(nums[-1]) >= 3
    return False


# ---------------------------------------------------------------------------
# Paragraph validation
# ---------------------------------------------------------------------------

def extract_paragraph(txt):
    lines = txt.splitlines()
    para_lines = []
    in_para = False
    for line in lines:
        s = line.strip()
        if FOOTNOTE_RE.match(s):
            in_para = True
            continue
        if in_para:
            para_lines.append(s)
        elif not in_para and not re.match(r"^\d+\.", s) and len(s) > 50:
            para_lines.append(s)
            in_para = True
    return " ".join(para_lines)


def extract_para_count(para_text):
    # Try strict form first: "N named/check varieties"
    m = COUNT_RE.search(para_text)
    if m:
        token = m.group(1).lower()
        return WORD_NUM.get(token, int(token) if token.isdigit() else None)
    return None


def find_names_in_para(para_text, candidate_names):
    found = []
    for name in (candidate_names or []):
        if not name:
            continue
        pat = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        if pat.search(para_text):
            found.append(name)
    return found


# ---------------------------------------------------------------------------
# Main parse + validate
# ---------------------------------------------------------------------------

def step1_parse(page, raw_txt, mg, year, verbose=False):
    result = {
        "year": year, "mg": mg,
        "entries": [],
        "checks": [], "experimental": [],
        "n_checks": 0, "n_experimental": 0,
        "confidence": 0,
        "val_para_count": None,
        "val_para_names": [],
        "split_method": "",
        "needs_review": False,
        "notes": "",
    }

    entries, col_bounds = extract_entry_table(page, verbose=verbose, year=year)
    result["entries"] = entries

    if not entries:
        result["notes"] = "No entries parsed — likely image-only PDF page"
        result["needs_review"] = True
        return result

    # Paragraph extraction: pre-1966 intro may be at TOP of page (before the table),
    # so search the full raw text for count information instead of just bottom para.
    if year <= 1965:
        search_text = raw_txt   # count may be anywhere on page
    else:
        search_text = extract_paragraph(raw_txt)
    para_count = extract_para_count(search_text)
    para_text  = search_text   # used for name-in-para check below

    # Detect pre-1966 format: no Previous Testing column exists.
    # When ALL entries have empty prev_testing, the heuristic is meaningless.
    # Pre-1966 pages use "Originating Agency / Origin" columns instead.
    has_prev_testing = any(e["prev_testing"] for e in entries)
    is_pre1966       = (year <= 1965) and not has_prev_testing

    # Split checks vs experimental
    if para_count is not None and 0 < para_count <= len(entries):
        checks      = entries[:para_count]
        experimentl = entries[para_count:]
        result["split_method"] = f"paragraph_count={para_count}"
    elif is_pre1966:
        # No prev_testing heuristic available — cannot classify without para count.
        # Emit all entries as unclassified (is_check=0) so they're available for
        # manual review; only para-count method can set is_check=1 here.
        checks      = []
        experimentl = entries
        result["split_method"] = "pre1966_no_prev_testing_column"
        result["notes"] = "pre-1966 format: no Previous Testing column; paragraph count required"
    else:
        checks      = [e for e in entries if prev_is_established(e["prev_testing"])]
        experimentl = [e for e in entries if not prev_is_established(e["prev_testing"])]
        result["split_method"] = "prev_testing_heuristic"

    check_names = [e["strain"] for e in checks if e["strain"]]
    exp_names   = [e["strain"] for e in experimentl if e["strain"]]

    result["checks"]         = check_names
    result["experimental"]   = exp_names
    result["n_checks"]       = len(check_names)
    result["n_experimental"] = len(exp_names)
    result["val_para_count"] = para_count

    # Confidence scoring (0–3)
    score = 0
    if para_count is not None and para_count == len(check_names):
        score += 2   # explicit paragraph count matches
    names_in_para = find_names_in_para(para_text, check_names)
    result["val_para_names"] = names_in_para
    if len(names_in_para) >= 2:
        score += 1   # checks mentioned in paragraph
    # +1 for clean parse: only award if we have meaningful prev_testing data
    # (pre-1966 entries always have empty prev_testing, so skip this check there)
    if entries and all(e["strain"] for e in entries) and (not is_pre1966 or para_count):
        score += 1   # clean parse with usable data

    result["confidence"]   = score
    result["needs_review"] = score < 2

    if verbose:
        print(f"      split={result['split_method']}  "
              f"checks={check_names}  conf={score}")
        if result["needs_review"]:
            print("      [LOW CONFIDENCE — flagged for review]")

    return result


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def result_to_strain_rows(result, pdf_page_1based):
    check_set = set(result["checks"])
    rows = []
    for e in result["entries"]:
        name = e["strain"]
        if not name:
            continue
        rows.append({
            "year":         result["year"],
            "mg":           result["mg"],
            "pdf_page":     pdf_page_1based,
            "strain":       name,
            "parentage":    e.get("parentage", ""),
            "prev_testing": e.get("prev_testing", ""),
            "is_check":     1 if name in check_set else 0,
            "confidence":   result["confidence"],
            "split_method": result["split_method"],
            "step":         1,
            "notes":        result["notes"],
        })
    return rows


def result_to_val_row(result, pdf_page_1based):
    return {
        "year":           result["year"],
        "mg":             result["mg"],
        "pdf_page":       pdf_page_1based,
        "n_checks":       result["n_checks"],
        "n_experimental": result["n_experimental"],
        "confidence":     result["confidence"],
        "split_method":   result["split_method"],
        "val_para_count": result["val_para_count"],
        "val_para_names": "|".join(result["val_para_names"]),
        "checks":         "|".join(result["checks"]),
        "needs_review":   result["needs_review"],
        "notes":          result["notes"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None,
                    help="Process single year (default: all 1941-1991)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    years = [args.year] if args.year else list(range(1941, 1992))

    strain_rows = []
    val_rows    = []
    n_pdfs = n_cells = n_review = 0

    for year in years:
        pdf_path = find_pdf(year)
        if pdf_path is None:
            if args.verbose:
                print(f"{year}: PDF not found")
            continue

        print(f"\n{year}  ({pdf_path.name})")
        n_pdfs += 1

        entry_pages = find_entry_pages(pdf_path, year, verbose=args.verbose)
        if not entry_pages:
            print(f"  No UNIFORM TEST entry-list pages found (image-only PDF?)")
            continue

        with pdfplumber.open(pdf_path) as pdf:
            for mg in MG_ORDER:
                if mg not in entry_pages:
                    continue
                page_idx, raw_txt = entry_pages[mg]
                page = pdf.pages[page_idx]
                if args.verbose:
                    print(f"  MG {mg} (PDF p{page_idx+1}):")

                result = step1_parse(page, raw_txt, mg, year,
                                     verbose=args.verbose)
                n_cells += 1
                if result["needs_review"]:
                    n_review += 1

                flag = " [REVIEW]" if result["needs_review"] else ""
                print(f"  MG {mg}: {result['n_checks']} checks "
                      f"{result['n_experimental']} exp  "
                      f"conf={result['confidence']}  "
                      f"{result['split_method']}{flag}")
                if result["checks"] and not args.verbose:
                    print(f"    checks: {', '.join(result['checks'])}")

                strain_rows.extend(result_to_strain_rows(result, page_idx + 1))
                val_rows.append(result_to_val_row(result, page_idx + 1))

    # Write outputs
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_s = pd.DataFrame(strain_rows)
    df_v = pd.DataFrame(val_rows)
    df_s.to_csv(OUT_STRAINS,    index=False)
    df_v.to_csv(OUT_VALIDATION, index=False)

    print(f"\n{'='*60}")
    print(f"PDFs processed : {n_pdfs}")
    print(f"MG×year cells  : {n_cells}")
    print(f"Needs review   : {n_review} "
          f"({100*n_review/n_cells:.0f}%)" if n_cells else "")
    print(f"Wrote: {OUT_STRAINS}  ({len(df_s)} rows)")
    print(f"Wrote: {OUT_VALIDATION}  ({len(df_v)} rows)")

    if n_review:
        print("\nCells needing review:")
        for r in val_rows:
            if r["needs_review"]:
                print(f"  {r['year']} MG {r['mg']}  "
                      f"conf={r['confidence']}  checks={r['checks']}")


if __name__ == "__main__":
    main()
