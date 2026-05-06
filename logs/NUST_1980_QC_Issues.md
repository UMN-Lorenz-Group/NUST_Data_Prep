# NUST 1980 — QC Issues Log (PDF vs CSV Values Verification)

**Last updated:** 2026-04-30  
**QC method:** `scripts/qc_pdf_vs_csv.py --mode values` — cell-by-cell PDF vs CSV comparison via Claude API  
**Status:** COMPLETE — all 144 Test×Location combos verified  
**Total cost:** ~$15 (prompt caching active; first call cache-write, subsequent calls cache-read)  
**Raw output:** `output_1980/qc/qc_1980_values.csv`, `output_1980/qc/qc_1980_values_progress.json`

---

## Master Issues Summary

| # | Category | Scope | Tests | Action | Status |
|---|---|---|---|---|---|
| 1 | Column swap — Height Fargo/Morden | 9 strains × 2 cities | UT-00 | Swap + patch from PDF | **DONE** |
| 2 | Missing data — SeedQuality Morden NULL | 9 strains | UT-00 | No action | Confirmed genuine |
| 3 | Cell errors — SeedQuality (2 cells) | 2 cells | UT-00 | Patch from PDF | **DONE** |
| 4 | Cell error — SeedSize Fargo (1 cell) | 1 cell | UT-00 | Patch from PDF | **DONE** |
| 5 | OCR strain names (5 strains) | Multiple locations | PT-I/II/III | Fix script | **DONE** |
| 6 | Column shift — PT-II Yield (Lafayette, Urbana) | 7 cells | PT-II | Patched from PDF | **DONE** |
| 7 | Cell errors — PT-III (4 cells) | 4 cells | PT-III | Patch from PDF | **DONE** |
| 8 | Missing values — NULLs linked to ghost strains | ~11 cells | PT-I/III | Resolves after ISSUE-5 | **Resolved** |
| 9 | Cell errors — PT-IV Lexington Oil (2 cells) | 2 cells | PT-IV | Manual PDF verify first | Needs verify |
| 10 | Wrong Maturity DOY — PT-IV Portageville Loam | 13 cells (rows existed; wrong values) | PT-IV | Patched from PDF/XLSX | **DONE** |
| 11 | OCR strain name — `M72- 107` space | All 8 locations | UT-0 | Merge rows | **DONE** |
| 12 | OCR strain name — `Hardin` / `Hardin (I)` split | 3 locations | UT-I | Merge rows | **DONE** |
| 13 | OCR strain name — `Pella (TII)` → `Pella (III)` | All 23 locations | UT-II | Merge rows | **DONE** |
| 14 | OCR strain name — `U2020325` → `U20325` | All 23 locations | UT-II | Merge rows | **DONE** |
| 15 | OCR strain name — `U566355` → `U56355` | 5 locations | UT-II | Merge rows | **DONE** |
| 16 | OCR strain name — `BSR 320` → `BSR 302` | 6 locations | UT-III | Merge rows | **DONE** |
| 17 | OCR strain name — `K1035` → `K1033` | All 21 locations | UT-IV | Merge rows | **DONE** |
| 18 | OCR strain name — `Ky75-146-74` variants (3 forms) | 15+ locations | UT-IV | Merge rows | **DONE** |
| 19 | OCR strain name — `H76-3840` → `HC76-3840` | 5 locations | UT-IV | Merge rows | **DONE** |
| 20 | Column shift — UT-I Lafayette (Lodging/Height/SeedQuality) | 11 cells | UT-I | Patched from PDF | **DONE** |
| 21 | Column shift — UT-III S. Charleston Lodging (all strains) | 20 cells | UT-III | Patched from PDF | **DONE** |
| 22 | Column shift — UT-IV Manhattan Lodging (all strains) | 12 cells | UT-IV | Patched from PDF | **DONE** |
| 23 | Column shift — UT-IV Powhattan Yield (5 strains) | 5 cells | UT-IV | Patched from PDF | **DONE** |
| 24 | Column shift — UT-II Harrow Yield (3 strains) | 3 cells | UT-II | Patched from PDF | **DONE** |
| 25 | Scattered cell errors (17 cells across 6 tests) | 17 cells | UT-0/I/II/III/IV | Patched from PDF | **DONE** |

---

## Action Plan (fix order)

