# System Prompt — Multi-Year Modification Notes

**Scope:** `extract_nust_xlsx.py` → `SYSTEM_PROMPT` constant  
**Data range:** 1941–1986 (Green folder XLSX files)  
**Analysis basis:** Column A tp-marker scan + trait label scan across all year XLSX files  

---

## Era Overview

The NUST XLSX files fall into three structural eras. The current system prompt was designed for the **Modern** era (validated on 1980). Earlier eras require addenda.

| Era | Years | Key differences |
|---|---|---|
| Early | 1941–1956 | Few traits; no tp3a/tp3b; City-State location format; many tp?? sections; merged tp tables |
| Transitional | 1957–1969 | Most traits present; mixed location formats; merged tp markers common; multi-year labels mixed in |
| Modern | 1970–1986 | Full tp suite; State-City location format; minor OCR noise only |

---

## 1. Merged / Fused tp Markers

Several years compress two sub-tables into one section. The current prompt has no handling for these.

| Observed marker | Years seen | Action |
|---|---|---|
| `tp6+7` | 1943, 1946, 1947, 1959 | Extract as both tp6 (yield) and tp7 (yield rank) from same block |
| `tp9+10` / `tp9+tp10` | 1945, 1950 | Extract as tp9 (lodging) and tp10 (height) |
| `tp8+11a` | 1946 | Extract as tp8 (maturity) and tp11a (seed quality) |
| `tp8+12a` | 1945 | Extract as tp8 (maturity) and tp12a (protein) |
| `tp12a & tp12b` | 1959 | Extract as tp12a (protein) and tp12b (oil) |
| `tp10 & tp12b` | 1957 | Extract as tp10 (height) and tp12b (oil) |
| `tp7+8` | 1987 frag. | Extract as tp7 (yield rank) and tp8 (maturity) |

**Prompt addition needed:** When a merged marker is encountered, treat the block as containing both traits. Use column headers to identify which columns belong to which trait.

---

## 2. Noisy / Malformed tp Codes

OCR and formatting artifacts produce non-standard tp values in column A.

| Observed value | Years | Correct interpretation |
|---|---|---|
| `tp??`, `tp???` | 1941–1963 scattered | Unknown section — **skip entirely** (treat like tp5) |
| `tptp11a` | 1968, 1969 | Duplicate prefix OCR error — treat as `tp11a` |
| `tp 2`, `tp 7` | 1959 | Spaces in marker — treat as `tp2`, `tp7` |
| `tp6 (Continued)` | 1944 | Continuation of previous tp6 block — merge with prior tp6 data |
| `tp2 (NB Baie swak beeld)` | 1979 | Afrikaans annotation — treat as `tp2` |
| `tp24` | 1959 | OCR error — skip |
| `tp3c` | 1972 | Unknown sub-type — extract as-is into `descriptive` with note |
| `tp3` (bare) | 1964, 1971 | Ambiguous — treat as `tp3a` if contains morphological data |
| `tp` (bare) | 1947, 1954–1956, 1970 | Section separator artifact — skip |

**Prompt addition needed:** List of fuzzy-match rules for malformed tp codes. Instruct Claude to flag unrecognised markers rather than silently skipping.

---

## 3. Trait Label Normalization — Missing Mappings

The current prompt covers Modern-era labels well. The following need to be added.

### Yield
```
"Yield in bushels per acre", "Yield in Bu/A", "Yield Bu/A",
"Yield (bushels per acre)", "Yields in bushels", "Summary of Yields...",
"Summary Yield in bushels", "Summary Yields", "Yield summary",
"YIELD (bu./A)", "1970 YIELD (bu/a)", "{year} YIELD (bu/a)"  → "YIELD (bu/a)"
```

### Yield Rank
```
"Rank of Yield", "Rank Yield", "Summary Yield Rank"  → "YIELD RANK"
```

