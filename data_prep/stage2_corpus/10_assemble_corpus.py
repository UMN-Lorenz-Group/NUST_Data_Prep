"""
10_assemble_corpus.py
=====================
Assemble the full NUST phenotype corpus from heterogeneous sources into a
unified long-form CSV. Year range is data-driven — the script discovers
which years are present in each source bucket and writes outputs whose
filenames reflect the actual range observed.

Renamed from 10_assemble_1965_2025.py (2026-05-21) because the script had
silently grown beyond its original 1965-2025 scope as earlier batches
(1950-59, 1941-49) extended the F4U source range. The data-driven output
naming below means future extensions won't need another rename.

Sources (each source contributes a contiguous range; gaps fall through to
the next bucket):
  1941-1990:            NUST_Historical_Data_1941_1988/{YYYY}_Processing/Files4Upload/  (long)
  1989, 1991, 1992:     NUST_Data/Phenotype_Measures_Final_Master_...csv      (long, plot-level)
  1993-2020:            NUST_Data_1993_2020_fromQueryportal/{bucket}/         (wide; renamed from
                        _1993_2022_ 2026-07-10 — the stale _1993_2022_ superset + its unused 2021 bucket
                        were retired; 2021+ come from the standalone year folders, not query-portal)
  2021-2025:            NUST_Data/{YYYY}/.../phenotypesTable1.csv             (wide)

Outputs (analysis/data/):
  nust_{Yfirst}_{Ylast}_combined.csv       — full union (canonical, e.g. nust_1941_2025_combined.csv)
  nust_1941_2025_combined.csv              — same content as above, stable filename for current corpus
  nust_1965_2025_combined.csv              — legacy alias (same content; kept for backward compat
                                              with 9 downstream scripts that hard-code this name)
  nust_{Yfirst_F4U}_{Ylast_F4U}_combined_f4u.csv   — F4U-only subset
  nust_{Yfirst_M}_{Ylast_M}_combined.csv           — master-CSV-only subset
  nust_{Yfirst_modern}_{Ylast_modern}_combined.csv — queryportal+root subset
  master_vs_queryportal_crosscheck.csv     — integrity comparison for 1993-2017
"""
import re
import sys
import warnings
from pathlib import Path

import pandas as pd
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO     = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
NUST_DATA = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
HIST     = NUST_DATA / "NUST_Historical_Data_1941_1988"
HIST8992 = NUST_DATA / "NUST_Data_1989_1992"          # 1989-1992 per-year source + processing
QP       = NUST_DATA / "NUST_Data_1993_2020_fromQueryportal"
OUT_DIR  = REPO / "analysis" / "data" / "_shared"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MASTER_CSV = NUST_DATA / "MiscellaneousFiles" / "Phenotype_Measures_Final_Master_1989_2017___2019_06_11_yearsALL.csv"

# Per-year source paths for 1941-1990 — ALL under NUST_Historical_Data_1941_1988/{YYYY}_Processing/
# Files4Upload/. Range start extended to 1941 (NUST inaugural year) after the 1941-1949 batch
# landed. 1975 + 1990 added 2026-05-20/21 via PDF-direct extraction (1975 had no Sojabone XLSX;
# 1990 master CSV had only 7 PT-IIIA rows + zero UT). 1975 is no longer the "missing year".
# 2026-07-10: 1976-1979 moved from NUST_Data/{YYYY}_Processing into HIST (were a leftover special-case).
# 2026-07-10: 1990_Processing moved out of HIST into NUST_Data_1989_1992/1990/ (with the 1988/1990
# maturity DOY fix baked in); 1990 F4U now loads from there.
# Historical F4U years 1941-1988 (Source F4U_1941_1988). The 1990 PDF pilot is loaded with the
# 1989-1992 group below (Source F4U_1989_1992) so the two source ranges are contiguous.
# (Legacy name was F4U_PATHS_1941_1988 — the range was extended back to 1941; renamed 2026-07.)
F4U_PATHS_1941_1988 = {}
for y in range(1941, 1989):
    F4U_PATHS_1941_1988[y] = HIST / f"{y}_Processing" / "Files4Upload" / "phenotypesTable1.csv"

# 2026-07-12: 1989/1991/1992 now sourced from provenance F4U (agronomic from the per-test
# report CSVs + Protein/Oil from the report PDFs) instead of the Master CSV, for these 9
# traits. The Master is kept ONLY for the disease/descriptive traits of these years (not in F4U).
F4U_PATHS_1989_1992 = {y: HIST8992 / str(y) / f"{y}_Processing" / "Files4Upload" / "phenotypesTable1.csv"
                       for y in (1989, 1990, 1991, 1992)}   # 1990 = PDF pilot, moved here 2026-07
F4U_TRAITS_1989_1992 = {"YieldBuA", "YieldRank", "Maturity", "Lodging", "Height",
                        "SeedQuality", "SeedSize", "Protein", "Oil"}

# 1993-2020 queryportal: year-specific subfolders (skip 2013_2015 superset)
QP_SUBFOLDERS = [
    "1993_1997", "1998_2003", "2004_2008",
    "2009", "2010", "2011", "2012", "2013", "2014", "2015",
    "2016", "2017", "2018", "2019", "2020",
]

# 2021-2025 paths
ROOT_PATHS_2021_2025 = {
    2021: NUST_DATA / "2021" / "phenotypesTable1.csv",
    2022: NUST_DATA / "2022" / "2022_NUST_Data" / "phenotypesTable1.csv",
    2023: NUST_DATA / "2023" / "2023_NUST_Processing" / "phenotypesTable1.csv",
    2024: NUST_DATA / "2024" / "2024_NUST_Processing" / "Files4Upload" / "phenotypesTable1.csv",
    2025: NUST_DATA / "2025" / "2025_NUST_Processing" / "Files4Upload" / "phenotypesTable1.csv",
}

# Key columns kept across all sources (internal during pipeline)
KEY_COLS = ["Year", "Test", "Variant", "Location", "State", "Strain", "Phenotype", "Value_num", "Units", "Source"]

# Final output columns include analysis-friendly derived columns (TestType, TestMG, IsCheck)
# and rename Location → City to match the existing 01_assemble.R output schema.
FINAL_COLS = ["Year", "TestType", "TestMG", "Test", "Variant", "City", "State",
              "Strain", "Strain_raw", "Phenotype", "Value_num", "Units", "IsCheck", "Source"]

# Auxiliary phenotypes dropped from the assembled corpus. YieldRank is a within-cell
# order-statistic of YieldBuA, not a measured trait: it is redundant with the (verified-clean)
# YieldBuA and is consumed by NO downstream analysis (only coverage/inventory listings). The
# 2026-07-21 yield/maturity QC found its transcribed values are unreliable — genuine corruption
# in the queryportal era (whole-cell rank reversals, out-of-range ranks, rank==yield-value) plus
# heterogeneous/OCR-noisy ranking conventions in the F4U era (within-location vs overall-mean).
# There is no single faithful recompute across eras, and nothing needs one, so the phenotype is
# dropped rather than recomputed. If a rank is ever wanted it is a 3-line groupby-rank on
# YieldBuA. Source F4U/portal files are untouched, so the SoyBase-mirror push is unaffected.
DROP_PHENOTYPES = {"YieldRank"}


def drop_aux_phenotypes(df):
    """Remove auxiliary/derived phenotypes (see DROP_PHENOTYPES) from a long-format frame."""
    if df is None or df.empty or "Phenotype" not in df.columns:
        return df
    return df[~df["Phenotype"].isin(DROP_PHENOTYPES)].copy()

# Pseudo-locations: disease-rating columns (Diaporthe / Purple Stain / Phytophthora /
# Miscellaneous) and region-mean summaries (Central/East Coast Mean, LSD, Average) that
# some source tables (notably 1974, minor 1971/73/76/77) mis-parsed into the Location/City
# field. They are not real test sites; they inflate per-year strain/MG counts (early checks
# wrongly assigned to PT-IV/MG IV) and leak summary aggregates into the location-level data.
# See analysis/scripts/P1_trial_design/21_strains_per_year_plot_1941_2025.py for the diagnosis.
PSEUDO_LOC_RE = re.compile(
    r"Diaporthe|Purple ?Stain|Phytophthora|Miscellaneous|\bMean\b|\bLSD\b|Average",
    re.IGNORECASE,
)

