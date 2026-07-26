"""
extract_nust_blocks.py
======================
Extract phenotype data from per-block XLSX files (1987/1988 format).

Each year has ~190-205 small XLSX files, one per PDF table. This script:
  1. Determines test group for each file via page-range lookup (tp4 files define boundaries).
  2. Processes standard files (have Strain column) in Pass 1.
  3. Processes continuation files (no Strain column) in Pass 2, row-aligned to strain lists.
  4. Handles 1988-specific combined files (tp7+8, tp11a+b).

Output:
  output_YYYY/combined_YYYY_phenotypesTable.csv
  output_YYYY/combined_YYYY_strainsTable.csv
  output_YYYY/combined_YYYY_parentageTable.csv  (same data as strainsTable; R bridge expects this)

Usage:
  python -B scripts/extract_nust_blocks.py ^
    --dir "R:\\...\\1987 (Excel-wrg.)\\Sojabone-1987 Excel-wrg (x193)" ^
    --year 1987 ^
    --test_map input_files/input_1987/1987_done_test_map.json ^
    --out_dir output_files/output_1987/
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import os
import re
import csv
from pathlib import Path
from collections import defaultdict

import openpyxl

# ---------------------------------------------------------------------------
# tp prefix → phenotype name
# ---------------------------------------------------------------------------
TP_PHENOTYPE = {
    "tp6":   "YieldBuA",
    "tp7":   "YieldRank",
    "tp8":   "Maturity",
    "tp9":   "Lodging",
    "tp10":  "Height",
    "tp11a": "SeedQuality",
    "tp11b": "SeedSize",
    "tp12a": "Protein",
    "tp12b": "Oil",
}

PHENO_PREFIXES = set(TP_PHENOTYPE.keys())

# Prefixes to skip entirely (disease/descriptive, summary tables)
SKIP_PREFIXES = {"tp3", "tp3a", "tp3b", "tp4", "tp5a", "tp5b"}

# Parentage/strain info prefixes
STRAIN_PREFIXES = {"tp1", "tp2"}

# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
UNITS = {
    "YieldBuA":    "bu/a",
    "YieldRank":   "",
    "Maturity":    "date",
    "Lodging":     "score",
    "Height":      "in.",
    "SeedQuality": "score",
    "SeedSize":    "g/100",
    "Protein":     "%",
    "Oil":         "%",
}

# ---------------------------------------------------------------------------
# Location parsing
# ---------------------------------------------------------------------------
PROVINCE_MAP = {
    "Man.": "MB", "Ont.": "ON", "Que.": "QC", "Sask.": "SK", "Alta.": "AB",
    "B.C.": "BC", "N.B.": "NB", "N.S.": "NS", "P.E.I.": "PE",
    "Man":  "MB", "Ont":  "ON",
}

# Matches "Mean N Tests", "N Mean Tests", "Tests Mean N", etc.
# Any cell with "Mean" + ("Test" OR digit) is a summary column, not a location.
MEAN_RE = re.compile(r"\bMean\b", re.IGNORECASE)


def parse_location(cell) -> tuple:
    """Parse 'City State' header → (city, state). Returns ('', '') on failure."""
    if cell is None:
        return "", ""
    s = str(cell).strip()
    # Remove hyphenated line breaks: "Arling-\nton" → "Arlington"
    s = re.sub(r"-\s*\n\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return "", ""
    parts = s.rsplit(" ", 1)
    if len(parts) == 2:
        city, state = parts[0].strip(), parts[1].strip()
        state = PROVINCE_MAP.get(state, state)
        return city, state
    return s, ""


def is_mean_col(cell) -> bool:
    if cell is None:
        return False
    s = str(cell).strip()
    # Any header containing "Mean" (word boundary) is a summary column, not a city.
    # No valid NUST city/state name contains "Mean".
    return bool(MEAN_RE.search(s))


# ---------------------------------------------------------------------------
# Footer row detection (for standard files that have strain in col 0)
# ---------------------------------------------------------------------------
# All compared case-insensitively via first.lower().startswith(...)
FOOTER_STARTS_LOWER = (
    "c.v.", "l.s.d.",
    "row sp",           # "Row sp. (in.)", "Row Sp. (In.)", "Row sp (in.)"
    "rows/plot", "rows/p",  # "Rows/Plot", "Rows/plot"
    "date ",            # "Date planted", "Date Planted", "Date of planting"
    "days ",            # "Days to mature", "Days to Mature"
    "reps",             # "Reps"
)
# "Mean" footer rows in some tables (row label in col 0)
MEAN_ROW_RE = re.compile(r"^Mean\b", re.IGNORECASE)


def is_footer_row(row) -> bool:
    """Detect footer rows by col 0 content."""
    first = str(row[0]).strip() if row[0] is not None else ""
    first_lower = first.lower()
    if any(first_lower.startswith(f) for f in FOOTER_STARTS_LOWER):
        return True
    if MEAN_ROW_RE.match(first):
        return True
    return False


# ---------------------------------------------------------------------------
# Title row detection (for continuation/combined files)
# A title row has content in col 0 only; all other cells are None.
# ---------------------------------------------------------------------------
def is_title_row(row) -> bool:
    if row[0] is None:
        return False
    return all(c is None for c in row[1:])


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------
# Matches: tp{prefix}_{page}.{version}[+page.version]...[annotation].xlsx
# prefix can contain digits + optional a/b suffix; combined with + for dual files
FILE_RE = re.compile(
    r"^(tp[\d]+[ab]?(?:\+(?:[\d]+[ab]?|[ab]))*)_"  # prefix: tp7+8, tp11a+b, tp7+8+9, etc.
    r"(\d+)"                                          # first page number
    r"\.\d+(?:\+\d+\.\d+)*"                          # .version[+page.version...] multi-page
    r"(?:\s+\([^)]*\))?"                              # optional annotation
    r"\.xlsx$",
    re.IGNORECASE
)

# Plain numbered files in 1987 (duplicates) — skip
NO_PREFIX_RE = re.compile(r"^\d+[\.\d+]*(?:\s*\([^)]*\))?\.xlsx$", re.IGNORECASE)


def parse_filename(name: str):
    """
    Parse filename → (prefix_raw, first_page, is_combined) or None if skip.
    """
    base = os.path.basename(name)

    # Skip plain numbered files (1987 duplicates like 1.1.xlsx, 9.2.xlsx)
    if NO_PREFIX_RE.match(base):
        return None

    m = FILE_RE.match(base)
    if not m:
        return None

    prefix_raw = m.group(1).lower()   # e.g., "tp6", "tp7+8", "tp11a+b"
    first_page = int(m.group(2))
    is_combined = "+" in prefix_raw
    return prefix_raw, first_page, is_combined


def split_combined_prefix(prefix_raw: str) -> list:
    """
    'tp7+8' → ['tp7', 'tp8']
    'tp11a+b' → ['tp11a', 'tp11b']
    """
    parts = prefix_raw.split("+")
    if len(parts) < 2:
        return [prefix_raw]

    p0 = parts[0]  # e.g., 'tp7' or 'tp11a'
    results = [p0]
    # Extract the numeric base: 'tp7' → 'tp7', 'tp11a' → 'tp11'
    base_match = re.match(r"(tp[\d]+)", p0)
    base = base_match.group(1) if base_match else p0

    for rest in parts[1:]:
        # rest is like '8' or 'b'
        if rest[0].isdigit():
            results.append("tp" + rest)       # 'tp7+8' → 'tp8'
        else:
            results.append(base + rest)       # 'tp11a+b' → 'tp11b'
    return results


def get_base_prefix(prefix_raw: str) -> str:
    """Get the first tp prefix from a possibly combined prefix."""
    return split_combined_prefix(prefix_raw)[0]


# ---------------------------------------------------------------------------
# Group assignment via page ranges
# ---------------------------------------------------------------------------

def build_group_map(xlsx_dir: str, groups: list) -> list:
    """
    Scan tp4_*.xlsx files to find their page numbers, sort, and pair with groups.
    Returns sorted [(start_page, group_code), ...].
    """
    tp4_pages = []
    for fname in os.listdir(xlsx_dir):
        # Match tp4_{page}.{version}[...].xlsx
        m = re.match(r"^tp4_([\d]+)\.\d+(?:\s+\([^)]*\))?\.xlsx$", fname, re.IGNORECASE)
        if m:
            tp4_pages.append(int(m.group(1)))

    tp4_pages = sorted(set(tp4_pages))

    if len(tp4_pages) != len(groups):
        print(f"  WARNING: {len(tp4_pages)} tp4 files vs {len(groups)} groups in test map.")
        n = min(len(tp4_pages), len(groups))
        tp4_pages = tp4_pages[:n]
        groups = groups[:n]

    return list(zip(tp4_pages, groups))


def get_group(page: int, group_map: list) -> str:
    """Find the group for a given page number using sorted boundaries."""
    result = None
    for start_page, group_code in group_map:
        if start_page <= page:
            result = group_code
        else:
            break
    return result


# ---------------------------------------------------------------------------
# XLSX reading
# ---------------------------------------------------------------------------

def load_rows(path: str) -> list:
    """Return all rows from active sheet as list of tuples."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    return [tuple(row) for row in ws.iter_rows(values_only=True)]