### Maturity
```
"MATURITY (relative date)", "MATURITY DATE", "Maturity data",
"Summary Maturity", "Summary Maturity data", "Maturity (date)"  → "MATURITY (date)"
```
> **Note:** "relative date" (days from standard) vs calendar date distinction exists but both map to same column; preserve original value as-is.

### Plant Height
```
"HEIGHT (inches)", "Height", "Plant height",
"Summary of Height data", "Summary Plant Height",
"Summary Plant Height (in inches)", "PLANT HEIGHT (in)", "PLANT HEIGHT (in.)"  → "PLANT HEIGHT (inches)"
```

### Lodging
```
"Lodging", "Lodging Score", "Summary of lodging data",
"LODGING (SCORE)", "Summary Lodging"  → "LODGING (score)"
```

### Seed Quality
```
"QUALITY (score)", "Seed Quality Score", "Seed quality",
"Seed quality scores", "Summary of seed quality",
"Summary Seed Quality"  → "SEED QUALITY (score)"
```

### Seed Size
```
"Seed Weight", "Seed weight", "Size (g/100)",
"Summary of seed weight data in grams per 100"  → "SEED SIZE (g/100)"
```
> **Unit flag:** Early years (1941–~1968) use `"SEED WEIGHT (cg)"` — centigrams, not g/100 seeds. These are **not equivalent**. Extract as `"SEED WEIGHT (cg)"` (separate phenotype name) rather than remapping to `"SEED SIZE (g/100)"`.

### Protein
```
"Percentage of Protein", "Percentage of protein",
"% Protein", "% protein", "Protein", "Percentages of protein",
"PROTEIN  (%)", "PROTIEN (%)"  → "PROTEIN (%)"
```

### Oil
```
"Percentage of Oil", "Percentage oil", "Percentage of oil",
"% Oil", "% OIL", "Oil (%)", "Oil", "Percentages of oil",
"YIELD (bu./A)"  → "OIL (%)"
```
> Note: `"YIELD (bu./A)"` appearing in an Oil column is an OCR artifact — verify context before mapping.

### New trait — Iodine Number (1943–~1948 only)
```
"Iodine number of oil", "Iodine Number of Oil"  → "IODINE NUMBER OF OIL"
```
Extract into the `phenotypes` table as a per-location trait. Not present after ~1948.

### Skip these (multi-year summaries — treat like tp5)
```
"2-year summary Yield...", "3-year summary...", "4-year summary...",
"Five-year summary...", "Six-year summary...", "{n}-year mean Yield",
"1968-70 MEAN YIELD", "1968-70 RANK", "{year1}-{year2} MEAN",
"Three-year summary", "Four-year summary"  → SKIP
```

### Skip these (continuation labels — no data row, just a header repeat)
```
"(Continued)", "(cont.)", "(continued)", "(Contained)"  → SKIP row, continue current table
```

---

## 4. Location Format — Early Years Use Reversed Order

The current prompt normalizes `"State. City"` format (e.g. `"Minn. Morris"`). Early years (pre-~1966) use `"City State"` format.

### US state abbreviations to add (City-State format)
| Abbreviation | State |
|---|---|
| `Ill.` | IL |
| `Ind.` | IN |
| `Mo.` | MO |
| `Wis.` | WI |
| `Mich.` | MI |
| `Minn.` | MN |
| `N.D.` | ND |
| `S.D.` | SD |
| `Kans.` | KS |
| `Md.` | MD |
| `Va.` | VA |
| `Pa.` | PA |
| `Del.` | DE |
| `N.J.` | NJ |
| `Ohio` | OH |
| `Ore.` | OR |
| `Wash.` | WA |
| `Neb.` | NE |

### Canadian province abbreviations to add
| Abbreviation | Province |
|---|---|
| `Ont.` | ONT |
| `Man.` | MAN |
| `Sask.` | SK |

