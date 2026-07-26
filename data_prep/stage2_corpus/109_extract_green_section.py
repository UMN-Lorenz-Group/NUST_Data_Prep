"""
109_extract_green_section.py
============================
General per-location extractor for the Green Sojabone XLSX tp-block matrices
(the structured digitized source). Recovers trait tables that the F4U extraction
SKIPPED for specific (year, test) sections — Phase 2 of the gap campaign.

The Green Sheet1 format is consistent across years: each test section's traits are
stored as `tp`-tagged per-location matrices, header row = `Strain | Mean N Tests |
<City, ST> | <City, ST> | ...`, data rows = `<strain> | <mean> | <per-loc values>`:
  tp6 -> YieldBuA, tp8 -> Maturity, tp9 -> Lodging, tp10 -> Height,
  tp11a -> SeedQuality, tp11b -> SeedSize, tp12a -> Protein, tp12b -> Oil.
(tp7 YieldRank is skipped.) A year may span multiple Green files; blocks are matched
to a target test section by STRAIN ROSTER overlap (robust to file splits / unlabeled
blocks). Protein/Oil get the x0.87 dry->13%mb convention (corpus convention).

Maturity: the section's anchor CHECK row carries absolute dates (openpyxl returns them
as datetimes, bogus year but real month/day); other strains carry relative offsets.
DOY(strain,loc) = day_of_year(anchor_date[loc]) + offset(strain,loc). Reuses the
convention of apply_patches_corpus_maturity_doy.py.

Output: long rows {Year,TestType,TestMG,Test,Strain,City,State,Phenotype,Value_num,Units,Source="Green"}.
This is ONE side of the dual-source cross-check (105); PDF side is 111. NO API.

Usage (library): extract_section(year, test_code, roster:set[str]) -> DataFrame
CLI:  uv run python 109_extract_green_section.py <year> <TEST_CODE>   (roster from F4U/PDF)
"""
import sys
import re
import glob
import datetime as dt
from collections import defaultdict
from pathlib import Path
import openpyxl
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
DRY_TO_13 = 0.87
TP_TRAIT = {"tp6": ("YieldBuA", "bu/a"), "tp8": ("Maturity", "date"),
            "tp9": ("Lodging", "score"), "tp10": ("Height", "inches"),
            "tp11a": ("SeedQuality", "score"), "tp11b": ("SeedSize", "g/100"),
            "tp12a": ("Protein", "%"), "tp12b": ("Oil", "%")}
STATE_FIX = {"ON": "ONT", "ONT": "ONT"}
# "State City" header prefixes (1970s-80s Green order), longest-first so two-word states win.
_STATE_PREFIX = [
    ("SOUTH DAKOTA", "SD"), ("NORTH DAKOTA", "ND"), ("NEW JERSEY", "NJ"),
    ("N. D.", "ND"), ("S. D.", "SD"), ("N.D.", "ND"), ("S.D.", "SD"), ("N.J.", "NJ"),
    ("ONTARIO", "ONT"), ("ONT", "ONT"), ("MANITOBA", "MB"), ("MINNESOTA", "MN"), ("MINN", "MN"),
    ("WISCONSIN", "WI"), ("WIS", "WI"), ("MICHIGAN", "MI"), ("MICH", "MI"), ("INDIANA", "IN"),
    ("IND", "IN"), ("ILLINOIS", "IL"), ("ILL", "IL"), ("IOWA", "IA"), ("OHIO", "OH"),
    ("NEBRASKA", "NE"), ("NEB", "NE"), ("MISSOURI", "MO"), ("KANSAS", "KS"),
]


def norm(s):
    s = re.sub(r"\s*\([^)]*\)", "", str(s))
    s = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return s.replace("O", "0").replace("L", "1").replace("I", "1")


def parse_loc(h):
    """Header cell -> (City, State) or None for the mean column. Handles both header orders:
    'Ames, IA' (City, ST) and 'Ont. Elora' / 'South Dakota Brookings' / 'N.D. Oakes I'
    (State City, state prefix 1-2 words). Strips a trailing footnote ' I'."""
    h = str(h).strip()
    if not h or re.match(r"(mean|strain)\b", h, re.I) or "test" in h.lower():
        return None
    m = re.match(r"^(.*?),\s*([A-Za-z]{2})\b", h)                 # "City, ST"
    if m:
        st = m.group(2).upper()
        return (re.sub(r"\s+I$", "", m.group(1).strip()), STATE_FIX.get(st, st))
    for pref, st in sorted(_STATE_PREFIX, key=lambda x: -len(x[0])):   # "State City"
        mm = re.match(rf"^{re.escape(pref)}\.?\s+(.+)$", h, re.I)
        if mm:
            city = re.sub(r"\s+I$", "", mm.group(1).strip(" .,"))
            return (city, st) if city else None
        if h.upper().rstrip(".") == pref:
            return None                                              # state-only header (no city)
    return (re.sub(r"\s+I$", "", h.strip(" .,")), "")


