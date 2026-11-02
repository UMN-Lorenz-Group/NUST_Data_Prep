#!/usr/bin/env python
"""
apply_patches_corpus_maturity_doy.py
====================================
Apply Maturity DOY conversion to Files4Upload phenotypesTable1.csv files
for the ~46 historical years where Maturity is stored as raw relative-to-
check offsets instead of absolute DOY.

Workflow per year:
  1. Locate PDF on R: drive (or skip year if missing).
  2. Load cached anchor JSON if present; else query PDF via Claude API
     (`scripts.combine_nust_outputs._query_pdf_for_anchors`) and cache.
  3. Load F4U phenotypesTable1.csv for the year, back up to
     phenotypesTable1_preDOYfix.csv.
  4. For each Maturity row whose Value is an offset (-50..+50), look up
     (Test, City) anchor and compute absolute_DOY = anchor_doy + offset.
     For rows whose Value is already a DOY (200..330), leave alone.
     For rows whose Value is a calendar date M-D (the reference rows),
     convert directly to DOY.
  5. Write updated F4U.

After running for all years, re-run analysis/10_assemble_corpus.py to
pick up the patched F4Us.

Usage:
    # Single-year pilot:
    uv run python fixes/apply_patches_corpus_maturity_doy.py --year 1972

    # All affected years (~$30-60 API spend):
    uv run python fixes/apply_patches_corpus_maturity_doy.py --all

    # Dry-run (locate PDFs + load anchors, but don't write F4U):
    uv run python fixes/apply_patches_corpus_maturity_doy.py --year 1972 --dry_run
"""

import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add scripts/ to path so we can reuse anchor extraction
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import pandas as pd

# Reuse the existing PDF anchor extraction logic
from combine_nust_outputs import (  # type: ignore
    _query_pdf_for_anchors,
    _load_pdf_anchors,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Years with 100% or near-100% Maturity offsets (from feasibility check)
BROKEN_YEARS = [
    1941, 1942, 1943, 1944, 1945, 1946, 1947, 1948, 1949,
    1950, 1951, 1952, 1953, 1954, 1955, 1956, 1957, 1958, 1959,
    1960, 1961, 1962, 1963, 1964, 1965, 1966, 1967, 1968, 1969,
    1970, 1971, 1972, 1973, 1974,
    1976, 1977, 1978,
    1981, 1982, 1983, 1984, 1985, 1986, 1987, 1988,
    1990,
]

RED_ROOT = Path(r"R:\cfans_agro_lore0149_lorenzlabresearch\NUST_Historical_Data_1941_1988")
NUST_DATA = Path(r"C:\Users\vramasub\Desktop\UMN_Projects\NUST_Projects\NUST_Data")
HIST_DATA = NUST_DATA / "NUST_Historical_Data_1941_1988"
REPO = Path(r"C:\Users\vramasub\Desktop\UMN_GIT\NUST_Data_Prep")

OFFSET_LO, OFFSET_HI = -50, 50
DOY_LO, DOY_HI       = 200, 330

# Days-before-month accumulator, NON-LEAP. Only used when the caller cannot supply a year.
_DBM = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def _to_doy(mo: int, dy: int, year: int | None) -> int | None:
    """Month/day -> DOY, leap-correct whenever `year` is known.

    History: this used to convert via the hardcoded non-leap `_DBM` table unconditionally,
    which made every date from Mar 1 onward exactly 1 day early in a leap year. The damage
    was real but uneven -- it landed per (year x test x MG) table depending on which code
    path built that table -- e.g. 1952 UT (all MGs), 1956 UT-0 and all 1956 PT, 1960/1964 PT,
    and most of 1988. See maturity_anchor_leak_findings.md.

    Always pass `year`. The `_DBM` fallback is kept only so the legacy callers that have no
    year in scope keep working; it is wrong by 1 day in a leap year, by construction.
    """
    if not (1 <= mo <= 12 and 1 <= dy <= 31):
        return None
    if year is None:
        return _DBM[mo - 1] + dy
    try:
        return datetime.date(int(year), mo, dy).timetuple().tm_yday
    except ValueError:
        return None


def parse_calendar(s: str, year: int | None = None) -> int | None:
    """Parse an 'M-D' / 'M/D' reference date to DOY. Pass `year` for leap-correct output."""
    s = str(s).strip().rstrip("*+ ")
    # Short M-D or M/D form (1972 era PDF reference dates)
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})(?:\.\d+)?$", s)
    if m:
        return _to_doy(int(m.group(1)), int(m.group(2)), year)
    # Pandas-mangled datetime form "2026-09-18 00:00:00" (R bridge auto-converted
    # an ambiguous "9-18" reference date string into a datetime; the YYYY is junk
    # but the month/day is what we want)
    m = re.match(r"^\d{4}-(\d{1,2})-(\d{1,2})(?:\s|T|$)", s)
    if m:
        return _to_doy(int(m.group(1)), int(m.group(2)), year)
    return None