# Stray STRAIN values that are not real varieties (diagnosed by the QC audit,
# data_prep/stage2_corpus/13_qc_strain_germplasm_audit.py): trial-mean summary rows
# (`Mean`, `MeanYield`) — 6 of which survive the RGG eligibility gate as phantom
# `Mean_*` genotypes — plus dates mis-parsed as strains, negative-number "strains",
# `??`/`???` OCR junk, and Unicode replacement-char damage. These carry yield values
# yet are not genotypes. The REVIEW-tier classes (numeric early-era line numbers, the
# H#/M#/L# short-code series) are LEGITIMATE and intentionally NOT matched here.
STRAY_STRAIN_RE = re.compile(
    r"^(Mean|MeanYield|Average|Median|Total|Sum|LSD)\W*$"   # summary-aggregate labels
    r"|^\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}:\d{2}"               # date / datetime as strain
    r"|^-\d+(\.\d+)?$"                                        # negative-number "strain"
    r"|[?�]",                                            # ??/??? OCR junk, U+FFFD mojibake
    re.IGNORECASE,
)

# All discrete (Strain, Year) -> corrected-Strain merges are curated in ONE reviewable apply-list,
# reference/nust_strain_corrections.csv, generated by 25_consolidate_strain_corrections.py from the
# QC sources (OCR short-codes, 1941 PI restores, value/neighbour-matched orphaned fragments, numeric
# origin-table recoveries) — each row source-confirmed (neighbour gate, script 26). Loaded here so
# the apply is data-driven and the dict isn't a 160-line literal. PI_RE additionally normalizes ALL
# Plant Introduction spellings to the GRIN `PI #####` convention (a regex, not an enumerable list).
STRAIN_CORRECTIONS_CSV = REPO / "reference" / "nust_strain_corrections.csv"
PI_RE = re.compile(r"(?i)^P\.?\s*I\.?[\s.\-]*(\d.*)$")


def load_strain_corrections():
    if not STRAIN_CORRECTIONS_CSV.exists():
        print(f"  (strain corrections {STRAIN_CORRECTIONS_CSV.name} absent — PI-normalize only)")
        return {}
    cc = pd.read_csv(STRAIN_CORRECTIONS_CSV, keep_default_na=False)
    return {(str(r.current_strain), int(r.year)): str(r.corrected_strain)
            for r in cc.itertuples(index=False)}


# Unicode cleanup for Strain names:
#  * backcross-generation subscript digits -> regular digits AND properly spaced (user-confirmed
#    convention 2026-07-14): 'WellsIIBC₆' -> 'Wells II BC6', 'WoodworthBC₅' -> 'Woodworth BC5'.
#    Subscript->digit is the general rule (₀-₉ U+2080-2089 -> 0-9); the re-spacing is an explicit
#    per-name map (only these 5 mashed BC names exist corpus-wide, all 1982-83 backcross checks) so
#    we never mis-split other strains. Re-run the subscript audit if new years/BC lines are added.
#  * trailing superscript digits are footnote markers (like the '*' marker) and are stripped:
#    'A2-5405³' -> 'A2-5405', 'Mean¹' -> 'Mean'  (¹²³ = U+00B9/B2/B3, others U+2070-2079)
_SUBDIGIT = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUPFOOT_RE = re.compile("[¹²³⁰⁴⁵⁶⁷⁸⁹]+\\s*$")
_BC_RESPACE = {
    "Amsoy71BC6": "Amsoy 71 BC6", "Beeson80BC6": "Beeson 80 BC6",
    "WellsIIBC6": "Wells II BC6", "WilliamsBC6": "Williams BC6",
    "WoodworthBC5": "Woodworth BC5",
}


def _norm_unicode_strain(s):
    s = _SUPFOOT_RE.sub("", str(s).translate(_SUBDIGIT)).strip()
    return _BC_RESPACE.get(s, s)


def apply_strain_corrections(df):
    """Remap Strain via the curated apply-list (reference/nust_strain_corrections.csv), keyed on
    (Strain, Year), then normalize ALL Plant Introduction designations to GRIN `PI #####` (PI_RE),
    and normalize unicode subscript/superscript digits in the name (see _norm_unicode_strain)."""
    fixes = load_strain_corrections()
    yr = pd.to_numeric(df["Year"], errors="coerce")
    # fillna("") first: de-starred Strain is a StringDtype where originally-NaN strains stay <NA>
    # (a float), which would break PI_RE.sub; the blank rows are dropped later by blank_mask.
    s = df["Strain"].fillna("").astype(str).str.strip()
    step1 = [fixes.get((st, int(y)) if pd.notna(y) else (st, None), st)
             for st, y in zip(s, yr)]
    final = [_norm_unicode_strain(PI_RE.sub(r"PI \1", st)) for st in step1]
    n_dict = sum(1 for a, b in zip(s, step1) if a != b)
    n_pi = sum(1 for a, b in zip(step1, final) if a != b)
    if n_dict or n_pi:
        df = df.copy()
        df["Strain"] = final
        print(f"  Strain corrections: {n_dict:,} remapped via {len(fixes)} apply-list entries "
              f"+ {n_pi:,} PI-normalized / unicode-cleaned")
    return df


# Authoritative check identity: the curated (MG, Strain) check list from the check-identification
# rebuild (analysis 65/67; 528 pairs). IsCheck is set from THIS list — NOT from the '*' marker —
# so every check variety is flagged consistently across all years/locations of the MG it is a
# check for. Runs after Strain is finalized (de-star + OCR/PI corrections) so codes match.
CHECK_LOOKUP_CSV = OUT_DIR / "nust_check_lookup_1941_2025.csv"


def assign_ischeck(df):
    # VARIETY-LEVEL: a curated check variety is flagged IsCheck=1 across ALL its appearances,
    # not just the MG it is listed under. The curated lookup is per-MG and has boundary gaps
    # (e.g. AG38X8 listed in MG III but also run in MG IV; ND Dickey 00/0 also in I), so a strict
    # per-MG match would under-flag exactly the adjacent-MG check placements. Marking by variety
    # name gives the consistent "all check varieties are checks across the table" behaviour.
    cnames = set()
    if CHECK_LOOKUP_CSV.exists():
        lk = pd.read_csv(CHECK_LOOKUP_CSV)
        cnames = set(lk["Strain"].astype(str)
                     .str.replace(r"\s*\*+\s*$", "", regex=True).str.strip())
    else:
        print(f"  (check lookup {CHECK_LOOKUP_CSV.name} absent — IsCheck from CHECK_VARIETIES only)")
    for names in CHECK_VARIETIES.values():              # legacy net (lookup is a superset)
        cnames |= set(names)
    df = df.copy()
    df["IsCheck"] = df["Strain"].astype(str).isin(cnames).astype(int)
    print(f"  IsCheck (curated check lookup, variety-level, {len(cnames)} check varieties): "
          f"{int(df['IsCheck'].sum()):,} check rows / {len(df):,}")
    return df


