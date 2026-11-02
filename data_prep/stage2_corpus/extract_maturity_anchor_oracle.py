"""
extract_maturity_anchor_oracle.py
=================================
Build a PDF-grounded ORACLE of the true per-location maturity ANCHOR for every
(Year, TestType, TestMG, City) maturity table in the F4U era (1941-1988).

Why this exists
---------------
Report maturity tables print, per location column, a footer block:

    "<Check> matured"  <date>      <- the ANCHOR
    "Date planted"     <date>
    "Days to mature"   <n>

and table entries are OFFSETS from that anchor, so DOY = anchor + offset.

Many tables lead with a "Mean of N Tests" SUMMARY column whose footer is a REAL cell
(mean planted / mean matured / mean days). Where the corpus assembler kept that cell in
the FOOTER vector but not in the HEADER vector, every location inherited the anchor of
the column immediately to its LEFT and the last location's anchor was dropped. The
per-strain offsets survive intact, so each affected column is displaced by one constant
-- silent, and invisible to range checks. Confirmed in 1944/1955/1956/1965; see
`analysis/data/analysis_results/Corpus_QC/maturity_anchor_leak_findings.md`.

This script produces the independent ground truth needed to find every instance.

THE CRITICAL DESIGN DECISION
----------------------------
Columns are bound to corpus locations by **offset matching, never by reading the header**.

The bug IS a header<->footer misalignment. Any oracle that trusts the header row would
reproduce the very defect it is meant to detect.

Matching is done on the **centered** value vector. A leaked corpus column holds
    true_anchor + offset_i + constant_error
so subtracting the column's own median removes `true_anchor` AND `constant_error`
together, leaving just the offset shape. Matching is therefore immune to the leak --
a badly displaced column still matches its own location perfectly.

Self-validation
---------------
Two independent routes to each anchor:
    route A  the printed "<Check> matured" date
    route B  planted_DOY + days_to_mature        (both leap-correct)
`identity_ok` records whether they agree. A column is auto-accepted (confidence=HIGH)
only when identity_ok AND the offset match is strong AND unambiguous vs the runner-up.
Everything else is emitted with a lower confidence for review rather than silently trusted.

Reuses the parsing approach of `97_extract_early_anchors_pdf.py` (find sections by their
"Days to mature" footer row, because the printed titles are wildly inconsistent across the
era) and `fix_1988_1990_maturity_doy.py` (x-centre column clustering, offset-vector match).

Usage
-----
    uv run --with pdfplumber python data_prep/stage2_corpus/extract_maturity_anchor_oracle.py
    ... --years 1955,1965        # subset
    ... --refresh                # ignore the per-year parse cache
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SH = REPO / "analysis" / "data" / "_shared"
CORPUS = SH / "nust_1941_2025_combined.csv"
OUT = SH / "nust_maturity_anchor_oracle.csv"
CACHE = REPO / "analysis" / "data" / "intermediate_output" / "anchor_oracle_cache"
RED = Path(r"R:\cfans_agro_lore0149_lorenzlabresearch\NUST_Data\NUST_Data\Red")

YEARS = list(range(1941, 1989))

# --- matching thresholds -------------------------------------------------------------
MIN_MATCH = 3        # min strains agreeing before a PDF column may bind to a corpus group
MIN_FRAC = 0.70      # min agree/compared
TOL = 0.6            # per-strain agreement tolerance, in days
MARGIN = 0.15        # winner must beat runner-up by this much agreement-fraction to be HIGH
OFFSET_MAX = 90      # |offset| sanity bound
DOY_LO, DOY_HI = 175, 340

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
NUMCELL = re.compile(r"^\s*\d{2,3}\s*$")


def nm(s: str) -> str:
    """strain key: drop parenthetical MG tag, keep lower alphanumerics."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())


