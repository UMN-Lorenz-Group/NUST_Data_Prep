"""
gen_f4u_1989_1992_agronomic.py
==============================
Generate the AGRONOMIC (7-trait) Files4Upload long table for 1989/1991/1992 from the
per-test report CSVs in NUST_Data_1989_1992/{year}/{TEST}.csv.

These report files contain ONLY the 7 agronomic blocks (Yield, YieldRank, Maturity,
Lodging, Height, SeedQuality, SeedSize); Protein/Oil come from the PDFs (separate step),
disease/descriptive stay on the Master. Output schema matches the existing 1990 F4U:
  Strain, Year, Test, City, State, Phenotype, Value, Units

Block layout (per trait, repeated per page):
  <TRAIT (units)>
  <fragment header>      ,,, Crook- , Moore- , , Cassel- , , , Spoon-
  <name header>          , Mean , Brandon , ston , head , Shelly* , ton , Elora , Ottawa , er
  Strain , N Tests , Man. , MN , MN , MN , ND , Ont. , Ont. , WI      <- col0=='Strain'
  _ , _ , ...
  <strain> , <mean> , <loc values...>
  ...
  C.V.(%) / L.S.D. / Row Sp. / Rows/Plot   <- footers, skipped
col1 = Mean (skipped). Maturity: reference-check row holds DATES per loc (e.g. 20-Sep);
others are day offsets -> DOY = anchorDOY(loc) + offset.

Usage:
    uv run python data_prep/stage2_corpus/gen_f4u_1989_1992_agronomic.py            # all years, report
    uv run python data_prep/stage2_corpus/gen_f4u_1989_1992_agronomic.py --write    # write per-year CSVs
"""
import argparse
import csv
import datetime
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

NUST = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
SRC = NUST / "NUST_Data_1989_1992"
YEARS = [1989, 1991, 1992]
TESTS = ["UT0", "UT00", "UTI", "UTII", "UTIII", "UTIV",
         "PTI", "PTIIA", "PTIIB", "PTIIIA", "PTIIIB", "PTIVA", "PTIVB"]

TEST_MAP = {"UT0": "UT-0", "UT00": "UT-00", "UTI": "UT-I", "UTII": "UT-II",
            "UTIII": "UT-III", "UTIV": "UT-IV", "PTI": "PT-I", "PTIIA": "PT-IIA",
            "PTIIB": "PT-IIB", "PTIIIA": "PT-IIIA", "PTIIIB": "PT-IIIB",
            "PTIVA": "PT-IVA", "PTIVB": "PT-IVB"}

# block title -> (Phenotype, Units)
BLOCKS = {
    "YIELD (BU/A)":          ("YieldBuA", "bu/a"),
    "YIELD RANK":            ("YieldRank", ""),
    "MATURITY (DATE)":       ("Maturity", "date"),
    "LODGING (SCORE)":       ("Lodging", "score"),
    "PLANT HEIGHT (INCHES)": ("Height", "inches"),
    "SEED QUALITY (SCORE)":  ("SeedQuality", "score"),
    "SEED SIZE (G/100)":     ("SeedSize", "g/100"),
}
# rows that terminate a block's strain data (agronomic footers + the maturity
# Date-Planted / Days-to-Mature rows, whose May dates must NOT be read as anchors)
FOOTER = ("C.V.", "L.S.D.", "ROW SP.", "ROWS/PLOT", "MEAN", "TEST", "STRAIN",
          "DATE PLANTED", "DATE", "DAYS", "PLANTED", "HARVEST")

STATE_FIX = {"MAN.": "MAN", "MAN": "MAN", "ONT.": "ONT", "ONT": "ONT",
             "QUE.": "QUE", "SASK.": "SASK", "MB": "MAN", "ON": "ONT"}
VALID_STATES = {  # US postal + Canadian provinces (post-norm) — a column is a location only if its header is one of these
    "AL", "AR", "AZ", "CA", "CO", "CT", "DE", "FL", "GA", "IA", "ID", "IL", "IN",
    "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND",
    "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
    "MAN", "ONT", "QUE", "SASK", "BC", "AB", "NB", "NS", "PE", "NL"}
SOIL = {"clay", "loam", "sand", "silt", "siltloam", "sandyloam"}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


# report spellings that differ from the canonical corpus/Master label
CITY_FIX = {"Moorehead": "Moorhead", "S.Charleston": "S. Charleston",
            "MT. Orab": "Mt. Orab", "St.Charleston": "St. Charleston"}

