# NUST Historical Batch Processing — Cost Estimate
**Date:** 2026-04-27
**Baseline:** 1980 processing = $13.50 (164 entries, 10 tests, 2 XLSX files)

---

## Cost Drivers

Each XLSX file is chunked by group (tp2 markers); large groups split further at tp6/tp7. Every chunk = 1+ Claude API calls (`claude-sonnet-4-6`). Total cost scales with:
- Number of entries (strains) per year
- Number of tests (maturity groups) per year
- Prompt length (era-aware addenda add input tokens)

---

## Estimate by Era

| Era | Years | Avg entries | Avg tests | Est. $/yr | Subtotal |
|---|---|---|---|---|---|
| Early (1941–1955) | ~15 | 30–60 | 3–5 | $3–5 | ~$60 |
| Mid (1956–1969) | ~14 | 60–100 | 4–6 | $5–8 | ~$90 |
| Transition (1970–1979) | ~9 | 100–140 | 6–8 | $8–12 | ~$90 |
| Late (1981–1986) | ~6 | ~160 | 8–10 | ~$13 | ~$80 |

**Estimated total: $300–420** for ~44 XLSX-processable years (~$7–9/year weighted average).

---

## Exclusions

| Year(s) | Reason | Status |
|---|---|---|
| 1980 | Already processed | Complete |
| 1975 | PDF-only, no XLSX | Separate extraction path needed |
| 1987–1988 | Fragmented XLSX structure | Separate assembler needed |

---

## Caveats (could push cost higher)

- **OCR artifacts** in early years may trigger multi-turn clarification calls
- **Era-aware system prompt** addenda increase input token count per call
- **1987/1988 fragmented files** may require multiple re-processing passes
- **1975 PDF path** cost unknown until that pipeline is built

---

## Recommended Approach: Staged Batch Run

Before committing to the full run, sample one year from each era to calibrate actual per-call cost:

1. Pick a year from 1941–1955 (e.g., 1950)
2. Pick a year from 1956–1969 (e.g., 1963)
3. Pick a year from 1970–1979 (e.g., 1972)

~$30 total to validate all three eras before spending the remainder.

---

## Reference

- **Extraction script:** `scripts/extract_nust_xlsx.py`
- **Validation script:** `scripts/validate_nust_hist.py`
- **Era-aware prompt notes:** `docs/system_prompt_multiyr_notes.md`
- **Source XLSX files:** `R:/NUST_Historical_Data/Green-*/Green/`