def is_strain_header(cell) -> bool:
    """True if cell looks like 'Strain' (col 0 of a standard file header)."""
    if cell is None:
        return False
    s = str(cell).strip().lower()
    return s == "strain" or s.startswith("no. of tests strain") or s.startswith("no. strain")


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

def parse_location_header(header_row, has_strain_col: bool) -> list:
    """
    Parse location columns from a header row.
    Returns [(col_index, city, state), ...].
    Skips col 0 if has_strain_col, skips Mean columns.
    """
    locations = []
    start_col = 1 if has_strain_col else 0
    for col_i, cell in enumerate(header_row):
        if col_i < start_col:
            continue
        if cell is None:
            continue
        if is_mean_col(cell):
            continue
        city, state = parse_location(cell)
        if city:
            locations.append((col_i, city, state))
    return locations


def extract_standard_section(rows: list, phenotype: str, group: str, year: int) -> tuple:
    """
    Process a standard file (has Strain column in row 0).
    Returns (records, strain_list).
    strain_list: ordered list of strain names (footers excluded).
    """
    records = []
    strain_list = []
    units = UNITS.get(phenotype, "")

    if not rows:
        return records, strain_list

    header_row = rows[0]
    locations = parse_location_header(header_row, has_strain_col=True)

    if not locations:
        # Could be a file where col 0 is not "Strain" but a combined header
        # Try interpreting entire row as multi-trait — skip for now
        return records, strain_list

    for row in rows[1:]:
        if all(c is None for c in row):
            continue
        if row[0] is None:
            continue
        if is_footer_row(row):
            continue

        strain_name = str(row[0]).strip()
        if not strain_name:
            continue

        strain_list.append(strain_name)

        for col_i, city, state in locations:
            if col_i >= len(row):
                continue
            val = row[col_i]
            if val is None:
                continue
            val_str = str(val).strip()
            if not val_str or val_str.lower() in ("none", "--", "- -"):
                continue
            records.append({
                "Year": year,
                "Test": group,
                "City": city,
                "State": state,
                "Strain": strain_name,
                "Phenotype": phenotype,
                "Value": val_str,
                "Units": units,
            })

    return records, strain_list