# Check varieties per MG. Coverage spans 1950-2025; pre-1960 cohort adds
# named varieties used as checks before modern hybrid checks took over
# (Capital, Renville, Mandarin, Ottawa, Manchu, Earlyana, Lincoln, Korean, etc.).
CHECK_VARIETIES = {
    "00": {"Acme", "Flambeau", "Altona", "Norman", "Portage", "Morsoy",
           "Capital", "Renville", "Mandarin", "Ottawa", "Crest"},
    "0":  {"Grant", "Merit", "Clay", "Traverse", "Swift", "Wilkin", "Evans",
           "Merit (0)", "Clay (0)", "Norchief",
           "Manchu", "Earlyana", "Mandarin (Ottawa)"},
    "I":  {"Chippewa", "Chippewa 64", "Hark", "A-100", "Hodgson", "SL7", "SL8",
           "Steele", "Hardin", "Hardin (I)", "MN1606", "MN1410",
           "Blackhawk", "Hawkeye", "Mukden", "Adams (I)"},
    "II": {"Amsoy", "Amsoy 71", "Harosoy", "Harosoy 63", "Beeson", "Corsoy",
           "Wells", "Magna", "Provar", "Williams",
           "Adams", "Lincoln", "Lindarin", "Wabash", "Korean"},
    "III": {"Calland", "Wayne", "Williams", "Shelby", "C1421", "Adelphia",
            "Cumberland", "Adelphia (III)", "Wayne (III)",
            "Ford", "Roanoke", "Clark (III)"},
    "IV": {"Clark", "Clark 63", "Kent", "Cutler", "Cutler 71", "Bonus",
           "L12A", "Custer", "Cutler 71 (IV)",
           "Bethel", "Ogden", "Roanoke (IV)", "Korean (IV)"},
    "V":  set(),  # Will be filled if needed
}

# ---------------------------------------------------------------------------
# Test-code normalization
# ---------------------------------------------------------------------------
TEST_RE = re.compile(r"^(UT|PT|UPT)(\d+|I{1,4}V?|V|VI?)([AB])?$")
# Mapping from RR/TM suffix → Variant
TRAITED_SUFFIXES = ("RR", "TM")


def parse_test_code(raw):
    """Return (Test_normalized, Variant) tuple.

    Variant ∈ {Conventional, Traited}. Test format: PT-0, PT-I, PT-IIA, UT-IV, ...
    Returns (None, None) if unparseable.
    """
    if raw is None or pd.isna(raw):
        return (None, None)
    t = str(raw).strip()
    if not t:
        return (None, None)

    # Strip year suffix _YYYY (master file)
    t = re.sub(r"_(19|20)\d{2}$", "", t)
    # Already-hyphenated? Strip hyphen for normalization, then re-add
    t_compact = t.replace("-", "")

    # Detect Traited
    variant = "Conventional"
    for sfx in TRAITED_SUFFIXES:
        if t_compact.endswith(sfx):
            variant = "Traited"
            t_compact = t_compact[: -len(sfx)]
            break

    # Normalize UPT- → PT-
    if t_compact.startswith("UPT"):
        t_compact = "PT" + t_compact[3:]

    # OCR fix: the 1981-1986 extraction batch rendered the Maturity Group-0/00 digit `0`
    # as the LETTER `O` ("UT-O" / "UT-OO"), so TEST_RE (which expects digits/Roman numerals
    # for the MG) dropped 28,944 real MG-0 rows. Map a pure letter-O MG back to the digit.
    m_o = re.match(r"^(UT|PT)(O{1,2})([AB]?)$", t_compact)
    if m_o:
        t_compact = m_o.group(1) + "0" * len(m_o.group(2)) + m_o.group(3)

    m = TEST_RE.match(t_compact)
    if not m:
        return (None, variant)
    prefix, mg, ab = m.group(1), m.group(2), m.group(3) or ""
    # MG normalization: I/II/III/IV/V stay; numbers 0/00 stay
    test_norm = f"{prefix}-{mg}{ab}"
    return (test_norm, variant)


def normalize_state(s):
    if s is None or pd.isna(s):
        return ""
    return str(s).strip().upper()


def normalize_location(loc):
    if loc is None or pd.isna(loc):
        return ""
    return str(loc).strip()


# Location standardization: canonical (City, State) lookup built by
# data_prep/stage1_processing/build_location_canonical_map.py (only the HIGH-confidence
# action=map_auto rows are applied; OCR/blank-state review rows are NOT applied until
# curated). Keyed on the LITERAL (City, State) corpus pair so this is an exact lookup.
LOC_CANON_MAP_CSV = REPO / "reference" / "nust_location_canonical_map.csv"


def apply_location_canonicalization(df):
    """Map (Location, State) -> (canon City, canon State) for the HIGH-confidence rows.
    Location column holds the city at this stage (renamed to City in add_derived_columns)."""
    if not LOC_CANON_MAP_CSV.exists():
        print(f"  (location map {LOC_CANON_MAP_CSV.name} absent — skipping canonicalization)")
        return df
    cm = pd.read_csv(LOC_CANON_MAP_CSV, keep_default_na=False)
    cm = cm[cm["action"] == "map_auto"]
    lut = {(str(r.raw_city), str(r.raw_state)): (r.canon_city, r.canon_state)
           for r in cm.itertuples(index=False)}
    loc = df["Location"].fillna("").astype(str).str.strip()
    st = df["State"].fillna("").astype(str).str.strip()
    keys = list(zip(loc, st))
    hit = sum(1 for k in keys if k in lut)
    df["Location"] = [lut[k][0] if k in lut else loc.iloc[i] for i, k in enumerate(keys)]
    df["State"] = [lut[k][1] if k in lut else st.iloc[i] for i, k in enumerate(keys)]
    print(f"  Location canonicalization: {hit:,} rows remapped via {len(lut)} HIGH-confidence entries")
    return df


def load_drop_location_pairs():
    """Curated pseudo / summary (City, State) pairs flagged action=drop by the location
    map builder (Composite of N Locations, loc{n}, col, Yield/RANK, Central/MEAN, East Coast,
    Cl vi, DescriptiveCode_NA). These are mis-parsed location fields, not real trial sites;
    drop rows are NEVER remapped, so they keep their original literal (City, State)."""
    if not LOC_CANON_MAP_CSV.exists():
        return set()
    cm = pd.read_csv(LOC_CANON_MAP_CSV, keep_default_na=False)
    cm = cm[cm["action"] == "drop"]
    return {(str(r.raw_city).strip(), str(r.raw_state).strip().upper())
            for r in cm.itertuples(index=False)}


# ---------------------------------------------------------------------------
# Derived columns helper
# ---------------------------------------------------------------------------
TEST_PARSE_RE = re.compile(r"^(UT|PT)-(00|0|I{1,4}V?|V|VI?)([AB])?$")

def add_derived_columns(df):
    """Add TestType (UT/PT), TestMG (00/0/I/...), City (renamed Location), IsCheck."""
    def split_test(t):
        m = TEST_PARSE_RE.match(str(t))
        if not m:
            return (None, None)
        return (m.group(1), m.group(2))

    parsed = df["Test"].apply(split_test)
    df["TestType"] = parsed.apply(lambda x: x[0])
    df["TestMG"]   = parsed.apply(lambda x: x[1])
    df["City"]     = df["Location"]
    # Preserve the original (unedited) Strain name, then strip the trailing '*' from ALL Strain
    # names. The '*' is a per-year SOURCE marker that, kept in the name, split a variety into two
    # genotypes (e.g. 'ND Dickey *' (2020) vs 'ND Dickey' (2025), 'Flyer *' vs 'Flyer'). The '*'
    # is NOT used to infer check status — IsCheck is set authoritatively in assign_ischeck().
    df["Strain_raw"] = df["Strain"].astype(str)
    df["Strain"] = df["Strain_raw"].str.replace(r"\s*\*+\s*$", "", regex=True).str.strip()
    n_destar = int((df["Strain"] != df["Strain_raw"].str.strip()).sum())
    if n_destar:
        nv = df.loc[df["Strain"] != df["Strain_raw"].str.strip(), "Strain"].nunique()
        print(f"  De-star Strain: stripped trailing '*' from {n_destar:,} rows ({nv} varieties); "
              f"original kept in Strain_raw")
    df["IsCheck"] = 0   # assigned authoritatively in assign_ischeck() once Strain is finalized
    return df[FINAL_COLS]


