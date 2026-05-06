#!/usr/bin/env python
"""
extract_test_map_pdf.py
=======================
Extract Group → NUST test name/code mapping from a historical NUST PDF report
using the Anthropic Files API (claude-sonnet-4-6 with PDF vision).

Outputs:
  <pdf_stem>_test_map.json   — full Claude response
  Console: R TEST_MAP snippet ready to paste into NUST_HistProcessing.R

Usage:
    python extract_test_map_pdf.py --file input_1980/1980_done.pdf
    python extract_test_map_pdf.py --file input_1980/1980_done.pdf --api_key sk-ant-...
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


EXTRACT_PROMPT = """\
This is a historical NUST (North American Uniform Soybean Trial) report.

Each trial year contains several entry groups, each belonging to an official NUST uniform test.
Test codes follow patterns such as: UT-0 (or UT0), UT-I, UT-II, UT-III, UT-IV, UT-V MG, or similar.
They may be labeled as "Uniform Test 0", "Group I", "Preliminary Test", "Test UT-I", etc.

Your task:
1. Identify how many entry groups are in this document.
2. For each group, determine its official NUST test code and full name.
3. Note any maturity group or regional designation if specified.

Return ONLY a JSON object with this exact structure (no markdown fences):
{
  "year": "<trial year visible in the document>",
  "total_groups": <integer>,
  "groups": [
    {
      "group_number": 1,
      "test_code": "<official short code, e.g. UT-0>",
      "test_name": "<full name, e.g. Uniform Test 0>",
      "maturity_group": "<MG label if stated, else null>",
      "notes": "<any ambiguity or inference made>"
    }
  ],
  "document_notes": "<observations about document structure or test naming conventions>"
}
"""


def upload_pdf(client: anthropic.Anthropic, pdf_path: Path) -> str:
    print(f"Uploading {pdf_path.name} ({pdf_path.stat().st_size / 1e6:.1f} MB) ...", flush=True)
    with open(pdf_path, "rb") as f:
        resp = client.beta.files.upload(
            file=(pdf_path.name, f, "application/pdf"),
        )
    print(f"  file_id: {resp.id}", flush=True)
    return resp.id


def extract_map(client: anthropic.Anthropic, file_id: str,
                max_retries: int = 3, retry_delay: int = 20) -> dict:
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"  Retry {attempt}/{max_retries} (waiting {retry_delay}s)...", flush=True)
            time.sleep(retry_delay)
        try:
            response = client.beta.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                betas=["files-api-2025-04-14"],
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {"type": "file", "file_id": file_id},
                        },
                        {"type": "text", "text": EXTRACT_PROMPT},
                    ],
                }],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)

        except json.JSONDecodeError as e:
            print(f"  JSON parse error on attempt {attempt}: {e}", flush=True)
            if attempt == max_retries:
                return {"_parse_error": str(e), "_raw": raw}
        except Exception as e:
            print(f"  API error on attempt {attempt}: {e}", flush=True)
            if attempt == max_retries:
                return {"_error": str(e)}

    return {"_error": "All retries exhausted"}


def print_r_snippet(result: dict) -> None:
    groups = result.get("groups", [])
    if not groups:
        return
    print("\n--- Paste into NUST_HistProcessing.R (TEST_MAP block) ---")
    print("TEST_MAP <- c(")
    for g in groups:
        n = g.get("group_number", "?")
        code = g.get("test_code", "UNKNOWN")
        print(f'  "Group_{n}" = "{code}",')
    print(")")


def _load_env_file() -> str | None:
    """Read API key from .Env file in the same directory as this script."""
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


def main():
    parser = argparse.ArgumentParser(
        description="Extract Group→TestCode mapping from NUST PDF via Claude Files API"
    )
    parser.add_argument("--file", required=True, help="Path to NUST PDF report")
    parser.add_argument("--api_key", default=None,
                        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    parser.add_argument("--out", default=None,
                        help="Output JSON file (default: <pdf_stem>_test_map.json)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY") or _load_env_file()
    if not api_key:
        print("Error: API key required. Add it to .Env, set ANTHROPIC_API_KEY, or use --api_key.")
        sys.exit(1)

    pdf_path = Path(args.file)
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}")
        sys.exit(1)

    out_path = Path(args.out) if args.out else pdf_path.parent / f"{pdf_path.stem}_test_map.json"
    client = anthropic.Anthropic(api_key=api_key)

    file_id = upload_pdf(client, pdf_path)

    print("Extracting group→test mappings...", flush=True)
    result = extract_map(client, file_id)

    print("\n--- Claude response ---")
    print(json.dumps(result, indent=2))

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved: {out_path}")

    print_r_snippet(result)

    try:
        client.beta.files.delete(file_id)
        print(f"\nDeleted file {file_id} from Anthropic Files API.")
    except Exception:
        pass


if __name__ == "__main__":
    main()
