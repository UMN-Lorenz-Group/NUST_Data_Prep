"""
112b_extract_perloc_pt.py
=========================
PT-section-capable **thin wrapper** around `112_extract_pdf_perloc.py`.

Why a wrapper (not a fork): `112` is under active development by the parallel recovery
campaign (its `_parse_region` city/column reconstruction). We do NOT want to duplicate
that evolving code. This module imports the sibling `112` at runtime (inheriting every
future improvement) and monkeypatches ONLY `section_pages` so it also finds the 1970s-80s
**"PRELIMINARY TEST <mg>, <year>"** headers (which drop the "UNIFORM" word that stock 112
requires -> stock 112 returns 0 rows for any PT section). The boundary test is made
type-aware so a same-MG UNIFORM section correctly ends a PRELIMINARY section.

STATUS (2026-07-20): PT-section discovery + non-maturity traits (Yield/Height/Lodging/…)
extract for 1972/1980 PT-III. **MATURITY is NOT yet reliable for these dense multi-location
PT tables** — the underlying 112 `_parse_region` currently recovers only ~3 of ~10 location
columns and mis-assigns them, so the check (dated) anchor row and the derived DOYs come out
WRONG (verified 1972 PT-III: Wayne's Girard read 9-23 vs printed 9-18). Do NOT integrate PT
maturity from here until 112's per-location column parity lands; then this wrapper yields it
for free. See MATURITY_GAP_RESOLUTION.md.

Usage:
    uv run python data_prep/stage2_corpus/112b_extract_perloc_pt.py 1972 PT-III
    from 112b: extract_pdf_section(year, code)  # same signature/return as 112
"""
import importlib.util
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_m112", _HERE / "112_extract_pdf_perloc.py")
_m112 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m112)


def section_pages(pdf, year, code):
    """PT-aware replacement for 112.section_pages. Matches 'UNIFORM TEST <mg>, <year>' for
    UT and 'PRELIMINARY TEST <mg>, <year>' for PT; a section boundary is any header with a
    DIFFERENT (type, mg)."""
    mg = re.sub(r"^(UT|PT)-", "", code)
    is_pt = code.startswith("PT")
    hdr_word = "preliminary" if is_pt else "uniform"
    hdr = re.compile(rf"\b{hdr_word} test\s+{re.escape(mg)}\b[, ]\s*{year}", re.I)
    anyhdr = re.compile(r"\b(uniform|preliminary) test\s+(0{1,2}|[ivx]+)\b", re.I)
    pages, state = [], "before"
    for i, pg in enumerate(pdf.pages):
        t = re.sub(r"\s+", " ", (pg.extract_text() or ""))
        is_self = bool(hdr.search(t))
        m = anyhdr.search(t)
        m_other = bool(m) and (m.group(2).upper() != mg.upper()
                               or (m.group(1).lower() == "preliminary") != is_pt)
        is_other = m_other and not is_self
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


# inject PT-aware section discovery into the live 112 module, then reuse its extractor as-is
_m112.section_pages = section_pages
extract_pdf_section = _m112.extract_pdf_section


def main():
    year, code = int(sys.argv[1]), sys.argv[2]
    df = extract_pdf_section(year, code)
    print(f"{year} {code}: {len(df)} rows")
    if len(df):
        print(df.groupby("Phenotype").agg(n=("Value_num", "size"),
                                          locs=("City", "nunique")).to_string())


if __name__ == "__main__":
    main()
