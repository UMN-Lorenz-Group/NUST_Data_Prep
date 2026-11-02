"""
94b_extract_1990_ut_anchors_pdf.py
==================================
Recover the 1990 UNIFORM TEST maturity ANCHOR dates (per Test x Location) from the
Red PDF input_files/1990.pdf, LOCALLY (pdfplumber word positions; ZERO API — the
PDF is never uploaded). Completes the documented partial DOY conversion for 1990's
UT rows (the OCR/API patchers never anchored 1990 UT — see
logs NUST_corpus_maturity_doy_partial_progress.md).

Method:
  1. For each UT maturity section, build a row x column GRID from word x-positions.
  2. Anchor row = the row whose location cells are DATES (m/d); its dates per column.
  3. Map each date-column to a corpus City by OFFSET-MATCHING: the non-anchor rows'
     integer offsets in the PDF match the corpus's offset-looking Maturity values
     for the same strain+city (those offsets are exactly the un-anchored rows).
     Voting across strains makes the column->city map robust; no fragile header
     reconstruction needed.
  4. Emit anchorDOY per (Test=UT-<MG>, City) -> nust_anchor_1990_ut_pdf.csv,
     consumed by 94_fix_1990_maturity.py.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/94b_extract_1990_ut_anchors_pdf.py
"""
import csv
import datetime
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

import pdfplumber

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
PDF  = REPO / "input_files/1990.pdf"
WIDE = REPO / "analysis/data/_shared/NUST_1941_2025_data_wide.csv"
OUT  = REPO / "analysis/data/_shared/nust_anchor_1990_ut_pdf.csv"
YEAR = 1990

HDR_RE = re.compile(r"UNIFORM\s+TEST\s+(00|0|[IV]+)\s*,?\s*1990", re.IGNORECASE)
DATE_RE = re.compile(r"^\s*\d{1,2}/\d{1,2}\s*$")
MONTHS_OK = True


def nm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())


def nc(s):
    return re.sub(r"[^a-z0-9]", "", str(s).split("_")[0].lower())


def to_doy(s):
    s = str(s).strip()
    if "/" not in s:
        return None
    a, b = s.split("/")[:2]
    try:
        return datetime.date(YEAR, int(a), int(b)).timetuple().tm_yday
    except ValueError:
        return None