def parse_offset(s: str) -> int | None:
    s = str(s).strip().rstrip("*+ ")
    m = re.match(r"^([+\-]?\d+)$", s)
    return int(m.group(1)) if m else None


def is_doy(v) -> bool:
    try:
        f = float(str(v).strip().rstrip("*+"))
        return DOY_LO <= f <= DOY_HI and f.is_integer()
    except (ValueError, TypeError):
        return False


def find_pdf(year: int) -> Path | None:
    """Find source PDF for a year on R: drive."""
    for red_dir in RED_ROOT.glob("Red-*/Red"):
        for stem in (f"{year}_done.pdf", f"{year}.pdf"):
            p = red_dir / stem
            if p.exists():
                return p
    # also check staged input dirs
    for stem in (f"input_files/input_{year}/{year}.pdf",
                  f"input_files/input_{year}/{year}_compressed.pdf"):
        p = REPO / stem
        if p.exists():
            return p
    return None


def find_f4u(year: int) -> Path | None:
    """Find F4U phenotypesTable1.csv for a year."""
    candidates = [
        HIST_DATA / f"{year}_Processing" / "Files4Upload" / "phenotypesTable1.csv",
        NUST_DATA / f"{year}_Processing" / "Files4Upload" / "phenotypesTable1.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def f4u_strain_norm(s: str) -> str:
    """F4U normalization — used to match strain names between sides."""
    s = str(s).strip()
    s = re.sub(r"\s*\(\s*(0{1,2}|[IV]{1,3})\s*\)\s*$", "", s, flags=re.IGNORECASE)
    s = s.replace(" ", "").rstrip("*")
    return s


# Reconcile city names between F4U and PDF anchor JSON. F4U applies its own
# normalization (no spaces, abbreviated periods); PDF anchors carry the raw
# OCR forms. Map both sides through canonicalize_city() before matching.
_CITY_ALIASES = {
    # PDF anchor form -> canonical (lowercase, no punctuation/spaces, no
    # sub-location suffix)
    "westlafayette":   "lafayette",     # F4U "West Lafayette" vs PDF "Lafayette"
    "elansing":        "eastlansing",
    "univpark":        "universitypark",
    # 1943-era OCR errors (user-flagged): m/n and W/V/M/H substitutions
    "colunbia":        "columbia",      # "Colunbia Mo." for Columbia
    "colunbus":        "columbus",      # same m/n confusion
    "hanhattan":       "manhattan",     # "Hanhattan Kan." for Manhattan
    "hadison":         "madison",       # M -> H OCR error
    "nandarin":        "mandarin",      # M -> N
    "harshalltown":    "marshalltown",
    # 1963-era OCR errors (consolidated-gap-table catches)
    "indedence":       "independence",  # F4U "Indedence" — missing 'pen'
    "kanapenwha":      "kanawha",       # F4U "Kanapenwha" — extra 'pen'
    # 1944/52 — OCR variants
    "lafayctte":       "lafayette",     # f and y next to each other lost
    # 1961 numeric-suffix OCR
    "manhattan2":      "manhattan",
    "lincolnnebr1":    "lincolnnebr",
    "lincolnnebr2":    "lincolnnebr",
    "evansvilleind2":  "evansvilleind",
    "e1dorado":        "eldorado",      # OCR 1 for l
    "e1ora":           "elora",         # 1970 R547 "E1ora" OCR 1 for l in Elora
    # 1958 Lafayette multi-planting trials: F4U drops "Indiana" from
    # the Sojabone form "Lafayette Indiana Planted X". Map F4U variants
    # to the Sojabone canonical so the patcher finds the anchor.
    "lafayetteinplanted":     "lafayetteindianaplanted514",  # UT-II default = early planting (5-14)
    "lafayetteplanted514":    "lafayetteindianaplanted514",  # UT-III early planting
    "lafayetteplanted71":     "lafayetteindianaplanted71",   # UT-III late planting
    # 1952 UT-IV Georgetown: OCR "Dul." for "Del." in some rows
    "georgetowndul":          "georgetown",
    # 1969 R126 OCR reordered "North Dakota Fargo" to "North Fargo Dakota"
    # parse_compound_city strips trailing " Dakota" -> "North Fargo" -> canon
    # = "northfargo" (NOT northfargodakota). Alias both forms defensively.
    "northfargodakota":       "fargo",
    "northfargo":             "fargo",
    "eldorado111":     "eldorado",      # "Eldorado Ill." with 1→1 OCR
    "urbanai11":       "urbana",        # "Urbana Ill." with 1→1 OCR
    "manhattankans":   "manhattan",     # convenience alias
    "lincolnnebr":     "lincoln",       # convenience alias
    "newarkdel":       "newark",
    "georgetowndel":   "georgetown",
    "corvallisoregon": "corvallis",
    "corvallisoreg":   "corvallis",
}

def canonicalize_city(s: str) -> str:
    """Normalize city name for cross-source matching. Strips spaces, periods,
    trailing sub-location markers like ' I' / ' B' / ' W'."""
    s = str(s).strip()
    # Strip trailing single-letter sub-location markers (I = irrigated, B/W = block)
    s = re.sub(r"\s+[IBW]$", "", s)
    s = re.sub(r"[\.\s\-]", "", s).lower()
    return _CITY_ALIASES.get(s, s)


def get_or_extract_anchors(year: int, pdf_path: Path, cache_dir: Path) -> dict:
    """Return anchor dict for the year, querying PDF + caching if needed."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"check_maturity_pdf_raw_{year}.json"

    if cache_path.exists():
        print(f"  [CACHE] using {cache_path.name}")
        raw = cache_path.read_text(encoding="utf-8")
        try:
            return _load_pdf_anchors(json.loads(raw), year)
        except Exception as e:
            print(f"  [WARN] cache unreadable: {e}; re-querying")

    print(f"  [API ] querying PDF for anchors: {pdf_path.name}")
    anchors = _query_pdf_for_anchors(pdf_path, year, cache_dir)
    # _query_pdf_for_anchors already wrote check_maturity_pdf_raw_{year}.json
    return anchors


def patch_f4u_year(year: int, dry_run: bool = False) -> dict:
    """Apply Maturity DOY conversion to one year's F4U file.

    Returns stats dict: {converted, offset_no_anchor, calendar_converted,
                          already_doy, other, total_maturity, anchors_used}.
    """
    print(f"\n=== {year} ===", flush=True)

    pdf = find_pdf(year)
    f4u = find_f4u(year)
    print(f"  PDF: {pdf}")
    print(f"  F4U: {f4u}")
    if not pdf:
        print(f"  [SKIP] no PDF for {year}")
        return {"year": year, "skipped": "no_pdf"}
    if not f4u:
        print(f"  [SKIP] no F4U for {year}")
        return {"year": year, "skipped": "no_f4u"}

    # Cache anchors next to F4U so re-runs are free
    cache_dir = f4u.parent.parent / "MaturityAnchors"
    anchors = get_or_extract_anchors(year, pdf, cache_dir)
    print(f"  Anchors: {len(anchors)} (Test, City) -> DOY")

    if not anchors:
        print(f"  [SKIP] no anchors extracted for {year}")
        return {"year": year, "skipped": "no_anchors"}

    # Build per-(Test, canonicalized_city) anchor lookup
    anchor_doy = {}
    for (t, c), rec in anchors.items():
        if rec.get("doy") is None:
            continue
        anchor_doy[(t, canonicalize_city(c))] = rec["doy"]

    # Load F4U
    df = pd.read_csv(f4u, dtype=str)
    if "Phenotype" not in df.columns or "Value" not in df.columns:
        print(f"  [SKIP] F4U columns missing Phenotype/Value")
        return {"year": year, "skipped": "bad_schema"}

    # Backup original
    backup = f4u.parent / f"phenotypesTable1_preDOYfix.csv"
    if not backup.exists() and not dry_run:
        shutil.copy2(f4u, backup)
        print(f"  [BACKUP] -> {backup.name}")

    mat_mask = df["Phenotype"] == "Maturity"
    mat = df[mat_mask].copy()
    print(f"  Maturity rows in F4U: {len(mat)}")

    stats = {
        "year": year,
        "total_maturity": len(mat),
        "anchors_used": len(anchor_doy),
        "converted_offset":   0,
        "converted_calendar": 0,
        "offset_no_anchor":   0,
        "already_doy":        0,
        "other":              0,
    }

    # Apply conversion
    for idx, row in mat.iterrows():
        v = row["Value"]
        if v is None or pd.isna(v):
            continue
        sv = str(v).strip()
        if is_doy(sv):
            stats["already_doy"] += 1
            continue

        test = row["Test"]
        city_canon = canonicalize_city(row["City"])
        anchor = anchor_doy.get((test, city_canon))

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
            else:
                stats["offset_no_anchor"] += 1
            continue

        stats["other"] += 1

    print(f"  Conversion stats: {stats}")

    if dry_run:
        print(f"  [DRY-RUN] not writing")
        return stats

    df.to_csv(f4u, index=False)
    print(f"  [WRITE] {f4u.name} ({len(df):,} rows)")
    return stats


def main():
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--year", type=int, help="Single year to patch")
    grp.add_argument("--all",  action="store_true", help="Patch all BROKEN_YEARS")
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args()

    if args.year:
        years = [args.year]
    else:
        years = BROKEN_YEARS

    all_stats = []
    for y in years:
        try:
            stats = patch_f4u_year(y, dry_run=args.dry_run)
            all_stats.append(stats)
        except Exception as e:
            print(f"  [ERROR] {y}: {e}")
            import traceback
            traceback.print_exc()
            all_stats.append({"year": y, "error": str(e)})

    # Summary
    print("\n=== Summary ===")
    print(f"{'Year':>5} | {'total':>6} | {'off->DOY':>9} | {'cal->DOY':>9} | "
          f"{'no_anchor':>9} | {'already':>8} | {'other':>6}")
    for s in all_stats:
        if "skipped" in s:
            print(f"{s['year']:>5} | SKIPPED ({s['skipped']})")
            continue
        if "error" in s:
            print(f"{s['year']:>5} | ERROR ({s['error'][:50]})")
            continue
        print(f"{s['year']:>5} | {s['total_maturity']:>6} | "
              f"{s['converted_offset']:>9} | {s['converted_calendar']:>9} | "
              f"{s['offset_no_anchor']:>9} | {s['already_doy']:>8} | "
              f"{s['other']:>6}")


if __name__ == "__main__":
    main()
