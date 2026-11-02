#!/usr/bin/env python
"""
extract_nust_pdf.py
===================
PDF-direct extractor for NUST historical reports. Used when no Sojabone XLSX
exists for a given year (e.g. 1990, 1975). Parallels ``extract_nust_xlsx.py``
in output schema so the downstream pipeline (combine_nust_outputs.py,
NUST_HistProcessing.R, etc.) works without modification.

Pipeline
--------
Step 1 — Upload the PDF once (base64 inline document block with
         ``cache_control=ephemeral``). Subsequent calls hit the prompt cache
         (~10× cheaper for input tokens).

Step 2 — Roster query (1 API call): list every Test/MG combo present, with
         the full strain roster (and parentage if printed) and the full
         per-location city list for each Test. Output:
         ``output_files/output_{year}/check_roster_pdf_raw_{year}.json``.

Step 3 — Per-(Test, City) extraction loop. Each call asks Claude to read the
         table at that test/location and return per-strain values for
         YieldBuA, YieldRank, Maturity (DOY), Lodging, Height, SeedQuality,
         SeedSize, Protein, Oil — **plus a self-reported confidence flag
         (high / medium / low) and a one-line note per cell**. Results are
         streamed into a long CSV and a parallel QC CSV with the confidence
         flags. Per-trait-block summary rows (Mean / N / CV / LSD) come out
         of the same call when the PDF lays them out next to the data, so we
         can recover Mean rows without a separate Phase 4 query.

Output files (under ``--out_dir``)
----------------------------------
    Sojabone-{year}_pdf_extract_phenotypes.csv  ← long-format (City rows + Mean rows)
    Sojabone-{year}_pdf_extract_strains.csv     ← Strain, Test, Year
    Sojabone-{year}_pdf_extract_parentage.csv   ← Strain, Parentage, PrevTesting, Generation, Test, Year
    Sojabone-{year}_pdf_extract_summary.csv     ← tp4-style averages (one row per Strain/Test)
    qc/qc_{year}_pdf_extract.csv                ← per-cell confidence + note
    check_roster_pdf_raw_{year}.json            ← Phase 2 raw roster JSON
    progress_{year}.json                        ← checkpoint (resumable)

Usage
-----
    python scripts/extract_nust_pdf.py --year 1990 --pdf input_files/input_1990/1990.pdf \
        --out_dir output_files/output_1990/

    # Resume a partial run:
    python scripts/extract_nust_pdf.py --year 1990 --pdf input_files/input_1990/1990.pdf \
        --out_dir output_files/output_1990/ --resume

    # Dry-run (lists combos, no API calls) after phase 2 completes:
    python scripts/extract_nust_pdf.py --year 1990 --pdf input_files/input_1990/1990.pdf \
        --out_dir output_files/output_1990/ --dry_run

    # Restrict to one test (debugging):
    python scripts/extract_nust_pdf.py --year 1990 --pdf input_files/input_1990/1990.pdf \
        --out_dir output_files/output_1990/ --test_filter UT-00
"""

import argparse
import base64
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


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RED_ROOT = Path("R:/cfans_agro_lore0149_lorenzlabresearch/NUST_Historical_Data_1941_1988")

# Pricing for claude-sonnet-4-6 (USD per million tokens)
_PRICE_INPUT       = 3.00
_PRICE_OUTPUT      = 15.00
_PRICE_CACHE_WRITE = 3.75
_PRICE_CACHE_READ  = 0.30

MODEL = "claude-sonnet-4-6"

