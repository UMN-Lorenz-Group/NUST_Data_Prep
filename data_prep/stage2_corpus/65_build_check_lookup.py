"""
65_build_check_lookup.py
========================
Build a comprehensive per-(MG, Strain) check variety lookup table from all
available source data.

Sources (in priority order):
  1941-1977  CHECK_VARIETIES dict (hardcoded pre-modern checks; no per-year source)
  1966-1991  analysis/data/_shared/nust_checks_from_pdf_1941_1991.csv (script 67,
             pdfplumber entry-list extraction; is_check=1, confidence>=1;
             1941-1965 image-only PDFs not extractable; 1979-1980 and
             1985-1988 have OCR gaps; cross-test MG suffixes handled)
  1978-1986  output_XXXX/combined_XXXX_strainsTable.csv  (Check column = 1)
  1987-1989  gap — bridged implicitly (1986 + 1990 checks cover)
  1990       output_files/output_1990/combined_1990_checksTable.csv
  1991-1992  gap — bridged implicitly (1990 + 1993 checks cover)
             NOTE: SoyBase NUST (https://www.soybase.org/tools/nust/) is a
             JavaScript SPA; programmatic download of 1989/1991/1992 per-year
             checks requires the Chrome browser extension. The union of 1990
             and 1993 checks covers all varieties used in these years.
  1993-2020  NUST_Data_1993_2020_fromQueryportal/*/checksTable1.csv  (2021 bucket retired 2026-07-10;
             existing lookup already carries 2021 checks from the prior build — re-run needs a 2021 source)
  2022       NUST_Data/2022/2022_NUST_Processing/checksTable1.csv
  2023       gap — bridged implicitly (2022 + 2024 checks cover; no checksTable1.csv
             was generated for 2023 because the source file
             "2023_List_of_Entries_Final_Checks_Mod.csv" is missing; the check
             variety roster is stable across 2022-2024 so bridging is valid)
  2024       NUST_Data/2024/2024_NUST_Processing/Files4Upload/checksTable1.csv
  2025       NUST_Data/2025/2025_NUST_Processing/checksTable1.csv

Output:
  analysis/data/_shared/nust_check_lookup_1941_2025.csv
  Columns: MG, Strain
  One row per unique (MG, Strain) pair that was EVER designated as a check.
  This is a static lookup; prep_stage0 joins on (MG, Strain) to assign
  check = "yes" / "no" instead of using the n_years >= 5 proxy.

Strain name normalization:
  - Trailing asterisk and spaces stripped (e.g. "MN1410 *" -> "MN1410")
  - The "(MG)" suffix present in 1978-1990 sources is stripped
    (e.g. "Clay (0)" -> "Clay") and MG is taken from the parenthesised code
  - Multi-word spaces normalized; leading/trailing whitespace removed
"""

import re
import sys
from pathlib import Path

import pandas as pd

REPO          = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
NUST_DATA_DIR = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
QP_DIR        = NUST_DATA_DIR / "NUST_Data_1993_2020_fromQueryportal"   # renamed 2026-07-10 (was _1993_2022_;
#          its unused 2021 bucket was deleted, so Source-4 query-portal checks now cover 1993-2020 only —
#          2021 checks, if needed on a re-run, must come from the standalone 2021/ year folder)
OUT           = REPO / "analysis/data/_shared/nust_check_lookup_1941_2025.csv"
OUT_YEARS     = REPO / "analysis/data/_shared/nust_check_designation_years_1941_2025.csv"

MG_ORDER = ["00", "0", "I", "II", "III", "IV"]

