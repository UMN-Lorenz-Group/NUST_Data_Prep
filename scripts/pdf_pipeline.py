#!/usr/bin/env python
"""
pdf_pipeline.py
===============
Unified PDF extraction pipeline for NUST historical annual reports.

Uploads the source PDF ONCE and runs up to four structured queries against
the same file_id, replacing the previously separate scripts:
  - extract_supplemental_pdf.py  (queries A + B)
  - compute_maturity_doy.py      (query C, PDF part)
  - qc_pdf_vs_csv.py --mode roster  (query D)

Saves a session file (pdf_session_{year}.json) recording the file_id and
completed queries so any downstream step can reuse the upload without
re-paying the upload cost.

Output files written to --csv_dir:
  supplemental_{year}_location_raw.json   raw Claude response — supplemental
  supplemental_{year}_meta_raw.json       raw Claude response — MetaTable
  check_maturity_pdf_raw_{year}.json      raw Claude response — maturity anchors
  roster_qc_{year}.json                   raw Claude response — roster QC
  pdf_session_{year}.json                 session record (file_id + completed queries)
  combined_{year}_locationsTable.csv      updated with Conductor + PlantingDate
  combined_{year}_checksTable.csv         updated with RM (NULL for pre-1990)
  combined_{year}_MetaTable.csv           created / updated

Usage:
    # Full run (all queries)
    python pdf_pipeline.py --pdf input_1980/1980_done.pdf --year 1980 --csv_dir output_1980/

    # Resume from existing session (skip re-upload, re-run only missing queries)
    python pdf_pipeline.py --session output_1980/pdf_session_1980.json --csv_dir output_1980/

    # Specific queries only
    python pdf_pipeline.py --pdf input_1980/1980_done.pdf --year 1980 --csv_dir output_1980/ \\
                           --queries supplemental metatable anchors

    # Roster QC only (needs session for file_id reuse)
    python pdf_pipeline.py --session output_1980/pdf_session_1980.json --queries roster
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import anthropic
import pandas as pd


# ---------------------------------------------------------------------------
# .Env loader
# ---------------------------------------------------------------------------

def _load_env(path=".Env"):
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
                os.environ.setdefault("ANTHROPIC_API_KEY", line)

_load_env()

# ---------------------------------------------------------------------------
# Shared normalisation maps (generalised from fix_supplemental_1980.py)
# ---------------------------------------------------------------------------

PHENOTYPE_MAP = {
    "YIELD (bu/a)": "YieldBuA", "YIELD": "YieldBuA",
    "YIELD RANK":   "YieldRank",
    "LODGING (score)": "Lodging", "LODGING": "Lodging",
    "PLANT HEIGHT (inches)": "Height", "HEIGHT (inches)": "Height", "HEIGHT": "Height",
    "MATURITY (date)": "Maturity", "MATURITY": "Maturity",
    "SEED QUALITY (score)": "SeedQuality", "SEED QUALITY": "SeedQuality",
    "SEED SIZE (g/100)": "SeedSize", "SEED SIZE": "SeedSize",
    "PROTEIN (%)": "Protein", "PROTEIN": "Protein",
    "OIL (%)": "Oil", "OIL": "Oil",
}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SUPPLEMENTAL_PROMPT = """\
You are reading a NUST (North American Uniform Soybean Trial) annual report PDF.

For EACH test group and EACH testing location, extract:
1. Conductor name or institution (often in a footnote, header, or location table).
2. Planting date at that location (if listed).
3. Any RM (relative maturity) values for check strains listed anywhere in the document
   (introduction, appendix, check strain table, or footnotes).

Return ONLY valid JSON (no markdown fences):
{
  "location_supplement": [
    {
      "test": "<test code, e.g. UT-00>",
      "city": "<city name>",
      "state": "<state/province abbreviation>",
      "conductor": "<name or institution, or null>",
      "planting_date": "<M/DD or YYYY-MM-DD string, or null>"
    }
  ],
  "check_rm": [
    {
      "strain": "<check strain name as printed>",
      "rm": "<numeric relative maturity value, e.g. 0.5, or null>"
    }
  ]
}

Include ALL locations across ALL test groups. Return null for any field not found.
"""

METATABLE_PROMPT = """\
You are reading a NUST (North American Uniform Soybean Trial) annual report PDF.