1. **Fix all OCR strain name duplicates** (ISSUES 5, 11–19) — one consolidated fix script
2. **Cross-check XLSX for all suspected column shifts** (ISSUES 1, 6, 20–24) before patching
3. **Manual PDF verify** ISSUE-9 (PT-IV Lexington Oil) and ISSUE-25 scattered cells
4. **Insert missing Maturity rows** for PT-IV Portageville Loam (ISSUE-10)
5. **Apply all confirmed cell patches** in one pass

---

## CATEGORY A — OCR Strain Name Duplicates

All of these follow the same pattern: OCR misread a strain name, creating a ghost row. Traits end up split between the canonical name and the ghost name. Fix by merging ghost row into canonical and deleting ghost.

### ISSUE-5 · Five OCR strain errors — PT-I, PT-II, PT-III

| Ghost name in CSV | Correct name | Tests/Locations | Traits affected |
|---|---|---|---|
| `A73D29` | `A75D29` | PT-II — all 9 locations | YieldBuA missing for A75D29 |
| `Cnome` | `Gnome` | PT-II/Arlington_WI | YieldBuA missing for Gnome |
| `H277-878` | `HC77-878` | PT-II — Hoytville, Lafayette, Urbana | Protein, Oil |
| `A790134034` | `A79-134034` | PT-I — Corwith, Lamberton | SeedSize |
| `L77-709` | `L78-709` | PT-III — 7 locations | Yield, Lodging, Height, SeedSize, Protein, Oil |

**Fix:** `fixes/fix_strain_ocr_1980.py` — already written; extend with new entries below.

---

### ISSUE-11 · `M72- 107` (extra space) → `M72-107` — UT-0, all 8 locations

Traits split across two rows. Merge under `M72-107`.

---

### ISSUE-12 · `Hardin` / `Hardin (I)` split — UT-I, Arlington, Dundee, Ithaca

Two rows for the same strain. `Hardin (I)` is the correct UT-I designation. Merge, consolidating Maturity and YieldBuA nulls.

---

### ISSUE-13 · `Pella (TII)` → `Pella (III)` — UT-II, all 23 locations

`(III)` OCR'd as `(TII)`. YieldBuA under ghost row, YieldRank/Maturity under canonical. Also affects SeedQuality and SeedSize at some locations. Merge into `Pella (III)`.

---

### ISSUE-14 · `U2020325` → `U20325` — UT-II, all 23 locations

Doubled `20` in strain number. YieldBuA under ghost row, rank/maturity under canonical. Merge into `U20325`.

---

### ISSUE-15 · `U566355` → `U56355` — UT-II, 5 locations (Adelphia, Hoytville, Landisville, Ridgetown, Wooster)

Extra `6`. YieldRank under ghost row. Merge into `U56355`.

---

### ISSUE-16 · `BSR 320` → `BSR 302` — UT-III, 6 locations (Adelphia, Clarksville, Hoytville, Landisville, Lexington, S. Charleston)

Digit transposition (302 → 320). Maturity and YieldBuA under ghost row. Merge into `BSR 302`.

---

### ISSUE-17 · `K1035` → `K1033` — UT-IV, all 21 locations

`K1033` misread as `K1035`. Height and SeedQuality appear under ghost row; Yield/Rank/Maturity under canonical. Merge Height/SeedQuality into `K1033`, remove `K1035`.

---

### ISSUE-18 · `Ky75-146-74` variants — UT-IV, 15+ locations

Three ghost forms created by OCR:
- `KG75-146-74` — most locations
- `K675-146-74` — Lubbock, Powhattan, Portageville, Novelty
- `K775-146-74` — Portageville Clay, Portageville Loam, Manhattan

YieldBuA split from YieldRank/Maturity across rows. Merge all variants into `Ky75-146-74`.

---

### ISSUE-19 · `H76-3840` → `HC76-3840` — UT-IV, 5 locations (Eldorado, Lafayette, Manhattan, Portageville Loam, Queenstown)

`HC` OCR'd as `H`. Protein/Oil appear under ghost row. Merge into `HC76-3840`.

---

## CATEGORY B — Systematic Column/Location Shifts

These require XLSX raw cell cross-check before patching. Pattern is consistent with data entry errors in the source XLSX (values entered under wrong column header).

### ISSUE-1 · Height Fargo/Morden swap — UT-00, all 9 strains  *(CONFIRMED from XLSX)*

**Root cause:** tp10 Height block has column order `Morden → Brandon → Fargo` (swapped vs tp6–tp9 which use `Fargo → Morden → Brandon`). Original data values were entered in the old Fargo-first order under the swapped headers.