# ---------------------------------------------------------------------------
# Pre-modern hardcoded checks (1941-1977; no per-year source available)
# Source: 10_assemble_corpus.py CHECK_VARIETIES + canonical NUST references
# ---------------------------------------------------------------------------
CHECK_VARIETIES_PREMODERN = {
    "00": ["Acme", "Flambeau", "Altona", "Norman", "Portage", "Morsoy",
           "Capital", "Renville", "Mandarin", "Ottawa", "Crest"],
    "0":  ["Grant", "Merit", "Clay", "Traverse", "Swift", "Wilkin", "Evans",
           "Norchief", "Manchu", "Earlyana", "Mandarin(Ottawa)",
           "Mandarin (Ottawa)"],
    "I":  ["Chippewa", "Chippewa 64", "Hark", "A-100", "Hodgson", "SL7",
           "SL8", "Steele", "Blackhawk", "Hawkeye", "Mukden"],
    "II": ["Amsoy", "Amsoy 71", "Harosoy", "Harosoy 63", "Beeson", "Corsoy",
           "Magna", "Provar", "Williams", "Adams", "Lincoln", "Lindarin",
           "Wabash", "Korean"],
    "III": ["Calland", "Wayne", "Williams", "Shelby", "C1421", "Adelphia",
            "Cumberland", "Ford", "Roanoke"],
    "IV": ["Clark", "Clark 63", "Kent", "Cutler", "Cutler 71", "Bonus",
           "L12A", "Custer", "Bethel", "Ogden", "Korean"],
}


# ---------------------------------------------------------------------------
# Helper: normalise a strain name
# ---------------------------------------------------------------------------
INVALID_NAMES = {"na", "nan", "n/a", "none", "unknown", ""}

