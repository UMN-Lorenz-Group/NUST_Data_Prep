"""
97_extract_early_anchors_pdf.py
===============================
Recover the maturity anchor DOY for the pre-1990 "no anchor table" years
(1965,1966,1967,1968,1971,1982,1986) from the Red PDFs, LOCALLY (pdfplumber word
positions; ZERO API). These years' maturity tables print the reference check as
all-zero offsets (no absolute date); the anchor comes from the footer rows
  Date Planted  +  Days to Mature
=>  anchorDOY(location) = plantedDOY(loc) + daysToMature(loc).

The PDF title wording for these tables is wildly inconsistent across the era
("Maturity dates, Uniform Test 00" / "Maturity, days earlier than Acme ... for
Uniform Test" / inline "MATURITY (relative date)"), so we DO NOT parse it.
Instead every maturity section is found by its "Days to mature" footer row, and
the section's whole strain x offset matrix is OFFSET-MATCHED against the corpus's
un-anchored Maturity values to (a) identify which (Year, Experiment) it is and
(b) map each grid column to a corpus city. Fully data-driven.

Output: analysis/data/_shared/nust_anchor_early_pdf.csv  (Year,Test,Location,AnchorDOY)
consumed by 96_fix_early_maturity.py.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/97_extract_early_anchors_pdf.py
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
# offsets live in the pre-96 backup (96 already NULLed them in the live corpus)
OFFSRC = REPO / "analysis/data/_shared/NUST_1941_2025_data_wide.pre_earlymatfix.bak"
OUT = REPO / "analysis/data/_shared/nust_anchor_early_pdf.csv"
YEARS = [1965, 1966, 1967, 1968, 1971, 1982, 1986]

NUMcell = re.compile(r"^\s*\d{2,3}\s*$")             # days-to-mature value
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def nm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())


def nc(s):
    s = re.sub(r"_\d+$", "", str(s).strip())
    return re.sub(r"[^a-z0-9]", "", str(s).split("_")[0].split(" ")[0].lower())


def to_doy(s, year):
    s = str(s).strip().replace(".", "")
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})$", s)                      # 5-20 / 5/20
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
    else:
        m = re.match(r"^([A-Za-z]{3,9})\.?\s*(\d{1,2})$", s)          # May 16 / September 15
        if m and m.group(1)[:3].lower() in MONTHS:
            mo, dy = MONTHS[m.group(1)[:3].lower()], int(m.group(2))
        else:
            m = re.match(r"^(\d{1,2})[-\s]([A-Za-z]{3,9})$", s)       # 16-May
            if m and m.group(2)[:3].lower() in MONTHS:
                mo, dy = MONTHS[m.group(2)[:3].lower()], int(m.group(1))
            else:
                return None
    try:
        return datetime.date(year, mo, dy).timetuple().tm_yday
    except ValueError:
        return None


def to_off(s):
    s = str(s).strip().replace("+", "").replace("**", "")
    if s in ("", "F", "-", "—", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def build_grid(words):
    if not words:
        return []
    xs = sorted(set(round((float(w["x0"]) + float(w["x1"])) / 2) for w in words))
    cols = []
    for x in xs:
        if cols and x - cols[-1][-1] <= 13:
            cols[-1].append(x)
        else:
            cols.append([x])
    centers = [sum(c) / len(c) for c in cols]
    rows = defaultdict(lambda: [""] * len(centers))
    for w in words:
        rk = round(float(w["top"]) / 7) * 7
        c = min(range(len(centers)), key=lambda i: abs(centers[i] - (float(w["x0"]) + float(w["x1"])) / 2))
        rows[rk][c] = (rows[rk][c] + " " + w["text"]).strip()
    return [rows[k] for k in sorted(rows)]


def load_corpus_offsets(years):
    """(year, Experiment) -> {normStrain: {city: offset}} for un-anchored rows."""
    off = defaultdict(lambda: defaultdict(dict))
    ys = set(str(y) for y in years)
    with open(OFFSRC, newline="", encoding="utf-8", errors="replace") as f:
        for x in csv.DictReader(f):
            if x.get("Year") not in ys:
                continue
            try:
                v = float((x.get("Maturity") or "").strip())
            except ValueError:
                continue
            if v < 150:
                off[(x["Year"], x["Experiment"])][nm(x["Strain"])][nc(x["Location"])] = v
    return off


def parse_section(grid, year):
    """Window grid -> (anchorDOY per col, {strain:{col:offset}}). None if no footer."""
    def find(key):
        for r in grid:
            if key in " ".join(r[:3]).lower():
                return r
        return None
    planted = find("planted")
    days = find("days to mat") or find("days")
    if planted is None or days is None:
        return None
    width = max(len(planted), len(days))

    def cell(r, c):
        return r[c].strip() if c < len(r) else ""

    anchor = {}
    for c in range(width):
        pdoy = to_doy(cell(planted, c), year)
        d = cell(days, c)
        if pdoy is not None and NUMcell.match(d):
            anchor[c] = pdoy + int(d)
    if not anchor:
        return None
    offs = {}
    for r in grid:
        head = " ".join(r[:3]).lower()
        if not r[0].strip() or any(k in head for k in ("planted", "days", "mean", "tests", "table")):
            continue
        s = nm(r[0])
        if not s:
            continue
        for c in anchor:
            v = to_off(cell(r, c))
            if v is not None:
                offs.setdefault(s, {})[c] = v
    return anchor, offs


def identify_exp(offs, corpus_year):
    """Pick the (year,Exp) whose strain x offset matrix best matches, by NON-ZERO hits."""
    best, best_key = 0, None
    for key, cstr in corpus_year.items():
        hits = 0
        for s, cols in offs.items():
            if s not in cstr:
                continue
            for c, ov in cols.items():
                if ov == 0:
                    continue
                if any(abs(cv - ov) < 0.01 for cv in cstr[s].values()):
                    hits += 1
        if hits > best:
            best, best_key = hits, key
    return best_key if best >= 2 else None


def main():
    corpus = load_corpus_offsets(YEARS)
    out = {}                                   # (year,exp,city) -> anchorDOY (dedup)
    for year in YEARS:
        cy = {k: v for k, v in corpus.items() if k[0] == str(year)}
        pdf_path = REPO / f"input_files/input_{year}/{year}_done.pdf"
        per_exp = Counter()
        with pdfplumber.open(pdf_path) as pdf:
            for pg in pdf.pages:
                words = [w for w in pg.extract_words(x_tolerance=1.5, y_tolerance=1.5)
                         if not (float(w["x0"]) < 14 and len(w["text"]) <= 2)]
                # every "days to mature" row marks a maturity section footer
                dtops = [float(w["top"]) for w in words
                         if w["text"].lower().startswith("days")]
                for yd in dtops:
                    win = [w for w in words if yd - 340 <= float(w["top"]) <= yd + 12]
                    res = parse_section(build_grid(win), year)
                    if res is None:
                        continue
                    anchor, offs = res
                    key = identify_exp(offs, cy)
                    if key is None:
                        continue
                    cstr = corpus[key]
                    for c, adoy in anchor.items():
                        votes = Counter()
                        for s, cols in offs.items():
                            if c in cols and s in cstr:
                                for city, cv in cstr[s].items():
                                    if abs(cv - cols[c]) < 0.01:
                                        votes[city] += (2 if cols[c] != 0 else 1)
                        if votes:
                            city = votes.most_common(1)[0][0]
                            ok = (year, key[1], city)
                            if ok not in out:
                                out[ok] = adoy
                                per_exp[key[1]] += 1
        print(f"{year}: {dict(per_exp)}  total {sum(per_exp.values())}")

    rows = [(y, e, c, d) for (y, e, c), d in sorted(out.items())]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Year", "Test", "Location", "AnchorDOY"])
        w.writerows(rows)
    print(f"\nWrote {OUT.name}: {len(rows)} anchors  (range "
          f"{min((r[3] for r in rows), default=0):.0f}-{max((r[3] for r in rows), default=0):.0f})")


if __name__ == "__main__":
    main()
