#!/usr/bin/env python
"""
qc_pdf_vs_csv.py
================
Cross-check extracted NUST CSV data against the source PDF report.

Two modes (run independently or together with --mode both):

  roster  — Verifies strain names, location names, and test structure per group.
             Compares PDF roster against combined_*_phenotypes.csv.

  flagged — For each row in review_flagged.csv, looks up the original value
             in the PDF and returns a verdict: confirmed_ocr_error | genuine_value | ambiguous.

Usage:
    python qc_pdf_vs_csv.py --year 1980 --csv_dir ./output_1980/ --out_dir ./output_1980/qc/
    python qc_pdf_vs_csv.py --pdf "R:/.../1980_done.pdf" --csv_dir ./output_1980/ --out_dir ./output_1980/qc/
    python qc_pdf_vs_csv.py --year 1980 --csv_dir ./output_1980/ --flagged ./output_1980/validated/combined_1980_phenotypes_review_flagged.csv --out_dir ./output_1980/qc/ --mode flagged
    python qc_pdf_vs_csv.py --year 1980 --csv_dir ./output_1980/ --flagged ./output_1980/validated/combined_1980_phenotypes_review_flagged.csv --out_dir ./output_1980/qc/ --mode both

  values — Cell-level verification of every extracted trait value against the PDF.
             Iterates over all Test×Location combos; one Claude call per combo.
             PDF is cached after the first call (10× cheaper for calls 2-N).
             Outputs only discrepancies — matching cells are not written.

    python qc_pdf_vs_csv.py --year 1980 --csv output_1980/validated/combined_1980_phenotypesTable_approved.csv --out_dir ./output_1980/qc/ --mode values
    python qc_pdf_vs_csv.py --year 1980 --csv output_1980/validated/combined_1980_phenotypesTable_approved.csv --out_dir ./output_1980/qc/ --mode values --test_filter UT-00
    python qc_pdf_vs_csv.py --year 1980 --csv output_1980/validated/combined_1980_phenotypesTable_approved.csv --out_dir ./output_1980/qc/ --mode values --resume
    python qc_pdf_vs_csv.py --year 1980 --csv output_1980/validated/combined_1980_phenotypesTable_approved.csv --out_dir ./output_1980/qc/ --mode values --dry_run
"""

import argparse
import json
import os
import re
import sys
import time
from io import StringIO
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import anthropic
import pandas as pd


RED_ROOT = Path("R:/NUST_Historical_Data")

ROSTER_PROMPT = """You are reviewing a NUST (North American Uniform Soybean Trial) annual report PDF.

For each entry group / test in the document, extract:
1. The group number (positional: Group 1, Group 2, ...) and the test code / maturity group designation (e.g. UT-00, PT-I, UT-III, etc.)
2. The complete list of strain/entry names tested in that group
3. The complete list of location names used in the per-location data tables for that group

Return ONLY valid JSON (no markdown fences) with this structure:
{
  "year": "<year>",
  "groups": [
    {
      "group_number": 1,
      "test_code": "UT-00",
      "maturity_group": "00",
      "strain_count": 22,
      "strains": ["Strain1", "Strain2", ...],
      "locations": ["Ottawa_ONT", "Morden_MAN", ...]
    }
  ]
}

Location keys must use City_State format (e.g. "Ottawa_ONT", "Morris_MN", "Fargo_ND").
Include ALL strains and ALL locations — do not truncate.
If a test code is not explicitly labelled, infer it from context (maturity group headings, check strain names like "Portage (00)", "Pella (III)", geographic zone).
"""