# ---------------------------------------------------------------------------
# Canonical name standardisation
# ---------------------------------------------------------------------------
# Maps from any observed variant form (post-basic-norm) to the single canonical
# display name used in the lookup. Covers:
#   • OCR garbles ("Norchlef" → "Norchief", "Vi s." → "Wis.")
#   • Abbreviation variants ("Mand.(Ott.)" → "Mandarin (Ottawa)")
#   • Spacing / punctuation differences ("M 65-217" → "M65-217")
#   • Parenthetical artefacts ("Chippewa 64 (LI)" → "Chippewa 64")
#   • Pre-1966 OCR noise ("Illin i" → "Illini")
#   • Sentence fragments that passed the artefact filter → None (remove)
#
# Source for Mandarin (Ottawa) variants: fixes/extract_sojabone_anchors.py
# _STRAIN_ALIASES which documents all matured-row label forms seen 1941-1965.
# ---------------------------------------------------------------------------
CANONICAL_NAMES: dict = {

    # ── Mandarin (Ottawa) ── distinct from plain "Mandarin" ─────────────────
    # All these map to the single canonical form "Mandarin (Ottawa)"
    "Mandarin(Ottawa)":            "Mandarin (Ottawa)",
    "Mand. (Ott.)":                "Mandarin (Ottawa)",
    "Mand.(Ott.)":                 "Mandarin (Ottawa)",
    "Mand.(Ottawa)":               "Mandarin (Ottawa)",
    "Mand. (Ottawa)":              "Mandarin (Ottawa)",
    "Mandarin (Ott.)":             "Mandarin (Ottawa)",
    "Mandarin (Ott)":              "Mandarin (Ottawa)",
    "Mand. (Ott)":                 "Mandarin (Ottawa)",
    "Mandarin(Ottawa)Central":     "Mandarin (Ottawa)",  # agency bleed
    "Mandarin (Ott.)":             "Mandarin (Ottawa)",
    # OCR space garbles seen in pre-1966 extraction
    "Mand. (Ott. )":               "Mandarin (Ottawa)",
    "Mandarin (Ott. )":            "Mandarin (Ottawa)",

    # ── Wis. Manchu variants ─────────────────────────────────────────────────
    "Wis.Manchu 3":                "Wis. Manchu 3",
    "Vi s. Manchu 3":              "Wis. Manchu 3",   # OCR "Wi" → "Vi"
    "Vis. Manchu 3":               "Wis. Manchu 3",   # OCR "Wi" → "Vi"
    "Wis.Maneh u 606":             "Wis. Manchu 606", # OCR garble "Maneh u"
    "Vis. Manchu 606":             "Wis. Manchu 606",
    "Uis. Manchu 606":             "Wis. Manchu 606", # OCR "W" → "U"
    "Wis.Manchu 3 Sel":            "Wis. Manchu 3",
    "Wis. Manchu 3 Sel":           "Wis. Manchu 3",
    # 1947-specific forms from extract_sojabone_anchors _STRAIN_ALIASES
    "Wis.Manchu 3":                "Wis. Manchu 3",
    "Wis. Mancu 3":                "Wis. Manchu 3",
    # Manchukota variants
    "Manchukota":                  "Manchukota",    # legitimate — keep as-is

    # ── OCR digit/letter substitution: "111" for "(III)" ────────────────────
    # In pre-1966 OCR, roman numeral III sometimes reads as "111" or "Ill"
    "Illini 111":                  "Illini",
    "Illini 111.":                 "Illini",
    "Illin i":                     "Illini",    # OCR space in middle
    "Illin 1":                     "Illini",    # OCR I→1
    "m in i":                      "Illini",    # severe garble of "Illini"
    "Lincoln 111":                 "Lincoln",
    "Lincoln I11.A.E.S":           "Lincoln",   # agency bleed
    "Viking 111":                  "Viking",
    "Chief 111":                   "Chief",     # "111" = "(III)" suffix

    # ── Simple OCR garbles ───────────────────────────────────────────────────
    "Norchlef":                    "Norchief",  # OCR f/f→lf, e→e
    "Norchlef":                    "Norchief",
    "M 65-217":                    "M65-217",   # inconsistent spacing
    "Gold soy":                    "Goldsoy",   # OCR space inserted
    "Morsoy (CM30)":               "Morsoy",    # CM30 is the experimental code
    "Altona (UM15)":               "Altona",    # UM15 is breeders designation,
                                                # same variety as Altona

    # ── Parenthetical artefacts from pre-1966 or OCR ─────────────────────────
    "Chippewa 64 (LI)":            "Chippewa 64",   # "(LI)" is OCR artefact
    "Hodgson 78 (1":               "Hodgson 78",    # unclosed paren
    "(Al-939)":                    "Al-939",        # paren from table border
    "(C1315)":                     "C1315",
    "Al-939)":                     "Al-939",
    "C1315)":                      "C1315",
    "Habaro U.S.Depti of":         "Habaro",        # partial agency bleed
    "Cl 128":                      "C1128",         # OCR l/1 confusion
    "Cl 301":                      "C1301",         # OCR l/1 confusion

    # ── Cross-reference parentheticals (strip breeding line codes) ───────────
    "A5-2683 (Adams)":             "Adams",         # breeding line code → variety
    "Adams (A5—2683)":             "Adams",
    "Perry (C612)":                "Perry",
    "Swift(M59-121)":              "Swift",
    "Steele(M59-213)":             "Steele",
    "Maple Arrow (073-15)":        "Maple Arrow",
    "Merit (0-•55-2065)":          "Merit",         # OCR cross code

    # ── Sentence fragments / noise that slipped through ─────────────────────
    "Group 0 was planted":          None,       # sentence fragment
    "7/is.i.Ian.3 Sel. 7/isconsin": None,       # OCR noise
    "Ills. Hanchu 3 Sel":           None,       # garble
    "m in i":                       "Illini",
    "mo":                           None,       # too short / ambiguous
    "mo 2":                         None,       # garble
    "For the":                      None,       # sentence fragment
    "Mukden ;/4":                   "Mukden",   # OCR garble of "Mukden 3/4"?

    # ── Additional OCR l/1 and digit confusion ────────────────────────────
    "Cl 291":                       "C1291",    # OCR "l" for "1"
    "CIO 68":                       "C1068",    # OCR "IO" for "10"
    "18-1O78O":                     "L8-10780", # OCR "18" for "L8", "O" for "0"
    "C10**8":                       None,       # too garbled to resolve safely
    "19-5138":                      "L9-5138",  # OCR "19" for "L9"
    "19-5142":                      "L9-5142",
    "18-1O78O":                     "L8-10780",
    "l8-10946":                     "L8-10946", # lowercase l
    "Pennsoy Penn":                 "Pennsoy",  # trailing agency bleed

    # ── Spacing / punctuation ────────────────────────────────────────────────
    "Mandarin(Ottawa)":            "Mandarin (Ottawa)",
    "Corsoy79":                    "Corsoy 79",
    "Corsoy 79 (II)":              "Corsoy 79",
    "Clark63":                     "Clark 63",
    "Harosoy63":                   "Harosoy 63",
    "Chippewa64":                  "Chippewa 64",
    "Chippewa 61+":                "Chippewa 61+",  # legitimate (keep)
    "Cutler71":                    "Cutler 71",
    "Hodgson78":                   "Hodgson 78",

    # ── Breeding-line codes with released names (strip code, keep name) ──────
    "Scott (S2-7158)":             "Scott",
    "Perry (C612)":                "Perry",      # already above, repeat for key form
    "Custer (S5)":                 "Custer",
    "L74L-125 Lawrence":           "Lawrence",   # L74L-125 is breeding line for Lawrence
    "Adams (A5—2683)":             "Adams",      # em-dash variant
    "Wye(Md63-3303-3)":            "Wye",        # breeding line code
}