# (nc(city), State) -> canonical corpus City, for report labels that don't
# normalize-match the corpus (state suffixes, abbreviations, OCR typos)
CITY_CANON = {
    ("arcadia", "IA"): "Arcadia_IA", ("cora", "IL"): "Cora_IL",
    ("grandpass", "MO"): "GrandPass_MO", ("inghamco", "MI"): "Ingham County",
    ("lafayette", "IN"): "West Lafayette", ("lenaweecounty", "MI"): "LenaweeCounty_MI",
    ("lexington", "NE"): "Lexington_NE", ("linclon", "NE"): "Lincoln",
    ("madison", "NE"): "Madison_NE", ("oak", "NE"): "Oak_NE",
    ("ridgtown", "ONT"): "Ridgetown", ("saginawcounty", "MI"): "Saginaw",
    ("scottsbluff", "NE"): "Scottsbluff_NE", ("socharleston", "OH"): "S. Charleston",
    ("southcharleston", "OH"): "S. Charleston", ("scharleston", "OH"): "S. Charleston",
    ("winterset", "IA"): "Winterset_IA",
}


def canon_city(city, state):
    key = (re.sub(r"[^a-z0-9]", "", str(city).lower()), state)
    return CITY_CANON.get(key, city)


def clean_city(frag, name):
    """Reconstruct a city that is split across the fragment + name header rows.
    Rule: concatenate (no space) when the join is a word continuation -- the fragment
    ends in '-' (Crook-|ston) OR the name part starts lowercase (Lexing|ton, Carbon|dale);
    insert a space only for genuine two-word names (Mt.|Orab, West|Lafayette)."""
    frag = (frag or "").strip().replace("\xad", "-").replace("*", "")
    name = (name or "").strip().replace("*", "")
    if not frag:
        city = name
    elif frag.endswith("-"):
        city = frag[:-1] + name
    elif name and name[:1].islower():
        city = frag + name
    else:
        city = (frag + " " + name).strip()
    city = re.sub(r"\s+", " ", city).strip()
    return CITY_FIX.get(city, city)


def norm_state(s):
    s = (s or "").strip()
    return STATE_FIX.get(s.upper(), s.upper().rstrip("."))


def to_doy(s, year):
    s = str(s).strip()
    # Excel "DD-Mon" / "D-Mon"
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})", s)
    if m and m.group(2).lower() in MONTHS:
        try:
            return datetime.date(year, MONTHS[m.group(2).lower()], int(m.group(1))).timetuple().tm_yday
        except ValueError:
            return None
    # "Mon-DD" just in case
    m = re.match(r"^([A-Za-z]{3})-(\d{1,2})", s)
    if m and m.group(1).lower() in MONTHS:
        try:
            return datetime.date(year, MONTHS[m.group(1).lower()], int(m.group(2))).timetuple().tm_yday
        except ValueError:
            return None
    # "m/d"
    m = re.match(r"^(\d{1,2})/(\d{1,2})", s)
    if m:
        try:
            return datetime.date(year, int(m.group(1)), int(m.group(2))).timetuple().tm_yday
        except ValueError:
            return None
    return None


def is_num(s):
    return re.match(r"^-?\d+(\.\d+)?$", str(s).strip()) is not None


def block_title(s):
    """Uppercased block title with backslash normalized to '/' (some files write
    'SEED SIZE (g\\100)' instead of 'g/100')."""
    return str(s).strip().upper().replace("\\", "/")


def clean_strain(s):
    """Normalize a strain label: collapse spaces, drop the inconsistent trailing
    ' dt'/' DT' determinacy marker (present in some blocks, absent in others -> would
    split the same variety into two keys, as Master already strips it)."""
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = re.sub(r"\s+[dD][tT]$", "", s)
    return s