FLAGGED_PROMPT_TEMPLATE = """You are reviewing a NUST (North American Uniform Soybean Trial) annual report PDF for year {year}.

The following values were flagged during data extraction validation as either out-of-range or non-numeric.
For each flagged item, look up the original value in the PDF and provide a verdict.

Flagged items:
{flagged_items}

For each item, find the corresponding table in the PDF (match by Test/group, Strain name, Location, and Phenotype/trait).
Return ONLY valid JSON (no markdown fences) with this structure:
{{
  "resolutions": [
    {{
      "id": <id>,
      "strain": "<strain>",
      "test": "<test>",
      "city": "<city>",
      "phenotype": "<phenotype>",
      "csv_value": "<value from CSV>",
      "pdf_value": "<value found in PDF, or null if not found>",
      "verdict": "<confirmed_ocr_error | genuine_value | not_found | ambiguous>",
      "note": "<brief explanation>"
    }}
  ]
}}

Verdict definitions:
- confirmed_ocr_error: PDF clearly shows a different value (e.g. PDF has "1" but CSV has "I")
- genuine_value: PDF confirms the extracted value is correct as-is
- not_found: Could not locate this entry in the PDF
- ambiguous: PDF is unclear or value is partially legible
"""

VALUES_PROMPT_TEMPLATE = """You are verifying extracted values from a NUST (North American Uniform Soybean Trial) \
annual report PDF for year {year}.

Test: {test}
Location: {city}, {state}

Below are the extracted values for every strain at this location (CSV format).
Column headers are trait names; each row is one strain.

{csv_block}

Task: Find the corresponding table in the PDF for this test and location.
Compare each Strain × Trait cell to the CSV. Identify ONLY cells where the PDF value
differs from the CSV, the cell is unreadable, or the strain/trait cannot be found.
Cells that match exactly should NOT appear in your output.

Note on Maturity: The CSV stores maturity as Day-of-Year (DOY, e.g. 269 = Sept 26).
The PDF shows it as a calendar date for the reference check (e.g. "9/20") and as
±day offsets for all other strains. To verify a non-reference strain's Maturity DOY,
add the PDF offset to the reference check's DOY. If you cannot verify the conversion,
skip that cell rather than flagging it as a discrepancy.

IMPORTANT: Output ONLY the JSON object below — no explanation, no analysis, no preamble.
Start your response with {{ and end with }}.

{{
  "test": "{test}",
  "city": "{city}",
  "state": "{state}",
  "discrepancies": [
    {{
      "strain": "<strain name>",
      "phenotype": "<trait name>",
      "csv_value": "<value from CSV, or null if missing>",
      "pdf_value": "<value read from PDF, or null if not found>",
      "verdict": "<discrepancy|ambiguous|not_found>",
      "note": "<brief explanation>"
    }}
  ]
}}

If every cell matches, output exactly: {{"test": "{test}", "city": "{city}", "state": "{state}", "discrepancies": []}}
"""


def _load_env_file() -> str | None:
    for candidate in [Path(__file__).parent / ".Env", Path(__file__).parent.parent / ".Env"]:
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
            if line.startswith("sk-ant-"):
                return line
    return None


def resolve_pdf(year: str) -> Path | None:
    """Auto-locate *_done.pdf for a given year under RED_ROOT."""
    for red_dir in RED_ROOT.glob("Red-*/Red"):
        candidate = red_dir / f"{year}_done.pdf"
        if candidate.exists():
            return candidate
    return None