### Specific location mappings to add
```
"Fargo N.D."        → city="Fargo",       state="ND"
"Columbia Mo."      → city="Columbia",     state="MO"
"Eau Claire Wis."   → city="Eau Claire",   state="WI"
"Madison Wis."      → city="Madison",      state="WI"
"Ashland Wis."      → city="Ashland",      state="WI"
"Guelph Ont."       → city="Guelph",       state="ONT"
"Ottawa Ont."       → city="Ottawa",       state="ONT"
"Ridgetown Ont."    → city="Ridgetown",    state="ONT"
"Harrow Ont."       → city="Harrow",       state="ONT"
"Morris Minn."      → city="Morris",       state="MN"
"Crookston Minn."   → city="Crookston",    state="MN"
"Lamberton Minn."   → city="Lamberton",    state="MN"
"East Lansing Mich."→ city="East Lansing", state="MI"
"Mt. Morris Ill."   → city="Morris",       state="IL"
"Urbana Ill."       → city="Urbana",       state="IL"
"DeKalb Ill."       → city="DeKalb",       state="IL"
"Beltsville Md."    → city="Beltsville",   state="MD"
"Georgetown Del."   → city="Georgetown",   state="DE"
"State College Pa." → city="State College",state="PA"
"Lafayette Ind."    → city="Lafayette",    state="IN"
"Evansville Ind."   → city="Evansville",   state="IN"
"Vincennes Ind."    → city="Vincennes",    state="IN"
"Prosser Wash."     → city="Prosser",      state="WA"
"Ontario Ore."      → city="Ontario",      state="OR"
"Manhattan Kans."   → city="Manhattan",    state="KS"
"Morden Man."       → city="Morden",       state="MAN"
"Brandon Man."      → city="Brandon",      state="MAN"
```

### Footnote/superscript stripping
Many early-year location headers include footnote markers: `"Guelph Ont.1"`, `"Fall City Wis.1"`, `"Mt. Morris Ill.¹"`, `"DeKalb Ill. 1"`. Strip trailing digits and superscript characters before normalizing.

---

## 5. Sub-Tables Absent in Early Years

These sub-tables are optional — if absent, return an empty list. The prompt already states this but should be explicit per era:

| Sub-table | First reliable appearance |
|---|---|
| `tp1` (global parentage) | ~1957 |
| `tp3b` (disease resistance) | ~1957 |
| `tp3a` (descriptive/morphological) | ~1963 |
| `tp11b` (seed size per-location) | ~1942 |
| `tp12a/tp12b` (protein/oil per-location) | ~1942 |

---

## 6. Recommended Implementation Strategy

Rather than one monolithic system prompt, use a **base prompt + era addendum** approach:

```python
ERA_ADDENDUM = {
    "early":        "...",   # 1941–1956
    "transitional": "...",   # 1957–1969
    "modern":       "",      # 1970–1986 — no addendum needed
}

def get_era(year: int) -> str:
    if year <= 1956: return "early"
    if year <= 1969: return "transitional"
    return "modern"
```

The addendum for each era would be appended to the base `SYSTEM_PROMPT` and cover:
- Which location format to expect
- Which tp markers are likely absent or fused
- Which trait labels are era-specific
- Whether iodine number should be extracted

This keeps the modern-era prompt clean and avoids confusing Claude with rules that don't apply to the year being processed.

---

## 7. Open Questions / To Verify

- [ ] **Seed Weight (cg) vs Seed Size (g/100):** Confirm conversion factor or keep as separate phenotype
- [ ] **"relative date" maturity:** Confirm how relative dates are encoded (e.g., days from Sept 1?) for pre-1970 years
- [ ] **Iodine number:** Confirm last year it appears (scan suggests 1943–~1948)
- [ ] **tp3c (1972):** Inspect that file to determine what data is in tp3c
- [ ] **1959 `tp24` and `tp 2`:** Inspect rows to confirm they are OCR artifacts
- [ ] **1987/1988:** Fragmented XLSX format — needs a separate assembler script, not covered by this prompt
- [ ] **1975:** PDF only (no XLSX in Green) — needs PDF extraction path
