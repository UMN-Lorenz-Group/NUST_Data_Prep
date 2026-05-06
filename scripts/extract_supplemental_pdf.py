#!/usr/bin/env python
"""
extract_supplemental_pdf.py
===========================
Extract supplemental metadata from NUST source PDF that is not available
in the XLSX files:

  1. Location supplement — Conductor, PlantingDate, MaturityDate per location/test
  2. MetaTable          — C.V.(%), L.S.D.(5%), No.of Tests, Reps per location/trait/test
  3. Checks supplement  — RM (relative maturity) values for check strains

Merges results into existing combined output CSVs.

Usage:
    python extract_supplemental_pdf.py --year 1980 --csv_dir ./output_1980/ --out_dir ./output_1980/
    python extract_supplemental_pdf.py --pdf "R:/.../1980_done.pdf" --csv_dir ./output_1980/ --out_dir ./output_1980/
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import anthropic
import pandas as pd

RED_ROOT = Path("R:/NUST_Historical_Data")

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

LOCATION_PROMPT = """You are reading a NUST (North American Uniform Soybean Trial) annual report PDF.

Extract the following for EACH test group and EACH testing location:
1. Conductor name or institution responsible for that test site (often listed as a footnote, header, or location table)
2. Planting date at that location (if listed)
3. Harvest or maturity date at that location (if listed)

Also extract RM (relative maturity) values for any check strains if listed anywhere in the document
(introduction, appendix, check strain table, or footnotes).

Return ONLY valid JSON (no markdown fences):
{
  "location_supplement": [
    {
      "test": "<test code, e.g. UT-00>",
      "city": "<city name>",
      "state": "<state/province abbreviation>",
      "conductor": "<name or institution, or null>",
      "planting_date": "<date string or null>",
      "maturity_date": "<date string or null>"
    }
  ],
  "check_rm": [
    {
      "strain": "<check strain name as it appears in the report>",
      "rm": "<relative maturity value, e.g. 0.5, or null if not listed>"
    }
  ]
}

Include ALL locations across ALL test groups.
If conductor/dates are not found in the document, return null for those fields — do not guess.
"""

METATABLE_PROMPT = """You are reading a NUST (North American Uniform Soybean Trial) annual report PDF.

For EACH combination of (Test group, Location, Trait), extract the footer statistics
that appear below the data rows in each per-location table. These are rows labelled:
  - "No. of Tests" or "No. Tests"
  - "C.V. (%)" or "C.V."
  - "L.S.D. (5%)" or "LSD"
  - "Row sp (in.)" or "Row spacing"
  - "Rows/plot"
  - "Reps"

Each per-location table has these footers as rows where column A has the label and
columns B onward have the per-location values.