def load_pdf_b64(pdf_path: Path) -> str:
    """Read PDF as base64 string for inline document blocks with prompt caching."""
    import base64
    print(f"  Loading PDF: {pdf_path.name} ({pdf_path.stat().st_size // 1024} KB)...", flush=True)
    with open(pdf_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    print(f"  PDF loaded ({len(data) // 1024} KB base64).", flush=True)
    return data


# Pricing for claude-sonnet-4-6 (per million tokens)
_PRICE_INPUT        = 3.00
_PRICE_OUTPUT       = 15.00
_PRICE_CACHE_WRITE  = 3.75
_PRICE_CACHE_READ   = 0.30


def _compute_cost(usage) -> float:
    """Return estimated USD cost from a response usage object."""
    inp    = getattr(usage, "input_tokens",                0) or 0
    out    = getattr(usage, "output_tokens",               0) or 0
    cwrite = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cread  = getattr(usage, "cache_read_input_tokens",     0) or 0
    return (
        inp    * _PRICE_INPUT       / 1_000_000
        + out  * _PRICE_OUTPUT      / 1_000_000
        + cwrite * _PRICE_CACHE_WRITE / 1_000_000
        + cread  * _PRICE_CACHE_READ  / 1_000_000
    )


def call_claude_pdf(client: anthropic.Anthropic, pdf_b64: str, prompt: str,
                    label: str, max_retries: int = 3) -> tuple[dict, float]:
    """Call Claude with an inline base64 PDF (prompt-cached) and a text prompt.

    Returns (parsed_result, estimated_cost_usd).
    cache_control is always applied — first call pays cache-write rate ($3.75/M),
    subsequent calls pay cache-read rate ($0.30/M), ~10× cheaper.
    """
    doc_block = {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
        "cache_control": {"type": "ephemeral"},
    }

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"  Retry {attempt}/{max_retries} for {label}...", flush=True)
            time.sleep(20)
        try:
            response = client.beta.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=16000,
                messages=[{
                    "role": "user",
                    "content": [
                        doc_block,
                        {"type": "text", "text": prompt},
                    ],
                }],
                betas=["prompt-caching-2024-07-31"],
            )

            usage  = response.usage
            cwrite = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cread  = getattr(usage, "cache_read_input_tokens",     0) or 0
            inp    = getattr(usage, "input_tokens",                0) or 0
            out    = getattr(usage, "output_tokens",               0) or 0
            cost   = _compute_cost(usage)

            cache_tag = (
                f"CACHE-WRITE {cwrite:,}tok"  if cwrite > 0 else
                f"CACHE-READ  {cread:,}tok"   if cread  > 0 else
                f"NO-CACHE    {inp:,}tok"
            )
            print(f"    [{cache_tag}] out={out:,}tok  ${cost:.4f}", flush=True)

            raw = response.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            try:
                return json.loads(raw), cost
            except json.JSONDecodeError:
                m = re.search(r'\{.*\}', raw, re.DOTALL)
                if m:
                    return json.loads(m.group(0)), cost
                raise
        except anthropic.RateLimitError:
            print(f"  Rate limit — sleeping 60s...", flush=True)
            time.sleep(60)
        except json.JSONDecodeError as e:
            print(f"  JSON parse error on attempt {attempt}: {e}", flush=True)
            if attempt == max_retries:
                return {"_parse_error": str(e)}, 0.0
        except Exception as e:
            print(f"  API error on attempt {attempt}: {e}", flush=True)
            if attempt == max_retries:
                return {"_error": str(e)}, 0.0
    return {"_error": "All retries exhausted"}, 0.0


# ---------------------------------------------------------------------------
# Roster mode
# ---------------------------------------------------------------------------