# ---------------------------------------------------------------------------
# Phase 1: Load 1965-1988 from Files4Upload
# ---------------------------------------------------------------------------
def load_1941_1988_f4u():
    rows = []
    for year, path in sorted(F4U_PATHS_1941_1988.items()):
        if not path.exists():
            print(f"  {year}: MISSING {path}")
            continue
        df = pd.read_csv(path, low_memory=False)
        # Long-format columns: Strain, Year, Test, City, State, Phenotype, Value, Units
        if "City" in df.columns:
            df = df.rename(columns={"City": "Location"})
        if "Value" in df.columns and "Value_num" not in df.columns:
            df["Value_num"] = pd.to_numeric(df["Value"], errors="coerce")
        elif "Value_num" not in df.columns:
            df["Value_num"] = np.nan
        # Test normalization
        parsed = df["Test"].astype(str).apply(parse_test_code)
        df["Test_norm"] = parsed.apply(lambda x: x[0])
        df["Variant"]   = parsed.apply(lambda x: x[1])
        n_unparsed = df["Test_norm"].isna().sum()
        df = df.dropna(subset=["Test_norm"]).copy()
        df["Test"] = df["Test_norm"]
        df.drop(columns=["Test_norm"], inplace=True)
        df["State"] = df["State"].apply(normalize_state)
        df["Location"] = df["Location"].apply(normalize_location)
        if "Units" not in df.columns:
            df["Units"] = ""
        df["Source"] = "F4U_1941_1988"
        df = df[KEY_COLS]
        print(f"  {year}: {len(df):>6} rows (unparseable Test dropped: {n_unparsed})")
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=KEY_COLS)


def load_1989_1992_f4u():
    """1989/1991/1992 from-source F4U (9 traits: agronomic + Protein/Oil). Same schema
    path as load_1941_1988_f4u; Source=F4U_1989_1992. Protein/Oil are DRY basis (report
    values) — 11_build_wide applies the ×0.87 13%-mb correction for these years."""
    rows = []
    for year, path in sorted(F4U_PATHS_1989_1992.items()):
        if not path.exists():
            print(f"  {year}: MISSING {path}")
            continue
        df = pd.read_csv(path, low_memory=False).rename(columns={"City": "Location"})
        df["Value_num"] = pd.to_numeric(df["Value"], errors="coerce")
        parsed = df["Test"].astype(str).apply(parse_test_code)
        df["Test"] = parsed.apply(lambda x: x[0])
        df["Variant"] = parsed.apply(lambda x: x[1])
        df = df.dropna(subset=["Test"]).copy()
        df["State"] = df["State"].apply(normalize_state)
        df["Location"] = df["Location"].apply(normalize_location)
        if "Units" not in df.columns:
            df["Units"] = ""
        df["Source"] = "F4U_1989_1992"
        df = df[KEY_COLS]
        print(f"  {year}: {len(df):>6} rows")
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=KEY_COLS)


# Phase-6 recovery: per-location trait tables the F4U extraction SKIPPED, recovered from the
# Green Sojabone XLSX and dual-source-validated (scripts 109/111; gap-campaign Phase 2).
RECOVERY_CSV = REPO / "data_prep" / "stage2_corpus" / "recovery_confirmed.csv"


def load_recovery_1970_1988():
    """Validated recovered per-location rows (Source=Recovered_1970_1988). Schema-matched
    to KEY_COLS and run through the same parse/normalize path as the F4U loader."""
    if not RECOVERY_CSV.exists():
        return pd.DataFrame(columns=KEY_COLS)
    df = pd.read_csv(RECOVERY_CSV, low_memory=False)
    df = df.rename(columns={"City": "Location"})
    parsed = df["Test"].astype(str).apply(parse_test_code)
    df["Test"] = parsed.apply(lambda x: x[0])
    df["Variant"] = parsed.apply(lambda x: x[1])
    df = df.dropna(subset=["Test"]).copy()
    df["State"] = df["State"].apply(normalize_state)
    df["Location"] = df["Location"].apply(normalize_location)
    if "Value_num" not in df.columns:
        df["Value_num"] = pd.to_numeric(df.get("Value"), errors="coerce")
    df["Source"] = "Recovered_1970_1988"
    df = df[KEY_COLS]
    print(f"  recovery (Phase-6): {len(df):>6} rows  years={sorted(df['Year'].unique())}")
    return df


QC_PATCH_CSV = REPO / "data_prep" / "stage2_corpus" / "qc_pdf_patches.csv"


def load_qc_pdf_patches():
    """Confidently-fixable OCR errors from the per-year CSV-vs-PDF QC (built by
    10a_build_qc_pdf_patches.py): cells still holding the OCR error whose PDF value is a
    clean in-range number. Source=QC_PDF_patch; supersedes the matching F4U cell."""
    if not QC_PATCH_CSV.exists():
        return pd.DataFrame(columns=KEY_COLS)
    df = pd.read_csv(QC_PATCH_CSV, low_memory=False).rename(columns={"City": "Location"})
    parsed = df["Test"].astype(str).apply(parse_test_code)
    df["Test"] = parsed.apply(lambda x: x[0])
    df["Variant"] = parsed.apply(lambda x: x[1])
    df = df.dropna(subset=["Test"]).copy()
    df["State"] = df["State"].apply(normalize_state)
    df["Location"] = df["Location"].apply(normalize_location)
    df["Value_num"] = pd.to_numeric(df.get("Value_num"), errors="coerce")
    df["Value"] = df["Value_num"]
    if "Units" not in df.columns:
        df["Units"] = ""
    df["Source"] = "QC_PDF_patch"
    df = df[KEY_COLS]
    print(f"  QC PDF patches: {len(df):>6} rows  years={sorted(df['Year'].unique())}")
    return df


# ---------------------------------------------------------------------------
# Phase 2: Load 1989-1992 from master file (gap-fill)
# ---------------------------------------------------------------------------
def load_master_full():
    """Load the entire 1989-2017 master file with parsing applied.

    Used both for 1989-1992 gap-fill (returned subset) and for the cross-check
    against queryportal 1993-2017.
    """
    print(f"\nLoading master file ({MASTER_CSV.name}; this may take a moment)...")
    df = pd.read_csv(MASTER_CSV, low_memory=False)
    print(f"  Raw rows: {len(df):,}")
    # Parse Year + Test from Experiment
    df["Year"] = df["Experiment"].astype(str).str.extract(r"_(\d{4})$").astype(float).astype("Int64")
    df = df[df["Year"].notna()].copy()
    df["Exp_base"] = df["Experiment"].astype(str).str.replace(r"_\d{4}$", "", regex=True)
    parsed = df["Exp_base"].apply(parse_test_code)
    df["Test"] = parsed.apply(lambda x: x[0])
    df["Variant"] = parsed.apply(lambda x: x[1])
    df = df.dropna(subset=["Test"]).copy()
    # Rename GermplasmId → Strain
    df = df.rename(columns={"GermplasmId": "Strain"})
    # State: not present directly, but Location often encodes state-coded names.
    # Master file Location is just town/site name; leave State blank for now.
    df["State"] = ""
    df["Location"] = df["Location"].apply(normalize_location)
    df["Value_num"] = pd.to_numeric(df["Value"], errors="coerce")
    df["Units"] = ""
    df["Source"] = "Master_1989_1992"
    df["Year"] = df["Year"].astype(int)
    return df


def aggregate_plot_to_location(df):
    """Mean over Rep/Plot/Range/Row → one row per (Year, Test, Variant, Location, Strain, Phenotype)."""
    grp_cols = ["Year", "Test", "Variant", "Location", "State", "Strain", "Phenotype", "Units", "Source"]
    agg = (
        df.groupby(grp_cols, dropna=False, as_index=False)["Value_num"]
          .mean()
    )
    return agg[KEY_COLS]


def load_1989_1992_from_master(master_df):
    # 1990 excluded — sourced from F4U via PDF-direct extraction instead (master CSV
    # had only 7 PT-IIIA rows + zero UT). Pulled into F4U_PATHS_1941_1988 above.
    # 2026-07-12: the 9 agronomic + composition traits now come from the from-source F4U
    # (load_1989_1992_f4u); keep the Master ONLY for the disease/descriptive traits it
    # uniquely carries for these years (Chlorosis, Shattering, SMV, PRRace1, BSR*, SDS*, ...).
    sub = master_df[master_df["Year"].isin([1989, 1991, 1992])
                    & ~master_df["Phenotype"].isin(F4U_TRAITS_1989_1992)].copy()
    print(f"  Master 1989+1991+1992 disease/descriptive plot-level rows: {len(sub):,} "
          f"(traits: {sorted(sub['Phenotype'].unique())})")
    agg = aggregate_plot_to_location(sub)
    print(f"  Aggregated to location-level: {len(agg):,} rows")
    return agg