# Per-cell traits we ask for at each (Test, City) — names match downstream
# PHENOTYPE_MAP keys after splitting Units. We output the raw "YIELD (bu/a)"
# form to mirror extract_nust_xlsx.py's output schema.
TRAITS = [
    ("YieldBuA",    "YIELD",        "bu/a"),
    ("YieldRank",   "YIELD RANK",   ""),
    ("Maturity",    "MATURITY",     "date"),
    ("Lodging",     "LODGING",      "score"),
    ("Height",      "PLANT HEIGHT", "inches"),
    ("SeedQuality", "SEED QUALITY", "score"),
    ("SeedSize",    "SEED SIZE",    "g/100"),
    ("Protein",     "PROTEIN",      "%"),
    ("Oil",         "OIL",          "%"),
]

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ROSTER_PROMPT = """You are reading a NUST (North American Uniform Soybean Trial) annual report PDF.

For each entry group / test in this report, extract:
1. The test code / maturity group designation (e.g. UT-00, UT-0, UT-I, UT-II, UT-III, UT-IV, PT-II, PT-III, etc.)
2. The maturity group label ("00", "0", "I", "II", "III", "IV", ...)
3. The COMPLETE list of strain / entry names tested in that group
4. Each strain's parentage line if printed (parentage table, e.g. "A x B"), previous-testing line, and generation composited
5. The COMPLETE list of per-location data tables for that test (use the per-location
   single-year tables — NOT multi-year-mean summary tables).

Return ONLY valid JSON (no markdown fences, no preamble, no commentary) with this structure:
{
  "year": "<4-digit year>",
  "tests": [
    {
      "test_code":      "UT-00",
      "maturity_group": "00",
      "strain_count":   25,
      "strains": [
        {
          "name":         "<strain>",
          "parentage":    "<A x B  or  null>",
          "prev_testing": "<prior tests or null>",
          "generation":   "<F-generation or null>"
        }
      ],
      "locations": ["Ottawa_ONT", "Morden_MAN", "Fargo_ND", "Morris_MN"]
    }
  ]
}

Location keys must use City_State format with US two-letter state abbreviations
(WI, MN, ND, SD, IA, IL, IN, MI, OH, MO, KS, NE, KY, PA, MD, DE, NJ, VA, NC,
GA, SC, TN, AR, etc.) and Canadian province codes (ONT, MAN, SK, QUE).
Examples: "Ottawa_ONT", "Morris_MN", "Fargo_ND", "Madison_WI", "Ames_IA",
"West Lafayette_IN", "St Paul_MN".

If a parentage / prev-testing / generation field is not printed, set it to null.
Include ALL strains and ALL per-location tables — do not truncate.
"""