def run_roster(client: anthropic.Anthropic, pdf_b64: str, year: str,
               csv_dir: Path, out_dir: Path) -> dict:
    print("\n--- ROSTER MODE ---", flush=True)

    # Load combined phenotypes CSV
    pheno_path = csv_dir / f"combined_{year}_phenotypes.csv"
    if not pheno_path.exists():
        # Fall back to raw if TEST_MAP not applied
        pheno_path = csv_dir / f"combined_{year}_phenotypes_raw.csv"
    if not pheno_path.exists():
        print(f"  [SKIP] No combined phenotypes CSV found in {csv_dir}")
        return {}

    df = pd.read_csv(pheno_path)
    df_loc = df[df["City"] != "Mean"]

    csv_tests = sorted(df_loc["Test"].unique())
    print(f"  CSV tests: {csv_tests}", flush=True)

    # Ask Claude to extract roster from PDF
    print("  Sending PDF to Claude for roster extraction...", flush=True)
    result, cost = call_claude_pdf(client, pdf_b64, ROSTER_PROMPT, "roster")
    print(f"  Roster call cost: ${cost:.4f}", flush=True)

    if "_error" in result or "_parse_error" in result:
        print(f"  [ERROR] Roster extraction failed: {result}")
        return result

    # Diff PDF roster vs CSV
    report = {"year": year, "groups": [], "summary": {}}
    total_missing_strains, total_extra_strains = 0, 0
    total_missing_locs, total_extra_locs = 0, 0

    for grp in result.get("groups", []):
        test_code = grp.get("test_code", f"Group_{grp.get('group_number','?')}")

        # CSV strains for this test
        csv_strains = set(df_loc[df_loc["Test"] == test_code]["Strain"].unique())
        pdf_strains = set(grp.get("strains", []))

        # CSV locations for this test
        csv_locs = set(
            df_loc[df_loc["Test"] == test_code]
            .apply(lambda r: f"{r['City']}_{r['State']}", axis=1)
            .unique()
        )
        pdf_locs = set(grp.get("locations", []))

        missing_strains = sorted(pdf_strains - csv_strains)
        extra_strains   = sorted(csv_strains - pdf_strains)
        missing_locs    = sorted(pdf_locs - csv_locs)
        extra_locs      = sorted(csv_locs - pdf_locs)

        total_missing_strains += len(missing_strains)
        total_extra_strains   += len(extra_strains)
        total_missing_locs    += len(missing_locs)
        total_extra_locs      += len(extra_locs)

        status = "OK" if not any([missing_strains, extra_strains, missing_locs, extra_locs]) else "DIFF"
        print(f"  [{status}] {test_code}: "
              f"strains pdf={grp.get('strain_count','?')} csv={len(csv_strains)} | "
              f"locs pdf={len(pdf_locs)} csv={len(csv_locs)}", flush=True)

        if missing_strains:
            print(f"    Missing strains (in PDF, not CSV): {missing_strains}")
        if extra_strains:
            print(f"    Extra strains (in CSV, not PDF):   {extra_strains}")
        if missing_locs:
            print(f"    Missing locs (in PDF, not CSV): {missing_locs}")
        if extra_locs:
            print(f"    Extra locs (in CSV, not PDF):   {extra_locs}")

        report["groups"].append({
            "test_code": test_code,
            "pdf_strain_count": grp.get("strain_count"),
            "csv_strain_count": len(csv_strains),
            "pdf_loc_count": len(pdf_locs),
            "csv_loc_count": len(csv_locs),
            "missing_strains": missing_strains,
            "extra_strains": extra_strains,
            "missing_locs": missing_locs,
            "extra_locs": extra_locs,
            "status": status,
        })

    report["summary"] = {
        "total_missing_strains": total_missing_strains,
        "total_extra_strains": total_extra_strains,
        "total_missing_locs": total_missing_locs,
        "total_extra_locs": total_extra_locs,
        "groups_with_diffs": sum(1 for g in report["groups"] if g["status"] == "DIFF"),
    }
    print(f"\n  Roster summary: missing_strains={total_missing_strains}, "
          f"extra_strains={total_extra_strains}, missing_locs={total_missing_locs}, "
          f"extra_locs={total_extra_locs}", flush=True)

    return report


# ---------------------------------------------------------------------------
# Flagged mode
# ---------------------------------------------------------------------------

def run_flagged(client: anthropic.Anthropic, pdf_b64: str, year: str,
                flagged_path: Path, out_dir: Path) -> dict:
    print("\n--- FLAGGED MODE ---", flush=True)

    flagged_df = pd.read_csv(flagged_path)
    if flagged_df.empty:
        print("  No flagged rows to resolve.")
        return {}

    print(f"  Resolving {len(flagged_df)} flagged rows against PDF...", flush=True)

    # Format flagged items for the prompt
    items = []
    for i, row in flagged_df.iterrows():
        items.append(
            f"  id={i} | Test={row['Test']} | Strain={row['Strain']} | "
            f"City={row['City']} {row['State']} | Phenotype={row['Phenotype']} | "
            f"CSV value={row['Value']} | Flag={row['Flag']}"
        )
    flagged_text = "\n".join(items)

    prompt = FLAGGED_PROMPT_TEMPLATE.format(year=year, flagged_items=flagged_text)
    result, cost = call_claude_pdf(client, pdf_b64, prompt, "flagged")
    print(f"  Flagged call cost: ${cost:.4f}", flush=True)

    if "_error" in result or "_parse_error" in result:
        print(f"  [ERROR] Flagged resolution failed: {result}")
        return result

    resolutions = result.get("resolutions", [])

    # Print resolution summary
    verdicts = {}
    for r in resolutions:
        v = r.get("verdict", "unknown")
        verdicts[v] = verdicts.get(v, 0) + 1
        icon = {"confirmed_ocr_error": "OCR", "genuine_value": "OK ",
                "not_found": "???", "ambiguous": "~~ "}.get(v, "   ")
        print(f"  [{icon}] id={r.get('id')} {r.get('test')} | {r.get('strain')} | "
              f"{r.get('city')} | {r.get('phenotype')}: "
              f"csv={r.get('csv_value')} pdf={r.get('pdf_value')} — {r.get('note','')}", flush=True)

    print(f"\n  Verdict summary: {verdicts}", flush=True)

    return {"year": year, "resolutions": resolutions, "verdict_summary": verdicts}