# ---------------------------------------------------------------------------
# Phase 3: Cross-check master vs queryportal for 1993-2017
# ---------------------------------------------------------------------------
def load_queryportal_year(year):
    """Load a single year from the queryportal year-specific or bucket folder."""
    bucket = None
    if year <= 1997:
        bucket = "1993_1997"
    elif year <= 2003:
        bucket = "1998_2003"
    elif year <= 2008:
        bucket = "2004_2008"
    else:
        bucket = str(year)
    fp = QP / bucket / "phenotypesTable1.csv"
    if not fp.exists():
        return None, fp
    df = pd.read_csv(fp, low_memory=False)
    df = df[df["Year"] == year].copy()
    return df, fp


def queryportal_to_long(df):
    """Wide-format → long-format. Identifies metadata columns and melts the rest."""
    meta = ["Year", "Test", "Location", "State", "Strain"]
    have = [c for c in meta if c in df.columns]
    trait_cols = [c for c in df.columns if c not in have]
    long = df.melt(id_vars=have, value_vars=trait_cols,
                   var_name="Phenotype", value_name="Value")
    long["Value"] = long["Value"].astype(str).str.strip()
    long = long[~long["Value"].isin(["", "NA", "nan", "NaN"])].copy()
    long["Value_num"] = pd.to_numeric(long["Value"], errors="coerce")
    long = long.dropna(subset=["Value_num"]).copy()
    if "State" not in long.columns:
        long["State"] = ""
    if "Units" not in long.columns:
        long["Units"] = ""
    return long


def crosscheck_master_vs_queryportal(master_df):
    """Compare per-year row counts and YieldBuA means between master and queryportal."""
    rows = []
    for year in range(1993, 2018):
        qp_raw, _ = load_queryportal_year(year)
        if qp_raw is None or qp_raw.empty:
            rows.append({"Year": year, "qp_rows": 0, "qp_strains": 0, "qp_yield_mean": np.nan,
                         "master_rows": int((master_df["Year"] == year).sum()),
                         "note": "queryportal missing"})
            continue
        qp_long = queryportal_to_long(qp_raw)
        master_y = master_df[master_df["Year"] == year]
        rows.append({
            "Year": year,
            "qp_rows": len(qp_long),
            "qp_strains": qp_long["Strain"].nunique() if "Strain" in qp_long.columns else 0,
            "qp_yield_mean": round(
                qp_long.loc[qp_long["Phenotype"] == "YieldBuA", "Value_num"].mean(), 2),
            "master_rows": len(master_y),
            "master_strains": master_y["Strain"].nunique(),
            "master_yield_mean": round(
                master_y.loc[master_y["Phenotype"] == "YieldBuA", "Value_num"].mean(), 2),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Phase 4: Load 1993-2020 from queryportal
# ---------------------------------------------------------------------------
def load_1993_2020_queryportal():
    rows = []
    for year in range(1993, 2021):
        df_raw, fp = load_queryportal_year(year)
        if df_raw is None or df_raw.empty:
            print(f"  {year}: MISSING from queryportal")
            continue
        long = queryportal_to_long(df_raw)
        parsed = long["Test"].astype(str).apply(parse_test_code)
        long["Test_norm"] = parsed.apply(lambda x: x[0])
        long["Variant"]   = parsed.apply(lambda x: x[1])
        long = long.dropna(subset=["Test_norm"]).copy()
        long["Test"] = long["Test_norm"]
        long.drop(columns=["Test_norm"], inplace=True)
        long["State"] = long["State"].apply(normalize_state)
        long["Location"] = long["Location"].apply(normalize_location)
        long["Units"] = ""
        long["Source"] = "Queryportal_1993_2020"
        long = long[KEY_COLS]
        rows.append(long)
        print(f"  {year}: {len(long):>6} rows ({fp.parent.name})")
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=KEY_COLS)


# ---------------------------------------------------------------------------
# Phase 5: Load 2021-2025 from root
# ---------------------------------------------------------------------------
def load_2021_2025_root():
    """Auto-detect long vs wide format per year (2021-2022 are wide; 2023-2025 are long)."""
    rows = []
    for year, fp in sorted(ROOT_PATHS_2021_2025.items()):
        if not fp.exists():
            print(f"  {year}: MISSING {fp}")
            continue
        df_raw = pd.read_csv(fp, low_memory=False)
        if "Year" in df_raw.columns:
            df_raw = df_raw[df_raw["Year"] == year].copy()
        is_long = ("Phenotype" in df_raw.columns) and ("Value" in df_raw.columns)
        if is_long:
            long = df_raw.copy()
            # Normalize column names
            if "City" in long.columns and "Location" not in long.columns:
                long = long.rename(columns={"City": "Location"})
            if "City" in long.columns and "Location" in long.columns:
                # 2025 has both — prefer Location
                long = long.drop(columns=["City"])
            long["Value_num"] = pd.to_numeric(long["Value"], errors="coerce")
            if "Units" not in long.columns:
                long["Units"] = ""
        else:
            long = queryportal_to_long(df_raw)
        parsed = long["Test"].astype(str).apply(parse_test_code)
        long["Test_norm"] = parsed.apply(lambda x: x[0])
        long["Variant"]   = parsed.apply(lambda x: x[1])
        long = long.dropna(subset=["Test_norm"]).copy()
        long["Test"] = long["Test_norm"]
        long.drop(columns=["Test_norm"], inplace=True)
        long["State"] = long["State"].apply(normalize_state)
        long["Location"] = long["Location"].apply(normalize_location)
        long["Source"] = "Root_2021_2025"
        long = long[KEY_COLS]
        rows.append(long)
        fmt = "long" if is_long else "wide"
        print(f"  {year}: {len(long):>6} rows ({fmt})")
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=KEY_COLS)


# ---------------------------------------------------------------------------
# Maturity DOY physical-validity fix
# ---------------------------------------------------------------------------
# The corpus stores soybean maturity as absolute day-of-year (DOY). A handful of
# pre-1988 test×location groups leaked into the corpus carrying the RAW value that
# the offset→DOY conversion was supposed to consume — small ± offsets relative to a
# dated check (1945/1965-68), a days-after-planting encoding (1944 UT-III West
# Lafayette), or garbled extraction cells on the anchor checks (1982/1986). All are
# physically impossible as DOY. Soybean R8 maturity in North America falls late
# summer→fall; the empirical corpus floor is DOY 183 (early July, ultra-early MG-00
# at southern sites) and the latest plausible is ~DOY 330 (mid-Nov, deep-south late
# MG). The window below sits just below the 183 floor (an empty guard band spans
# 165-182) so it flags the June-impossible groups without clipping any real value.
#
# Fix strategy (mirrors data_prep/stage2_corpus/96_fix_early_maturity.py and the
# 1988/1990 DOY reconstruction, but applied AT SOURCE inside the assembly so every
# rebuild reproduces it):
#   1. reconstruct DOY = AnchorDOY(Year,Test,City,State) + offset when an anchor is
#      supplied AND the stored value is offset-like AND the result lands in-window;
#   2. otherwise DROP the impossible Maturity row (NULL — a wrong value is worse than
#      missing; consistent with the established method NULLing unrecoverable groups).
# Reconstruction is a drop-in upgrade: populate reference/nust_maturity_doy_anchors.csv
# (Year,Test,City,State,AnchorDOY) with the dated-check calendar maturity DOY read
# from the Red-PDF annual reports and rebuild — the cell is then reconstructed rather
# than NULLed. With no anchor file present (the default), every impossible cell NULLs.
MAT_DOY_LO, MAT_DOY_HI = 175, 340
MAT_ANCHOR_CSV = REPO / "reference" / "nust_maturity_doy_anchors.csv"
MAT_OFFSET_MAX = 60.0   # a leaked value beyond ±this is not an anchor offset (won't reconstruct)
# 1966 UT-III "D.tom." is a "days-to-maturity" summary label mis-parsed into the
# Strain field, not a genotype: all 18 of its traits are NaN except an impossible
# maturity at 20 locations. Dropped as a pseudo-strain.
DTOM_PSEUDO_STRAINS = {"d.tom.", "d.tom", "dtom"}