**Evidence:** XLSX "Fargo" column = PDF Morden for all 9 strains (perfect match). XLSX "Morden" column ≠ PDF Fargo.

| Strain | XLSX "Morden" | XLSX "Fargo" | PDF Morden | PDF Fargo |
|---|---|---|---|---|
| Clay (0) | 20 | 26 | 26 ✓ | 26 |
| Maple Arrow | 22 | 28 | 28 ✓ | 28 |
| Maple Presto | 21 | 22 | 22 ✓ | 20 |
| McCall | 23 | 27 | 27 ✓ | 27 |
| Portage (00) | 21 | 24 | 24 ✓ | 27 |
| M71-148 | 24 | 26 | 26 ✓ | 26 |
| OT80-1 | 23 | 24 | 24 ✓ | 26 |
| OT80-2 | 22 | 23 | 23 ✓ | 23 |
| OT80-3 | 22 | 24 | 24 ✓ | 25 |

**Fix:** Swap Fargo↔Morden Height values; use PDF ground truth for Fargo. Write `fixes/fix_height_swap_1980.py`.

---

### ISSUE-20 · UT-I / Lafayette_IN — Lodging, Height, SeedQuality, SeedSize (multiple strains)

Multiple traits wrong at a single location — consistent with column mis-assignment in the XLSX.

| Strain | Trait | CSV | PDF |
|---|---|---|---|
| Hardin | Lodging | 1.5 | 1.2 |
| Hodgson 78 (I) | Lodging | 1.5 | 1.9 |
| Evans (0) | Height | 24 | 36 |
| Hardin | Height | 35 | 37 |
| M72-3 | Height | 26 | 29 |
| Corsoy 79 (II) | SeedQuality | 1.5 | 2.0 |
| Evans (0) | SeedQuality | 2.5 | 3.0 |
| Hodgson 78 (I) | SeedQuality | 1.5 | 2.0 |
| M71-80 | SeedQuality | 1.5 | 1.8 |
| M75-2 | SeedQuality | 1.5 | 1.6 |
| Hardin | SeedSize | 14 | 14.9 |

**Action:** Cross-check XLSX tp9/tp10/tp11 blocks for UT-I Lafayette before patching.

---

### ISSUE-21 · UT-III / S. Charleston_OH — Lodging, all strains

All 22+ strains show wrong Lodging values. Likely a single column shift in the XLSX Lodging block for this location. Other traits may also be affected.

| Strain | CSV Lodging | PDF Lodging |
|---|---|---|
| BSR 302 | 3.5 | 3.2 |
| Century (II) | 2.3 | 1.8 |
| Cumberland (III) | 2.3 | 2.0 |
| Williams 79 | 2.0 | 2.5 |
| Union (IV) | 2.7 | 2.9 |
| (all other strains) | various | varies |

**Action:** Cross-check XLSX Lodging block for UT-III S. Charleston.

---

### ISSUE-22 · UT-IV / Manhattan_KS — Lodging, all strains

Every strain at Manhattan has Lodging ~2–3 in CSV; PDF shows 1.0 for all. One-value-for-all pattern strongly suggests a single wrong column was read for this location.

**Action:** Cross-check XLSX Lodging block for UT-IV Manhattan.

---

### ISSUE-23 · UT-IV / Powhattan_KS — Yield, 4 strains

Large gaps suggest row or column shift in XLSX yield block:

| Strain | CSV Yield | PDF Yield |
|---|---|---|
| Williams79 (III) | 16.4 | 13.5 |
| K1033 | 18.8 | 16.4 |
| K1041 | 18.5 | 13.6 |
| HC76-3840 | 11.1 | 16.6 |

**Action:** Cross-check XLSX Yield block for UT-IV Powhattan.

---

### ISSUE-24 · UT-II / Harrow_OH — Yield, 3 strains

Two adjacent strain values appear swapped between rows:

| Strain | CSV Yield | PDF Yield |
|---|---|---|
| A77-211021 | 60.4 | 55.4 |
| A78-122031 | 54.5 | 60.4 |
| Pella (III) | 55.9 | 51.6 |

**Action:** Cross-check XLSX Yield block for UT-II Harrow.

---

### ISSUE-6 · PT-II / Lafayette_IN and Urbana_IL — Yield, multiple strains