# ---------------------------------------------------------------------------
# Values mode — cell-level verification
# ---------------------------------------------------------------------------

TRAIT_COL_ORDER = [
    "YieldBuA", "YieldRank", "Maturity", "Lodging", "Height",
    "SeedQuality", "SeedSize", "Protein", "Oil",
]

def _build_csv_block(df: pd.DataFrame) -> str:
    """Pivot Test×Location slice to wide format and render as compact CSV text."""
    wide = df.pivot_table(
        index="Strain", columns="Phenotype", values="Value", aggfunc="first"
    )
    # Order columns by known trait order, put any extras at end
    ordered = [c for c in TRAIT_COL_ORDER if c in wide.columns]
    extras  = [c for c in wide.columns if c not in TRAIT_COL_ORDER]
    wide = wide[ordered + extras].reset_index()
    return wide.to_csv(index=False)


def run_values(
    client: anthropic.Anthropic,
    pdf_b64: str,
    year: str,
    csv_path: Path,
    out_dir: Path,
    test_filter: str = None,
    resume: bool = False,
    dry_run: bool = False,
) -> dict:
    print("\n--- VALUES MODE ---", flush=True)

    df = pd.read_csv(csv_path)
    # Per-location rows only (exclude Mean rows)
    df = df[df["City"].notna() & (df["City"] != "") & (df["City"] != "Mean")].copy()

    # Build list of (Test, City, State) combos
    combos = (
        df[["Test", "City", "State"]]
        .drop_duplicates()
        .sort_values(["Test", "City"])
        .reset_index(drop=True)
    )

    if test_filter:
        combos = combos[combos["Test"] == test_filter].reset_index(drop=True)
        print(f"  Filtered to test: {test_filter} ({len(combos)} locations)", flush=True)

    print(f"  Total combos to verify: {len(combos)}", flush=True)

    # Progress checkpoint
    progress_path = out_dir / f"qc_{year}_values_progress.json"
    completed: set = set()
    if resume and progress_path.exists():
        prog = json.loads(progress_path.read_text(encoding="utf-8"))
        completed = {(r["test"], r["city"], r["state"]) for r in prog.get("completed", [])}
        print(f"  Resuming — {len(completed)} combos already done", flush=True)

    all_discrepancies: list[dict] = []
    completed_records: list[dict] = []

    # Load any prior completed records for checkpoint merge
    if resume and progress_path.exists():
        prog = json.loads(progress_path.read_text(encoding="utf-8"))
        completed_records = prog.get("completed", [])
        all_discrepancies = prog.get("discrepancies", [])

    call_count = 0
    skip_count = 0
    total_cost = 0.0

    for _, row in combos.iterrows():
        test  = str(row["Test"]).strip()
        city  = str(row["City"]).strip()
        state = str(row["State"]).strip()
        key   = (test, city, state)

        if key in completed:
            skip_count += 1
            continue

        slice_df = df[(df["Test"] == test) & (df["City"] == city) & (df["State"] == state)]
        if slice_df.empty:
            continue

        csv_block = _build_csv_block(slice_df)
        n_strains = slice_df["Strain"].nunique()
        label = f"{test}/{city}_{state}"

        if dry_run:
            print(f"  [DRY-RUN] {label}: {n_strains} strains, {len(slice_df)} rows", flush=True)
            completed.add(key)
            completed_records.append({"test": test, "city": city, "state": state})
            continue

        prompt = VALUES_PROMPT_TEMPLATE.format(
            year=year, test=test, city=city, state=state, csv_block=csv_block
        )

        call_count += 1
        result, call_cost = call_claude_pdf(client, pdf_b64, prompt, label, max_retries=3)
        total_cost += call_cost

        if "_error" in result or "_parse_error" in result:
            print(f"  [ERROR] {label}: {result}", flush=True)
            discrepancies = []
        else:
            discrepancies = result.get("discrepancies", [])
            for d in discrepancies:
                d["Test"]  = test
                d["City"]  = city
                d["State"] = state

        n_disc = len(discrepancies)
        icon = "OK " if n_disc == 0 else f"{n_disc:2d}!"
        print(f"  [{icon}] {label}: {n_strains} strains, {n_disc} disc  "
              f"(call ${call_cost:.4f} | run total ${total_cost:.4f})", flush=True)

        all_discrepancies.extend(discrepancies)
        completed.add(key)
        completed_records.append({"test": test, "city": city, "state": state})

        # Save checkpoint after every call
        progress_path.write_text(
            json.dumps({"completed": completed_records,
                        "discrepancies": all_discrepancies}, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    if dry_run:
        print(f"\n  Dry run complete — {len(combos)} combos listed, no API calls made.", flush=True)
        return {"year": year, "dry_run": True, "combos": len(combos)}

    print(f"\n  Calls made: {call_count} | Skipped (resumed): {skip_count}", flush=True)
    print(f"  Total discrepancies: {len(all_discrepancies)}", flush=True)
    print(f"  Estimated cost this run: ${total_cost:.4f}", flush=True)

    # Write discrepancies CSV
    disc_path = out_dir / f"qc_{year}_values.csv"
    if all_discrepancies:
        disc_df = pd.DataFrame(all_discrepancies)
        col_order = ["Test", "City", "State", "strain", "phenotype",
                     "csv_value", "pdf_value", "verdict", "note"]
        disc_df = disc_df[[c for c in col_order if c in disc_df.columns]]
        disc_df.to_csv(disc_path, index=False)
        print(f"  Discrepancies -> {disc_path.name}", flush=True)
    else:
        disc_path.write_text("Test,City,State,strain,phenotype,csv_value,pdf_value,verdict,note\n",
                              encoding="utf-8")
        print(f"  No discrepancies found — empty CSV written to {disc_path.name}", flush=True)

    verdict_counts: dict = {}
    for d in all_discrepancies:
        v = d.get("verdict", "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    summary = {
        "year": year, "combos_checked": call_count + skip_count,
        "calls_made": call_count, "total_discrepancies": len(all_discrepancies),
        "verdict_counts": verdict_counts,
        "estimated_cost_usd": round(total_cost, 4),
    }
    print(f"  Verdicts: {verdict_counts}", flush=True)
    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="QC NUST extracted CSVs against source PDF (roster / flagged / values)"
    )
    parser.add_argument("--year",    type=str, default=None, help="Trial year (auto-resolves PDF from Red folder)")
    parser.add_argument("--pdf",     type=str, default=None, help="Explicit path to source PDF")
    parser.add_argument("--csv_dir", type=str, default=None, help="Directory with combined_*_phenotypes.csv (roster/flagged modes)")
    parser.add_argument("--csv",     type=str, default=None, help="Explicit path to phenotypesTable CSV (values mode)")
    parser.add_argument("--flagged", type=str, default=None, help="Path to review_flagged.csv")
    parser.add_argument("--out_dir", type=str, required=True, help="Output directory for QC reports")
    parser.add_argument("--mode",    type=str, default="both",
                        choices=["roster", "flagged", "both", "values"],
                        help="QC mode: roster, flagged, both, or values (default: both)")
    parser.add_argument("--test_filter", type=str, default=None,
                        help="values mode: restrict to one test code, e.g. UT-00")
    parser.add_argument("--resume",  action="store_true",
                        help="values mode: skip combos already in progress checkpoint")
    parser.add_argument("--dry_run", action="store_true",
                        help="values mode: list combos without making API calls")
    parser.add_argument("--api_key", type=str, default=None)
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY") or _load_env_file()
    if not api_key and not (args.dry_run and args.mode == "values"):
        print("Error: API key required. Add to .Env, set ANTHROPIC_API_KEY, or use --api_key.")
        sys.exit(1)

    # Resolve PDF path
    if args.pdf:
        pdf_path = Path(args.pdf)
    elif args.year:
        pdf_path = resolve_pdf(args.year)
        if not pdf_path:
            print(f"Error: could not find PDF for year {args.year} under {RED_ROOT}")
            sys.exit(1)
    else:
        print("Error: provide --year (auto-resolve) or --pdf (explicit path).")
        sys.exit(1)

    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)

    year = args.year or re.search(r'(19|20)\d{2}', pdf_path.name).group(0)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Validate mode requirements
    if args.mode in ("flagged", "both") and not args.flagged:
        print("Error: --flagged is required for flagged/both mode.")
        sys.exit(1)
    if args.mode == "values" and not args.csv and not args.csv_dir:
        print("Error: --csv (explicit phenotypesTable path) is required for values mode.")
        sys.exit(1)
    if args.mode in ("roster", "flagged", "both") and not args.csv_dir:
        print("Error: --csv_dir is required for roster/flagged/both mode.")
        sys.exit(1)

    is_dry_run_values = args.dry_run and args.mode == "values"
    client = anthropic.Anthropic(api_key=api_key) if not is_dry_run_values else None

    print(f"\nQC run: year={year}, pdf={pdf_path.name}, mode={args.mode}")

    # Load PDF as base64 once — passed to every API call with cache_control
    if is_dry_run_values:
        pdf_b64 = "dry-run"
        print("  [DRY-RUN] Skipping PDF load.")
    else:
        pdf_b64 = load_pdf_b64(pdf_path)

    combined_report = {"year": year, "pdf": pdf_path.name, "mode": args.mode}

    if args.mode in ("roster", "both"):
        csv_dir = Path(args.csv_dir)
        roster_report = run_roster(client, pdf_b64, year, csv_dir, out_dir)
        combined_report["roster"] = roster_report
        roster_out = out_dir / f"qc_{year}_roster.json"
        roster_out.write_text(json.dumps(roster_report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Roster report -> {roster_out.name}")

    if args.mode in ("flagged", "both"):
        flagged_report = run_flagged(client, pdf_b64, year, Path(args.flagged), out_dir)
        combined_report["flagged"] = flagged_report
        flagged_out = out_dir / f"qc_{year}_flagged.json"
        flagged_out.write_text(json.dumps(flagged_report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Flagged report -> {flagged_out.name}")

    if args.mode == "values":
        # Resolve phenotypesTable path
        if args.csv:
            csv_path = Path(args.csv)
        else:
            csv_dir = Path(args.csv_dir)
            csv_path = csv_dir / f"validated/combined_{year}_phenotypesTable_approved.csv"
            if not csv_path.exists():
                csv_path = csv_dir / f"combined_{year}_phenotypesTable.csv"
        if not csv_path.exists():
            print(f"Error: phenotypesTable CSV not found: {csv_path}")
            sys.exit(1)
        print(f"  Input CSV: {csv_path.name}")

        values_report = run_values(
            client, pdf_b64, year, csv_path, out_dir,
            test_filter=args.test_filter,
            resume=args.resume,
            dry_run=args.dry_run,
        )
        combined_report["values"] = values_report
        values_summary_out = out_dir / f"qc_{year}_values_summary.json"
        values_summary_out.write_text(
            json.dumps(values_report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\n  Values summary -> {values_summary_out.name}")

    # Write combined report (skip for dry-run)
    if not args.dry_run:
        combined_out = out_dir / f"qc_{year}_report.json"
        combined_out.write_text(json.dumps(combined_report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nFull report -> {combined_out.name}")
    print("\nDone.")


if __name__ == "__main__":
    main()