def load_maturity_doy_anchors():
    """Optional (Year,Test,City,State) -> AnchorDOY table for reconstructing offset-
    leaked Maturity cells. Absent/empty (the default) => impossible cells are NULLed."""
    if not MAT_ANCHOR_CSV.exists():
        return {}
    a = pd.read_csv(MAT_ANCHOR_CSV, keep_default_na=False)
    out = {}
    for r in a.itertuples(index=False):
        try:
            out[(int(r.Year), str(r.Test).strip(), str(r.City).strip(),
                 str(r.State).strip().upper())] = float(r.AnchorDOY)
        except (ValueError, TypeError, AttributeError):
            continue
    if out:
        print(f"  maturity-DOY: loaded {len(out)} reconstruction anchors from {MAT_ANCHOR_CSV.name}")
    return out


def fix_maturity_doy(df):
    """Drop the 'D.tom.' pseudo-strain and correct physically-impossible Maturity DOY
    (outside [MAT_DOY_LO, MAT_DOY_HI]) by reconstruct-or-NULL. Fixed at source."""
    df = df.copy()
    # (a) drop the 1966 "D.tom." days-to-maturity pseudo-strain (non-genotype)
    dtom = (df["Strain"].astype(str).str.strip().str.lower()
            .str.replace(" ", "", regex=False).isin(DTOM_PSEUDO_STRAINS))
    if dtom.any():
        print(f"  maturity-DOY: dropping {int(dtom.sum())} 'D.tom.' pseudo-strain rows "
              f"(days-to-maturity artifact, years {sorted(df.loc[dtom, 'Year'].unique())})")
        df = df[~dtom].copy()
    # (a2) confirmed SOURCE-REPORT maturity typos that fall INSIDE the physical window
    # (so the range check in (b) can't catch them). Verified vs the annual report PDF +
    # same-site cross-test. (Year, Test, City-lower, State, Strain-lower) -> corrected DOY.
    MATURITY_CONTEXT_CORRECTIONS = [
        # 2004 UT-II Roundup-Ready, Beresford SD, AG2801 (check): report prints the maturity
        # OFFSET as '46' (glyph-verified + 8x render; anchor AG2302 9/19=DOY262) -> DOY ~309, an
        # impossible +46d offset when column-mates are +2/+4/+6. True 269 (PT-II RR same site+year)
        # / 266 (adjacent Brookings SD). Standalone maturity-adjusted estimator flagged it; DOY 309
        # is IN-window so (b) misses it. See fix_2004_beresford_ag2801_maturity.py.
        (2004, "UT-II", "beresford", "SD", "ag2801", 269.0),
    ]
    is_mat0 = df["Phenotype"] == "Maturity"
    for (yr, test, city, state, strain, newdoy) in MATURITY_CONTEXT_CORRECTIONS:
        m = (is_mat0 & (df["Year"] == yr)
             & (df["Test"].astype(str).str.strip() == test)
             & (df["City"].astype(str).str.strip().str.lower() == city)
             & (df["State"].astype(str).str.strip().str.upper() == state)
             & (df["Strain"].astype(str).str.strip().str.lower() == strain))
        if m.any():
            df.loc[m, "Value_num"] = newdoy
            print(f"  maturity-DOY: context-corrected {int(m.sum())} in-window typo cell(s) "
                  f"{yr} {test} {city} {state} {strain} -> {newdoy}")
    # (b) correct impossible Maturity DOY
    is_mat = df["Phenotype"] == "Maturity"
    v = pd.to_numeric(df["Value_num"], errors="coerce")
    bad = is_mat & v.notna() & ((v < MAT_DOY_LO) | (v > MAT_DOY_HI))
    if not bad.any():
        print("  maturity-DOY: no physically-impossible values (all in "
              f"[{MAT_DOY_LO},{MAT_DOY_HI}])")
        return df
    anchors = load_maturity_doy_anchors()
    recon = 0
    drop_idx = []
    for idx in df.index[bad]:
        off = pd.to_numeric(df.at[idx, "Value_num"], errors="coerce")
        key = (int(df.at[idx, "Year"]), str(df.at[idx, "Test"]).strip(),
               str(df.at[idx, "City"]).strip(), str(df.at[idx, "State"]).strip().upper())
        a = anchors.get(key)
        if a is not None and abs(off) <= MAT_OFFSET_MAX:
            doy = round(a + off)
            if MAT_DOY_LO <= doy <= MAT_DOY_HI:
                df.at[idx, "Value_num"] = float(doy)
                recon += 1
                continue
        drop_idx.append(idx)
    by_year = df.loc[drop_idx, "Year"].value_counts().sort_index().to_dict()
    print(f"  maturity-DOY: {int(bad.sum())} impossible cells → "
          f"reconstructed {recon}, NULLed(dropped) {len(drop_idx)}  (NULLed by year: {by_year})")
    return df.drop(index=drop_idx)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _yr_range(df, label):
    """Return (yfirst, ylast) for a df, or (None, None) if empty."""
    if df is None or df.empty or "Year" not in df.columns:
        return None, None
    ys = sorted(df["Year"].unique())
    return int(ys[0]), int(ys[-1])


_US_STATES = set("AL AK AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE "
                 "NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY "
                 "ON QC MB SK AB BC NB NS".split())


def refile_year_in_state(df):
    """Some 1940s report tables print a station across TWO+ years (a multi-year comparison), and the
    OCR put the YEAR in the State slot: `Evansville IN`,State=`1943` alongside `Evansville IN`,State=`1944`.
    Canonicalization would collapse both to (Evansville, IN) at the report Year -> a spurious value-conflict
    that mixes two crop years. Fix at attribution: a column labeled with year YYYY is a YYYY observation.
    Set Year<-YYYY for prior-year columns (state-year < report Year) and recover the real State from the
    city text ('Evansville IN'->IN) for all year-labeled columns. The unlabeled base column (State already
    a real code) is untouched; if it genuinely coexists with the current-year column it stays a held
    conflict for PDF review (e.g. 1947 Worthington base). Runs on `Location` (pre add_derived rename)."""
    st = df["State"].astype(str).str.strip()
    ymask = st.str.fullmatch(r"(18|19|20)\d\d")
    if not ymask.any():
        return df
    df = df.copy()
    # Evidence-based base override FIRST, on the RAW Location (before the year-labeled re-file below
    # normalizes 'Worthington IN'->'Worthington'): 1947 PT-IV Worthington OCR split the 1946 column — its
    # MATURITY parsed under `Worthington IN`,State=`1946` but its YIELD landed in the unlabeled base
    # `Worthington`,`IN` (values ~4-8 below the complete 1947 column). Re-file the base yield to 1946 so
    # base+|1946 reunite as the 1946 observation. Verified via per-column phenotype coverage (base=Yield/
    # Rank only, |1946=Maturity only, |1947=all). Scoped to PT-IV (UT Worthington has no year-split).
    base_ovr = ((pd.to_numeric(df["Year"], errors="coerce") == 1947) & (df["Test"] == "PT-IV")
                & (df["Location"].astype(str).str.strip() == "Worthington")
                & (df["State"].astype(str).str.strip().str.upper() == "IN"))
    if base_ovr.any():
        df.loc[base_ovr, "Year"] = 1946
        print(f"  Year-in-state base override: {int(base_ovr.sum())} rows (1947 PT-IV Worthington base yield -> 1946)")
    ex = df["Location"].astype(str).str.strip().str.extract(r"^(?P<base>.*\S)\s+(?P<st>[A-Za-z]{2})$")
    ok = ymask & ex["st"].str.upper().isin(_US_STATES)
    sy = pd.to_numeric(st, errors="coerce")
    yr = pd.to_numeric(df["Year"], errors="coerce")
    n_prior = int((ok & (sy < yr)).sum())
    df.loc[ok, "Location"] = ex.loc[ok, "base"]
    df.loc[ok, "State"] = ex.loc[ok, "st"].str.upper()
    df.loc[ok & (sy < yr), "Year"] = sy[ok & (sy < yr)].astype(int)
    print(f"  Year-in-state re-file: {int(ok.sum())} rows fixed "
          f"({n_prior} prior-year cols re-filed to true Year; rest state-corrected)")
    return df