def to_off(s):
    s = str(s).strip()
    if s in ("", "F"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def get_words(page):
    return [w for w in page.extract_words(x_tolerance=1.5, y_tolerance=1.5)
            if not (float(w["x0"]) < 15 and len(w["text"]) <= 2)]


def build_grid(words):
    """Words (already y-windowed) -> (rows grid, column center list)."""
    xs = sorted(set(round((float(w["x0"]) + float(w["x1"])) / 2) for w in words))
    cols = []
    for x in xs:
        if cols and x - cols[-1][-1] <= 14:
            cols[-1].append(x)
        else:
            cols.append([x])
    centers = [sum(c) / len(c) for c in cols]

    def colof(w):
        xc = (float(w["x0"]) + float(w["x1"])) / 2
        return min(range(len(centers)), key=lambda i: abs(centers[i] - xc))

    rows = defaultdict(lambda: [""] * len(centers))
    for w in words:
        rk = round(float(w["top"]) / 7) * 7
        c = colof(w)
        rows[rk][c] = (rows[rk][c] + " " + w["text"]).strip()
    return [rows[k] for k in sorted(rows)], centers


def parse_maturity_section(grid):
    """Return (anchor_strain, anchor_date_by_col, offsets_by_strain_col, loc_cols)."""
    # strain label = first non-empty cell of a row; merge col0+col1 if col1 is '(xx)'
    def strain_of(r):
        s = (r[0] + (" " + r[1] if len(r) > 1 and r[1].startswith("(") else "")).strip()
        return s
    # data rows: those whose col0 looks like a strain (alpha/code), not headers
    data = [r for r in grid if r and r[0] and r[0].lower() not in
            ("strain", "mean", "tests") and not r[0].upper().startswith("MATURITY")
            and r[0].lower() not in ("date", "days")]
    # location columns = columns where the anchor row holds dates; first find anchor
    ncol = max((len(r) for r in grid), default=0)
    anchor_idx = None
    for i, r in enumerate(data):
        nd = sum(1 for c in range(2, len(r)) if DATE_RE.match(r[c]))
        if nd >= 2:
            anchor_idx = i; break
    if anchor_idx is None:
        return None
    arow = data[anchor_idx]
    loc_cols = [c for c in range(2, len(arow)) if DATE_RE.match(arow[c])]
    if len(loc_cols) < 1:
        return None
    anchor_date = {c: arow[c].strip() for c in loc_cols}
    anchor_strain = strain_of(arow)
    offsets = {}
    for i, r in enumerate(data):
        if i == anchor_idx:
            continue
        s = nm(strain_of(r))
        if not s:
            continue
        for c in loc_cols:
            v = to_off(r[c]) if c < len(r) else None
            if v is not None:
                offsets[(s, c)] = v
    return anchor_strain, anchor_date, offsets, loc_cols


def load_corpus_offsets():
    """Experiment -> {(normStrain, normCity): offset} for 1990 UT offset rows,
    and Experiment -> set of normCity (all cities present)."""
    off = defaultdict(dict)
    with open(WIDE, newline="", encoding="utf-8", errors="replace") as f:
        for x in csv.DictReader(f):
            if x.get("Year") != "1990":
                continue
            exp = x.get("Experiment", "")
            if not exp.upper().startswith("UT"):
                continue
            try:
                v = float((x.get("Maturity") or "").strip())
            except ValueError:
                continue
            if v < 150:
                off[exp][(nm(x.get("Strain")), nc(x.get("Location")))] = v
    return off


def main():
    corpus = load_corpus_offsets()
    out_rows = []
    seen = set()
    with pdfplumber.open(PDF) as pdf:
        for pi, page in enumerate(pdf.pages):
            txt = page.extract_text() or ""
            m = HDR_RE.search(txt)
            if not m or "MATURITY" not in txt.upper():
                continue
            mg = m.group(1).upper()
            exp = f"UT{mg}"   # corpus Experiment format (no hyphen): UT00, UTI, ...
            if exp in seen or exp not in corpus:
                continue
            words = get_words(page)
            mi = next((w for w in words if w["text"].upper().startswith("MATURITY")), None)
            if mi is None:
                continue
            y0 = float(mi["top"])
            sec = [w for w in words if y0 <= float(w["top"]) < y0 + 320]
            grid, _ = build_grid(sec)
            pr = parse_maturity_section(grid)
            if pr is None:
                print(f"  {exp} (p{pi+1}): no anchor parsed"); continue
            anchor_strain, anchor_date, offsets, loc_cols = pr

            # column -> city via offset-matching (vote across strains)
            cstrains = corpus[exp]
            cities_by_strain = defaultdict(dict)
            for (s, city), v in cstrains.items():
                cities_by_strain[s][city] = v
            col_city = {}
            for c in loc_cols:
                votes = Counter()
                for (s, cc), v in offsets.items():
                    if cc != c:
                        continue
                    for city, cv in cities_by_strain.get(s, {}).items():
                        if abs(cv - v) < 0.01:
                            votes[city] += 1
                if votes:
                    col_city[c] = votes.most_common(1)[0][0]
            # emit anchor DOY per mapped city
            n = 0
            for c, city in col_city.items():
                doy = to_doy(anchor_date[c])
                if doy is not None:
                    out_rows.append((YEAR, exp, mg, city, anchor_strain, anchor_date[c], doy))
                    n += 1
            seen.add(exp)
            print(f"  {exp} (p{pi+1}): anchor={anchor_strain:14s} loc_cols={len(loc_cols)} mapped_cities={n}")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Year", "Test", "MG", "Location", "AnchorStrain", "AnchorDate", "AnchorDOY"])
        w.writerows(out_rows)
    print(f"\nWrote {OUT.name}: {len(out_rows)} (Test,City) anchors for {len(seen)} UT trials")


if __name__ == "__main__":
    main()