def to_doy(s, year: int):
    """Leap-CORRECT date -> DOY. Accepts 5-20, 5/20, May 16, 16-May."""
    s = str(s).strip().rstrip("*+ ").replace(".", "")
    mo = dy = None
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})$", s)
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
    if mo is None:
        m = re.match(r"^([A-Za-z]{3,9})\s*(\d{1,2})$", s)
        if m and m.group(1)[:3].lower() in MONTHS:
            mo, dy = MONTHS[m.group(1)[:3].lower()], int(m.group(2))
    if mo is None:
        m = re.match(r"^(\d{1,2})[-\s]([A-Za-z]{3,9})$", s)
        if m and m.group(2)[:3].lower() in MONTHS:
            mo, dy = MONTHS[m.group(2)[:3].lower()], int(m.group(1))
    if mo is None:
        return None
    try:
        return datetime.date(year, mo, dy).timetuple().tm_yday
    except ValueError:
        return None


def to_off(s):
    s = str(s).strip().replace("+", "").replace("**", "").replace("*", "")
    if s in ("", "F", "-", "—", "--", "―"):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if abs(v) <= OFFSET_MAX else None


SKIP_LABEL = ("planted", "days", "mean", "tests", "table", "matur", "pltd", "rank",
              "yield", "average", "l.s.d", "lsd", "c.v")
FOOTER_BIND_TOL = 20.0   # max |dx| binding a footer cell to a data column centre
ROW_GAP = 5.0            # `top` gap that starts a new row band

# Word-extraction tolerances. The older scans fragment badly: signs split from digits
# ("+ 3"), and multi-digit values split per character, so "Days to mature 111 126 119"
# arrives as "1 1 1 1 2 6 ...". Merging at x_tol=4.0/y_tol=3.0 reassembles them -- on
# 1955 Table 4 it turns 5 recoverable day-values into all 10, and every one of the ten
# planted+days==matured identities then closes exactly.
X_TOL, Y_TOL = 4.0, 3.0


def _rows_from_words(sec):
    """Section words -> list of rows, each a list of tokens sorted left-to-right.

    Rows are clustered by GAPS in `top` rather than a fixed bucket. Row pitch varies a lot
    across the era, and on the poorer scans a cell's digits can drop onto a continuation
    line a few points below its label -- a fixed bucket either splits those apart or merges
    genuinely distinct rows, depending on the table.
    """
    tops = sorted({float(w["top"]) for w in sec})
    if not tops:
        return []
    bands = [[tops[0]]]
    for t in tops[1:]:
        if t - bands[-1][-1] <= ROW_GAP:
            bands[-1].append(t)
        else:
            bands.append([t])
    centres = [sum(b) / len(b) for b in bands]
    rws = defaultdict(list)
    for w in sec:
        t = float(w["top"])
        rws[min(range(len(centres)), key=lambda i: abs(centres[i] - t))].append(w)
    return [sorted(rws[k], key=lambda w: float(w["x0"])) for k in sorted(rws)]


def _split_label(row, year):
    """Leading non-numeric tokens are the row label; the rest are data cells."""
    i = 0
    while i < len(row):
        t = row[i]["text"]
        if to_off(t) is not None or to_doy(t, year) is not None or NUMCELL.match(t):
            break
        i += 1
    return " ".join(w["text"] for w in row[:i]), row[i:]