Large gaps for Gnome suggest a column shift. Urbana errors are smaller and may be individual cell mistakes.

| Test | City | Strain | CSV | PDF |
|---|---|---|---|---|
| PT-II | Lafayette | Gnome | 18.1 | 51.1 |
| PT-II | Urbana | Century | 42.1 | 43.8 |
| PT-II | Urbana | Gnome | 35.6 | 49.5 |
| PT-II | Urbana | Hardin (I) | 36.6 | 41.9 |
| PT-II | Urbana | Pella (III) | 46.9 | 45.3 |

**Action:** Cross-check XLSX Yield block for PT-II Lafayette and Urbana.

---

## CATEGORY C — Individual Cell Errors (PDF-confirmed or suspected)

### ISSUE-3 · UT-00 SeedQuality — 2 cells

| City | State | Strain | CSV | PDF | Action |
|---|---|---|---|---|---|
| Ashland | WI | Maple Presto | 2.7 | 3.5 | Patch to 3.5 |
| Rosemount | MN | OT80-1 | 3 | 2.0 | Patch to 2.0 |

---

### ISSUE-4 · UT-00 SeedSize — 1 cell

| City | State | Strain | CSV | PDF | Action |
|---|---|---|---|---|---|
| Fargo | ND | Maple Presto | 14.2 | 13.3 | Patch to 13.3 |

Note: SeedSize Fargo/Rosemount column swap suspected for some strains. Verify full SeedSize block before patching.

---

### ISSUE-7 · PT-III — 2 cells

| City | State | Strain | Trait | CSV | PDF | Action |
|---|---|---|---|---|---|---|
| Lafayette | IN | L77-443 | Lodging | 2.3 | 1.8 | Patch to 1.8 |
| Ottumwa | IA | HC76-3863 | Oil | 23.3 | 22.9 | Patch to 22.9 |

---

### ISSUE-9 · PT-IV Lexington Oil — 2 cells  *(needs manual PDF verification)*

CSV matches XLSX exactly; discrepancy is between XLSX source and PDF printed report.

| Strain | XLSX/CSV | PDF | Action |
|---|---|---|---|
| L77-8079 | 22.6 | 20.5 | Open PDF ~p.194 PT-IV Lexington Oil column to confirm |
| L77-8209 | 22.1 | 21.4 | Same |

---

### ISSUE-25 · Scattered cell errors — UT-0 through UT-IV (17 cells, needs XLSX verify)

| Test | City | State | Strain | Trait | CSV | PDF |
|---|---|---|---|---|---|---|
| UT-0 | Elora | ONT | M72-24 | Protein | 42.1 | 43.2 |
| UT-I | Oakes | ND | Evans (0) | SeedQuality | 1.0 | 2.5 |
| UT-I | Ridgetown | ONT | Hardin | Protein | 41.0 | 41.7 |
| UT-I | Lamberton | MN | A78-121014 | SeedSize | 19.4 | 19.6 |
| UT-I | Dekalb | IL | Evans (0) | YieldRank | 10 | 9 |
| UT-I | Dekalb | IL | M75-2 | YieldRank | 9 | 7 |
| UT-II | Ridgetown | ONT | A78-227015 | Lodging | 2.8 | 1.2 |
| UT-II | Ridgetown | ONT | A78-227016 | Lodging | 2.2 | 1.8 |
| UT-II | Ames | IA | A78-122028 | Protein | 37.5 | 40.9 |
| UT-II | Waseca | MN | A78-227013 | Lodging | 2.0 | 1.7 |
| UT-II | Urbana | IL | Pella (III) | SeedQuality | 3.3 | 2.0 |
| UT-III | Elk Point | SD | U36276 | SeedQuality | 3.5 | 3.0 |
| UT-III | Manhattan | KS | HW74-3385 | Lodging | 2.5 | 1.0 |
| UT-IV | Portageville Clay | MO | K1033 | SeedQuality | 1.5 | 2.5 |
| UT-IV | Queenstown | MD | Franklin | SeedQuality | 2.2 | 1.2 |
| UT-IV | Manhattan | KS | H76-3840 | Protein | 42.8 | 42.2 |
| UT-IV | Manhattan | KS | H76-3840 | Oil | 21.5 | 19.1 |

Note: H76-3840 issues will be resolved once ISSUE-19 (HC76-3840 merge) is applied — verify post-merge.

---

## CATEGORY D — Missing Data (extraction gaps)

