"""
89a_extract_checks_1989_1992_pdf.py
====================================
Targeted check-variety extraction for 1989, 1991, 1992 from the NUST Red PDFs.

WHY: script 65's lookup has no per-year checks for these three years (script 67's
pdfplumber sweep used find_pdf() paths that don't match these flat PDFs, AND the
1989+ entry-list format dropped the numbered rows + the ">=3 years previous
testing" check signal that 67 relied on). The IsCheck rebuild (script 89) needs
(MG, Strain, Year) check designations for them.

HOW (zero-API, fully local — the Red PDFs are NEVER uploaded anywhere):
  pdfplumber text extraction of each test's "REGIONAL SUMMARY" table (the
  per-MG check/yield summary the user referred to). For each UNIFORM TEST <MG>
  regional summary page, a strain row is a CHECK iff BOTH:
    (a) its first token is a purely-alphabetic cultivar name (NOT a breeding
        code like A86-103002 / K1191 / IA2007 / LN88-10534), AND
    (b) it is an ESTABLISHED check variety, i.e. EITHER
          - in the existing check ROSTER (union of all (MG,Strain) ever
            designated a check, from nust_check_designation_years_1941_2025.csv),
            OR
          - it RECURS >= RECUR_MIN distinct years in the combined long file
            (established public cultivars used as references recur for many
            years; one-off experimental named lines do not).
  Designation MG = the TEST's MG (from the page header), so a cross-MG check
  (e.g. Burlison in both UT-II and UT-III) is recorded under EACH test MG it
  served in — matching how TestMG is stored in the combined file.

  The recurrence arm fills genuine gaps the bridged 1990+1993 roster missed
  (Jack, Ripley, Charleston, Pennyrile, ...). Validated on 1990 (the one
  adjacent year with an authoritative checksTable): this rule recovers ALL
  designated checks with ZERO misses. (a)+(b) together exclude breeding-code
  lines and one-off experimental names; candidates failing (b) are logged, not
  emitted, for transparency.

OCR robustness: the yield column is often garbled with doubled punctuation
("47..9", "1,.8"); the row regex tolerates [.,]+ in the leading number. Leading
column-bleed tokens ("I SIBLEY") are stripped as a matching variant.

Output: analysis/data/_shared/nust_checks_1989_1992_from_pdf.csv  (MG, Strain, Year)
        + console report of per-(year,MG) hits and unmatched candidates.

Usage:
    PYTHONUTF8=1 uv run python analysis/89a_extract_checks_1989_1992_pdf.py
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO     = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
DATA     = REPO / "analysis/data/_shared"
DESIG    = DATA / "nust_check_designation_years_1941_2025.csv"
COMBINED = DATA / "nust_1941_2025_combined.csv"
OUT      = DATA / "nust_checks_1987_1992_from_pdf.csv"

YEARS = [1987, 1988, 1989, 1991, 1992]   # ERA-C regional-summary years lacking per-year checks
MG_ORDER = ["00", "0", "I", "II", "III", "IV"]
RECUR_MIN = 3   # >= this many distinct years in combined => established check

# Summary / non-variety row labels that must never be taken as a strain name
STOPWORDS = {
    "mean", "means", "average", "avg", "median", "lsd", "cv", "se", "sd", "std",
    "total", "range", "grand", "check", "checks", "entry", "entries", "no",
    "number", "test", "tests", "location", "locations", "overall", "high", "low",
    "max", "min", "sum", "count", "strain", "variety",
}

# UNIFORM TEST <MG>, <year>  (regional-summary page header)
HDR_RE = re.compile(r"UNIFORM\s+TEST\s+(0{1,2}|[IV]+)\s*,?\s*(19\d\d)", re.IGNORECASE)
# strain row: leading name then a yield number (OCR-doubled punctuation tolerated)
ROW_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 .()/'\-]*?)\s+(\d{1,3}[.,]+\d)\b")


def norm(s):
    """lowercase, drop trailing asterisk/space — match key shared with script 89."""
    return re.sub(r"\s*\*?\s*$", "", str(s).strip().lower())


def strip_paren(b):
    return re.sub(r"\s*\([^)]*\)\s*$", "", str(b)).strip()


def first_token_is_cultivar(base):
    """True if the first token is a purely-alphabetic cultivar word (no digits)
    and not a summary/non-variety row label (Mean, LSD, ...)."""
    toks = base.split()
    if not toks or not re.match(r"^[A-Za-z][A-Za-z.'\-]*$", toks[0]):
        return False
    return toks[0].lower().strip(".") not in STOPWORDS


def match_variants(base):
    """Candidate cleaned forms tried against the roster (handles column bleed)."""
    base = strip_paren(base)
    return {
        base,
        re.sub(r"^[IVX0O]{1,3}\s+(?=[A-Za-z])", "", base),  # strip leading bled MG/rank token
        re.sub(r"\s+[IVX0O]{1,3}$", "", base),              # strip trailing bled token
    }


def load_roster():
    """norm(name) -> canonical display name, from the existing designation file."""
    desig = pd.read_csv(DESIG, dtype=str)
    roster = {}
    for s in desig["Strain"].dropna():
        roster[norm(s)] = s
    return roster


def load_combined_recurrence():
    """norm(strain) -> (n_distinct_years, example_display_spelling) from combined.

    Used for the recurrence arm: an established check recurs many years. The
    example spelling is the combined file's own Strain text (proper case), so
    emitted names match the combined rows under norm()."""
    years = defaultdict(set)
    spell = {}
    with open(COMBINED, newline="", encoding="utf-8", errors="replace") as f:
        for x in csv.DictReader(f):
            s = x.get("Strain")
            if not s:
                continue
            k = norm(s)
            try:
                years[k].add(int(float(x["Year"])))
            except (TypeError, ValueError, KeyError):
                continue
            spell.setdefault(k, s.strip())
    return {k: (len(ys), spell.get(k, k)) for k, ys in years.items()}


def find_pdf(year):
    for cand in (REPO / f"input_files/{year}.pdf",
                 REPO / f"input_files/input_{year}/{year}_done.pdf",
                 REPO / f"input_files/input_{year}/{year}.pdf"):
        if cand.exists():
            return cand
    return None


def accept(base, roster, recur):
    """Return (canonical_name, reason) if base is an established check, else None.

    Tries cleaned variants against the roster, then against the recurrence map."""
    for v in match_variants(base):
        nk = norm(v)
        if nk in roster:
            return roster[nk], "roster"
    for v in match_variants(base):
        nk = norm(v)
        if nk in recur and recur[nk][0] >= RECUR_MIN:
            return recur[nk][1], f"recur={recur[nk][0]}y"
    return None


def extract_year(year, roster, recur):
    pdf_path = find_pdf(year)
    if pdf_path is None:
        print(f"{year}: PDF not found at input_files/{year}.pdf — skipped")
        return [], []
    rows, unmatched = [], []
    with pdfplumber.open(pdf_path) as pdf:
        seen_mg = set()
        for i, pg in enumerate(pdf.pages):
            txt = pg.extract_text() or ""
            if "REGIONAL SUMMARY" not in txt.upper():
                continue
            m = HDR_RE.search(txt)
            if not m:
                continue
            mg = m.group(1).upper()
            if mg not in MG_ORDER or mg in seen_mg:
                continue
            seen_mg.add(mg)
            hits = {}
            for ln in txt.splitlines():
                rm = ROW_RE.match(ln.strip())
                if not rm:
                    continue
                base = strip_paren(rm.group(1).strip())
                if not first_token_is_cultivar(base):
                    continue            # breeding-code line — skip
                res = accept(base, roster, recur)
                if res:
                    canon, reason = res
                    hits[norm(canon)] = (canon, reason)
                else:
                    unmatched.append((year, mg, base))
            for canon, _reason in hits.values():
                rows.append({"MG": mg, "Strain": canon, "Year": year})
            shown = sorted(f"{c} [{r}]" for c, r in hits.values())
            print(f"  {year} UT-{mg:<3s} (p{i+1}): {shown}")
    return rows, unmatched


def main():
    roster = load_roster()
    print(f"Loaded check roster: {len(roster)} canonical names")
    recur = load_combined_recurrence()
    print(f"Loaded combined recurrence: {len(recur)} distinct strains\n")
    all_rows, all_unmatched = [], []
    for yr in YEARS:
        print(f"=== {yr} ===")
        rows, unmatched = extract_year(yr, roster, recur)
        all_rows.extend(rows)
        all_unmatched.extend(unmatched)
        print()

    df = pd.DataFrame(all_rows, columns=["MG", "Strain", "Year"]).drop_duplicates()
    df["MG"] = pd.Categorical(df["MG"], categories=MG_ORDER, ordered=True)
    df = df.sort_values(["Year", "MG", "Strain"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Wrote: {OUT}  ({len(df)} (MG,Strain,Year) check rows)")
    print("Per-year check counts:")
    print(df.groupby("Year", observed=True).size().to_string())

    # Transparency: named-cultivar candidates NOT in the roster (NOT emitted)
    if all_unmatched:
        uniq = sorted(set(all_unmatched))
        print(f"\nNamed-cultivar candidates NOT in roster ({len(uniq)} — logged, not emitted):")
        for yr, mg, base in uniq:
            print(f"  {yr} UT-{mg}: {base}")


if __name__ == "__main__":
    main()