VALUES_PROMPT_TEMPLATE = """You are extracting trial data from a NUST (North American Uniform Soybean Trial)
annual report PDF for year {year}.

Test:    {test}
Location: {city}, {state}  (location key: {loc_key})

Read the per-strain table for this test at this location only (NOT the
multi-year-mean tables, NOT summary tables). For every strain listed in this
test, extract the following trait values from the per-location columns:

  YieldBuA      (yield in bu/a, from the YIELD column)
  YieldRank     (rank number at this location, if printed)
  Maturity      (Day-of-Year, integer; if PDF shows a calendar date for the
                 reference and ±offsets for others, convert to DOY using
                 reference DOY + offset)
  Lodging       (score)
  Height        (inches; column may be labelled "Plant height")
  SeedQuality   (score; column may be labelled "Quality")
  SeedSize      (g/100 seeds)
  Protein       (%)
  Oil           (%)

Mean row: if the PDF also prints a per-location summary row (Mean, N, CV%,
LSD) for this trait/location, capture the Mean only and put it under
strain="Mean".

For each cell, ALSO provide:
  confidence  ∈ {{"high", "medium", "low"}}
              high   = unambiguous read, clearly printed
              medium = partial OCR doubt, slight overprint, or "looks-like"
              low    = ambiguous, blurry, faded, missing, or you had to guess
  note        ≤ 80 chars; required for medium/low; "" for high

Return ONLY valid JSON (no markdown fences, no preamble) with this structure:
{{
  "test":  "{test}",
  "city":  "{city}",
  "state": "{state}",
  "cells": [
    {{
      "strain":     "<strain name>",
      "phenotype":  "YieldBuA",
      "value":      "<value or null>",
      "confidence": "high",
      "note":       ""
    }}
  ]
}}

IMPORTANT:
- Output only the JSON object — start with {{ and end with }}.
- Use null (not the literal string "null", not empty string) for missing values.
- Use phenotype names exactly as listed above (YieldBuA, YieldRank, Maturity,
  Lodging, Height, SeedQuality, SeedSize, Protein, Oil).
- Include EVERY strain in this test, even if some cells are missing.
- Skip the table if it is a multi-year mean table; we only want current-year
  ({year}) data.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_env_file() -> str | None:
    for candidate in [Path(__file__).parent / ".Env",
                      Path(__file__).parent.parent / ".Env"]:
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
            if line.startswith("sk-ant-"):
                return line
    return None


def resolve_pdf(year: str, explicit: str | None) -> Path | None:
    """Try explicit path, then RED_ROOT for {year}.pdf or {year}_done.pdf."""
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    for red_dir in RED_ROOT.glob("Red-*/Red"):
        for stem in (f"{year}.pdf", f"{year}_done.pdf"):
            cand = red_dir / stem
            if cand.exists():
                return cand
    return None


def load_pdf_b64(pdf_path: Path) -> str:
    """Read PDF as base64 string for inline cache_control document blocks."""
    print(f"  Loading PDF: {pdf_path.name} "
          f"({pdf_path.stat().st_size // 1024} KB)...", flush=True)
    with open(pdf_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    print(f"  PDF loaded ({len(data) // 1024} KB base64).", flush=True)
    return data


def _compute_cost(usage) -> float:
    """USD cost estimate from a response.usage object."""
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
                    label: str, max_retries: int = 3,
                    max_tokens: int = 32000) -> tuple[dict, float]:
    """Call Claude with a cache-controlled base64 PDF + text prompt.

    Streaming-based to support large responses. Returns (parsed_result,
    estimated_cost_usd). First call pays cache-write; subsequent calls hit
    cache-read (~10× cheaper for input tokens).
    """
    doc_block = {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf",
                   "data": pdf_b64},
        "cache_control": {"type": "ephemeral"},
    }

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"    Retry {attempt}/{max_retries} for {label}...", flush=True)
            time.sleep(20)
        try:
            raw_parts = []
            final_usage = None
            with client.beta.messages.stream(
                model=MODEL,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        doc_block,
                        {"type": "text", "text": prompt},
                    ],
                }],
                betas=["prompt-caching-2024-07-31"],
            ) as stream:
                for text in stream.text_stream:
                    raw_parts.append(text)
                final_message = stream.get_final_message()
                final_usage = final_message.usage

            usage  = final_usage
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

            raw = "".join(raw_parts).strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            try:
                return json.loads(raw), cost
            except json.JSONDecodeError:
                m = re.search(r'\{.*\}', raw, re.DOTALL)
                if m:
                    try:
                        return json.loads(m.group(0)), cost
                    except json.JSONDecodeError:
                        pass
                if attempt == max_retries:
                    return {"_parse_error": "invalid JSON", "_raw": raw}, cost
        except anthropic.RateLimitError:
            print(f"    Rate limit — sleeping 60s...", flush=True)
            time.sleep(60)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                print(f"    Overloaded (529) — sleeping 30s...", flush=True)
                time.sleep(30)
            else:
                print(f"    API error attempt {attempt}: {e}", flush=True)
                if attempt == max_retries:
                    return {"_error": str(e)}, 0.0
        except Exception as e:
            print(f"    API error attempt {attempt}: {e}", flush=True)
            if attempt == max_retries:
                return {"_error": str(e)}, 0.0
    return {"_error": "All retries exhausted"}, 0.0


# ---------------------------------------------------------------------------
# Phase 1 — Roster
# ---------------------------------------------------------------------------

def run_roster(client: anthropic.Anthropic, pdf_b64: str, year: str,
               out_dir: Path) -> dict:
    """Phase 1: extract Test × Strain × City inventory from PDF."""
    print("\n=== Phase 1 — Roster ===", flush=True)

    raw_path = out_dir / f"check_roster_pdf_raw_{year}.json"

    if raw_path.exists():
        print(f"  Reusing existing roster JSON: {raw_path.name}", flush=True)
        roster = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        roster, cost = call_claude_pdf(client, pdf_b64, ROSTER_PROMPT,
                                       "roster", max_tokens=32000)
        print(f"  Roster call cost: ${cost:.4f}", flush=True)
        if "_error" in roster or "_parse_error" in roster:
            print(f"  [ERROR] Roster failed: {roster}", flush=True)
            return roster
        raw_path.write_text(json.dumps(roster, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"  Roster saved -> {raw_path.name}", flush=True)

    # Summary
    n_tests = len(roster.get("tests", []))
    n_strains_total = sum(len(t.get("strains", [])) for t in roster.get("tests", []))
    n_locs_total    = sum(len(t.get("locations", [])) for t in roster.get("tests", []))
    print(f"  Roster: {n_tests} tests, {n_strains_total} strain rows, "
          f"{n_locs_total} (Test, Location) combos", flush=True)
    for t in roster.get("tests", []):
        print(f"    {t.get('test_code')}: "
              f"{len(t.get('strains', []))} strains × "
              f"{len(t.get('locations', []))} locations", flush=True)

    return roster


# ---------------------------------------------------------------------------
# Phase 2 — Per-(Test, City) extraction
# ---------------------------------------------------------------------------

def _parse_loc_key(loc_key: str) -> tuple[str, str]:
    """'Ottawa_ONT' -> ('Ottawa', 'ONT'); 'St Paul_MN' -> ('St Paul', 'MN')."""
    if "_" not in loc_key:
        return loc_key, ""
    city, state = loc_key.rsplit("_", 1)
    return city.strip().replace("_", " "), state.strip()


def _enumerate_combos(roster: dict, test_filter: str | None) -> list[dict]:
    """Build the (test, loc_key, city, state) combo list from roster."""
    combos = []
    for t in roster.get("tests", []):
        test_code = t.get("test_code", "").strip()
        if not test_code:
            continue
        if test_filter and test_code != test_filter:
            continue
        for loc_key in t.get("locations", []):
            city, state = _parse_loc_key(loc_key)
            combos.append({
                "test": test_code, "loc_key": loc_key,
                "city": city, "state": state,
            })
    return combos


def run_extraction(client: anthropic.Anthropic, pdf_b64: str, year: str,
                   roster: dict, out_dir: Path, qc_dir: Path,
                   test_filter: str | None = None,
                   resume: bool = False, dry_run: bool = False) -> dict:
    """Phase 2: per-(Test, City) extraction loop with confidence flags."""
    print("\n=== Phase 2 — Per-(Test, City) extraction ===", flush=True)

    combos = _enumerate_combos(roster, test_filter)
    print(f"  Total combos: {len(combos)}", flush=True)
    if not combos:
        print("  [ABORT] No (Test, City) combos to process.", flush=True)
        return {"calls": 0, "cells": 0}

    progress_path = out_dir / f"progress_{year}.json"
    completed_keys: set[tuple[str, str]] = set()
    all_cells: list[dict] = []
    total_cost = 0.0

    if resume and progress_path.exists():
        try:
            saved = json.loads(progress_path.read_text(encoding="utf-8"))
            completed_keys = {(r["test"], r["loc_key"])
                              for r in saved.get("completed", [])}
            all_cells = saved.get("cells", [])
            total_cost = float(saved.get("cost_so_far", 0.0))
            print(f"  Resuming — {len(completed_keys)} combos already done, "
                  f"prior spend ${total_cost:.4f}", flush=True)
        except Exception as e:
            print(f"  [WARN] Progress file unreadable: {e}", flush=True)

    completed_records: list[dict] = [
        {"test": k[0], "loc_key": k[1]} for k in completed_keys
    ]

    call_count, skip_count = 0, 0

    for i, combo in enumerate(combos, start=1):
        test    = combo["test"]
        loc_key = combo["loc_key"]
        city    = combo["city"]
        state   = combo["state"]
        key     = (test, loc_key)
        label   = f"{test}/{loc_key}"

        if key in completed_keys:
            skip_count += 1
            continue

        if dry_run:
            print(f"  [DRY-RUN {i}/{len(combos)}] {label}", flush=True)
            continue

        prompt = VALUES_PROMPT_TEMPLATE.format(
            year=year, test=test, city=city, state=state, loc_key=loc_key
        )

        call_count += 1
        print(f"  [{i}/{len(combos)}] {label} -> Claude API...", flush=True)
        result, cost = call_claude_pdf(client, pdf_b64, prompt, label,
                                       max_retries=3, max_tokens=16000)
        # 16000 is plenty per (Test, City) — each combo has at most ~50 strains × 9 traits
        total_cost += cost

        if "_error" in result or "_parse_error" in result:
            print(f"    [ERROR] {label}: {result.get('_error') or result.get('_parse_error')}",
                  flush=True)
            err_path = qc_dir / f"error_{test.replace('/', '_')}_{loc_key}.json"
            err_path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                encoding="utf-8")
            # NOTE: deliberately NOT adding errored combos to completed_keys /
            # completed_records. This means --resume will retry them on the
            # next run, which is the desired behavior (otherwise transient
            # API errors silently drop those combos).
            continue

        cells = result.get("cells", []) or []
        for c in cells:
            c["Test"]    = test
            c["City"]    = city
            c["State"]   = state
            c["LocKey"]  = loc_key
            c["Year"]    = year
            all_cells.append(c)

        # Confidence breakdown for this combo
        conf_counts = {"high": 0, "medium": 0, "low": 0, "missing": 0}
        for c in cells:
            cv = (c.get("confidence") or "missing").lower()
            conf_counts[cv if cv in conf_counts else "missing"] += 1
        print(f"    {len(cells)} cells | high={conf_counts['high']} "
              f"med={conf_counts['medium']} low={conf_counts['low']} "
              f"miss={conf_counts['missing']} | "
              f"call ${cost:.4f} | total ${total_cost:.4f}", flush=True)

        completed_keys.add(key)
        completed_records.append({"test": test, "loc_key": loc_key})

        # Checkpoint after every call
        progress_path.write_text(
            json.dumps({"completed": completed_records,
                        "cells": all_cells,
                        "cost_so_far": round(total_cost, 4)},
                       ensure_ascii=False),
            encoding="utf-8"
        )

    print(f"\n  Calls made: {call_count} | Skipped (resumed): {skip_count}",
          flush=True)
    print(f"  Total cells collected: {len(all_cells)}", flush=True)
    print(f"  Estimated cost this run: ${total_cost:.4f}", flush=True)

    return {"calls": call_count, "skipped": skip_count,
            "cells": len(all_cells), "cost_usd": round(total_cost, 4)}


# ---------------------------------------------------------------------------
# Phase 3 — Build long CSVs from collected cells + roster
# ---------------------------------------------------------------------------

# Map our per-cell phenotype keys back to the raw "{LABEL} ({units})" form so
# the resulting CSV is interchangeable with extract_nust_xlsx.py output.
_RAW_PHENO_BY_KEY = {key: raw for (key, raw, _u) in TRAITS}
_UNITS_BY_KEY     = {key: u for (key, _r, u) in TRAITS}


def build_long_csvs(roster: dict, all_cells: list[dict], year: str,
                    out_dir: Path, qc_dir: Path, prefix: str) -> None:
    """Phase 3: turn collected cells + roster into the 4 long CSVs + QC CSV."""
    print("\n=== Phase 3 — Building long CSVs ===", flush=True)

    # ---------------- Phenotypes CSV ----------------
    pheno_rows = []
    qc_rows    = []
    for c in all_cells:
        strain    = str(c.get("strain") or "").strip()
        pheno_key = str(c.get("phenotype") or "").strip()
        if not strain or not pheno_key:
            continue
        value     = c.get("value")
        if value is None:
            continue  # don't carry empty cells in long CSV
        raw_name  = _RAW_PHENO_BY_KEY.get(pheno_key, pheno_key)
        units     = _UNITS_BY_KEY.get(pheno_key, "")
        pheno_rows.append({
            "Strain":    strain,
            "Year":      year,
            "Test":      c["Test"],
            "City":      c["City"],
            "State":     c["State"],
            "Phenotype": raw_name,
            "Value":     value,
            "Units":     units,
        })
        qc_rows.append({
            "Year":       year,
            "Test":       c["Test"],
            "City":       c["City"],
            "State":      c["State"],
            "Strain":     strain,
            "Phenotype":  pheno_key,
            "Value":      value,
            "Confidence": (c.get("confidence") or "").lower(),
            "Note":       c.get("note") or "",
        })

    pheno_df = pd.DataFrame(pheno_rows).drop_duplicates()
    pheno_path = out_dir / f"{prefix}_phenotypes.csv"
    pheno_df.to_csv(pheno_path, index=False)
    print(f"  phenotypes: {len(pheno_df):,} rows -> {pheno_path.name}",
          flush=True)

    qc_df = pd.DataFrame(qc_rows)
    if not qc_df.empty:
        qc_path = qc_dir / f"qc_{year}_pdf_extract.csv"
        qc_df.to_csv(qc_path, index=False)
        conf_counts = qc_df["Confidence"].value_counts().to_dict()
        print(f"  QC:         {len(qc_df):,} rows -> {qc_path.name}  "
              f"confidence: {conf_counts}", flush=True)

    # ---------------- Strains + Parentage CSVs (from roster) ----------------
    strain_rows   = []
    parent_rows   = []
    for t in roster.get("tests", []):
        test_code = t.get("test_code", "")
        for s in t.get("strains", []):
            name = (s.get("name") or "").strip()
            if not name:
                continue
            strain_rows.append({"Strain": name, "Test": test_code, "Year": year})
            parent_rows.append({
                "Strain":      name,
                "Parentage":   s.get("parentage") or "",
                "PrevTesting": s.get("prev_testing") or "",
                "Generation":  s.get("generation") or "",
                "Test":        test_code,
                "Year":        year,
            })

    strains_df = pd.DataFrame(strain_rows).drop_duplicates()
    strains_path = out_dir / f"{prefix}_strains.csv"
    strains_df.to_csv(strains_path, index=False)
    print(f"  strains:    {len(strains_df):,} rows -> {strains_path.name}",
          flush=True)

    parent_df = pd.DataFrame(parent_rows).drop_duplicates()
    parent_path = out_dir / f"{prefix}_parentage.csv"
    parent_df.to_csv(parent_path, index=False)
    print(f"  parentage:  {len(parent_df):,} rows -> {parent_path.name}",
          flush=True)

    # ---------------- Summary CSV (tp4-equivalent averages) ----------------
    # We derive per-(Strain, Test) averages from the per-City cells (mean of
    # non-Mean rows for YieldBuA, Lodging, Height, etc.). This stands in for
    # the tp4 averages that the XLSX pipeline ingests directly.
    sum_rows = []
    if not pheno_df.empty:
        per_loc = pheno_df[pheno_df["City"] != "Mean"].copy()
        if not per_loc.empty:
            # numeric coerce for averageable traits
            per_loc["NumVal"] = pd.to_numeric(per_loc["Value"], errors="coerce")
            grouped = (
                per_loc.groupby(["Strain", "Test", "Phenotype"])["NumVal"]
                .mean()
                .unstack(fill_value=None)
                .reset_index()
            )
            rename = {
                "YIELD":         "YieldBuA",
                "YIELD RANK":    "Rank",
                "MATURITY":      "Maturity",
                "LODGING":       "Lodging",
                "PLANT HEIGHT":  "HeightIn",
                "SEED QUALITY":  "Quality",
                "SEED SIZE":     "SeedSizeG100",
                "PROTEIN":       "Protein_pct",
                "OIL":           "Oil_pct",
            }
            grouped = grouped.rename(columns=rename)
            for col in rename.values():
                if col not in grouped.columns:
                    grouped[col] = None
            grouped["Year"] = year
            cols = ["Strain", "YieldBuA", "Rank", "Maturity", "Lodging",
                    "HeightIn", "Quality", "SeedSizeG100", "Protein_pct",
                    "Oil_pct", "Test", "Year"]
            sum_rows = grouped[[c for c in cols if c in grouped.columns]]

    if len(sum_rows):
        sum_path = out_dir / f"{prefix}_summary.csv"
        sum_rows.to_csv(sum_path, index=False)
        print(f"  summary:    {len(sum_rows):,} rows -> {sum_path.name}",
              flush=True)
    else:
        print("  summary:    (no rows derived)", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PDF-direct NUST extractor (parallel to extract_nust_xlsx.py)"
    )
    parser.add_argument("--year",    required=True, help="Trial year (e.g. 1990)")
    parser.add_argument("--pdf",     default=None,
                        help="Explicit PDF path (else auto-resolves under R: Red folder)")
    parser.add_argument("--out_dir", required=True,
                        help="Output dir (parallel to output_19XX/ used by combine step)")
    parser.add_argument("--prefix",  default=None,
                        help="CSV filename prefix (default: 'Sojabone-{year}_pdf_extract')")
    parser.add_argument("--test_filter", default=None,
                        help="Restrict Phase 2 to one Test code")
    parser.add_argument("--resume",  action="store_true",
                        help="Skip combos already in progress checkpoint")
    parser.add_argument("--dry_run", action="store_true",
                        help="Phase 1 only — list combos; no Phase 2 API calls")
    parser.add_argument("--api_key", default=None,
                        help="Anthropic API key (overrides .Env / ANTHROPIC_API_KEY)")
    args = parser.parse_args()

    year     = args.year
    out_dir  = Path(args.out_dir);  out_dir.mkdir(parents=True, exist_ok=True)
    qc_dir   = out_dir / "qc";      qc_dir.mkdir(parents=True, exist_ok=True)
    prefix   = args.prefix or f"Sojabone-{year}_pdf_extract"

    pdf_path = resolve_pdf(year, args.pdf)
    if not pdf_path:
        print(f"Error: could not find PDF for year {year}. "
              f"Tried --pdf={args.pdf!r} and {RED_ROOT}/Red-*/Red/{{{year}.pdf,{year}_done.pdf}}.")
        sys.exit(1)
    print(f"PDF resolved: {pdf_path}", flush=True)

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY") or _load_env_file()
    if not api_key:
        print("Error: ANTHROPIC_API_KEY required (set env or .Env or --api_key)")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    pdf_b64 = load_pdf_b64(pdf_path)

    # Phase 1
    roster = run_roster(client, pdf_b64, year, out_dir)
    if "_error" in roster or "_parse_error" in roster:
        print("[ABORT] Roster phase failed.")
        sys.exit(2)

    # Phase 2
    extract_result = run_extraction(
        client, pdf_b64, year, roster, out_dir, qc_dir,
        test_filter=args.test_filter,
        resume=args.resume, dry_run=args.dry_run,
    )

    if args.dry_run:
        print("\nDry run done — no Phase 3 build.")
        return

    # Phase 3 — load all collected cells from the progress file (single source of truth)
    progress_path = out_dir / f"progress_{year}.json"
    if not progress_path.exists():
        print("[ABORT] No progress checkpoint found; nothing to build.")
        sys.exit(3)
    saved = json.loads(progress_path.read_text(encoding="utf-8"))
    build_long_csvs(roster, saved.get("cells", []), year, out_dir, qc_dir, prefix)

    print("\nAll done.")


if __name__ == "__main__":
    main()