def extract_continuation_section(rows: list, phenotype: str, group: str, year: int,
                                  strain_list: list) -> list:
    """
    Process a continuation section (no Strain column).
    row-aligns with strain_list; stops when strain_list exhausted.
    rows: may start with a title row then location header, or just location header.
    """
    records = []
    units = UNITS.get(phenotype, "")

    if not rows or not strain_list:
        return records

    # Find location header row: first row where NOT a title row
    header_idx = 0
    if is_title_row(rows[0]):
        header_idx = 1
        # If row 1 is also None/empty, skip
        if header_idx < len(rows) and all(c is None for c in rows[header_idx]):
            header_idx = 2

    if header_idx >= len(rows):
        return records

    header_row = rows[header_idx]
    locations = parse_location_header(header_row, has_strain_col=False)

    if not locations:
        return records

    # Data rows start after header
    data_rows = rows[header_idx + 1:]

    strain_idx = 0
    for row in data_rows:
        if all(c is None for c in row):
            continue
        if strain_idx >= len(strain_list):
            break  # exhausted strain list; remaining rows are footers

        strain_name = strain_list[strain_idx]
        strain_idx += 1

        for col_i, city, state in locations:
            if col_i >= len(row):
                continue
            val = row[col_i]
            if val is None:
                continue
            val_str = str(val).strip()
            if not val_str or val_str.lower() in ("none", "--", "- -"):
                continue
            records.append({
                "Year": year,
                "Test": group,
                "City": city,
                "State": state,
                "Strain": strain_name,
                "Phenotype": phenotype,
                "Value": val_str,
                "Units": units,
            })

    return records