For EACH combination of (Test group, Location, Trait), extract footer statistics
that appear below the data rows in each per-location table. These rows are labelled:
  "No. of Tests" / "No. Tests", "C.V. (%)" / "C.V.", "L.S.D. (5%)" / "LSD",
  "Row sp (in.)" / "Row spacing", "Rows/plot", "Reps"

Return ONLY valid JSON (no markdown fences):
{
  "metatable": [
    {
      "test": "<test code>",
      "trait": "<trait name, e.g. YIELD (bu/a)>",
      "location": "<City_State, e.g. Ottawa_ONT>",
      "no_of_tests": "<value or null>",
      "cv_pct": "<value or null>",
      "lsd_5pct": "<value or null>",
      "row_spacing_in": "<value or null>",
      "rows_per_plot": "<value or null>",
      "reps": "<value or null>"
    }
  ]
}
"""

MATURITY_ANCHORS_PROMPT = """\
You are reading a NUST (North American Uniform Soybean Trial) annual report PDF.

I need the ABSOLUTE maturity dates (calendar dates like "9/5", "9/18", "10/1") for the
PRIMARY REFERENCE CHECK variety in EVERY test in this report.

Background: In each NUST test table the maturity column shows most strains as ± integer days
relative to one primary reference check. That reference check has its maturity shown as a
calendar date (M/D format) rather than a ± integer.

For each test:
1. Identify which check variety shows calendar dates in the maturity column.
2. List that variety's maturity date at EVERY test location.

Return ONLY valid JSON (no markdown fences):
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

Include ALL locations. Return only M/D calendar dates — do NOT return ± integers.
"""

ROSTER_PROMPT_TEMPLATE = """\
You are reading a NUST (North American Uniform Soybean Trial) annual report PDF.

For the test group {test}, list:
1. ALL strain/variety names exactly as printed in the data table (one per line).
2. ALL testing locations (city + state/province) exactly as printed.