def parse_section(sec_words, year):
    """One maturity block -> per-column anchor evidence + the strain x offset matrix.

    NO header names are read anywhere. Column geometry is derived from the DATA rows, and
    footer cells are then bound to those columns by x-proximity. This matters: binding the
    footer by grid index lets a footer date drift into a neighbouring column -- which is
    the very failure mode under investigation, and would make the oracle reproduce the bug.
    """
    rows = _rows_from_words(sec_words)
    labelled = [(_split_label(r, year), r) for r in rows]

    data_rows, planted, days, matured = [], None, None, None
    for (lab, cells), _raw in labelled:
        low = lab.lower()
        if any(k in low for k in ("planted", "pltd", "date of planting")):
            planted = planted or cells
        elif any(k in low for k in ("days to mat", "da.to mat", "da. to mat", "d.to m",
                                    "days", "da.to", "d. to m")):
            days = days or cells
        elif "matur" in low:
            if matured is None and sum(1 for w in cells if to_doy(w["text"], year)) >= 2:
                matured, matured_label = cells, lab
        elif lab.strip() and not any(k in low for k in SKIP_LABEL):
            data_rows.append((nm(lab), cells))

    if matured is None and (planted is None or days is None):
        return []
    if not data_rows:
        return []

    # column centres from the DATA rows only
    xs = sorted((float(w["x0"]) + float(w["x1"])) / 2
                for _sk, cells in data_rows for w in cells
                if to_off(w["text"]) is not None)
    if len(xs) < 4:
        return []
    clusters = []
    for x in xs:
        if clusters and x - clusters[-1][-1] <= 13:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    # keep clusters seen in enough rows to be a real column
    centers = [sum(c) / len(c) for c in clusters if len(c) >= max(2, len(data_rows) // 3)]
    if not centers:
        return []

    def bind(cells):
        """footer token -> nearest data-column index, by x, within tolerance."""
        out = {}
        for w in cells or []:
            xcen = (float(w["x0"]) + float(w["x1"])) / 2
            i = min(range(len(centers)), key=lambda k: abs(centers[k] - xcen))
            if abs(centers[i] - xcen) <= FOOTER_BIND_TOL:
                out.setdefault(i, w["text"])
        return out

    a_cells, p_cells, d_cells = bind(matured), bind(planted), bind(days)

    cols = {}
    for i in range(len(centers)):
        a_date = a_cells.get(i, "")
        a_doy = to_doy(a_date, year)
        p_doy = to_doy(p_cells.get(i, ""), year)
        d_raw = d_cells.get(i, "")
        d_val = int(d_raw) if NUMCELL.match(d_raw) else None
        ident = (p_doy + d_val) if (p_doy is not None and d_val is not None) else None
        anchor = a_doy if a_doy is not None else ident
        # a maturity anchor outside the physical window is a mis-parse, not a finding
        if anchor is None or not (DOY_LO <= anchor <= DOY_HI):
            continue
        cols[i] = dict(col=i, x=centers[i], anchor_date=a_date, anchor_doy=anchor,
                       anchor_doy_date=a_doy, anchor_doy_identity=ident,
                       planted_doy=p_doy, days=d_val,
                       identity_ok=bool(a_doy is not None and ident is not None
                                        and a_doy == ident),
                       offsets={})
    if not cols:
        return []

    anchor_strain = ""
    if matured is not None:
        anchor_strain = nm(re.sub(r"matur\w*", "", matured_label, flags=re.I))

    for sk, cells in data_rows:
        if not sk:
            continue
        for w in cells:
            v = to_off(w["text"])
            if v is None:
                continue
            xcen = (float(w["x0"]) + float(w["x1"])) / 2
            i = min(range(len(centers)), key=lambda k: abs(centers[k] - xcen))
            if i in cols and abs(centers[i] - xcen) <= FOOTER_BIND_TOL:
                cols[i]["offsets"].setdefault(sk, v)
    if anchor_strain:
        for d in cols.values():
            d["offsets"].setdefault(anchor_strain, 0.0)

    out = [d for d in cols.values() if len(d["offsets"]) >= 2]
    for d in out:
        d["anchor_strain"] = anchor_strain
    return out


def parse_year(year: int, refresh=False):
    """All maturity columns printed in a year's report. Cached per year."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"anchor_cols_{year}.json"
    if cf.exists() and not refresh:
        return json.loads(cf.read_text(encoding="utf-8"))
    pdf_path = REPO / f"input_files/input_{year}/{year}_done.pdf"
    if not pdf_path.exists():
        pdf_path = RED / f"{year}_done.pdf"
    if not pdf_path.exists():
        print(f"  {year}: NO PDF")
        return []
    import pdfplumber
    found = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for pi, page in enumerate(pdf.pages):
            words = [w for w in page.extract_words(x_tolerance=X_TOL, y_tolerance=Y_TOL)
                     if not (float(w["x0"]) < 14 and len(w["text"]) <= 2)]
            if not words:
                continue
            txt = " ".join(w["text"] for w in words).lower()
            if "days" not in txt and "matur" not in txt:
                continue
            # a maturity block is anchored by its "days to mature" footer; a page can hold
            # more than one, so window around each occurrence
            tops = sorted({float(w["top"]) for w in words
                           if w["text"].lower().startswith(("days", "da.to", "da."))}
                          | {float(w["top"]) for w in words
                             if w["text"].lower().startswith("matur")})
            if not tops:
                continue
            seen_spans = []
            for t in tops:
                if any(abs(t - s) < 60 for s in seen_spans):
                    continue
                seen_spans.append(t)
                # Try several window heights above the footer. Standalone maturity tables
                # want a tall window; combined "yield + rank + maturity" tables (e.g. 1965
                # Table 57) want a short one, or yield figures leak in as offsets. Emit all
                # candidates -- the offset match downstream keeps whichever binds best.
                for up in (140, 220, 300, 380):
                    # +95 below: the footer block is three stacked rows ("<check> matured",
                    # "date planted", "days to mature") in either order, and clipping it
                    # costs the identity cross-check that makes a column trustworthy.
                    sec = [w for w in words if (t - up) <= float(w["top"]) <= t + 95]
                    if len(sec) < 12:
                        continue
                    for d in parse_section(sec, year):
                        d["page"] = pi + 1
                        d["window"] = up
                        found.append(d)
    cf.write_text(json.dumps(found), encoding="utf-8")
    print(f"  {year}: parsed {len(found)} maturity columns from {pdf_path.name}")
    return found


def corpus_groups(c: pd.DataFrame, year: int):
    """(TestType, TestMG, City, State) -> {strainKey: DOY} for one year."""
    g = c[c.Year == str(year)]
    out = {}
    for key, sub in g.groupby(["TestType", "TestMG", "City", "State"], dropna=False):
        d = {}
        for sk, v in zip(sub.skey, sub.v):
            if pd.notna(v):
                d.setdefault(sk, v)
        if len(d) >= 2:
            out[key] = d
    return out


def _centered(d: dict):
    """Translation-invariant shape of a value vector: subtract its own median.

    This is what makes matching immune to the leak -- a displaced column carries
    true_anchor + offset + constant_error, and centering removes the anchor and the
    error together, leaving only the offset pattern.
    """
    if not d:
        return {}
    med = float(pd.Series(list(d.values())).median())
    return {k: v - med for k, v in d.items()}


def match_column(col, groups):
    """Bind one PDF column to its corpus group by centered-offset agreement.

    Returns (best_key, agree, compared, frac, runner_up_frac).
    """
    pc = _centered(col["offsets"])
    best = (None, 0, 0, 0.0)
    second = 0.0
    for key, vals in groups.items():
        cc = _centered(vals)
        shared = set(pc) & set(cc)
        if len(shared) < MIN_MATCH:
            continue
        agree = sum(1 for s in shared if abs(pc[s] - cc[s]) <= TOL)
        frac = agree / len(shared)
        if agree < MIN_MATCH or frac < MIN_FRAC:
            continue
        if frac > best[3] or (frac == best[3] and agree > best[1]):
            second = best[3]
            best = (key, agree, len(shared), frac)
        elif frac > second:
            second = frac
    return best + (second,)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default="", help="comma list; default 1941-1988")
    ap.add_argument("--refresh", action="store_true", help="ignore the per-year parse cache")
    args = ap.parse_args()
    years = [int(y) for y in args.years.split(",") if y.strip()] if args.years else YEARS

    print("loading corpus maturity ...")
    c = pd.read_csv(CORPUS, dtype=str, low_memory=False,
                    usecols=["Year", "TestType", "TestMG", "City", "State", "Strain",
                             "Phenotype", "Value_num"])
    c = c[c.Phenotype == "Maturity"].copy()
    c["v"] = pd.to_numeric(c.Value_num, errors="coerce")
    c = c.dropna(subset=["v"])
    c["skey"] = c.Strain.map(nm)
    c["City"] = c.City.astype(str).str.strip()

    rows = []
    for year in years:
        cols = parse_year(year, args.refresh)
        if not cols:
            continue
        groups = corpus_groups(c, year)
        if not groups:
            print(f"  {year}: no corpus maturity groups")
            continue
        used = {}
        for col in cols:
            key, agree, cmp_n, frac, second = match_column(col, groups)
            if key is None:
                continue
            # the corpus anchor implied by THIS column's printed offsets: mode of
            # (corpus_value - printed_offset). Deliberately not the anchor cell -- 1944 UT-I
            # Strongsville's anchor cell reads 239 while 13/16 strains say 240.
            vals = groups[key]
            diffs = [vals[s] - col["offsets"][s]
                     for s in set(vals) & set(col["offsets"])]
            implied = float(pd.Series(diffs).round().mode().iloc[0]) if diffs else None
            unambiguous = (frac - second) >= MARGIN or second == 0.0
            conf = ("HIGH" if (col["identity_ok"] and frac >= 0.9 and agree >= MIN_MATCH
                               and unambiguous)
                    else "MED" if (frac >= MIN_FRAC and agree >= MIN_MATCH and unambiguous)
                    else "LOW")
            tt, mg, city, state = key
            rec = dict(Year=year, TestType=tt, TestMG=mg, City=city, State=state,
                       anchor_strain=col.get("anchor_strain", ""),
                       anchor_date=col["anchor_date"],
                       anchor_doy=col["anchor_doy"],
                       anchor_doy_date=col["anchor_doy_date"],
                       anchor_doy_identity=col["anchor_doy_identity"],
                       planted_doy=col["planted_doy"], days_to_mature=col["days"],
                       identity_ok=col["identity_ok"],
                       corpus_implied_anchor=implied,
                       delta=(None if (implied is None or col["anchor_doy"] is None)
                              else col["anchor_doy"] - implied),
                       n_offsets_matched=agree, n_compared=cmp_n,
                       match_frac=round(frac, 3), runner_up_frac=round(second, 3),
                       # x + page locate the column on the printed page, so the diff can ask
                       # the decisive question: does this column hold its LEFT NEIGHBOUR's anchor?
                       page=col["page"], x=round(col["x"], 1),
                       window=col.get("window"), confidence=conf)
            # keep the strongest binding when two PDF columns claim one corpus group
            prev = used.get(key)
            if prev is None or (frac, agree) > (prev["match_frac"], prev["n_offsets_matched"]):
                used[key] = rec
        rows.extend(used.values())
        n_hi = sum(1 for r in used.values() if r["confidence"] == "HIGH")
        n_bad = sum(1 for r in used.values() if r["delta"] not in (0, None))
        print(f"  {year}: bound {len(used):3d} columns  (HIGH {n_hi:3d})  delta!=0: {n_bad}")

    d = pd.DataFrame(rows)
    if d.empty:
        print("no columns bound -- nothing written")
        return
    d = d.sort_values(["Year", "TestType", "TestMG", "City"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}  ({len(d)} bound columns)")
    print(f"  confidence: {d.confidence.value_counts().to_dict()}")
    print(f"  identity_ok: {int(d.identity_ok.sum())}/{len(d)}")
    nz = d[(d.delta.notna()) & (d.delta != 0)]
    print(f"  columns whose corpus anchor disagrees with the report: {len(nz)}")
    if len(nz):
        print(nz.groupby(["Year", "TestType", "TestMG"]).size()
              .sort_values(ascending=False).head(30).to_string())


if __name__ == "__main__":
    main()
