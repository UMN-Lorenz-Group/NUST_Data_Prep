# NUST 1980 — Open Items
**Date recorded:** 2026-04-27  
**Pipeline status:** Extraction complete, validated (21,261 rows approved, 0 flagged)

All items below are data-boundary issues inherent to the 1980 era, not pipeline failures.

---

## FLAG 1 — PlantingDate NULL (5 rows)

| Test | City | State | Note |
|---|---|---|---|
| PT-IV | Portageville | MO | Plain Portageville entry absent from supplemental section |
| UT-II | Harrow | OH | Not printed in 1980 supplemental |
| UT-III | Ashland | KS | Not printed in 1980 supplemental |
| UT-III | Greenfield | IL | Not printed in 1980 supplemental |
| UT-III | Sullivan | IL | Not printed in 1980 supplemental |

**Resolution:** Manual lookup from printed 1980 NUST PDF (`input_1980/1980_done.pdf`), pages covering PT-IV and UT-III location tables.

---

## FLAG 2 — Conductor NULL (all 141 locationsTable rows)

**Reason:** Conductors (site PIs) were not listed by location in the 1980 NUST publication. This is a consistent gap for early-era years (pre-~1990).  
**Resolution:** Not resolvable from the source document. Leave NULL for 1980 and earlier years unless a separate personnel directory is identified.

---

## FLAG 3 — checksTable RM NULL (all 26 rows)

**Reason:** Numeric relative maturity (RM) ratings were not assigned to soybean varieties until the mid-1980s. The 1980 NUST publication reports maturity group (MG 00 through IV) only.  
**Resolution:** Requires a separate historical MG → RM conversion table. Candidate source: USDA/SCS soybean variety performance records or a published RM assignment timeline. Until that table exists, RM stays NULL for all pre-RM era years.  
**Scope:** Affects all years roughly 1941–1984.

---

## FLAG 4 — 194 null-DOY rows in maturityVerification (expected missing data)

**Reason:** All 194 rows have `OriginalMaturity = NaN` — maturity was simply not recorded at those locations. This is NOT a computation failure; the DOY pipeline correctly produces no output when there is no input.

**Affected location patterns:**
- UT-00 / Brandon MAN — Canadian northern stations often omitted maturity
- UT-0 / Fargo ND — similar
- UT-I / Corwith IA and Oakes ND — yield-only locations for some strains
- PT-I / Corwith IA — all entries null (yield-only preliminary site)
- UT-III / Ottumwa IA, Novelty MO, Powhattan KS — maturity not reported for several strains
- UT-IV / Novelty MO, Clinton MO, Powhattan/Ottawa KS — similar
- PT-IV / Lexington KY — partial null

**Resolution:** No action needed. These are accurately recorded as NULL in `combined_1980_phenotypesTable.csv`.

---

## Validator rule updates applied (2026-04-27)

The following known omissions were added to `KNOWN_TRAIT_OMISSIONS` in `validate_nust_hist.py` after confirming against the 1980 source PDF:

| Pattern | Exempt traits | Reason |
|---|---|---|
| `PT-*` (all Preliminary Tests) | YieldRank | Rank not assigned in PT series |
| `PT-III` | YieldRank, Maturity | MG III prelim also omitted maturity |
| `UT-0` | YieldRank | Not reported in 1980 source PDF |
| `UT-III` | YieldRank | Not reported in 1980 source PDF |

Strain-count consistency tolerance widened from ±2 to ±5 to accommodate the normal pattern where quality/maturity traits have fewer strains than yield within the same test.

---

## Files produced — 1980

| File | Rows | Notes |
|---|---|---|
| `combined_1980_phenotypesTable.csv` | 21,261 | All state codes canonical; 3 OCR values nulled |
| `combined_1980_locationsTable.csv` | 141 | lat/lon 141/141; PlantingDate 136/141 |
| `combined_1980_strainsTable.csv` | 316 | — |
| `combined_1980_checksTable.csv` | 26 | RM NULL (see FLAG 3) |
| `combined_1980_parentageTable.csv` | 316 | — |
| `combined_1980_MetaTable.csv` | 655 | YieldBuA only |
| `combined_1980_maturityAnchorsTable.csv` | — | Anchor reference per Test×Location |
| `combined_1980_maturityVerification.csv` | 2,495 | DOY 2,301/2,495; 194 expected NULL |
| `validated/combined_1980_phenotypesTable_approved.csv` | 21,261 | All rows approved |
| `validated/combined_1980_phenotypesTable_review_flagged.csv` | 0 | Clean |