def find_combined_split(rows: list) -> int:
    """
    Find row index of the SECOND title-like row in a combined file.
    Title rows: only col 0 non-None (all others None) AND match a trait keyword.
    Returns index or -1 if not found.
    """
    TRAIT_TITLE_RE = re.compile(
        r"(MATURITY|SEED\s+SIZE|SEED\s+QUALITY|OIL|PROTEIN|YIELD\s+RANK|LODGING|HEIGHT)",
        re.IGNORECASE
    )
    found_first = False
    for i, row in enumerate(rows):
        if not is_title_row(row):
            continue
        s = str(row[0]).strip()
        if TRAIT_TITLE_RE.search(s):
            if not found_first:
                found_first = True
            else:
                return i
    return -1


# ---------------------------------------------------------------------------
# Parentage extraction
# ---------------------------------------------------------------------------

def extract_parentage(rows: list, group: str, year: int) -> list:
    """Extract (Strain, Parentage) pairs from tp1/tp2 files."""
    records = []
    if not rows:
        return records
    for row in rows[1:]:  # skip header
        if all(c is None for c in row):
            continue
        if row[0] is None:
            continue
        strain = str(row[0]).strip()
        if not strain or is_footer_row(row):
            continue
        parentage = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        records.append({
            "Year": year,
            "Test": group,
            "Strain": strain,
            "Parentage": parentage,
            "Descriptive.Code": "",
            "Check": 0,
        })
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir",      required=True, help="Directory of per-block XLSX files")
    parser.add_argument("--year",     required=True, type=int, help="Year (e.g. 1987)")
    parser.add_argument("--test_map", required=True, help="Path to YYYY_done_test_map.json")
    parser.add_argument("--out_dir",  required=True, help="Output directory")
    args = parser.parse_args()

    xlsx_dir = args.dir
    year = args.year
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load test map
    with open(args.test_map, encoding="utf-8") as f:
        test_map = json.load(f)
    groups = [g["test_code"] for g in test_map["groups"]]
    print(f"Year {year}: {len(groups)} groups: {groups}")

    # Build group page map from tp4 files
    group_map = build_group_map(xlsx_dir, groups)
    print(f"Group boundaries: {group_map}")

    # Enumerate XLSX files
    all_xlsx = sorted(f for f in os.listdir(xlsx_dir) if f.lower().endswith(".xlsx"))
    print(f"Total XLSX files: {len(all_xlsx)}")

    # Categorize files
    standard_pheno   = []   # (fname, prefix_raw, first_page, is_combined, rows)
    continuation     = []   # (fname, prefix_raw, first_page, is_combined, rows)
    parentage_todo   = []   # (fname, first_page)
    skipped          = []

    for fname in all_xlsx:
        parsed = parse_filename(fname)
        if parsed is None:
            skipped.append(fname)
            continue

        prefix_raw, first_page, is_combined = parsed
        base_prefix = get_base_prefix(prefix_raw)

        # Classify by prefix (exact match — avoid "tp12a".startswith("tp1") false positives)
        if base_prefix in SKIP_PREFIXES:
            skipped.append(fname)
            continue

        if base_prefix in STRAIN_PREFIXES:
            parentage_todo.append((fname, first_page))
            continue

        # Check if it's a phenotype prefix (or combined phenotype)
        all_prefixes = split_combined_prefix(prefix_raw) if is_combined else [prefix_raw]
        if not all(p in TP_PHENOTYPE for p in all_prefixes):
            skipped.append(fname)
            continue

        # Load rows to determine standard vs continuation
        path = os.path.join(xlsx_dir, fname)
        try:
            rows = load_rows(path)
        except Exception as e:
            print(f"  ERROR loading {fname}: {e}")
            skipped.append(fname)
            continue

        if not rows:
            skipped.append(fname)
            continue

        first_cell = rows[0][0] if rows[0] else None
        if is_strain_header(first_cell):
            standard_pheno.append((fname, prefix_raw, first_page, is_combined, rows))
        else:
            continuation.append((fname, prefix_raw, first_page, is_combined, rows))

    print(f"  Standard phenotype files : {len(standard_pheno)}")
    print(f"  Continuation files       : {len(continuation)}")
    print(f"  Parentage files          : {len(parentage_todo)}")
    print(f"  Skipped                  : {len(skipped)}")

    # -------------------------------------------------------------------------
    # Pass 1: Standard files (have Strain column)
    # -------------------------------------------------------------------------
    print("\n--- Pass 1: Standard files ---")
    pheno_records = []
    strain_lists  = {}   # group_code → list of strain names

    for fname, prefix_raw, first_page, is_combined, rows in standard_pheno:
        group = get_group(first_page, group_map)
        if group is None:
            print(f"  WARN: no group for page {first_page}: {fname}")
            continue

        if is_combined:
            # Unusual: combined file that starts with Strain col
            # Process only the first section (standard layout)
            prefixes = split_combined_prefix(prefix_raw)
            phenotype = TP_PHENOTYPE.get(prefixes[0])
        else:
            phenotype = TP_PHENOTYPE.get(prefix_raw)

        if phenotype is None:
            continue

        recs, slist = extract_standard_section(rows, phenotype, group, year)
        pheno_records.extend(recs)

        # Store strain list for this group (first file sets it; later files may add new strains
        # if same group has multiple standard files for different traits)
        if group not in strain_lists:
            strain_lists[group] = slist
        elif len(slist) > len(strain_lists[group]):
            # Keep the longer strain list for this group
            strain_lists[group] = slist

        print(f"  {fname} → {group}/{phenotype}: {len(recs)} records, {len(slist)} strains")

    print(f"\nPass 1 total: {len(pheno_records):,} records")
    print(f"Groups with strain lists: {sorted(strain_lists.keys())}")

    # -------------------------------------------------------------------------
    # Pass 2: Continuation files
    # -------------------------------------------------------------------------
    print("\n--- Pass 2: Continuation files ---")
    warn_count = 0

    for fname, prefix_raw, first_page, is_combined, rows in continuation:
        group = get_group(first_page, group_map)
        if group is None:
            print(f"  WARN: no group for page {first_page}: {fname}")
            warn_count += 1
            continue

        strain_list = strain_lists.get(group, [])
        if not strain_list:
            print(f"  WARN: no strain list for {group} (page {first_page}): {fname}")
            warn_count += 1
            continue

        if is_combined:
            prefixes = split_combined_prefix(prefix_raw)
            split_idx = find_combined_split(rows)

            if split_idx < 0:
                # No second section found — process as single continuation
                phenotype = TP_PHENOTYPE.get(prefixes[0])
                if phenotype:
                    recs = extract_continuation_section(rows, phenotype, group, year, strain_list)
                    pheno_records.extend(recs)
                    print(f"  {fname} → {group}/{phenotype}: {len(recs)} records (no split)")
            else:
                # Section 1: rows[0:split_idx]
                sec1 = rows[:split_idx]
                phen1 = TP_PHENOTYPE.get(prefixes[0])
                if phen1 and sec1:
                    recs1 = extract_continuation_section(sec1, phen1, group, year, strain_list)
                    pheno_records.extend(recs1)
                    print(f"  {fname} → {group}/{phen1}: {len(recs1)} records (section 1)")

                # Section 2: rows[split_idx:]
                sec2 = rows[split_idx:]
                phen2 = TP_PHENOTYPE.get(prefixes[1]) if len(prefixes) > 1 else None
                if phen2 and sec2:
                    recs2 = extract_continuation_section(sec2, phen2, group, year, strain_list)
                    pheno_records.extend(recs2)
                    print(f"  {fname} → {group}/{phen2}: {len(recs2)} records (section 2)")
        else:
            phenotype = TP_PHENOTYPE.get(prefix_raw)
            if phenotype is None:
                continue
            recs = extract_continuation_section(rows, phenotype, group, year, strain_list)
            pheno_records.extend(recs)
            print(f"  {fname} → {group}/{phenotype}: {len(recs)} records")

    print(f"\nPass 2 complete. Warnings: {warn_count}")
    print(f"Total phenotype records: {len(pheno_records):,}")

    # -------------------------------------------------------------------------
    # Parentage files
    # -------------------------------------------------------------------------
    print("\n--- Parentage files ---")
    parentage_records = []
    for fname, first_page in parentage_todo:
        group = get_group(first_page, group_map)
        if group is None:
            group = "GlobalParentage"
        path = os.path.join(xlsx_dir, fname)
        try:
            rows = load_rows(path)
        except Exception as e:
            print(f"  ERROR loading {fname}: {e}")
            continue
        recs = extract_parentage(rows, group, year)
        parentage_records.extend(recs)

    print(f"Parentage records: {len(parentage_records):,}")

    # -------------------------------------------------------------------------
    # Write outputs
    # -------------------------------------------------------------------------
    pheno_out    = out_dir / f"combined_{year}_phenotypesTable.csv"
    strain_out   = out_dir / f"combined_{year}_strainsTable.csv"
    parentage_out = out_dir / f"combined_{year}_parentageTable.csv"

    pheno_cols  = ["Year", "Test", "City", "State", "Strain", "Phenotype", "Value", "Units"]
    # Include Descriptive.Code (empty) so R bridge takes the direct-merge path.
    # Check=0 for all historical strains (no formal check identification in PDFs).
    strain_cols = ["Year", "Test", "Strain", "Parentage", "Descriptive.Code", "Check"]

    # Dedup: multi-page files may overlap with single-page files for same locations
    seen = set()
    deduped = []
    dup_count = 0
    for r in pheno_records:
        key = (r["Year"], r["Test"], r["City"], r["State"], r["Strain"], r["Phenotype"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
        else:
            dup_count += 1
    if dup_count:
        print(f"  Deduped {dup_count} duplicate records")
    pheno_records = deduped

    with open(pheno_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=pheno_cols)
        w.writeheader()
        w.writerows(pheno_records)

    with open(strain_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=strain_cols)
        w.writeheader()
        w.writerows(parentage_records)

    # R bridge expects a separate parentageTable file — write same data with same schema
    with open(parentage_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=strain_cols)
        w.writeheader()
        w.writerows(parentage_records)

    print(f"\nOutputs:")
    print(f"  {pheno_out}  ({len(pheno_records):,} rows)")
    print(f"  {strain_out} ({len(parentage_records):,} rows)")
    print(f"  {parentage_out} ({len(parentage_records):,} rows)")

    # Summary
    try:
        import pandas as pd
        if pheno_records:
            df = pd.DataFrame(pheno_records)
            print(f"\nSummary:")
            print(f"  Groups    : {sorted(df['Test'].unique())}")
            print(f"  Phenotypes: {sorted(df['Phenotype'].unique())}")
            print(f"  Strains   : {df['Strain'].nunique():,}")
            print(f"  Cities    : {df['City'].nunique():,}")
            print(f"\nRows per group × phenotype:")
            print(df.groupby(["Test", "Phenotype"]).size().to_string())
    except ImportError:
        pass


if __name__ == "__main__":
    main()
