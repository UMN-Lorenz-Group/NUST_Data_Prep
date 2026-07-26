#!/usr/bin/env python
"""
apply_patches_corpus_maturity_doy_via_ocr.py
============================================
Maturity DOY patcher that extracts (Test, City) anchor dates from doc-AI
intermediate xlsx files (no Claude API needed). For problem years where the
Claude PDF anchor query returned poor results, or any year that has doc-AI
intermediates available.

Source-data layout expected (matching 1975_done):
  {source_root}/{YYYY}_done-{timestamp}/{YYYY}_done/{page}.{n}.xlsx
  {source_root}/{YYYY}_done-{timestamp}/{YYYY}_done/{page}.{n}_title.txt
  {source_root}/{YYYY}_done-{timestamp}/{YYYY}_done/{page}_OR.png
  ...etc

OR a `.zip` containing the same structure (auto-extracted to a local temp
folder — `R:` is slow file-by-file so working from a zip is ~13× faster, see
`logs/benchmark_R_vs_C_2026_05_21.md`).

Workflow per year:
  1. Locate source (folder or .zip) for the year.
  2. If .zip, extract to local temp.
  3. Walk per-page xlsx files; find Maturity tables that contain the
     reference strain row (absolute M-D calendar dates per city column).
  4. Build (Test, City) -> DOY anchor dict.
  5. Apply to F4U phenotypesTable1.csv (backup -> _preDOYfix_via_ocr.csv).

Usage:
    # Folder input:
    uv run python fixes/apply_patches_corpus_maturity_doy_via_ocr.py \\
        --year 1975 --source "C:\\Temp\\bench_1975_done"

    # Zip input (auto-extracts):
    uv run python fixes/apply_patches_corpus_maturity_doy_via_ocr.py \\
        --year 1942 --source "R:\\...\\1942_done.zip"

    # Auto-discover all _done-* folders/zips under R: for given years:
    uv run python fixes/apply_patches_corpus_maturity_doy_via_ocr.py \\
        --years 1942,1943,1947,1952,1953 --auto

    # All problem years (Tier 1 + Tier 2 + Tier 3):
    uv run python fixes/apply_patches_corpus_maturity_doy_via_ocr.py --all-problem
"""

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import openpyxl
import pandas as pd