# Cell dedup: after all merges (strain corrections, patch/recovery supersede, sub-env location split),
# a (Year,Test,Variant,City,State,Strain,Phenotype) cell may still carry duplicate rows. Resolve them so
# every cell is a single observation (RGG one-obs-per-GxLxY). Small OCR value drift is averaged; a wide
# gap (two genuinely different reads / a two-year-merged column) is HELD for PDF review, not silently
# averaged. See [[project_nust_corpus_integrity_audit]] (dedup + subenv split, 2026-07-17).
DEDUP_GAP_THR = {"YieldBuA": 5, "Height": 4, "Maturity": 4, "Lodging": 1.0, "SeedQuality": 1.0,
                 "SeedSize": 2, "Protein": 2, "Oil": 1.5, "YieldRank": 1e9}  # YieldRank derived -> always mean
DEDUP_REVIEW_CSV = REPO / "data_prep" / "stage2_corpus" / "conflict_large_gap_review.csv"


def dedup_cells(full):
    KEY = ["Year", "Test", "Variant", "City", "State", "Strain", "Phenotype"]
    n0 = len(full)
    full = full.copy()
    full["_k"] = list(zip(*[full[k].astype(str) for k in KEY]))
    # (1) nan-padding: a key with any valued row -> drop its NaN rows
    hasval = full.groupby("_k")["Value_num"].transform(lambda s: s.notna().any())
    full = full[~(full["Value_num"].isna() & hasval)].copy()
    n_pad = n0 - len(full)
    # (2) all-NaN duplicate keys -> keep first
    allnan = full[full["Value_num"].isna()]
    full = full.drop(index=allnan[allnan.duplicated("_k", keep="first")].index)
    n_allnan = n0 - n_pad - len(full)
    # (3) multi-VALUED conflict keys
    val = full[full["Value_num"].notna()]
    nd = val.groupby("_k")["Value_num"].apply(lambda s: s.round(3).nunique())
    conf = set(nd[nd >= 2].index)
    review, drop_idx, n_mean = [], [], 0
    for k, g in val[val["_k"].isin(conf)].groupby("_k"):
        vals = g["Value_num"]; ph = g["Phenotype"].iloc[0]
        if (vals.max() - vals.min()) <= DEDUP_GAP_THR.get(ph, 3):
            keep = g.index[0]
            full.at[keep, "Value_num"] = round(vals.mean(), 3)
            drop_idx.extend(i for i in g.index if i != keep); n_mean += 1
        else:
            review.append(dict(zip(KEY, k)) | {"gap": round(vals.max() - vals.min(), 2),
                          "vmin": vals.min(), "vmax": vals.max(), "n": len(g)})
    full = full.drop(index=drop_idx).drop(columns="_k")
    pd.DataFrame(review).to_csv(DEDUP_REVIEW_CSV, index=False)
    print(f"  Cell dedup: {n0:,} → {len(full):,} rows  (nan-pad {n_pad:,}, all-NaN dup {n_allnan:,}, "
          f"small-gap mean {n_mean}, large-gap HELD {len(review)} → {DEDUP_REVIEW_CSV.name})")
    return full