def cellnum(v):
    """Parse a numeric cell value (str/float); ignore dates/blanks/'--'."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().rstrip("*+ ")
    if not s or s in ("--", "-", "—") or "00:00:00" in s:
        return None
    s = s.replace(",", ".")
    s = re.sub(r"(?<=\d)\.\.(?=\d)", ".", s)            # OCR "2..5" -> "2.5"
    m = re.match(r"^[+\-]?\d+(\.\d+)?$", s)
    return float(s) if m else None


def cell_doy(v, year):
    """day-of-year from a date-ish maturity cell ('9-15', datetime, '2026-09-15 00:00:00').

    `year` is REQUIRED and must be the real report year. This previously converted through a
    fixed reference year (1959, non-leap), which made every date from Mar 1 on 1 day early in
    a leap year. Positional and required so a missed call site raises rather than silently
    mis-converting.
    """
    if isinstance(v, (dt.datetime, dt.date)):
        return v.timetuple().tm_yday
    s = str(v).strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s) or re.match(r"^(\d{1,2})[-/](\d{1,2})$", s)
    if not m:
        return None
    if m.lastindex == 3:
        mo, dy = int(m.group(2)), int(m.group(3))
    else:
        mo, dy = int(m.group(1)), int(m.group(2))
    if not (1 <= mo <= 12 and 1 <= dy <= 31):
        return None
    try:
        return dt.date(int(year), mo, dy).timetuple().tm_yday
    except ValueError:
        return None


def load_blocks(year):
    """Every tp-table block across the year's Green files: list of dicts
    {trait, units, locs, rows, section}. `section` increments at each `tp2` parentage marker
    (continuous across the year's page-ordered files) so blocks can be grouped by test SECTION
    rather than by global strain-roster overlap (adjacent sections share check varieties)."""
    files = sorted(set(glob.glob(str(REPO / "input_files" / f"input_{year}" / "*Sojabone*.xlsx")) +
                       glob.glob(str(REPO / "input_files" / f"input_{year}" / "*OR*.xlsx"))))
    blocks = []
    section = 0
    for f in files:
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        ws = wb["Sheet1"]
        grid = [list(r) for r in ws.iter_rows(values_only=True)]
        i = 0
        while i < len(grid):
            tag = str(grid[i][0]).strip() if grid[i][0] is not None else ""
            if tag == "tp2":                      # parentage table = start of a new test section
                section += 1
                i += 1
                continue
            if tag in TP_TRAIT:
                trait, units = TP_TRAIT[tag]
                # header = next row whose col A is "Strain"
                h = i + 1
                while h < len(grid) and h < i + 4 and str(grid[h][0]).strip().lower() != "strain":
                    h += 1
                if h >= len(grid) or str(grid[h][0]).strip().lower() != "strain":
                    i += 1
                    continue
                header = grid[h]
                locs = [parse_loc(c) for c in header[1:]]
                rows = {}
                r = h + 1
                while r < len(grid):
                    a = grid[r][0]
                    atag = str(a).strip() if a is not None else ""
                    if not atag:
                        r += 1
                        if r < len(grid) and (grid[r][0] is None):
                            break
                        continue
                    if re.match(r"tp\d", atag) or atag.lower() in ("strain",):
                        break
                    if re.match(r"(mean|no\.?\s|c\.?v|l\.?s\.?d|coef|range|row spacing|bu\.|grand)", atag, re.I):
                        r += 1
                        continue
                    rows[atag] = list(grid[r][1:])
                    r += 1
                blocks.append({"trait": trait, "units": units, "locs": locs,
                               "rows": rows, "file": Path(f).name, "row": i, "section": section})
                i = r
            else:
                i += 1
    return blocks


def _block_long_rows(b, year):
    """Yield (strain, city, state, phenotype, value, units) for one tp-table block.
    Maturity: reconstruct DOY from the block's anchor (dated) row + per-strain offsets.
    `year` is required for leap-correct date -> DOY conversion."""
    locs = b["locs"]
    if b["trait"] == "Maturity":
        # anchor = the CHECK variety's "matured" date row. The block can also contain a
        # "Date planted" row (~May, DOY ~120-160); restrict anchors to the soybean maturity
        # window (DOY 200-330) so the planting row is never mistaken for the anchor.
        anchor_doy = {}
        for strain, cells in b["rows"].items():
            doys = [(j, cell_doy(c, year)) for j, c in enumerate(cells)
                    if cell_doy(c, year) is not None and 200 <= cell_doy(c, year) <= 330]
            if len(doys) >= max(2, sum(1 for L in locs if L) // 2):
                for j, d in doys:
                    if j < len(locs) and locs[j]:
                        anchor_doy[j] = d
                break
        for strain, cells in b["rows"].items():
            for j, c in enumerate(cells):
                if j >= len(locs) or not locs[j]:
                    continue
                city, state = locs[j]
                d = cell_doy(c, year)
                if d is None or not (200 <= d <= 330):       # not an absolute matured date -> offset
                    off = cellnum(c)
                    if off is None or j not in anchor_doy:
                        continue
                    d = int(anchor_doy[j] + off)
                yield (strain, city, state, "Maturity", float(d), "date")
    else:
        for strain, cells in b["rows"].items():
            for j, c in enumerate(cells):
                if j >= len(locs) or not locs[j]:
                    continue
                v = cellnum(c)
                if v is None:
                    continue
                # the combined corpus stores Protein/Oil DRY-basis for the F4U era (verified:
                # 1977 Coles protein ~39.9 dry, not x0.87) -> store dry; any moisture conversion
                # is applied uniformly downstream.
                city, state = locs[j]
                yield (strain, city, state, b["trait"], round(v, 2), b["units"])


def _select_section(blocks, roster):
    """Pick the single Green section whose strain set best covers `roster` (target test).
    Returns (section_id, coverage, blocks_in_section). Avoids cross-section roster bleed."""
    from collections import defaultdict
    secs = defaultdict(list)
    for b in blocks:
        secs[b["section"]].append(b)
    best = (None, 0.0, [])
    for sid, bs in secs.items():
        strains = set()
        for b in bs:
            strains |= {norm(s) for s in b["rows"]}
        if not strains:
            continue
        cov = len(roster & strains) / max(1, len(roster))
        if cov > best[1]:
            best = (sid, cov, bs)
    return best


def extract_section(year, test_code, roster):
    """Recover per-location long rows for (year, test_code). `roster` = normalized strain keys
    identifying the target test. Selects the matching Green SECTION (by roster coverage), then
    emits only that section's blocks (incl. its page1+page2 continuations). KEY_COLS schema."""
    tt = "PT" if test_code.startswith("PT") else "UT"
    mg = re.sub(r"^(UT|PT)-", "", test_code)
    sid, cov, section_blocks = _select_section(load_blocks(year), roster)
    out = []
    if sid is not None and cov >= 0.5:
        for b in section_blocks:
            out.extend(_block_long_rows(b, year))
    df = pd.DataFrame(out, columns=["Strain", "City", "State", "Phenotype", "Value_num", "Units"])
    if len(df):
        df.insert(0, "Year", year)
        df.insert(1, "TestType", tt)
        df.insert(2, "TestMG", mg)
        df.insert(3, "Test", test_code)
        df["Source"] = "Green"
    return df


def section_means(year, test_code, roster):
    """{(strain_norm, trait): Green 'Mean N Tests' value} for the matched section — used to
    cross-check against the PDF Regional Summary strain-mean (validation independent of the
    possibly-buggy existing corpus). Maturity excluded (its mean is a relative offset)."""
    sid, cov, blocks = _select_section(load_blocks(year), roster)
    means = {}
    if sid is None or cov < 0.5:
        return means
    for b in blocks:
        if b["trait"] == "Maturity":
            continue
        mean_idx = next((idx for idx, L in enumerate(b["locs"]) if L is None), None)  # the "Mean" col
        if mean_idx is None:
            continue
        for strain, cells in b["rows"].items():
            if mean_idx < len(cells):
                v = cellnum(cells[mean_idx])
                if v is not None:
                    means[(norm(strain), b["trait"])] = round(v, 2)
    return means


def _roster_from_f4u_or_pdf(year, test_code):
    """Best-effort roster for the target section (F4U if present, else caller supplies)."""
    from pathlib import Path as _P
    NUST = _P("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
    for base in (NUST / "NUST_Historical_Data_1941_1988", NUST):
        p = base / f"{year}_Processing" / "Files4Upload" / "phenotypesTable1.csv"
        if p.exists():
            d = pd.read_csv(p, dtype=str)
            tcol = next(c for c in d.columns if c.lower() == "test")
            scol = next(c for c in d.columns if c.lower() in ("strain", "germplasmid", "entry"))
            r = {norm(s) for s in d[d[tcol] == test_code][scol].dropna() if str(s).strip().lower() != "mean"}
            if r:
                return r
    return set()


def main():
    year, code = int(sys.argv[1]), sys.argv[2]
    roster = _roster_from_f4u_or_pdf(year, code)
    print(f"{year} {code}: roster {len(roster)} strains (from F4U)")
    df = extract_section(year, code, roster)
    print(f"extracted {len(df)} long rows")
    if len(df):
        print(df.groupby(["Phenotype"]).agg(n=("Value_num", "size"),
              locs=("City", "nunique")).to_string())
        print("\nsample:")
        print(df.head(6).to_string(index=False))


if __name__ == "__main__":
    main()