# Reuse from the API-based version
sys.path.insert(0, str(Path(__file__).parent))
from apply_patches_corpus_maturity_doy import (  # type: ignore
    parse_calendar,
    parse_offset,
    is_doy,
    find_f4u,
    canonicalize_city,
    DOY_LO, DOY_HI, OFFSET_LO, OFFSET_HI,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# 100%-still-broken patched years + completely unpatched years from the
# 2026-05-21 partial run (see logs/NUST_corpus_maturity_doy_partial_progress.md)
TIER_1_BROKEN_AFTER_PATCH = [1942, 1943, 1947, 1952, 1953]
TIER_2_UNPATCHED          = [1969, 1970, 1971, 1973, 1974,
                              1976, 1977, 1978,
                              1981, 1982, 1983, 1984, 1985, 1986, 1987, 1988,
                              1990]
TIER_3_PARTIAL_OFFSETS    = [1955, 1956, 1957, 1958, 1959,
                              1960, 1961, 1962, 1963, 1964]
ALL_PROBLEM_YEARS = TIER_1_BROKEN_AFTER_PATCH + TIER_2_UNPATCHED + TIER_3_PARTIAL_OFFSETS

R_ROOT = Path(r"R:\cfans_agro_lore0149_lorenzlabresearch\NUST_Historical_Data_1941_1988")
TEMP_ROOT = Path(r"C:\Users\vramasub\AppData\Local\Temp\ocr_extract")

# Yellow-* zip from Google Drive, extracted locally. Contains
# {decade-bucket}/{YYYY}_done/ subfolders. Added 2026-05-21.
YELLOW_LOCAL = Path(r"C:\Users\vramasub\AppData\Local\Temp\yellow_extract\Yellow")

# ---------------------------------------------------------------------------
# Source location + zip extraction
# ---------------------------------------------------------------------------

def find_source(year: int) -> Path | None:
    """Auto-find {YYYY}_done folder OR {YYYY}_done.zip across known locations.

    Priority:
      1. YELLOW_LOCAL (extracted Yellow-*.zip on C:\\Temp\\)
      2. R: drive folder
      3. R: drive zip
    """
    # Yellow-extract local: walk one level (the Yellow zip has decade buckets)
    if YELLOW_LOCAL.exists():
        for bucket in YELLOW_LOCAL.iterdir():
            if bucket.is_dir():
                cand = bucket / f"{year}_done"
                if cand.is_dir():
                    return cand
        cand = YELLOW_LOCAL / f"{year}_done"
        if cand.is_dir():
            return cand

    # R: extracted folder
    for d in R_ROOT.glob(f"{year}_done-*"):
        inner = d / f"{year}_done"
        if inner.is_dir():
            return inner

    # R: zip
    for z in R_ROOT.glob(f"{year}_done*.zip"):
        return z
    for z in R_ROOT.glob(f"Yellow*.zip"):
        return z
    return None


def get_working_folder(source: Path, year: int) -> Path:
    """If source is a .zip, extract to local temp and return the inner folder.
    If a folder, return as-is."""
    if source.is_dir():
        return source
    if source.is_file() and source.suffix.lower() == ".zip":
        target = TEMP_ROOT / f"{year}_done"
        if target.exists():
            print(f"  [TEMP] removing prior extract at {target}")
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        print(f"  [EXTRACT] {source.name} -> {target}")
        with zipfile.ZipFile(source, "r") as zf:
            zf.extractall(target)
        # Locate the inner folder
        inner = target / f"{year}_done"
        if inner.is_dir():
            return inner
        # Maybe zip is flat
        return target
    raise ValueError(f"Source must be a folder or .zip: {source}")


# ---------------------------------------------------------------------------
# Title parsing
# ---------------------------------------------------------------------------

_TITLE_TEST_RE = re.compile(
    # MG can appear as: 00, 0, I-IV (Roman), OR OCR-corrupted arabic numerals
    # 1/11/111 (=I/II/III), 1V (=IV), TV (=IV), o/O (=0), oo/OO (=00).
    # A/B sub-letter suffix captured separately so we can normalize the MG
    # core then re-append the suffix.
    r"(UNIFORM|PRELIMINARY)\s+TEST\s+"
    r"((?:0{1,2}|1{1,3}V?|[IV]+|TV|oo|OO|[oO]))([AB]?)\b",
    re.IGNORECASE,
)
_UT_PT = {"UNIFORM": "UT", "PRELIMINARY": "PT"}
_MG_NORM = {
    # canonical (Roman)
    "0":"0", "00":"00", "I":"I", "II":"II", "III":"III", "IV":"IV",
    # OCR arabic-numeral confusion → Roman canonical
    "1":"I", "11":"II", "111":"III", "1V":"IV",
    # other OCR typos
    "TV":"IV", "o":"0", "O":"0", "oo":"00", "OO":"00",
}
_TITLE_MULTIYEAR_RE = re.compile(
    r"\b\d+\s*-\s*YEAR\s+MEAN\b|\b(19[6-9]\d)\s*-\s*(19[6-9]\d|7[0-5])\b",
    re.IGNORECASE,
)


def parse_test_from_title(title: str) -> tuple[str | None, bool]:
    """Return (test_code, is_multiyear). e.g. ('UT-III', False)."""
    if not title or "no_title" in title.lower():
        return None, False
    is_multi = bool(_TITLE_MULTIYEAR_RE.search(title))
    m = _TITLE_TEST_RE.search(title)
    if not m:
        return None, is_multi
    kind = _UT_PT[m.group(1).upper()]
    mg_core = m.group(2).upper()
    suffix = (m.group(3) or "").upper()
    mg = _MG_NORM.get(mg_core, mg_core) + suffix
    return f"{kind}-{mg}", is_multi


# ---------------------------------------------------------------------------
# Per-loc Maturity table parsing
# ---------------------------------------------------------------------------

def _norm(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _looks_like_calendar(s: str) -> bool:
    """Return True if string looks like an M-D or M/D calendar date.

    Both separators are common in NUST OCR output: 1968-78 era uses
    hyphen ("9-25"), 1979-80 era uses slash ("9/12"). The downstream
    parse_calendar() already handles both — this detector just needed
    to match.
    """
    if not s:
        return False
    s = s.strip().rstrip("*+")
    return bool(re.match(r"^\d{1,2}[-/]\d{1,2}(?:\.\d+)?$", s))


def _looks_like_offset(s: str) -> bool:
    if not s:
        return False
    s = s.strip().rstrip("*+")
    return bool(re.match(r"^[+\-]?\d{1,3}(?:\.\d+)?$", s))


def extract_city_columns(rows: list[list]) -> dict[int, str]:
    """Return dict {col_index: city_name} from header rows 0-2 of a per-loc
    Maturity table. State names are in row 0; city names in row 1 (sometimes
    spread across row 0-2 due to OCR mangling). Multi-column state spans get
    associated with the city in their column."""
    # Most tables: row 0 has state spans, row 1 has city names per col.
    # Some OCR mangling spreads city across rows 1+2. We just take row 1 as
    # primary, fall back to row 0 if row 1 is blank for a column.
    r0 = [_norm(c) for c in rows[0]] if rows else []
    r1 = [_norm(c) for c in rows[1]] if len(rows) > 1 else []
    r2 = [_norm(c) for c in rows[2]] if len(rows) > 2 else []
    n_cols = max(len(r0), len(r1), len(r2))
    while len(r0) < n_cols: r0.append("")
    while len(r1) < n_cols: r1.append("")
    while len(r2) < n_cols: r2.append("")

    cities = {}
    for ci in range(1, n_cols):
        # Prefer row 1 if it has a non-meta name
        for r in (r1, r2, r0):
            val = r[ci]
            if not val or val.lower() in ("mean", "tests", "no. of tests"):
                continue
            # Skip pure numeric (like "5 Tests")
            if re.match(r"^\d+\s*Tests?", val, re.IGNORECASE):
                continue
            # Skip trait-label fragments
            if any(w in val.lower() for w in ("matur", "yield", "lodg",
                                                "height", "seed", "protein",
                                                "oil")):
                continue
            cities[ci] = val
            break
    return cities


def detect_reference_row(rows: list[list]) -> int | None:
    """Find the row index whose col B+ contains calendar-date values.

    Two patterns in the wild:

    Pattern 1 — 1968-era footer rows (NEW, added 2026-05-21):
      col A says "X matured" (e.g. "Wayne matured", "Clark 63 matured",
      "Clark matured") and col B+ are absolute M-D dates per city. The
      reference strain row itself contains all-zeros (offsets relative
      to self), so the absolute dates live at the table footer.
      Companion rows ("Date planted" + "Days to mature") cross-validate.
      Tried FIRST because it's unambiguous: only ~1 row per table will
      match.

    Pattern 2 — 1972+ strain-row layout (original):
      The reference strain row sits among the strain rows, with col A
      naming the strain (e.g. "Cutler 71") and col B+ holding absolute
      M-D dates. Heuristic: ≥3 columns parse as calendar dates and
      ≤1 parses as a pure offset. Searched in rows[1:20] (widened
      2026-05-21 from rows[3:15]).
    """
    # Pattern 1 — footer "X matured" row. Scan the whole table since
    # it's typically at the bottom (rows 18-22), and there's never
    # ambiguity.
    for i, r in enumerate(rows):
        if not r:
            continue
        a = _norm(r[0] if len(r) > 0 and r[0] is not None else "").lower()
        if "matured" not in a:
            continue
        # Avoid confusing with "Days to mature" (no 'd' at end) or
        # "Date planted" (no 'matur').
        if "days to" in a:
            continue
        cells = [_norm(c) for c in r[1:]]
        n_cal = sum(1 for c in cells if _looks_like_calendar(c))
        if n_cal >= 3:
            return i

    # Pattern 2 — strain row with calendar dates.
    for i, r in enumerate(rows[1:20], start=1):
        if not r:
            continue
        cells = [_norm(c) for c in r[1:]]  # skip col A (strain name)
        n_cal = sum(1 for c in cells if _looks_like_calendar(c))
        n_off = sum(1 for c in cells if _looks_like_offset(c) and not _looks_like_calendar(c))
        if n_cal >= 3 and n_cal > n_off:
            return i
    return None


def has_maturity_label(rows: list[list], title: str = "") -> bool:
    """True if any of the first 5 rows OR the title contains 'maturity'."""
    if title and "matur" in title.lower():
        return True
    for r in rows[:5]:
        for c in r or []:
            if c and "matur" in str(c).lower():
                return True
    return False


def parse_maturity_table(xlsx_path: Path, title: str,
                         year: int | None = None) -> dict[tuple[str, str], int]:
    """Parse one per-loc Maturity xlsx; return (test, city_canonical) -> DOY.

    Returns empty dict if the table isn't a maturity per-loc table or doesn't
    contain a reference row.
    """
    test_code, is_multi = parse_test_from_title(title)
    if not test_code or is_multi:
        return {}

    try:
        wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception:
        return {}

    if not has_maturity_label(rows, title=title):
        return {}

    cities = extract_city_columns(rows)
    ref_row_idx = detect_reference_row(rows)
    if ref_row_idx is None:
        return {}

    anchors = {}
    ref_row = rows[ref_row_idx]
    for col_idx, city in cities.items():
        if col_idx >= len(ref_row):
            continue
        cell = _norm(ref_row[col_idx])
        if not cell:
            continue
        doy = parse_calendar(cell, year)
        if doy is None or not (DOY_LO <= doy <= DOY_HI):
            continue
        anchors[(test_code, canonicalize_city(city))] = doy
    return anchors


def build_anchors_from_folder(folder: Path,
                              year: int | None = None) -> dict[tuple[str, str], int]:
    """Walk a {YYYY}_done folder; return merged anchor dict."""
    anchors: dict[tuple[str, str], int] = {}
    n_tables = 0
    for xp in sorted(folder.glob("*.xlsx")):
        tp = folder / f"{xp.stem}_title.txt"
        title = tp.read_text(encoding="utf-8").strip() if tp.exists() else ""
        a = parse_maturity_table(xp, title, year)
        if a:
            n_tables += 1
            anchors.update(a)
    print(f"  Maturity tables found: {n_tables}, anchors built: {len(anchors)}")
    return anchors


# ---------------------------------------------------------------------------
# F4U patching (mirrors apply_patches_corpus_maturity_doy.py)
# ---------------------------------------------------------------------------

def patch_f4u_with_anchors(year: int, anchor_doy: dict,
                           dry_run: bool = False,
                           backup_suffix: str = "_preDOYfix_via_ocr",
                           test_means: dict[str, int] | None = None) -> dict:
    f4u = find_f4u(year)
    if not f4u:
        return {"year": year, "skipped": "no_f4u"}

    df = pd.read_csv(f4u, dtype=str)
    if "Phenotype" not in df.columns or "Value" not in df.columns:
        return {"year": year, "skipped": "bad_schema"}

    backup = f4u.parent / f"phenotypesTable1{backup_suffix}.csv"
    if not backup.exists() and not dry_run:
        shutil.copy2(f4u, backup)
        print(f"  [BACKUP] -> {backup.name}")

    mat_mask = df["Phenotype"] == "Maturity"
    mat = df[mat_mask].copy()

    test_means = test_means or {}
    stats = {
        "year": year, "total_maturity": len(mat),
        "anchors_used": len(anchor_doy),
        "test_means_used": len(test_means),
        "converted_offset": 0, "converted_offset_via_mean": 0,
        "converted_calendar": 0,
        "offset_no_anchor": 0, "already_doy": 0, "other": 0,
    }

    for idx, row in mat.iterrows():
        v = row["Value"]
        if v is None or pd.isna(v):
            continue
        sv = str(v).strip()
        if is_doy(sv):
            stats["already_doy"] += 1
            continue

        test = row["Test"]
        city_raw = str(row["City"]).strip()
        city_canon = canonicalize_city(city_raw)
        anchor = anchor_doy.get((test, city_canon))
        # If direct lookup misses, try state-suffix and numeric-suffix
        # fallbacks. F4U cities can have any of these stored forms:
        #   "Manhattan" (canon "manhattan")  - clean F4U
        #   "Manhattan KS" (canon "manhattankans") - 4-letter state appended
        #   "Manhattan Kans." (canon "manhattankans") - 4-letter state
        #   "Manhattan2" (canon "manhattan2") - numeric suffix
        # Anchors can be stored in F4U's form OR the parse_compound_city
        # stripped form. Try BOTH directions:
        #   1. Strip from F4U: try anchor with 2/3/4/5-char state stripped,
        #      or trailing digit stripped
        #   2. Append to F4U: try anchor with " ks", " kans", etc. appended
        if anchor is None and len(city_canon) > 2:
            # Try stripping a trailing state suffix (2-5 chars) or digit
            state_suffixes = (
                # 5-char state names
                ["oregon", "kansas", "iowa", "ohio", "texas"]
                # 4-char abbreviations seen in 1953-65 Sojabone
                + ["kans", "nebr", "mich", "minn", "wisc", "mass", "conn",
                    "tenn", "okla", "mont", "ariz", "ark", "colo", "fla"]
                # 3-char (older era)
                + ["del", "ind", "ill", "ohio", "neb", "wis", "kan", "ont",
                    "man", "ore", "ida", "okl", "fla", "ala"]
                # 2-char USPS codes
                + ["al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id",
                    "il","in","ia","ks","ky","la","me","md","ma","mi","mn","ms",
                    "mo","mt","ne","nv","nh","nj","nm","ny","nc","nd","oh","ok",
                    "or","pa","ri","sc","sd","tn","tx","ut","vt","va","wa","wv",
                    "wi","wy","on","mb","qc","sk","ab","bc"]
            )
            # Try longest suffixes first
            for suffix in sorted(set(state_suffixes), key=len, reverse=True):
                if city_canon.endswith(suffix) and len(city_canon) > len(suffix):
                    stem = city_canon[:-len(suffix)]
                    if (test, stem) in anchor_doy:
                        anchor = anchor_doy[(test, stem)]
                        break
            # Also try with trailing digits stripped ("manhattan2" -> "manhattan")
            if anchor is None:
                stripped_digits = re.sub(r"\d+$", "", city_canon)
                if stripped_digits != city_canon and (test, stripped_digits) in anchor_doy:
                    anchor = anchor_doy[(test, stripped_digits)]
        mean_fallback = test_means.get(test)

        cal_doy = parse_calendar(sv, year)
        if cal_doy is not None and DOY_LO <= cal_doy <= DOY_HI:
            df.at[idx, "Value"] = str(cal_doy)
            stats["converted_calendar"] += 1
            continue

        off = parse_offset(sv)
        if off is not None and OFFSET_LO <= off <= OFFSET_HI:
            if anchor is not None:
                df.at[idx, "Value"] = str(int(anchor + off))
                stats["converted_offset"] += 1
            elif mean_fallback is not None:
                # Tier B fallback: use test-mean anchor (±5-10 day approx)
                df.at[idx, "Value"] = str(int(mean_fallback + off))
                stats["converted_offset_via_mean"] += 1
            else:
                stats["offset_no_anchor"] += 1
            continue
        stats["other"] += 1

    print(f"  Stats: {stats}")
    if dry_run:
        return stats
    df.to_csv(f4u, index=False)
    print(f"  [WRITE] {f4u.name} ({len(df):,} rows)")
    return stats


# ---------------------------------------------------------------------------
# Main per-year function
# ---------------------------------------------------------------------------

def load_anchors_from_standardized(year: int,
                                    std_dir: Path) -> tuple[dict[tuple[str, str], int], dict[str, int]]:
    """Read anchors from a Sojabone-{year}_yellow_standardized.xlsx file.

    Returns (anchors, test_means):
      anchors      = {(test_code, city_canon): DOY}  — Tier A direct matches
      test_means   = {test_code: DOY}                — Tier B fallback
    """
    std_path = std_dir / f"Sojabone-{year}_yellow_standardized.xlsx"
    if not std_path.exists():
        return {}, {}
    try:
        df = pd.read_excel(std_path, sheet_name="anchors")
    except Exception as e:
        print(f"  [WARN] standardized xlsx unreadable: {e}")
        return {}, {}
    if df.empty or "AnchorDOY" not in df.columns:
        return {}, {}
    anchors: dict[tuple[str, str], int] = {}
    test_means: dict[str, int] = {}
    for _, row in df.iterrows():
        if pd.isna(row["AnchorDOY"]):
            continue
        test = str(row["Test"]).strip()
        # Re-canonicalize the stored City_canon so any newly-added
        # _CITY_ALIASES (e.g., "manhattankans" -> "manhattan",
        # "lincolnnebr" -> "lincoln") are applied even for anchors
        # written by older extractor runs.
        city = canonicalize_city(str(row["City_canon"]).strip())
        doy = int(row["AnchorDOY"])
        tier = str(row.get("Tier", "A")).strip()
        # Test-code aliases:
        # 1. UT-0 <-> UT-O (1981-86 F4U typo, letter O for digit zero;
        #    same for UT-00 / UT-OO).
        # 2. PT-X <-> UPT-X (1988 F4U stores Uniform Preliminary Test as
        #    "UPT-IIA"/"UPT-IIIB"/etc.; my Sojabone extractor and the
        #    combined extractor both normalize to PT-X).
        test_variants = {test}
        if "-0" in test:
            test_variants.add(test.replace("-0", "-O", 1))
            if "-00" in test:
                test_variants.add(test.replace("-00", "-OO", 1))
        elif "-O" in test:
            test_variants.add(test.replace("-O", "-0", 1))
            if "-OO" in test:
                test_variants.add(test.replace("-OO", "-00", 1))
        # UPT <-> PT alias (do this AFTER -0/-O so we get both
        # PT-IIA and UPT-IIA, etc.)
        for tv in list(test_variants):
            if tv.startswith("PT-"):
                test_variants.add("U" + tv)
            elif tv.startswith("UPT-"):
                test_variants.add(tv[1:])
        for t in test_variants:
            if tier == "B" or city == "_test_mean_":
                test_means[t] = doy
            else:
                anchors[(t, city)] = doy
    return anchors, test_means


def patch_one_year(year: int, source: Path | None = None,
                   dry_run: bool = False,
                   from_standardized: Path | None = None) -> dict:
    print(f"\n=== {year} ===")

    test_means: dict[str, int] = {}
    if from_standardized is not None:
        print(f"  Anchor source: standardized xlsx at {from_standardized}")
        anchors, test_means = load_anchors_from_standardized(year, from_standardized)
        if not anchors and not test_means:
            print(f"  [SKIP] no anchors found in standardized xlsx for {year}")
            return {"year": year, "skipped": "no_anchors_in_std"}
        print(f"  Loaded {len(anchors)} Tier-A + {len(test_means)} Tier-B "
              f"(test-mean) anchors from standardized xlsx")
    else:
        if source is None:
            source = find_source(year)
            if source:
                print(f"  Auto-found source: {source}")
        if source is None:
            print(f"  [SKIP] no source for {year}")
            return {"year": year, "skipped": "no_source"}
        folder = get_working_folder(source, year)
        print(f"  Working folder: {folder}")
        anchors = build_anchors_from_folder(folder, year)
        if not anchors:
            print(f"  [SKIP] no Maturity anchors extracted from OCR")
            return {"year": year, "skipped": "no_anchors"}

    return patch_f4u_with_anchors(year, anchors, dry_run=dry_run,
                                    test_means=test_means)


def main():
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--year",  type=int, help="Single year")
    grp.add_argument("--years", type=str, help="Comma-separated years")
    grp.add_argument("--all-problem", action="store_true",
                     help=f"All problem years (T1+T2+T3 = {len(ALL_PROBLEM_YEARS)})")
    ap.add_argument("--source", type=str, default=None,
                    help="Explicit folder or .zip path (overrides auto-discovery)")
    ap.add_argument("--auto", action="store_true",
                    help="Auto-discover sources on R: for --years list")
    ap.add_argument("--from-standardized", type=str, default=None,
                    help="Read anchors from Sojabone-{year}_yellow_standardized.xlsx "
                         "in this directory instead of re-extracting from raw xlsx. "
                         "Typical value: analysis/data/yellow_standardized/")
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args()

    if args.year:
        years = [args.year]
    elif args.years:
        years = [int(y) for y in args.years.split(",")]
    else:
        years = ALL_PROBLEM_YEARS

    source = Path(args.source) if args.source else None
    if source and len(years) > 1:
        sys.exit("ERROR: --source only valid with a single --year")

    from_std = Path(args.from_standardized) if args.from_standardized else None

    all_stats = []
    for y in years:
        try:
            stats = patch_one_year(y, source=source, dry_run=args.dry_run,
                                   from_standardized=from_std)
            all_stats.append(stats)
        except Exception as e:
            import traceback
            traceback.print_exc()
            all_stats.append({"year": y, "error": str(e)})

    # Summary
    print("\n=== Summary ===")
    print(f"{'Year':>5} | {'total':>6} | {'off->DOY':>9} | {'off->mean':>9} | "
          f"{'cal->DOY':>9} | {'no_anchor':>9} | {'already':>8} | {'other':>6}")
    for s in all_stats:
        if "skipped" in s:
            print(f"{s['year']:>5} | SKIPPED ({s['skipped']})")
            continue
        if "error" in s:
            print(f"{s['year']:>5} | ERROR ({s['error'][:50]})")
            continue
        print(f"{s['year']:>5} | {s.get('total_maturity',0):>6} | "
              f"{s.get('converted_offset',0):>9} | "
              f"{s.get('converted_offset_via_mean',0):>9} | "
              f"{s.get('converted_calendar',0):>9} | "
              f"{s.get('offset_no_anchor',0):>9} | {s.get('already_doy',0):>8} | "
              f"{s.get('other',0):>6}")


if __name__ == "__main__":
    main()