### ISSUE-8 · PT-I/III — NULL values linked to ghost strains

Most of these will resolve after ISSUE-5 (L77-709 → L78-709 OCR fix). Remaining genuine NULL:

| Test | City | State | Strain | Trait | PDF value | Note |
|---|---|---|---|---|---|---|
| PT-I | Ridgetown | ONT | W442 | Protein | 41.5 | Not linked to ghost strain |
| PT-III | Girard–Urbana | various | L78-709 | Lodging, Height | various | Resolves after ISSUE-5 |
| PT-III | S. Charleston | OH | L77-709 | Multiple | multiple | Resolves after ISSUE-5 |

---

### ISSUE-10 · PT-IV / Portageville Loam_MO — Maturity missing for all 36 strains

**Root cause:** PT-IV Maturity block for southern locations is labeled `tp7` in XLSX (row 1620), not `tp8`. The extraction captured Eldorado/Queenstown/Lexington Maturity correctly but missed Portageville Loam entirely.

**XLSX source data (tp7 block, row 1621):**
- Reference: Union (IV) = 9/15 = DOY 259 (1980 leap year)
- All 36 strain offsets available in col 3 of that block

**Action:** Write `fixes/fix_pt4_portageville_maturity_1980.py` to compute and insert 36 Maturity DOY rows.

---

### ISSUE-2 · UT-00 / Morden_MAN — SeedQuality NULL, all 9 strains *(no action)*

XLSX source has NULL for Morden SeedQuality for every strain. Morden did not report seed quality in 1980. Confirmed genuine missing data.

---

## CATEGORY E — False Positives (no action needed)

### FP-1 · Maturity off-by-1 DOY — widespread across all tests

**Cause:** Claude computes DOY using a non-leap calendar (Feb = 28 days). In 1980 (leap year), this produces a 1-day error for any date after Feb 28. CSV values computed from XLSX are correct. XLSX cross-checks confirm this pattern in UT-00, UT-0, UT-I, UT-III, UT-IV.

Pattern: Claude says `csv_value − 1` or `csv_value + 1`; XLSX confirms CSV is right. No fix needed.

---

### FP-2 · PT-IV Maturity flags — Queenstown and Eldorado

Claude computed wrong DOY from PDF offsets (varied errors, not the uniform off-by-1 pattern). XLSX tp7 block cross-check confirms CSV values are correct for all strains at both locations. No fix needed.

---

### FP-3 · Ambiguous/matching noise

Claude flags these as discrepancies when values actually match:
- Integer vs decimal: `3` vs `3.0`
- Asterisk suffix: `9*` vs `9`
- Confirmed-matching values where Claude adds explanatory notes

**Prompt improvement:** Add to `VALUES_PROMPT_TEMPLATE`: "If the numeric value matches (ignoring trailing `.0` and `*` suffix), do NOT list it."

---

## Pre-existing Open Items (from NUST_1980_Open_Items.md)

- **FLAG 1** — PlantingDate NULL for 5 locations — manual PDF lookup needed
- **FLAG 2** — Conductor NULL all 141 rows — not in 1980 publication
- **FLAG 3** — checksTable RM NULL all 26 rows — pre-RM era
- **FLAG 4** — 194 null-DOY rows — expected missing data

---

## XLSX Source Structure Notes

### UT-00 tp marker column order (confirmed)

| tp marker | Table | Location column order |
|---|---|---|
| tp6 | Yield (bu/a) | Fargo → Morden → Brandon |
| tp7 | Yield Rank | Fargo → Morden → Brandon |
| tp8 | Maturity | Fargo → Morden → Brandon |
| tp9 | Lodging | Fargo → Morden → Brandon |
| **tp10** | **Height** | **Morden → Brandon → Fargo** ← swapped |
| **tp11a** | **SeedQuality** | **Morden → Brandon → Fargo** ← swapped |
| **tp11b** | **SeedSize** | **Morden → Brandon → Fargo** ← swapped |
| tp12a | Protein | Ottawa, Elora, Ashland, Morden, Rosemount only |
| tp12b | Oil | Ottawa, Elora, Ashland, Morden, Rosemount only |

### PT-IV tp7 Maturity block (row 1621, file 2)

Covers: Portageville Loam, Portageville Clay, Belleville, Eldorado, Queenstown, Lexington (6 southern locations). Labeled `tp7` instead of `tp8` — extraction captured all locations except Portageville Loam (see ISSUE-10).