def main():
    print("=" * 70)
    print("NUST Full Corpus Assembly (year range discovered from data)")
    print("=" * 70)

    print("\n[1/5] Loading F4U historical years...")
    df_1941_1988 = load_1941_1988_f4u()
    df_1941_1988 = drop_aux_phenotypes(df_1941_1988)   # drop YieldRank (redundant + unreliable; see DROP_PHENOTYPES)
    f4u_lo, f4u_hi = _yr_range(df_1941_1988, "F4U")
    df_1941_1988.to_csv(OUT_DIR / f"nust_{f4u_lo}_{f4u_hi}_combined_f4u.csv", index=False)  # -> nust_1941_1988_combined_f4u.csv
    print(f"  → {len(df_1941_1988):,} rows  "
          f"({len(df_1941_1988['Year'].unique())} years, {f4u_lo}-{f4u_hi})")

    print("\n[2/5] Loading 1989-2017 master file...")
    master_df = load_master_full()
    master_df["Value_num"] = pd.to_numeric(master_df["Value"], errors="coerce")
    print("  1989-1992: from-source F4U (9 traits) + Master (disease/descriptive only)")
    df_8992_f4u = load_1989_1992_f4u()
    df_8992_disease = load_1989_1992_from_master(master_df)
    df_1989_1992 = pd.concat([df_8992_f4u, df_8992_disease], ignore_index=True)
    df_1989_1992 = drop_aux_phenotypes(df_1989_1992)   # drop YieldRank (see DROP_PHENOTYPES)
    df_1989_1992.to_csv(OUT_DIR / "nust_1989_1992_combined.csv", index=False)
    print(f"  → 1989-1992: {len(df_1989_1992):,} rows  ({len(df_1989_1992['Year'].unique())} years; "
          f"F4U {len(df_8992_f4u):,} + Master-disease {len(df_8992_disease):,})")

    print("\n[3/5] Cross-checking master vs queryportal (1993-2017)...")
    # Aggregate master to location-level for fair comparison
    master_agg = aggregate_plot_to_location(
        master_df[(master_df["Year"] >= 1993) & (master_df["Year"] <= 2017)]
    )
    crosscheck = crosscheck_master_vs_queryportal(master_agg)
    crosscheck.to_csv(OUT_DIR / "master_vs_queryportal_crosscheck.csv", index=False)
    print(crosscheck.to_string(index=False))

    print("\n[4/5] Loading 1993-2020 from queryportal...")
    df_1993_2020 = load_1993_2020_queryportal()
    print(f"  → {len(df_1993_2020):,} rows  ({len(df_1993_2020['Year'].unique())} years)")

    print("\n[5/5] Loading 2021-2025 from root...")
    df_2021_2025 = load_2021_2025_root()
    print(f"  → {len(df_2021_2025):,} rows  ({len(df_2021_2025['Year'].unique())} years)")

    # 1993-2025 combined
    df_1993_2025 = pd.concat([df_1993_2020, df_2021_2025], ignore_index=True)
    df_1993_2025 = drop_aux_phenotypes(df_1993_2025)   # drop YieldRank (see DROP_PHENOTYPES)
    df_1993_2025.to_csv(OUT_DIR / "nust_1993_2025_combined.csv", index=False)
    print(f"\n1993-2025 combined: {len(df_1993_2025):,} rows  "
          f"({sorted(df_1993_2025['Year'].unique())[0]}-{sorted(df_1993_2025['Year'].unique())[-1]})")

    # Full union — add derived columns. Output filename is data-driven from
    # actual min/max Year. Legacy aliases `nust_1941_2025_combined.csv` and
    # `nust_1965_2025_combined.csv` are also written so downstream scripts
    # don't break when the year range extends.
    df_recovery = load_recovery_1970_1988()
    df_qcpatch = load_qc_pdf_patches()
    full = pd.concat([df_1941_1988, df_recovery, df_qcpatch, df_1989_1992, df_1993_2025], ignore_index=True)
    full = drop_aux_phenotypes(full)               # belt-and-suspenders: also drop any YieldRank from recovery/qcpatch
    full = refile_year_in_state(full)              # 1940s multi-year cols: attribute to true Year + real State
    full = apply_location_canonicalization(full)   # standardize City/State before deriving City
    full = add_derived_columns(full)
    # Strain corrections run BEFORE the supersede (moved 2026-07-17). The apply-list unifies OCR
    # strain-name variants that change ALPHANUMERICS (e.g. F4U 'L3-700'->'L6-700', '35-41'->'S5-41',
    # 'Ml'->'M1', 'Ancka'->'Anoka') — a second, partial OCR read of the SAME line that lands under a
    # misread name and duplicates the canonical roster at the shared locations. If corrections ran
    # after the supersede (as they used to), the variant row still carried its misread name, so the
    # patch/recovery raw-key supersede could not match it (and the normalized _nmk pass only strips
    # punctuation/(), never a digit change l3700!=l6700) -> the variant survived as a duplicate cell
    # ALONGSIDE the patch. Renaming first makes every variant canonical so the supersede below drops it.
    full = apply_strain_corrections(full)          # source-confirmed OCR + PI/name restorations
    # Phase-6: a recovered per-location cell supersedes the F4U cell for the same (cell) — both the
    # all-NaN placeholders the original extraction emitted for SKIPPED trait tables, AND the
    # wrong-valued cells the 1977 corrections replace (Green-correct). Recovery rows are emitted
    # ONLY for cells we mean to supersede, so dropping the matching F4U row (any value) is safe.
    # Done AFTER canonicalization so City spellings (Lafayette->West Lafayette) match on both sides.
    # QC_PDF_patch (10a) supersedes the F4U cell the same way (confirmed OCR-error corrections).
    kcols = ["Year", "Test", "City", "State", "Strain", "Phenotype"]
    for supers_source in ("Recovered_1970_1988", "QC_PDF_patch"):
        keys = set(map(tuple, full.loc[full["Source"] == supers_source, kcols].astype(str).values))
        if not keys:
            continue
        fk = pd.Series(map(tuple, full[kcols].astype(str).values), index=full.index)
        superseded = (full["Source"] == "F4U_1941_1988") & fk.isin(keys)
        if superseded.any():
            print(f"  {supers_source}: dropped {int(superseded.sum())} superseded F4U cells "
                  f"({int((superseded & full['Value_num'].notna()).sum())} valued corrections)")
            full = full[~superseded].copy()

    # QC patch: also supersede on a NORMALIZED key. Belt-and-suspenders after the corrections above —
    # catches residual punctuation/() City/Strain differences (e.g. 'PI 92,717' vs 'PI 92717') that
    # the raw-string key would miss. Strip punctuation/() from Strain and City so the patch value wins.
    def _nmk(s):
        return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())

    def _nck(s):
        return re.sub(r"[^a-z0-9]", "", str(s).lower())

    pk = full.loc[full["Source"] == "QC_PDF_patch"]
    if len(pk):
        nkeys = set(zip(pk["Year"].astype(str), pk["Test"].astype(str), pk["State"].astype(str),
                        pk["City"].map(_nck), pk["Strain"].map(_nmk), pk["Phenotype"].astype(str)))
        fn = pd.Series(zip(full["Year"].astype(str), full["Test"].astype(str), full["State"].astype(str),
                           full["City"].map(_nck), full["Strain"].map(_nmk), full["Phenotype"].astype(str)),
                       index=full.index)
        drop2 = (full["Source"] == "F4U_1941_1988") & fn.isin(nkeys)
        if drop2.any():
            print(f"  QC_PDF_patch (normalized key): dropped {int(drop2.sum())} more OCR-variant F4U cells")
            full = full[~drop2].copy()
    full = assign_ischeck(full)                    # authoritative IsCheck from curated check lookup
    # Drop disease-rating / region-mean pseudo-locations mis-parsed into City: the regex
    # (PSEUDO_LOC_RE) plus the location map's curated drop-tier (City, State) pairs
    # (Composite/loc{n}/col/Yield/East Coast/Cl vi — see build_location_canonical_map.py).
    n_before = len(full)
    drop_pairs = load_drop_location_pairs()
    city_s = full["City"].fillna("").astype(str).str.strip()
    state_s = full["State"].fillna("").astype(str).str.strip().str.upper()
    pseudo_mask = (city_s.apply(lambda c: bool(PSEUDO_LOC_RE.search(c)))
                   | pd.Series([p in drop_pairs for p in zip(city_s, state_s)], index=full.index))
    if pseudo_mask.any():
        print(f"  Dropping {int(pseudo_mask.sum())} pseudo-location rows "
              f"(disease-rating / region-mean mis-parsed as City): "
              f"{sorted(full.loc[pseudo_mask, 'City'].unique())}")
        full = full[~pseudo_mask].copy()
    print(f"  Pseudo-location filter: {n_before:,} → {len(full):,} rows")
    # Drop stray STRAIN values that are not real varieties (see STRAY_STRAIN_RE).
    n_before = len(full)
    stray_mask = full["Strain"].fillna("").astype(str).apply(lambda s: bool(STRAY_STRAIN_RE.search(s)))
    if stray_mask.any():
        print(f"  Dropping {int(stray_mask.sum())} stray-strain rows "
              f"(summary/date/negative/OCR-junk Strain values): "
              f"{sorted(full.loc[stray_mask, 'Strain'].astype(str).unique())[:20]}")
        full = full[~stray_mask].copy()
    print(f"  Stray-strain filter: {n_before:,} → {len(full):,} rows")
    # Drop blank / NaN Strain rows (no genotype to attribute — QC rule `blank_or_nan`; the lone
    # case is a 1970 UT-III extraction artifact, 108 rows, 104 of them entirely NaN-valued).
    n_before = len(full)
    blank_mask = full["Strain"].isna() | (full["Strain"].astype(str).str.strip() == "")
    if blank_mask.any():
        print(f"  Dropping {int(blank_mask.sum())} blank/NaN-strain rows "
              f"(years {sorted(full.loc[blank_mask, 'Year'].unique())})")
        full = full[~blank_mask].copy()
    print(f"  Blank-strain filter: {n_before:,} → {len(full):,} rows")
    full = dedup_cells(full)                       # collapse duplicate cells to one obs (RGG-ready)
    # Maturity DOY physical-validity fix: drop the 'D.tom.' pseudo-strain + reconstruct
    # or NULL any Maturity value outside the physical DOY window (offset leaks the
    # DOY conversion missed in 1944/1945/1965-68 + garbled 1982/1986 check cells).
    n_before = len(full)
    full = fix_maturity_doy(full)
    print(f"  Maturity-DOY fix: {n_before:,} → {len(full):,} rows")
    yrs = sorted(full["Year"].unique())
    yfirst, ylast = int(yrs[0]), int(yrs[-1])
    canonical_name = f"nust_{yfirst}_{ylast}_combined.csv"
    full.to_csv(OUT_DIR / canonical_name, index=False)
    # Stable aliases for backward compat with hardcoded names in downstream
    for alias in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
        if alias != canonical_name:
            full.to_csv(OUT_DIR / alias, index=False)
    print(f"\nFull corpus union: {len(full):,} rows across {len(yrs)} years "
          f"({yfirst}-{ylast})")
    print(f"  Canonical: {canonical_name}")
    print(f"  Legacy aliases: nust_1941_2025_combined.csv, nust_1965_2025_combined.csv")
    print("Missing years (within range):",
          sorted(set(range(yfirst, ylast + 1)) - set(yrs)))

    # Era subsets (data-driven names + legacy aliases)
    full_modern = full[full["Year"] >= 1993]
    m_lo, m_hi = _yr_range(full_modern, "modern")
    full_modern.to_csv(OUT_DIR / f"nust_{m_lo}_{m_hi}_combined.csv", index=False)
    full_modern.to_csv(OUT_DIR / "nust_1993_2025_combined.csv", index=False)  # legacy alias

    full_f4u_era = full[full["Year"] <= 1988]
    f_lo, f_hi = _yr_range(full_f4u_era, "F4U-era")
    full_f4u_era.to_csv(OUT_DIR / f"nust_{f_lo}_{f_hi}_combined_f4u.csv", index=False)  # -> nust_1941_1988_combined_f4u.csv

    print("\nVariant breakdown:")
    print(full["Variant"].value_counts())
    print("\nSource breakdown:")
    print(full["Source"].value_counts())
    print("\nPer-decade row counts:")
    full["Decade"] = (full["Year"] // 10) * 10
    print(full.groupby("Decade").size())

    print("\nDone.")


if __name__ == "__main__":
    main()
