"""
check_k1033_pdf.py
One-shot PDF lookup for K1033 vs K1033 Douglas in UT-IV (1980).

Asks Claude to find:
  1. K1033's descriptive code (seed color, hilum, maturity group, pubescence, etc.)
     in the UT-IV descriptive/notes section of the PDF
  2. Any disease data rows listed under K1033 (as opposed to K1033 Douglas)
  3. Confirm which name appears where (K1033 vs K1033 Douglas)

Single call with PDF cache-write — cost is one cache-write (~$0.01-0.02 for this PDF).
"""
import sys, base64
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
import anthropic

# ── config ────────────────────────────────────────────────────────────────────
PDF_PATH = Path(__file__).parent.parent / "input_1980" / "1980_done.pdf"

def _load_api_key() -> str:
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
    key = __import__("os").getenv("ANTHROPIC_API_KEY", "")
    if key:
        return key
    raise RuntimeError("ANTHROPIC_API_KEY not found in .Env or environment")

PROMPT = """You are reviewing a 1980 NUST (North American Uniform Soybean Trial) annual report PDF.

I need you to look at the UT-IV section and find information about two closely related entries:
  - "K1033" (also possibly written as K 1033)
  - "K1033 Douglas" (also possibly K1033-Douglas or similar)

Please answer these specific questions:

1. DESCRIPTIVE/VARIETY DATA: In the descriptive characteristics table or notes section
   for UT-IV, does K1033 appear as a separate entry from K1033 Douglas?
   If yes, what are its descriptive codes or characteristics (seed color, hilum color,
   pubescence, maturity group, flower color, pod color, etc.)?

2. DISEASE DATA: In any disease resistance or disease rating table for UT-IV,
   does K1033 appear as a separate entry? If yes, list the disease traits and
   values shown for K1033.

3. STRAIN LISTING: In the UT-IV strain/entry list (the roster at the start of the group),
   are both K1033 and K1033 Douglas listed? Or only one of them?

4. CONFIRMATION: In the yield/performance tables for UT-IV, which name appears:
   K1033, K1033 Douglas, or both?

Return ONLY valid JSON (no markdown fences):
{
  "utiv_strain_roster": {
    "K1033_present": true/false,
    "K1033_Douglas_present": true/false,
    "note": "..."
  },
  "descriptive_data": {
    "K1033": {
      "found": true/false,
      "descriptive_code": "<code or null>",
      "characteristics": "<any listed traits or null>",
      "note": "..."
    },
    "K1033_Douglas": {
      "found": true/false,
      "descriptive_code": "<code or null>",
      "note": "..."
    }
  },
  "disease_data": {
    "K1033": {
      "found": true/false,
      "traits": [{"trait": "...", "value": "..."}],
      "note": "..."
    },
    "K1033_Douglas": {
      "found": true/false,
      "traits": [{"trait": "...", "value": "..."}],
      "note": "..."
    }
  },
  "yield_tables": {
    "name_used": "<K1033 | K1033 Douglas | both | unclear>",
    "note": "..."
  }
}
"""

def main():
    api_key = _load_api_key()
    client  = anthropic.Anthropic(api_key=api_key)

    print(f"Loading PDF: {PDF_PATH.name} ({PDF_PATH.stat().st_size // 1024} KB)...", flush=True)
    pdf_b64 = base64.standard_b64encode(PDF_PATH.read_bytes()).decode("utf-8")
    print(f"PDF loaded ({len(pdf_b64) // 1024} KB base64). Sending request...", flush=True)

    response = client.beta.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        betas=["pdfs-2024-09-25", "prompt-caching-2024-07-31"],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": PROMPT,
                    },
                ],
            }
        ],
    )

    usage = response.usage
    cwrite = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cread  = getattr(usage, "cache_read_input_tokens",     0) or 0
    inp    = getattr(usage, "input_tokens",                0) or 0
    out    = getattr(usage, "output_tokens",               0) or 0
    cost   = (inp * 3.00 + out * 15.00 + cwrite * 3.75 + cread * 0.30) / 1_000_000

    print(f"\nTokens — input: {inp}, output: {out}, "
          f"cache_write: {cwrite}, cache_read: {cread}")
    print(f"Estimated cost: ${cost:.4f}\n")
    print("=" * 60)
    print(response.content[0].text)
    print("=" * 60)

if __name__ == "__main__":
    main()