def parse_block(rows, start, year, test):
    """Parse one trait block starting at title row `start`. Handles the multi-PANEL
    side-by-side layout of wide tests (the block title repeats at each panel's strain
    column; each panel has strain col, optional Mean col, then its own location cols).
    Return (f4u_rows, next_i)."""
    title = block_title(rows[start][0])
    if title not in BLOCKS:
        return [], start + 1
    pheno, units = BLOCKS[title]

    def cell(r, c):
        return r[c].strip() if r and c < len(r) else ""

    # find the state header row (col0 == 'Strain') within the next ~6 rows
    hs = None
    for i in range(start + 1, min(start + 8, len(rows))):
        if cell(rows[i], 0).lower() == "strain":
            hs = i
            break
    if hs is None or hs < start + 2:
        return [], start + 1
    frag_row, name_row, state_row = rows[hs - 2], rows[hs - 1], rows[hs]
    width = max(len(frag_row), len(name_row), len(state_row), len(rows[start]))

    # panel start columns = the 'Strain' markers in the state row (each panel's strain
    # column). Falls back to the title-row repeats, then col 0.
    panel_starts = [c for c in range(width) if cell(state_row, c).lower() == "strain"]
    if not panel_starts:
        panel_starts = [c for c in range(len(rows[start])) if cell(rows[start], c).upper() == title] or [0]

    # per-panel column -> (city, state, panel_strain_col)
    panels = []  # list of (strain_col, {loc_col: (city, state)})
    ends = panel_starts + [width]
    for pi, ps in enumerate(panel_starts):
        pe = ends[pi + 1]
        cols = {}
        base = ""  # last real city in this panel, for soil-type sub-columns
        for c in range(ps + 1, pe):
            st = norm_state(cell(state_row, c))
            if st not in VALID_STATES:
                continue  # Mean/Rank/Tests/label column, not a location
            frag_c, name_c = cell(frag_row, c), cell(name_row, c)
            if name_c.strip("*").lower() in SOIL:
                # Portageville | Clay ; (empty) | Loam  -> Portageville-Clay / Portageville-Loam
                b = clean_city(frag_c, "") or base
                city = f"{b}-{name_c.strip('*').title()}" if b else name_c.strip("*").title()
                base = b  # carry base city to the next soil sub-column
            else:
                city = clean_city(frag_c, name_c)
                if city:
                    base = city
            if city:
                cols[c] = (canon_city(city, st), st)
        if cols:
            panels.append((ps, cols))

    # collect data rows (until footer / new title / blank run)
    data_rows = []
    i = hs + 1
    while i < len(rows):
        r = rows[i]
        c0 = cell(r, 0)
        u = c0.upper()
        if not c0 or c0 == "_":
            i += 1
            if data_rows and i < len(rows) and cell(rows[i], 0).upper() in BLOCKS:
                break
            continue
        if u.startswith(FOOTER) or block_title(c0) in BLOCKS or "UNIFORM TEST" in u or "PRELIMINARY" in u:
            break
        data_rows.append(r)
        i += 1

    # maturity anchor per location column (first date row = reference check)
    anchor = {}
    if pheno == "Maturity":
        for r in data_rows:
            for _, cols in panels:
                for c in cols:
                    d = to_doy(cell(r, c), year)
                    if d is not None and c not in anchor:
                        anchor[c] = d

    out = []
    for r in data_rows:
        for ps, cols in panels:
            strain = clean_strain(cell(r, ps))
            if not strain or strain.upper() in ("_", "STRAIN"):
                continue
            for c, (city, st) in cols.items():
                v = cell(r, c)
                if v in ("", "-", "_", "F", "NS"):
                    continue
                if pheno == "Maturity":
                    d = to_doy(v, year)
                    if d is not None:
                        val = d
                    elif is_num(v) and c in anchor:
                        val = int(round(anchor[c] + float(v)))
                    else:
                        continue
                    out.append((strain, year, test, city, st, pheno, val, units))
                elif is_num(v):
                    out.append((strain, year, test, city, st, pheno, v, units))
    return out, i


def parse_test(year, test_file):
    path = SRC / str(year) / f"{test_file}.csv"
    if not path.exists():
        return []
    rows = list(csv.reader(open(path, encoding="utf-8", errors="replace")))
    test = TEST_MAP[test_file]
    out = []
    i = 0
    while i < len(rows):
        c0 = block_title(rows[i][0]) if rows[i] else ""
        if c0 in BLOCKS:
            r, i = parse_block(rows, i, year, test)
            out.extend(r)
        else:
            i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    for year in YEARS:
        allrows = []
        for t in TESTS:
            allrows.extend(parse_test(year, t))
        from collections import Counter
        byph = Counter(r[5] for r in allrows)
        print(f"{year}: {len(allrows):,} agronomic rows | {dict(byph)}")
        if args.write:
            outdir = SRC / str(year) / f"{year}_Processing" / "Files4Upload"
            outdir.mkdir(parents=True, exist_ok=True)
            out = outdir / "phenotypesTable1_agronomic.csv"
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Strain", "Year", "Test", "City", "State", "Phenotype", "Value", "Units"])
                w.writerows(allrows)
            print(f"   wrote {out}")


if __name__ == "__main__":
    main()
