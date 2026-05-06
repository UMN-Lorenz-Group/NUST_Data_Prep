"""
compute_maturity_doy.py
=======================
Convert relative maturity day offsets to absolute DOY by anchoring to the
primary check variety's calendar maturity date for each Test × Location.

Strategy:
  1. Auto-detect anchor from CSV: for each test, find the check whose maturity
     values are all DOY-like (>100). Those are the reference checks.
  2. For tests with no CSV anchor (UT-00, UT-I, PT-I, PT-II), upload the source
     PDF and ask Claude for the reference check's absolute maturity dates.
  3. Build anchor table: {(Test, City) -> anchor_DOY}
  4. Compute absolute_DOY = anchor_DOY + relative_offset for every integer-offset row.
  5. Write intermediate verification CSV with original + computed columns.

Usage:
    python compute_maturity_doy.py --pdf input_1980/1980_done.pdf --year 1980
"""

import argparse
import calendar
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import anthropic
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUT_DIR = Path("output_1980")
YEAR = 1980

# Tests whose anchor check was NOT captured as DOY in the XLSX extraction
PDF_NEEDED_TESTS = ["UT-00", "UT-I", "PT-I", "PT-II", "UT-IV"]

# .Env loader (same as other scripts)
def load_env_file(path=".Env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            elif line.startswith("sk-ant-"):
                # bare API key without KEY= prefix
                os.environ.setdefault("ANTHROPIC_API_KEY", line)

load_env_file()

# ---------------------------------------------------------------------------
# PDF-based anchor extraction prompt
# ---------------------------------------------------------------------------
CHECK_MATURITY_PROMPT = """You are reading a 1980 NUST (North American Uniform Soybean Trial) annual report PDF.

I need the ABSOLUTE maturity dates (shown as calendar dates like "9/5", "9/18", "10/1") for the
PRIMARY REFERENCE CHECK variety in EVERY test in this report:
  UT-00, UT-0, UT-I, PT-I, UT-II, PT-II, UT-III, PT-III, UT-IV, PT-IV

Background: In each NUST test table the maturity column shows most strains as ± integer days relative
to one primary reference check. That reference check has its maturity shown as an actual calendar date
(M/D format) rather than as a ± integer. The secondary checks and all experimental strains are relative
to it. For example, if Evans has "9/19" at Rosemount and Hodgson shows "+6", then Hodgson's maturity
at Rosemount = September 25.

For each test, please:
  1. Identify which check variety's dates appear as calendar dates (not ± integers) in the maturity column.
  2. List that variety's maturity date at EVERY test location (city/state) within that test.

Return ONLY valid JSON — no markdown fences, no prose — in this exact schema:
{
  "anchors": [
    {
      "test": "<e.g. UT-00>",
      "reference_check": "<variety name exactly as printed>",
      "locations": [
        {
          "city": "<city name>",
          "state": "<state or province abbreviation>",
          "maturity_date": "<M/D string, e.g. 9/5 or 10/1>"
        }
      ]
    }
  ]
}

Include ALL locations listed for each test. If dates appear in both M/D and ± formats in the same
table, return the M/D format values only. If no absolute date is found for a location, omit it.
Do NOT return ± integer values in maturity_date — only actual M/D calendar dates.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doy(month: int, day: int, year: int = YEAR) -> int:
    return date(year, month, day).timetuple().tm_yday

def _parse_date_str(s: str, year: int = YEAR):
    """Parse 'M/D' or 'M-D' date string to DOY. Returns None on failure."""
    s = str(s).strip()
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})$', s)
    if m:
        return _doy(int(m.group(1)), int(m.group(2)), year)
    return None

def _is_doy(v) -> bool:
    """True if value looks like an absolute DOY (>100)."""
    try:
        return float(str(v)) > 100
    except (ValueError, TypeError):
        return False

def _is_offset(v) -> bool:
    """True if value looks like a relative day offset (-50..50)."""
    s = str(v).strip().rstrip("*").lstrip("+")
    try:
        f = float(s)
        return -60 <= f <= 60
    except (ValueError, TypeError):
        return False

def upload_pdf(client: anthropic.Anthropic, pdf_path: Path) -> str:
    print(f"  Uploading {pdf_path.name} ({pdf_path.stat().st_size // 1024} KB)...")
    with open(pdf_path, "rb") as fh:
        resp = client.beta.files.upload(
            file=(pdf_path.name, fh, "application/pdf"),
        )
    print(f"  file_id: {resp.id}")
    return resp.id

def query_pdf_anchors(client: anthropic.Anthropic, file_id: str, out_dir: Path) -> dict:
    """Ask Claude to extract reference check maturity dates for PDF-needed tests."""
    print("  Querying PDF for reference check maturity dates...")
    resp = client.beta.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "file", "file_id": file_id},
                },
                {"type": "text", "text": CHECK_MATURITY_PROMPT},
            ],
        }],
        betas=["files-api-2025-04-14"],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    print(f"  Response length: {len(raw)} chars, stop_reason: {resp.stop_reason}")
    # Save raw text for debugging
    (out_dir / "check_maturity_raw_response.txt").write_text(raw, encoding="utf-8")
    return json.loads(raw)

# ---------------------------------------------------------------------------
# Step 1: Detect CSV anchors
# ---------------------------------------------------------------------------

def detect_csv_anchors(ph: pd.DataFrame, ck: pd.DataFrame) -> dict:
    """
    For each test, find the check variety whose maturity values are DOY-like.
    Returns {(Test, City): anchor_DOY}.
    """
    mat = ph[ph["Phenotype"] == "Maturity"].copy()
    check_strains = set(ck["Strain"])
    anchors = {}
    missing_tests = []

    for test in mat["Test"].unique():
        tdf = mat[mat["Test"] == test]
        anchor_check = None
        for strain in check_strains:
            sdf = tdf[tdf["Strain"] == strain]
            doy_vals = sdf["Value"].dropna().apply(_is_doy)
            if len(doy_vals) > 0 and doy_vals.sum() / len(doy_vals) > 0.5:
                anchor_check = strain
                break

        if anchor_check:
            print(f"  {test}: anchor = {anchor_check}")
            for _, row in tdf[tdf["Strain"] == anchor_check].iterrows():
                if _is_doy(row["Value"]):
                    anchors[(test, str(row["City"]).strip())] = int(float(str(row["Value"])))
        else:
            print(f"  {test}: no CSV anchor — will use PDF")
            missing_tests.append(test)

    return anchors, missing_tests

# ---------------------------------------------------------------------------
# Step 2: PDF anchor extraction for missing tests
# ---------------------------------------------------------------------------

def _parse_pdf_result(result: dict) -> tuple:
    """Parse anchors dict from Claude's JSON result."""
    anchors = {}
    for entry in result.get("anchors", []):
        test = entry["test"]
        ref = entry.get("reference_check", "?")
        print(f"  PDF anchor: {test} → {ref} ({len(entry.get('locations', []))} locations)")
        for loc in entry.get("locations", []):
            city = str(loc["city"]).strip()
            doy = _parse_date_str(loc.get("maturity_date", ""))
            if doy:
                anchors[(test, city)] = doy
            else:
                print(f"    WARNING: could not parse '{loc.get('maturity_date')}' for {test}/{city}")
    return anchors, result


def extract_pdf_anchors(pdf_path: Path, api_key: str) -> dict:
    """Returns {(Test, City): anchor_DOY} from PDF."""
    client = anthropic.Anthropic(api_key=api_key)
    file_id = upload_pdf(client, pdf_path)
    result = query_pdf_anchors(client, file_id, OUT_DIR)
    return _parse_pdf_result(result)

# ---------------------------------------------------------------------------
# Step 2b: Fill anchor gaps from already-DOY values in the CSV
# ---------------------------------------------------------------------------

def fill_gaps_from_existing_doy(ph: pd.DataFrame, anchors: dict) -> dict:
    """
    For any (Test, City) pair that's still missing an anchor, look for rows in
    the phenotypesTable where a strain already has a DOY-like maturity value at
    that location.  Use the most common DOY value found (handles name variants
    like 'Corsoy 79 (II)*').
    """
    mat = ph[ph["Phenotype"] == "Maturity"]
    filled = dict(anchors)

    # Collect all (test, city) combos that have at least one already-DOY value
    doy_rows = mat[mat["Value"].apply(lambda v: _is_doy(v) if not pd.isna(v) else False)].copy()
    doy_rows["Value"] = doy_rows["Value"].apply(lambda v: int(float(str(v))))

    for (test, city), grp in doy_rows.groupby(["Test","City"]):
        key = (str(test).strip(), str(city).strip())
        if key not in filled:
            # Use the median DOY of whatever anchor-like values exist at this location
            anchor = int(grp["Value"].median())
            filled[key] = anchor

    return filled


# ---------------------------------------------------------------------------
# Step 3: Compute absolute DOY
# ---------------------------------------------------------------------------

def compute_doy(ph: pd.DataFrame, anchors: dict) -> pd.DataFrame:
    """
    For every Maturity row with an integer offset, compute absolute DOY
    using the anchor for that (Test, City).

    For 'Mean' rows (City == 'Mean') compute DOY as the mean of all
    location-specific computed DOY values for that (Test, Strain).

    Returns a verification DataFrame.
    """
    mat = ph[ph["Phenotype"] == "Maturity"].copy()

    # First pass: compute DOY for all non-Mean rows
    rows = []
    for _, row in mat.iterrows():
        v = row["Value"]
        test = str(row["Test"]).strip()
        city = str(row["City"]).strip()
        orig = v

        if pd.isna(v):
            computed = None
            status = "null"
        elif _is_doy(v):
            computed = int(float(str(v)))
            status = "already_doy"
        elif _is_offset(v):
            offset = float(str(v).rstrip("*").lstrip("+"))
            anchor = anchors.get((test, city))
            if anchor is not None:
                computed = int(anchor + offset)
                status = "offset_converted"
            else:
                computed = None
                status = "no_anchor"
        else:
            computed = None
            status = "special"

        rows.append({
            "Strain":            row["Strain"],
            "Year":              row["Year"],
            "Test":              test,
            "City":              city,
            "State":             row.get("State", ""),
            "OriginalMaturity":  orig,
            "ComputedDOY":       computed,
            "Status":            status,
        })

    verif = pd.DataFrame(rows)

    # Second pass: fill 'Mean' rows from average of location-specific DOY
    # Build per-(Test, Strain) mean from non-Mean rows that have a ComputedDOY
    location_means = (
        verif[(verif["City"] != "Mean") & verif["ComputedDOY"].notna()]
        .groupby(["Test","Strain"])["ComputedDOY"]
        .mean()
        .round()
        .astype(int)
    )

    for i, r in verif[verif["City"] == "Mean"].iterrows():
        if pd.isna(r["ComputedDOY"]):
            key = (r["Test"], r["Strain"])
            if key in location_means.index:
                verif.at[i, "ComputedDOY"] = location_means[key]
                verif.at[i, "Status"] = "mean_averaged"

    return verif

# ---------------------------------------------------------------------------
# Leap-year calendar verification
# ---------------------------------------------------------------------------

def verify_leap_calendar(ph: pd.DataFrame, year: int, pdf_json_path) -> str:
    """
    For leap years: determine whether stored maturity DOY values use the
    actual leap-year calendar or the perpetual 365-day calendar.

    Compares each PDF-anchor M/D date against the stored DOY for that
    reference check × city.  Needs the cached PDF JSON produced during
    Step 2; returns 'SKIP' if the file is absent (non-PDF years).

    Returns 'LEAP', 'PERPETUAL', 'AMBIGUOUS', or 'SKIP'.
    """
    if not calendar.isleap(year):
        return None  # nothing to do for non-leap years

    pdf_json_path = Path(pdf_json_path) if pdf_json_path else None
    if pdf_json_path is None or not pdf_json_path.exists():
        print(f"\n[Leap-year check] {year} is a leap year — no PDF JSON cache found.")
        print(f"  Calendar encoding cannot be auto-verified for this year.")
        print(f"  If maturity values were extracted as DOY integers from the XLSX,")
        print(f"  confirm manually that Sep/Oct DOYs match the leap-year calendar.")
        return "SKIP"

    print(f"\n[Leap-year check] {year} is a leap year — verifying DOY calendar encoding...")

    with open(pdf_json_path, encoding="utf-8") as f:
        pdf_data = json.load(f)

    mat = ph[(ph["Phenotype"] == "Maturity") & (ph["City"] != "Mean")].copy()

    leap_exact = 0
    perp_exact = 0
    off_by_more = 0

    for entry in pdf_data.get("anchors", []):
        test = entry["test"]
        ref  = entry.get("reference_check", "").strip()
        for loc in entry.get("locations", []):
            city   = loc["city"].strip()
            md_str = loc.get("maturity_date", "")
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})$', md_str.strip())
            if not m:
                continue
            mo, dy   = int(m.group(1)), int(m.group(2))
            leap_doy = date(year, mo, dy).timetuple().tm_yday
            perp_doy = leap_doy - 1  # perpetual is always 1 less for Mar+ dates

            mask = (
                (mat["Test"] == test) &
                (mat["City"].str.strip() == city) &
                (mat["Strain"].str.strip() == ref)
            )
            stored_rows = mat[mask]["Value"].dropna()
            if len(stored_rows) == 0:
                continue
            try:
                stored = float(str(stored_rows.iloc[0]))
            except Exception:
                continue

            if abs(stored - leap_doy) == 0:
                leap_exact += 1
            elif abs(stored - perp_doy) == 0:
                perp_exact += 1
            else:
                off_by_more += 1

    total = leap_exact + perp_exact + off_by_more
    if total == 0:
        print("  No anchor matches found — cannot determine calendar encoding.")
        return "SKIP"

    print(f"  Anchors checked: {total}  "
          f"(leap-exact: {leap_exact}, perp-exact: {perp_exact}, off: {off_by_more})")

    if leap_exact >= perp_exact * 3:
        verdict = "LEAP"
        print(f"  VERDICT: LEAP calendar confirmed ({leap_exact}/{total} exact matches).")
        print(f"  DOY values are leap-year-correct — no correction needed.")
    elif perp_exact >= leap_exact * 3:
        verdict = "PERPETUAL"
        print(f"  VERDICT: PERPETUAL calendar detected ({perp_exact}/{total} exact matches).")
        print(f"  WARNING: Sep/Oct DOY values are off by -1 for this leap year.")
        print(f"  Re-run with --force-leap-correct to apply +1 to all maturity DOYs.")
    else:
        verdict = "AMBIGUOUS"
        print(f"  VERDICT: AMBIGUOUS (leap={leap_exact}, perp={perp_exact}, off={off_by_more}).")
        print(f"  Manual inspection recommended before applying data.")

    return verdict


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf",  default="input_1980/1980_done.pdf", help="Path to source PDF")
    ap.add_argument("--year", type=int, default=1980)
    ap.add_argument("--csv_dir", default="output_1980")
    ap.add_argument("--no_pdf", action="store_true", help="Skip PDF extraction (CSV anchors only)")
    ap.add_argument("--pdf_json", default=None, help="Load cached PDF raw JSON from previous run")
    ap.add_argument("--force-leap-correct", action="store_true",
                    help="Add +1 to all maturity DOY values (use when source data used perpetual calendar for a leap year)")
    args = ap.parse_args()

    global YEAR, OUT_DIR
    YEAR = args.year
    OUT_DIR = Path(args.csv_dir)
    pdf_path = Path(args.pdf)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.no_pdf:
        print("ERROR: ANTHROPIC_API_KEY not set. Use --no_pdf for CSV-only mode.")
        sys.exit(1)

    print("Loading CSVs...")
    ph = pd.read_csv(OUT_DIR / f"combined_{YEAR}_phenotypesTable.csv")
    ck = pd.read_csv(OUT_DIR / f"combined_{YEAR}_checksTable.csv")

    # Step 1: CSV anchors
    print("\nStep 1: Detecting CSV anchors...")
    csv_anchors, missing_tests = detect_csv_anchors(ph, ck)
    print(f"  CSV anchors found: {len(csv_anchors)} (Test×City pairs)")

    all_anchors = dict(csv_anchors)
    pdf_result_raw = None

    # Step 2: PDF anchors for missing tests
    if args.no_pdf:
        print("\nStep 2: Skipped (--no_pdf)")
    elif args.pdf_json:
        print(f"\nStep 2: Loading cached PDF JSON from {args.pdf_json}...")
        with open(args.pdf_json, encoding="utf-8") as f:
            pdf_result_raw = json.load(f)
        pdf_anchors, _ = _parse_pdf_result(pdf_result_raw)
        all_anchors.update(pdf_anchors)
        print(f"  PDF anchors loaded: {len(pdf_anchors)} (Test×City pairs)")
    elif missing_tests:
        actual_missing = missing_tests
        print(f"\nStep 2: PDF extraction for {actual_missing}...")
        pdf_anchors, pdf_result_raw = extract_pdf_anchors(pdf_path, api_key)
        all_anchors.update(pdf_anchors)
        print(f"  PDF anchors found: {len(pdf_anchors)} (Test×City pairs)")
        raw_out = OUT_DIR / f"check_maturity_pdf_raw_{YEAR}.json"
        with open(raw_out, "w", encoding="utf-8") as f:
            json.dump(pdf_result_raw, f, indent=2)
        print(f"  Raw JSON -> {raw_out}")

    # Step 2c: Fill remaining anchor gaps from existing DOY values in CSV
    print("\nStep 2c: Filling anchor gaps from existing DOY values in CSV...")
    all_anchors = fill_gaps_from_existing_doy(ph, all_anchors)
    print(f"  Total anchors after gap-fill: {len(all_anchors)}")

    # Step 3: Compute DOY
    print("\nStep 3: Computing DOY (including Mean-row averaging)...")
    verif = compute_doy(ph, all_anchors)

    # Summary
    sc = verif["Status"].value_counts()
    print(f"\n  already_doy:      {sc.get('already_doy', 0)}")
    print(f"  offset_converted: {sc.get('offset_converted', 0)}")
    print(f"  mean_averaged:    {sc.get('mean_averaged', 0)}")
    print(f"  no_anchor:        {sc.get('no_anchor', 0)}")
    print(f"  special/null:     {sc.get('special', 0) + sc.get('null', 0)}")

    # Leap-year calendar verification
    pdf_json_cache = (
        Path(args.pdf_json) if args.pdf_json
        else OUT_DIR / f"check_maturity_pdf_raw_{YEAR}.json"
    )
    leap_verdict = verify_leap_calendar(ph, YEAR, pdf_json_cache)

    # Optional +1 correction when perpetual calendar confirmed in source
    if getattr(args, "force_leap_correct", False):
        if not calendar.isleap(YEAR):
            print("\n[--force-leap-correct] Ignored — year is not a leap year.")
        else:
            n_corrected = verif["ComputedDOY"].notna().sum()
            verif.loc[verif["ComputedDOY"].notna(), "ComputedDOY"] += 1
            print(f"\n[--force-leap-correct] Applied +1 to {n_corrected} DOY values.")

    # Write intermediate verification file
    verif_out = OUT_DIR / f"maturity_verification_{YEAR}.csv"
    verif.to_csv(verif_out, index=False)
    print(f"\nIntermediate verification -> {verif_out}")

    # Report no_anchor cases
    no_anch = verif[verif["Status"] == "no_anchor"]
    if len(no_anch) > 0:
        print(f"\nWARNING: {len(no_anch)} rows could not be converted (no anchor for Test×City):")
        print(no_anch.groupby(["Test","City"]).size().to_string())

    # Write anchor table for reference
    anchor_rows = [{"Test": t, "City": c, "AnchorDOY": d} for (t, c), d in sorted(all_anchors.items())]
    pd.DataFrame(anchor_rows).to_csv(OUT_DIR / f"maturity_anchors_{YEAR}.csv", index=False)
    print(f"Anchors table     -> {OUT_DIR}/maturity_anchors_{YEAR}.csv")

    print("\nDone. Review maturity_verification_{}.csv before applying to main table.".format(YEAR))

if __name__ == "__main__":
    main()