def _norm_key(s):
    """Compute lookup key: lowercase, alphanum only, no spaces or punctuation."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


# Build a secondary lookup keyed on norm_key for fuzzy matching
# (handles spacing/punct variations not covered by exact CANONICAL_NAMES)
_CANONICAL_KEY_MAP: dict[str, str] = {}
for _k, _v in CANONICAL_NAMES.items():
    if _v is not None:
        _CANONICAL_KEY_MAP[_norm_key(_k)] = _v

# Also add aliases from extract_sojabone_anchors._STRAIN_ALIASES logic
# These map abbreviated keys → canonical display forms
_SOJABONE_TO_DISPLAY: dict[str, str] = {
    "mandarinottawa":  "Mandarin (Ottawa)",
    "mandott":         "Mandarin (Ottawa)",
    "mandottawa":      "Mandarin (Ottawa)",
    "mandarinott":     "Mandarin (Ottawa)",
    "chippewa64":      "Chippewa 64",
    "corsoy79":        "Corsoy 79",
    "harosoy63":       "Harosoy 63",
    "clark63":         "Clark 63",
    "cutler71":        "Cutler 71",
    "hodgson78":       "Hodgson 78",
    "wismanchu3":      "Wis. Manchu 3",
    "wismanchu606":    "Wis. Manchu 606",
}
_CANONICAL_KEY_MAP.update(_SOJABONE_TO_DISPLAY)


def norm_strain(s):
    """Strip rank prefix, trailing asterisk/spaces, collapse internal spaces,
    then apply canonical-name standardisation to resolve synonym variants.

    Rank prefix: some 1978-1986 strainsTables include a leading ordinal like
    '2. ' or '4. ' inherited from the original NUST table layout.
    Canonical names: "Mand.(Ott.)" → "Mandarin (Ottawa)", etc.
    """
    if not isinstance(s, str):
        return None
    s = s.strip()
    s = re.sub(r"^\d+\s*\.\s*", "", s)   # leading rank prefix "N. " or "N . "
    s = re.sub(r"\s*\*\s*$", "", s)      # trailing asterisk
    s = re.sub(r"\s+", " ", s)           # collapse spaces
    s = s.strip()
    if not s or s.lower() in INVALID_NAMES:
        return None

    # 1. Exact match in CANONICAL_NAMES
    if s in CANONICAL_NAMES:
        result = CANONICAL_NAMES[s]
        return result  # None → remove this entry

    # 2. Normalized-key match (handles remaining spacing/punct variants)
    key = _norm_key(s)
    if key in _CANONICAL_KEY_MAP:
        return _CANONICAL_KEY_MAP[key]

    return s


# ---------------------------------------------------------------------------
# Helper: parse MG from strings like "MG 0", "Early-MG IV", "E-MG 0", "L-MG 0"
# ---------------------------------------------------------------------------
MG_RE = re.compile(r"MG\s+(\d{1,2}|[IV]{1,4}V?)", re.IGNORECASE)

def parse_mg_from_phenotype(ph):
    if not isinstance(ph, str):
        return None
    m = MG_RE.search(ph)
    if not m:
        return None
    mg = m.group(1).upper()
    # normalise: digits stay as-is (00, 0); Roman numerals upper-cased
    return mg


# ---------------------------------------------------------------------------
# Helper: extract strain name and MG from "(MG)" suffix format
#   "Clay (0)"      -> ("Clay", "0")
#   "Hodgson 78 (I)"-> ("Hodgson 78", "I")
#   "McCall (00)"   -> ("McCall", "00")
# ---------------------------------------------------------------------------
PAREN_MG_RE = re.compile(r"^(.*?)\s*\((\d{1,2}|[IV]{1,4})\)\s*$")

def parse_strain_with_paren_mg(s):
    if not isinstance(s, str):
        return None, None
    m = PAREN_MG_RE.match(s.strip())
    if m:
        strain = norm_strain(m.group(1))
        mg     = m.group(2).upper()
        return strain, mg
    # No parenthesised MG — return cleaned name only
    return norm_strain(s), None


# ---------------------------------------------------------------------------
# Collect checks from all sources into a set of (MG, Strain) tuples
# ---------------------------------------------------------------------------
checks = set()

# Per-year designation records: (MG, Strain, Year). Populated whenever the
# source carries a calendar year (all sources except the pre-modern hardcoded
# list, which has no per-year provenance). Written out as a companion long CSV
# so downstream tables (e.g. script 49) can show the years each check was used.
checks_year = set()


def add(mg, strain, year=None):
    mg  = (mg  or "").strip().upper()
    s   = norm_strain(strain)
    if mg in MG_ORDER and s:
        checks.add((mg, s))
        if year is not None:
            try:
                checks_year.add((mg, s, int(float(year))))
            except (TypeError, ValueError):
                pass


# ── 1. Pre-modern hardcoded ────────────────────────────────────────────────
print("Source 1: pre-modern hardcoded CHECK_VARIETIES (1941-1977)")
for mg, names in CHECK_VARIETIES_PREMODERN.items():
    for n in names:
        add(mg, n)
print(f"  Running total: {len(checks)}")


# ── 2. Per-year strainsTable 1978-1986 (Check column = 1, UT tests) ────────
print("Source 2: output_XXXX/combined_XXXX_strainsTable.csv (1978-1986)")
for yr in range(1978, 1987):
    fpath = REPO / f"output_files/output_{yr}" / f"combined_{yr}_strainsTable.csv"
    if not fpath.exists():
        print(f"  {yr}: MISSING — skipped")
        continue
    df = pd.read_csv(fpath, low_memory=False)
    # Columns: Year, Test, Strain, OriginalStrain, Descriptive.Code,
    #          Unique.traits, Gen.Comp., Check
    check_col = next((c for c in df.columns if c.lower() == "check"), None)
    if check_col is None:
        print(f"  {yr}: no Check column — skipped")
        continue
    sub = df[(df[check_col] == 1) &
             (df["Test"].astype(str).str.match(r"UT", na=False))]
    n = 0
    for _, row in sub.iterrows():
        strain_raw = str(row.get("Strain", ""))
        s, mg = parse_strain_with_paren_mg(strain_raw)
        if s and mg:
            add(mg, s, yr)
            n += 1
        elif s:
            # No parenthesised MG — try parsing from Test field
            test_mg = re.search(r"UT[-\s]?(\d{1,2}|[IV]{1,4})", str(row.get("Test", "")))
            if test_mg:
                add(test_mg.group(1).upper(), s, yr)
                n += 1
    print(f"  {yr}: {n} check rows added")
print(f"  Running total: {len(checks)}")


# ── 2b. PDF-extracted checks from script 67 (1966-1991) ───────────────────
print("Source 2b: nust_checks_from_pdf_1941_1991.csv (script 67, pdfplumber)")
fpath_pdf = REPO / "analysis/data/_shared/nust_checks_from_pdf_1941_1991.csv"
if fpath_pdf.exists():
    pdf_df = pd.read_csv(fpath_pdf, low_memory=False)
    # Include positively identified checks with at least some confidence.
    # conf=0 cells are excluded (garbled OCR or empty extraction).
    # conf>=1 is included via union — false positives are harmless since the
    # lookup is a union; missed checks are the larger risk.
    checks_sub = pdf_df[(pdf_df["is_check"] == 1) & (pdf_df["confidence"] >= 1)]
    # Reject obvious OCR artefacts before adding to the set
    ARTEFACT_RE = re.compile(
        r"^[\d\s\.\|\-~]+$"      # purely numeric/punctuation: "0", "2 . ", "~|"
        r"|^Also\b"               # footnote: "Also in U.T. IVS"
        r"|[|~]{2,}",             # heavy garble: "hJ o hJ r—>"
        re.IGNORECASE,
    )

    n_pdf = 0
    for _, row in checks_sub.iterrows():
        strain_raw = str(row.get("strain", "")).strip()
        # Skip artefacts: too short, all-punctuation, footnote text, heavy garble
        # Also reject strings that are obviously contaminated with agency text
        # (pre-1966 format bleeds "Agr. Exp. Sta." into strain column)
        if len(strain_raw) <= 1 or len(strain_raw) > 40:
            continue
        if ARTEFACT_RE.search(strain_raw):
            continue
        if re.search(r"\bAgr\b|\bExp\b|\bSta\b|\bSelection\b|\bStation\b",
                     strain_raw, re.IGNORECASE):
            continue
        test_mg = str(row.get("mg", "")).strip().upper()
        # parse_strain_with_paren_mg handles cross-test suffixes:
        # "Clay (0)" -> (Clay, MG=0), "Portage (00)" -> (Portage, MG=00)
        s, mg_paren = parse_strain_with_paren_mg(strain_raw)
        mg = mg_paren if mg_paren else test_mg
        if s and mg in MG_ORDER and len(s) >= 2:
            add(mg, s, row.get("year"))
            n_pdf += 1
    yr_min = int(pdf_df["year"].min())
    yr_max = int(pdf_df["year"].max())
    print(f"  PDF source ({yr_min}-{yr_max}): {n_pdf} check rows processed")
else:
    print("  PDF checks CSV not found — skipped")
print(f"  Running total: {len(checks)}")


# ── 3. 1990 checksTable ────────────────────────────────────────────────────
print("Source 3: output_files/output_1990/combined_1990_checksTable.csv")
fpath = REPO / "output_files/output_1990" / "combined_1990_checksTable.csv"
if fpath.exists():
    df = pd.read_csv(fpath, low_memory=False)
    # Columns: Year, Test, Strain, OriginalStrain, Phenotype, RM
    # Filter UT tests only
    sub = df[df["Test"].astype(str).str.match(r"UT", na=False)]
    n = 0
    for _, row in sub.iterrows():
        strain_raw = str(row.get("Strain", ""))
        s, mg_paren = parse_strain_with_paren_mg(strain_raw)
        # Also try Phenotype column for MG
        mg_ph = parse_mg_from_phenotype(str(row.get("Phenotype", "")))
        mg = mg_paren or mg_ph
        if s and mg:
            add(mg, s, row.get("Year", 1990))
            n += 1
    print(f"  1990: {n} check rows added")
else:
    print("  1990 checksTable MISSING — skipped")
print(f"  Running total: {len(checks)}")


# ── 4. Query portal 1993-2021 ──────────────────────────────────────────────
print("Source 4: query portal checksTable1.csv (1993-2021)"
      "  [NUST_Data_1993_2020_fromQueryportal]")
qp_batches = sorted(QP_DIR.iterdir()) if QP_DIR.exists() else []
total_qp = 0
for batch_dir in qp_batches:
    fpath = batch_dir / "checksTable1.csv"
    if not fpath.exists():
        continue
    df = pd.read_csv(fpath, low_memory=False)
    # Columns: Year, Test, Strain, Phenotype
    # Filter to UT tests only
    sub = df[df["Test"].astype(str).str.match(r"UT", na=False)]
    n = 0
    for _, row in sub.iterrows():
        strain = norm_strain(str(row.get("Strain", "")))
        mg     = parse_mg_from_phenotype(str(row.get("Phenotype", "")))
        if strain and mg:
            add(mg, strain, row.get("Year"))
            n += 1
    yrs = sorted(df["Year"].dropna().unique().astype(int).tolist())
    print(f"  {batch_dir.name} (years {yrs[0]}-{yrs[-1]}): {n} check rows added")
    total_qp += n
print(f"  Query portal total: {total_qp} rows")
print(f"  Running total: {len(checks)}")


# ── Shared helper: process any standard checksTable1.csv ─────────────────
# Columns: Year, Test, Strain, [OriginalStrain,] Phenotype, [RM]
# Filter UT tests only; MG from Phenotype column.

def process_standard_checks(fpath, label):
    """Load a checksTable1.csv and add UT check (MG, Strain) pairs.

    Handles both the query-portal format (Year,Test,Strain,Phenotype) and
    the modern format (Year,Test,Strain,OriginalStrain,Phenotype,RM).
    Returns count of pairs added.
    """
    if not fpath.exists():
        print(f"  {label}: MISSING — skipped")
        return 0
    df = pd.read_csv(fpath, low_memory=False)
    sub = df[df["Test"].astype(str).str.match(r"UT", na=False)]
    n = 0
    for _, row in sub.iterrows():
        strain = norm_strain(str(row.get("Strain", "")))
        mg     = parse_mg_from_phenotype(str(row.get("Phenotype", "")))
        if strain and mg:
            add(mg, strain, row.get("Year"))
            n += 1
    print(f"  {label}: {n} check rows added")
    return n


# ── 5. 2022 checksTable ────────────────────────────────────────────────────
print("Source 5: 2022/2022_NUST_Processing/checksTable1.csv")
process_standard_checks(
    NUST_DATA_DIR / "2022" / "2022_NUST_Processing" / "checksTable1.csv",
    "2022"
)
print(f"  Running total: {len(checks)}")


# ── 6. 2024 checksTable (Files4Upload) ────────────────────────────────────
print("Source 6: 2024/2024_NUST_Processing/Files4Upload/checksTable1.csv")
process_standard_checks(
    NUST_DATA_DIR / "2024" / "2024_NUST_Processing" / "Files4Upload" / "checksTable1.csv",
    "2024"
)
print(f"  Running total: {len(checks)}")


# ── 7. 2025 checksTable ────────────────────────────────────────────────────
print("Source 7: 2025/2025_NUST_Processing/checksTable1.csv")
process_standard_checks(
    NUST_DATA_DIR / "2025" / "2025_NUST_Processing" / "checksTable1.csv",
    "2025"
)
print(f"  Final total: {len(checks)}")


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------
result = pd.DataFrame(sorted(checks), columns=["MG", "Strain"])
result["MG"] = pd.Categorical(result["MG"], categories=MG_ORDER, ordered=True)
result = result.sort_values(["MG", "Strain"]).reset_index(drop=True)

OUT.parent.mkdir(parents=True, exist_ok=True)
result.to_csv(OUT, index=False)
print(f"\nWritten: {OUT}  ({len(result)} rows)")

# Companion long table: one row per (MG, Strain, Year) the variety was
# designated as a check. Pre-modern hardcoded checks (1941-1977) have no
# per-year provenance and therefore contribute no rows here unless they also
# appear in a year-bearing source (PDF sweep / strainsTable / checksTable).
years_df = pd.DataFrame(sorted(checks_year), columns=["MG", "Strain", "Year"])
years_df["MG"] = pd.Categorical(years_df["MG"], categories=MG_ORDER, ordered=True)
years_df = years_df.sort_values(["MG", "Strain", "Year"]).reset_index(drop=True)
years_df.to_csv(OUT_YEARS, index=False)
n_pairs_with_year = years_df[["MG", "Strain"]].drop_duplicates().shape[0]
print(f"Written: {OUT_YEARS}  ({len(years_df)} rows; "
      f"{n_pairs_with_year}/{len(result)} (MG,Strain) pairs have year provenance)")
print("\nPer-MG check counts:")
print(result.groupby("MG", observed=True).size().to_string())

# Quick sanity: show all checks per MG
print("\nFull lookup:")
for mg in MG_ORDER:
    names = result[result["MG"] == mg]["Strain"].tolist()
    print(f"  {mg:4s} ({len(names):2d}): {', '.join(sorted(names))}")