Return ONLY valid JSON (no markdown fences):
{{
  "test": "{test}",
  "strains": ["<strain 1>", "<strain 2>", ...],
  "locations": [
    {{"city": "<city>", "state": "<state>"}}
  ]
}}
"""

# ---------------------------------------------------------------------------
# Claude API helpers
# ---------------------------------------------------------------------------

def _upload_pdf(client: anthropic.Anthropic, pdf_path: Path) -> str:
    print(f"  Uploading {pdf_path.name} ({pdf_path.stat().st_size // 1024} KB)...")
    with open(pdf_path, "rb") as fh:
        resp = client.beta.files.upload(file=(pdf_path.name, fh, "application/pdf"))
    print(f"  file_id: {resp.id}")
    return resp.id


def _call_claude(client: anthropic.Anthropic, file_id: str, prompt: str,
                 label: str, max_tokens: int = 16000, max_retries: int = 3) -> str:
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.beta.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": [
                    {"type": "document", "source": {"type": "file", "file_id": file_id}},
                    {"type": "text",     "text": prompt},
                ]}],
                betas=["files-api-2025-04-14"],
            )
            raw = resp.content[0].text.strip()
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            print(f"  [{label}] {len(raw)} chars, stop={resp.stop_reason}")
            return raw
        except anthropic.RateLimitError:
            print(f"  [{label}] Rate limit — sleeping 60s (attempt {attempt})")
            time.sleep(60)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                print(f"  [{label}] Overloaded — sleeping 30s (attempt {attempt})")
                time.sleep(30)
            else:
                raise
    raise RuntimeError(f"[{label}] Failed after {max_retries} attempts")


def _parse_json(raw: str, label: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  WARNING [{label}]: JSON parse error — {e}")
        return {}

# ---------------------------------------------------------------------------
# Post-processing helpers (generalised from fix_supplemental_1980.py)
# ---------------------------------------------------------------------------

def _standardise_date(val, year: int):
    """Convert M/DD or MM/DD to YYYY-MM-DD."""
    if pd.isna(val) or str(val).strip() in ("", "nan", "None"):
        return None
    s = str(val).strip()
    if re.match(r'\d{4}-\d{2}-\d{2}', s):
        return s
    m = re.match(r'^(\d{1,2})/(\d{1,2})$', s)
    if m:
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return s


def _is_real_rm(val) -> bool:
    """True only for genuine numeric RM values (soybeans: typically 0.0–10.0, reported as X.X)."""
    if pd.isna(val):
        return False
    try:
        f = float(val)
        # A bare integer ≤ 5 or a Roman numeral string is an MG designation, not RM
        return f > 5
    except (ValueError, TypeError):
        return False


def _normalise_trait(name: str) -> str:
    s = str(name).strip()
    return PHENOTYPE_MAP.get(s, PHENOTYPE_MAP.get(s.upper(), s))

# ---------------------------------------------------------------------------
# Query A: Supplemental metadata
# ---------------------------------------------------------------------------

def run_supplemental(client, file_id: str, year: int,
                     csv_dir: Path) -> dict:
    print("\n  [Query A] Supplemental metadata (conductor, planting dates, check RM)...")
    raw = _call_claude(client, file_id, SUPPLEMENTAL_PROMPT, "supplemental")

    raw_path = csv_dir / f"supplemental_{year}_location_raw.json"
    raw_path.write_text(raw, encoding="utf-8")
    result = _parse_json(raw, "supplemental")

    loc_entries  = result.get("location_supplement", [])
    check_rm     = result.get("check_rm", [])
    print(f"  Locations found: {len(loc_entries)} | Check RM entries: {len(check_rm)}")

    # ---- Merge into locationsTable ----
    locs_path = csv_dir / f"combined_{year}_locationsTable.csv"
    if locs_path.exists():
        locs = pd.read_csv(locs_path)
        sup  = pd.DataFrame(loc_entries)

        if not sup.empty and "city" in sup.columns:
            sup = sup.rename(columns={"city": "City", "state": "State",
                                      "conductor": "Conductor",
                                      "planting_date": "PlantingDate"})
            for _, srow in sup.iterrows():
                mask = (locs["City"].str.strip() == str(srow["City"]).strip())
                if "test" in srow and pd.notna(srow.get("test")):
                    mask &= (locs["Test"] == srow.get("test", ""))
                if mask.any():
                    if pd.notna(srow.get("Conductor")):
                        locs.loc[mask, "Conductor"]    = srow["Conductor"]
                    if pd.notna(srow.get("PlantingDate")):
                        locs.loc[mask, "PlantingDate"] = _standardise_date(srow["PlantingDate"], year)

        n_pd = locs["PlantingDate"].notna().sum()
        n_c  = locs["Conductor"].notna().sum()
        print(f"  locationsTable: {len(locs)} rows | conductor={n_c}, planting={n_pd}")
        locs.to_csv(locs_path, index=False)

    # ---- Merge RM into checksTable ----
    ck_path = csv_dir / f"combined_{year}_checksTable.csv"
    if ck_path.exists() and check_rm:
        ck     = pd.read_csv(ck_path)
        rm_map = {str(r["strain"]).strip(): r.get("rm") for r in check_rm}
        ck["RM"] = ck["Strain"].apply(
            lambda s: rm_map.get(str(s).strip(), ck.loc[ck["Strain"] == s, "RM"].values[0]
                      if s in ck["Strain"].values else None)
        )
        # Reset any RM that is not a genuine numeric value (pre-1990 reports return MG labels)
        ck["RM"] = ck["RM"].apply(lambda v: v if _is_real_rm(v) else None)
        n_rm = ck["RM"].notna().sum()
        print(f"  checksTable: {len(ck)} rows | RM filled={n_rm}")
        ck.to_csv(ck_path, index=False)

    return result

# ---------------------------------------------------------------------------
# Query B: MetaTable
# ---------------------------------------------------------------------------

def run_metatable(client, file_id: str, year: int,
                  csv_dir: Path) -> dict:
    print("\n  [Query B] MetaTable (CV%, LSD, Reps, Row spacing)...")
    raw = _call_claude(client, file_id, METATABLE_PROMPT, "metatable")

    raw_path = csv_dir / f"supplemental_{year}_meta_raw.json"
    raw_path.write_text(raw, encoding="utf-8")
    result = _parse_json(raw, "metatable")

    entries = result.get("metatable", [])
    print(f"  MetaTable entries: {len(entries)}")
    if not entries:
        return result

    rows = []
    for e in entries:
        trait = _normalise_trait(e.get("trait", ""))
        loc   = str(e.get("location", "")).strip()
        city  = loc.split("_")[0] if "_" in loc else loc
        state = loc.split("_")[1] if "_" in loc else ""
        for meta_type, col in [
            ("C.V. (%)",    "cv_pct"),
            ("L.S.D. (5%)", "lsd_5pct"),
            ("Reps",        "reps"),
            ("Row sp (in.)", "row_spacing_in"),
            ("Rows/plot",   "rows_per_plot"),
            ("No. of Tests","no_of_tests"),
        ]:
            val = e.get(col)
            if val is not None:
                rows.append({
                    "Year-Test":       f"{year}-{e.get('test','')}",
                    "Trait":           trait,
                    "City":            city,
                    "State":           state,
                    "Meta_data_type":  meta_type,
                    "Value":           val,
                })

    meta_path = csv_dir / f"combined_{year}_MetaTable.csv"
    meta_df = pd.DataFrame(rows)
    meta_df.to_csv(meta_path, index=False)
    print(f"  MetaTable: {len(meta_df)} rows -> {meta_path.name}")
    return result

# ---------------------------------------------------------------------------
# Query C: Maturity anchors
# ---------------------------------------------------------------------------

def run_maturity_anchors(client, file_id: str, year: int,
                         csv_dir: Path) -> dict:
    print("\n  [Query C] Maturity reference check anchors...")
    raw = _call_claude(client, file_id, MATURITY_ANCHORS_PROMPT, "maturity_anchors")

    raw_path = csv_dir / f"check_maturity_pdf_raw_{year}.json"
    raw_path.write_text(raw, encoding="utf-8")
    result = _parse_json(raw, "maturity_anchors")

    n_locs = sum(len(e.get("locations", [])) for e in result.get("anchors", []))
    print(f"  Anchor entries: {len(result.get('anchors', []))} tests, {n_locs} locations")
    print(f"  Saved -> {raw_path.name}  (use --pdf_json in combine_nust_outputs.py)")
    return result

# ---------------------------------------------------------------------------
# Query D: Roster QC
# ---------------------------------------------------------------------------

def run_roster_qc(client, file_id: str, year: int,
                  csv_dir: Path, tests: list[str]) -> dict:
    print(f"\n  [Query D] Roster QC for {len(tests)} tests...")
    results = {}

    ph_path = csv_dir / f"combined_{year}_phenotypesTable.csv"
    if not ph_path.exists():
        print(f"  WARNING: {ph_path.name} not found — skipping roster diff")
        return results

    ph = pd.read_csv(ph_path)

    for test in tests:
        prompt = ROSTER_PROMPT_TEMPLATE.format(test=test)
        raw    = _call_claude(client, file_id, prompt, f"roster/{test}", max_tokens=4096)
        data   = _parse_json(raw, f"roster/{test}")
        results[test] = data

        pdf_strains = set(data.get("strains", []))
        pdf_locs    = {(l["city"], l.get("state","")) for l in data.get("locations", [])}

        csv_strains = set(ph[ph["Test"] == test]["Strain"].unique())
        csv_locs    = {
            (r["City"], r.get("State",""))
            for _, r in ph[(ph["Test"] == test) & (ph["City"] != "Mean")][["City","State"]].drop_duplicates().iterrows()
        }

        missing_strains = pdf_strains - csv_strains
        extra_strains   = csv_strains - pdf_strains
        missing_locs    = pdf_locs    - csv_locs
        extra_locs      = csv_locs    - pdf_locs

        ok = not any([missing_strains, extra_strains, missing_locs, extra_locs])
        print(f"  {test}: {'OK' if ok else 'MISMATCH'}"
              f" | strains: PDF={len(pdf_strains)} CSV={len(csv_strains)}"
              f" | locs: PDF={len(pdf_locs)} CSV={len(csv_locs)}")
        if missing_strains:
            print(f"    Missing from CSV: {sorted(missing_strains)[:5]}"
                  f"{'...' if len(missing_strains) > 5 else ''}")
        if extra_strains:
            print(f"    Extra in CSV:     {sorted(extra_strains)[:5]}"
                  f"{'...' if len(extra_strains) > 5 else ''}")
        if missing_locs:
            print(f"    Missing locs:     {sorted(missing_locs)}")
        if extra_locs:
            print(f"    Extra locs:       {sorted(extra_locs)}")

    roster_path = csv_dir / f"roster_qc_{year}.json"
    roster_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"  Roster QC saved -> {roster_path.name}")
    return results

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def _load_session(session_path: Path) -> dict:
    if session_path and session_path.exists():
        with open(session_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_session(session_path: Path, session: dict):
    session_path.write_text(json.dumps(session, indent=2), encoding="utf-8")
    print(f"  Session saved -> {session_path.name}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_QUERIES = ["supplemental", "metatable", "anchors", "roster"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf",      default=None, help="Path to source PDF")
    ap.add_argument("--session",  default=None, help="Path to existing pdf_session JSON (skip re-upload)")
    ap.add_argument("--year",     type=int,     help="Year (required if --pdf used without --session)")
    ap.add_argument("--csv_dir",  required=True, help="Directory containing combined_YEAR_*.csv files")
    ap.add_argument("--queries",  nargs="+", default=ALL_QUERIES,
                    choices=ALL_QUERIES,
                    help="Which queries to run (default: all)")
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    csv_dir = Path(args.csv_dir)

    # ---- Resolve session ----
    session_path = Path(args.session) if args.session else None
    session      = _load_session(session_path) if session_path else {}

    year = args.year or session.get("year")
    if not year:
        print("ERROR: --year required when not using an existing session.")
        sys.exit(1)

    if not session_path:
        session_path = csv_dir / f"pdf_session_{year}.json"

    # ---- Get or create file_id ----
    client  = anthropic.Anthropic(api_key=api_key)
    file_id = session.get("file_id")

    if not file_id:
        if not args.pdf:
            print("ERROR: --pdf required when no existing session has a file_id.")
            sys.exit(1)
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            print(f"ERROR: PDF not found: {pdf_path}")
            sys.exit(1)
        file_id = _upload_pdf(client, pdf_path)
        session.update({
            "file_id":    file_id,
            "year":       year,
            "pdf_path":   str(args.pdf),
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "queries_completed": {},
        })
    else:
        print(f"  Reusing file_id: {file_id}  (uploaded {session.get('uploaded_at','?')})")

    completed = session.setdefault("queries_completed", {})

    # ---- Run requested queries ----
    queries_to_run = [q for q in args.queries if q not in completed]
    already_done   = [q for q in args.queries if q in completed]
    if already_done:
        print(f"  Skipping already-completed queries: {already_done}")

    for query in queries_to_run:
        if query == "supplemental":
            result = run_supplemental(client, file_id, year, csv_dir)
            completed["supplemental"] = str(csv_dir / f"supplemental_{year}_location_raw.json")

        elif query == "metatable":
            result = run_metatable(client, file_id, year, csv_dir)
            completed["metatable"] = str(csv_dir / f"supplemental_{year}_meta_raw.json")

        elif query == "anchors":
            result = run_maturity_anchors(client, file_id, year, csv_dir)
            completed["anchors"] = str(csv_dir / f"check_maturity_pdf_raw_{year}.json")

        elif query == "roster":
            ph_path = csv_dir / f"combined_{year}_phenotypesTable.csv"
            if ph_path.exists():
                tests = sorted(pd.read_csv(ph_path)["Test"].dropna().unique().tolist())
            else:
                tests = []
                print("  WARNING: phenotypesTable not found — roster QC skipped")
            if tests:
                run_roster_qc(client, file_id, year, csv_dir, tests)
                completed["roster"] = str(csv_dir / f"roster_qc_{year}.json")

        _save_session(session_path, session)

    print(f"\nDone. Queries completed: {list(completed.keys())}")
    print(f"Session file: {session_path}")
    if "anchors" in completed:
        print(f"\nNext step — re-run combine with PDF anchors:")
        print(f"  python combine_nust_outputs.py --out_dir {csv_dir}/ --year {year} "
              f"--pdf_json {csv_dir}/check_maturity_pdf_raw_{year}.json")


if __name__ == "__main__":
    main()