Return ONLY valid JSON (no markdown fences):
{
  "metatable": [
    {
      "test": "<test code, e.g. UT-00>",
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

Include ALL tests, ALL traits, ALL locations.
Use null for any footer value that is blank or not present.
Location keys use City_State format: "Ottawa_ONT", "Morris_MN", "Morden_MAN".
"""

PHENOTYPE_MAP = {
    "YIELD (bu/a)": "YieldBuA", "YIELD": "YieldBuA",
    "YIELD RANK": "YieldRank",
    "LODGING (score)": "Lodging", "LODGING": "Lodging",
    "PLANT HEIGHT (inches)": "Height", "HEIGHT": "Height",
    "MATURITY (date)": "Maturity", "MATURITY": "Maturity",
    "SEED QUALITY (score)": "SeedQuality", "SEED QUALITY": "SeedQuality",
    "SEED SIZE (g/100)": "SeedSize", "SEED SIZE": "SeedSize",
    "PROTEIN (%)": "Protein", "PROTEIN": "Protein",
    "OIL (%)": "Oil", "OIL": "Oil",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_env_file() -> str | None:
    env_path = Path(__file__).parent / ".Env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
        if line.startswith("sk-ant-"):
            return line
    return None


def resolve_pdf(year: str) -> Path | None:
    for red_dir in RED_ROOT.glob("Red-*/Red"):
        candidate = red_dir / f"{year}_done.pdf"
        if candidate.exists():
            return candidate
    return None


def upload_pdf(client: anthropic.Anthropic, pdf_path: Path) -> str:
    print(f"  Uploading {pdf_path.name} ({pdf_path.stat().st_size // 1024} KB)...", flush=True)
    with open(pdf_path, "rb") as f:
        resp = client.beta.files.upload(file=(pdf_path.name, f, "application/pdf"))
    print(f"  file_id: {resp.id}", flush=True)
    return resp.id


def call_claude(client, file_id, prompt, label, max_retries=3):
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"  Retry {attempt}/{max_retries} for {label}...", flush=True)
            time.sleep(20)
        try:
            resp = client.beta.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=16000,
                messages=[{"role": "user", "content": [
                    {"type": "document", "source": {"type": "file", "file_id": file_id}},
                    {"type": "text",     "text": prompt},
                ]}],
                betas=["files-api-2025-04-14"],
            )
            raw = resp.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except anthropic.RateLimitError:
            print("  Rate limit — sleeping 60s...", flush=True)
            time.sleep(60)
        except json.JSONDecodeError as e:
            print(f"  JSON parse error on attempt {attempt}: {e}", flush=True)
            if attempt == max_retries:
                return {"_error": str(e)}
        except Exception as e:
            print(f"  Error on attempt {attempt}: {e}", flush=True)
            if attempt == max_retries:
                return {"_error": str(e)}
    return {"_error": "All retries exhausted"}


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def merge_location_supplement(csv_dir: Path, year: str, supplement: list[dict]) -> pd.DataFrame:
    """Merge conductor/dates into existing locationsTable."""
    loc_path = csv_dir / f"combined_{year}_locationsTable.csv"
    if not loc_path.exists():
        print(f"  [SKIP] {loc_path.name} not found")
        return pd.DataFrame()

    locs = pd.read_csv(loc_path)
    supp = pd.DataFrame(supplement)

    if supp.empty:
        print("  No location supplement data returned.")
        return locs

    # Normalise city/state for merge
    supp["city_norm"]  = supp["city"].str.strip()
    supp["state_norm"] = supp["state"].str.strip().str.upper()
    locs["city_norm"]  = locs["City"].str.strip()
    locs["state_norm"] = locs["State"].str.strip().str.upper().fillna("")

    # Merge on Test + city_norm + state_norm
    merged = locs.merge(
        supp[["test", "city_norm", "state_norm", "conductor", "planting_date", "maturity_date"]],
        left_on=["Test", "city_norm", "state_norm"],
        right_on=["test", "city_norm", "state_norm"],
        how="left"
    ).drop(columns=["test", "city_norm", "state_norm"])

    # Fill in where original columns were null
    for col, src in [("Conductor", "conductor"), ("PlantingDate", "planting_date"), ("MaturityDate", "maturity_date")]:
        if src in merged.columns:
            merged[col] = merged[col].combine_first(merged[src])
            merged = merged.drop(columns=[src])

    return merged[["Year", "Test", "City", "State", "lat", "lon",
                   "Conductor", "PlantingDate", "MaturityDate"]]


def merge_check_rm(csv_dir: Path, year: str, check_rm: list[dict]) -> pd.DataFrame:
    """Merge RM values into existing checksTable."""
    ck_path = csv_dir / f"combined_{year}_checksTable.csv"
    if not ck_path.exists():
        print(f"  [SKIP] {ck_path.name} not found")
        return pd.DataFrame()

    checks = pd.read_csv(ck_path)
    if not check_rm:
        print("  No check RM data returned.")
        return checks

    rm_df = pd.DataFrame(check_rm)
    rm_df["strain_norm"] = rm_df["strain"].str.strip().str.lower()
    checks["strain_norm"] = checks["Strain"].str.strip().str.lower()

    checks = checks.merge(rm_df[["strain_norm", "rm"]], on="strain_norm", how="left")
    checks["RM"] = checks["RM"].combine_first(checks["rm"])
    checks = checks.drop(columns=["rm", "strain_norm"])
    return checks


def build_metatable(year: str, metatable_rows: list[dict]) -> pd.DataFrame:
    """Build MetaTable in 2025 format: Year-Test, Test-Year, Location, Meta_data_type, Value."""
    rows = []
    for r in metatable_rows:
        test     = str(r.get("test", "")).strip()
        location = str(r.get("location", "")).strip()
        trait    = PHENOTYPE_MAP.get(str(r.get("trait", "")).strip().upper(),
                                     str(r.get("trait", "")).strip())
        year_test = f"{year}_{test.replace('-','')}"
        test_year = f"{test.replace('-','')}_{year}"

        field_map = {
            "no_of_tests":    "No. of Tests",
            "cv_pct":         "C.V. (%)",
            "lsd_5pct":       "L.S.D. (5%)",
            "row_spacing_in": "Row sp (in.)",
            "rows_per_plot":  "Rows/plot",
            "reps":           "Reps",
        }
        for key, label in field_map.items():
            val = r.get(key)
            if val is not None and str(val).strip() not in ("", "null", "None"):
                rows.append({
                    "Year-Test":       year_test,
                    "Test-Year":       test_year,
                    "Location":        location,
                    "Trait":           trait,
                    "Meta_data_type":  label,
                    "Value":           val,
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract supplemental metadata from NUST source PDF"
    )
    parser.add_argument("--year",    default=None)
    parser.add_argument("--pdf",     default=None)
    parser.add_argument("--csv_dir", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--api_key", default=None)
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY") or _load_env_file()
    if not api_key:
        print("Error: API key required.")
        sys.exit(1)

    if args.pdf:
        pdf_path = Path(args.pdf)
    elif args.year:
        pdf_path = resolve_pdf(args.year)
        if not pdf_path:
            print(f"Error: PDF not found for year {args.year}")
            sys.exit(1)
    else:
        print("Error: provide --year or --pdf")
        sys.exit(1)

    year    = args.year or re.search(r'\b(19|20)\d{2}\b', pdf_path.name).group(0)
    csv_dir = Path(args.csv_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    client  = anthropic.Anthropic(api_key=api_key)
    file_id = upload_pdf(client, pdf_path)

    # ---- Call 1: location supplement + check RM ----
    print("\nExtracting location conductor/dates and check RM values...", flush=True)
    loc_result = call_claude(client, file_id, LOCATION_PROMPT, "location+checks")

    if "_error" not in loc_result:
        raw_path = out_dir / f"supplemental_{year}_location_raw.json"
        raw_path.write_text(json.dumps(loc_result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Raw JSON -> {raw_path.name}")

        supplement = loc_result.get("location_supplement", [])
        check_rm   = loc_result.get("check_rm", [])
        print(f"  Locations found: {len(supplement)}")
        print(f"  Check RM entries: {len(check_rm)}")

        # Merge locations
        locs_updated = merge_location_supplement(csv_dir, year, supplement)
        if not locs_updated.empty:
            locs_updated.to_csv(out_dir / f"combined_{year}_locationsTable.csv", index=False)
            n_conductor = locs_updated["Conductor"].notna().sum()
            n_planting  = locs_updated["PlantingDate"].notna().sum()
            n_maturity  = locs_updated["MaturityDate"].notna().sum()
            print(f"  locationsTable: {len(locs_updated)} rows | "
                  f"conductor={n_conductor}, planting={n_planting}, maturity={n_maturity}")

        # Merge check RM
        checks_updated = merge_check_rm(csv_dir, year, check_rm)
        if not checks_updated.empty:
            checks_updated.to_csv(out_dir / f"combined_{year}_checksTable.csv", index=False)
            n_rm = checks_updated["RM"].notna().sum()
            print(f"  checksTable: {len(checks_updated)} rows | RM filled={n_rm}/{len(checks_updated)}")
    else:
        print(f"  [ERROR] Location/check extraction: {loc_result}")

    # ---- Call 2: MetaTable ----
    print("\nExtracting MetaTable (C.V.%, L.S.D., No. of Tests)...", flush=True)
    meta_result = call_claude(client, file_id, METATABLE_PROMPT, "metatable")

    if "_error" not in meta_result:
        raw_path = out_dir / f"supplemental_{year}_meta_raw.json"
        raw_path.write_text(json.dumps(meta_result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Raw JSON -> {raw_path.name}")

        meta_rows = meta_result.get("metatable", [])
        print(f"  MetaTable entries: {len(meta_rows)}")

        meta_df = build_metatable(year, meta_rows)
        if not meta_df.empty:
            meta_path = out_dir / f"combined_{year}_MetaTable.csv"
            meta_df.to_csv(meta_path, index=False)
            print(f"  MetaTable: {len(meta_df)} rows -> {meta_path.name}")
            print(f"  Meta types: {sorted(meta_df['Meta_data_type'].unique())}")
        else:
            print("  MetaTable: no data extracted")
    else:
        print(f"  [ERROR] MetaTable extraction: {meta_result}")

    print("\nDone.")


if __name__ == "__main__":
    main()
