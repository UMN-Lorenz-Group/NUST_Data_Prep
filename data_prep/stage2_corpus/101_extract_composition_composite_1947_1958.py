"""
101_extract_composition_composite_1947_1958.py
==============================================
Recover the 1947-1958 seed-composition data that the original extraction missed.

WHY THIS IS SEPARATE FROM THE CORPUS
------------------------------------
In 1947-1958 the NUST reports analysed COMPOSITE (bulked) seed samples, so the
source carries composition only as two MARGINALS -- never a strain x location
matrix:
  * strain-mean   : "Summary of agronomic and chemical data for the strains ...
                     Uniform Test, Group X, YYYY"  -> one value per (year, group,
                     strain), averaged over locations.
  * loc-composite : "Chemical composition of soybean seed grown at each Uniform
                     Test location" ("composite sample or mean of all strains")
                     -> one value per (year, group, location), averaged over strains.
There is NO per-(strain,location) cell, so these values are NOT usable in the
per-location RGG models (E2V-idh / E7Y) and must NOT enter the wide corpus. They
are written to a STANDALONE file and only flagged (composite-only shade) in the
traits coverage heatmap.

LOCAL extraction only -- pdfplumber over input_files/input_YYYY/YYYY_done.pdf.
No Claude API. Mirrors the helper pattern of 99_extract_chlorosis_1970_1988.py.

Phenotypes recovered: Protein, Oil, Oil_IodineNumber, SeedQuality, SeedSize
(the "Seed Weight" column; the modern wide trait). Protein/Oil get the x0.87
dry->13%-moisture-basis correction (1941-1988 convention).

Output: data_prep/stage2_corpus/nust_composition_composite_1947_1958.csv
  Year, TestMG, Aggregation, Strain, City, State, Phenotype, Value_num, Units, Source
  (Aggregation in {strain_mean, location_composite}; Strain XOR City populated.)
"""
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
CORPUS = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
INPUT = REPO / "input_files"
OUT = REPO / "data_prep" / "stage2_corpus" / "nust_composition_composite_1947_1958.csv"

YEARS = list(range(1947, 1959))
DRY_TO_13MC = 0.87
SOURCE = "ComposRecover_1947_1958"

# Per-trait plausible ranges (post-OCR sanity filter). Protein/Oil are DRY-basis
# here (pre x0.87): dry protein ~38-46, dry oil ~16-23, iodine ~120-145.
RANGES = {
    "SeedQuality": (1.0, 5.5),
    "SeedSize":    (8.0, 26.0),    # "Seed Weight" g/100 seed
    "Protein":     (33.0, 50.0),
    "Oil":         (14.0, 26.0),
    "Oil_IodineNumber": (115.0, 150.0),
}
UNITS = {"SeedQuality": "score", "SeedSize": "g/100sd", "Protein": "%",
         "Oil": "%", "Oil_IodineNumber": "iodine#"}

GROUP_RE = re.compile(r"GROUP\s+(0{1,2}|[IV]+)\b", re.IGNORECASE)
# "numeric-ish": a token that is mostly digits (allow OCR junk ^ . , - to be cleaned out)
NUMISH_RE = re.compile(r"^[+\-^•■]?\d[\d.,\-^]*$")
FOOTER_RE = re.compile(r"^(mean|l\.?s\.?d|c\.?v|average|no\.|mo\.|difference|range|"
                       r"standard|coefficient|table|group)", re.IGNORECASE)


def clean_num(tok):
    """Lenient OCR number cleaner for the POSITIVE chemical columns: strip junk,
    treat stray -/,/^ as decimal points, collapse. Returns float or None."""
    t = tok.strip("^•■*~()").replace(",", ".").replace("-", ".")
    t = re.sub(r"[^0-9.]", "", t)
    t = re.sub(r"\.+", ".", t).strip(".")
    if not t:
        return None
    if t.count(".") > 1:               # keep first dotted group
        a, b = t.split(".")[:2]
        t = f"{a}.{b}"
    try:
        return float(t)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# strain matching (OCR-tolerant) -- same idea as script 99
# ---------------------------------------------------------------------------
def strain_key(s, collapse=False):
    s = re.sub(r"\s*\([^)]*\)", "", str(s)).replace("*", "")
    s = re.sub(r"[\s.]+", "", s).upper()
    if collapse:
        s = s.replace("O", "0").replace("I", "1").replace("L", "1")
    return s


def build_strain_map():
    """Authoritative 1947-1958 strain spellings from the corpus (they already
    exist there via yield/maturity/oil)."""
    src = pd.read_csv(CORPUS, low_memory=False, usecols=["Year", "Strain"])
    src = src[src["Year"].between(1947, 1958)]
    exact, collapsed = {}, {}
    for sp in sorted(set(str(x).strip() for x in src["Strain"].dropna())):
        if not sp or sp.lower() == "strain":
            continue
        exact.setdefault(strain_key(sp), sp)
        collapsed.setdefault(strain_key(sp, collapse=True), sp)
    return exact, collapsed


def match_strain(raw, exact, collapsed):
    k = strain_key(raw)
    if k in exact:
        return exact[k]
    kc = strain_key(raw, collapse=True)
    return collapsed.get(kc)


def match_prefix(tokens, exact, collapsed):
    for p in range(min(len(tokens), 5), 0, -1):
        cand = " ".join(tokens[:p])
        if not re.search(r"[A-Za-z]", cand):
            continue
        m = match_strain(cand, exact, collapsed)
        if m is not None:
            return m, p
    return None, 0


# ---------------------------------------------------------------------------
# pdf helpers
# ---------------------------------------------------------------------------
def cx(w):
    return (w["x0"] + w["x1"]) / 2.0


def words_by_line(page, tol=2.4):
    d = defaultdict(list)
    for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        d[round(w["top"] / tol) * tol].append(w)
    return [(t, sorted(d[t], key=lambda w: w["x0"])) for t in sorted(d)]


def to_float(tok):
    t = tok.replace(",", ".").lstrip("+")
    try:
        return float(t)
    except ValueError:
        return None


def pdf_path(year):
    p = INPUT / f"input_{year}" / f"{year}_done.pdf"
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# strain-mean table parser
# ---------------------------------------------------------------------------
def single_year_group(text):
    """Return the MG group IFF the page carries a SINGLE-year UNIFORM-test
    strain-mean caption '… agronomic and chemical data for the strains in the
    Uniform Test, Group X …'. Anchored on the OCR-stable 'agronomic and chemical
    data for the strain…' (the word 'Summary' OCRs as 'sunnary', the year as
    '195c', so neither is required). Skips 'N-year summary …' multi-year tables
    and the Preliminary Test. The caller scans each year's own PDF, so any
    single-year strain table found is that year's."""
    norm = re.sub(r"\s+", " ", (text or "").lower())
    # anchor on the OCR-stable 'chemical data for the strain…' ('agronomic' OCRs
    # as 'agrohomic'/'agronomio'; 'Summary' as 'sunnary'; the year as '195c').
    for mm in re.finditer(
            r"chemical data for the strain[s]?(.{0,45}?)"
            r"\bgroup\s+(0{1,2}|[ivx]+)\b", norm):
        gap = mm.group(1)
        pre = norm[max(0, mm.start() - 48):mm.start()]
        if "year" in pre:                 # 'two-year summary of agronomic …'
            continue
        if "prelimin" in gap or "prelimin" in pre:   # Preliminary Test, not UT
            continue
        return mm.group(2).upper()
    return None


def header_anchors(header_words):
    """From the words in the header region, return {trait: x-center} for the 5
    right-hand chemical columns, keyed on header keywords. Iodine is optional."""
    qual = weight = protein = None
    oils = []   # (x) of every 'oil' token
    number = None
    for w in header_words:
        t = w["text"].lower().strip(".,:-")
        x = cx(w)
        if t.startswith("qual") and qual is None:
            qual = x
        elif t.startswith("weight") and weight is None:
            weight = x
        elif t.startswith("protein") and protein is None:
            protein = x
        elif t == "oil" or t.startswith("oil"):
            oils.append(x)
        elif t.startswith("number") and number is None:
            number = x
    anc = {}
    if qual is not None:
        anc["SeedQuality"] = qual
    if weight is not None:
        anc["SeedSize"] = weight
    if protein is not None:
        anc["Protein"] = protein
        # the Oil COLUMN is the first 'oil' to the right of Protein
        right_oils = sorted(x for x in oils if x > protein - 4)
        if right_oils:
            anc["Oil"] = right_oils[0]
    if number is not None:
        anc["Oil_IodineNumber"] = number
    elif "Oil" in anc and len(oils) >= 2:
        # iodine labelled 'of Oil' (no clean 'Number'): use the rightmost 'oil'
        far = max(oils)
        if far > anc["Oil"] + 25:
            anc["Oil_IodineNumber"] = far
    return anc


def parse_strainmean(page, year, group, exact, collapsed):
    """Yield (Strain, {trait: value}) for one single-year Group table, assigning
    cleaned numeric tokens to header-keyword column anchors."""
    lines = words_by_line(page)
    # anchor on the column-header row: the line with a 'Protein' HEADER word (text,
    # not a number). The chemical header spans ~3 lines, so scan a window around it.
    hidx = None
    for i, (top, ws) in enumerate(lines):
        if any(w["text"].lower().startswith("protein") for w in ws):
            hidx = i
            break
    if hidx is None:
        return []
    header_words = [w for _, ws in lines[max(0, hidx - 3):hidx + 3] for w in ws]
    anc = header_anchors(header_words)
    if "Protein" not in anc or "Oil" not in anc:   # mandatory; seed traits optional
        return []
    traits = list(anc.items())   # [(trait, x), ...]
    idx0 = hidx + 1

    # group physical lines into logical rows (strain line + wrapped continuations)
    rows, cur = [], None
    for top, ws in lines[idx0:]:
        toks = [w["text"] for w in ws]
        first = toks[0].strip(".,") if toks else ""
        sp, n = match_prefix(toks, exact, collapsed)
        if sp is not None:
            if cur:
                rows.append(cur)
            cur = {"strain": sp, "words": list(ws[n:]), "cont": 0}
        elif cur is not None:
            if FOOTER_RE.match(first):
                break
            nums = [w for w in ws if NUMISH_RE.match(w["text"])]
            if nums and len(nums) >= len(ws) - 1 and cur["cont"] < 2:
                cur["words"].extend(nums)
                cur["cont"] += 1
            elif re.search(r"[A-Za-z]{3,}", " ".join(toks)):
                break
    if cur:
        rows.append(cur)

    out = []
    for r in rows:
        vals = {}
        for w in r["words"]:
            if not NUMISH_RE.match(w["text"]):
                continue
            v = clean_num(w["text"])
            if v is None:
                continue
            xx = cx(w)
            trait, ax = min(traits, key=lambda kv: abs(xx - kv[1]))
            if abs(xx - ax) > 16:
                continue
            lo, hi = RANGES[trait]
            if lo <= v <= hi and trait not in vals:
                vals[trait] = v
        if vals:
            out.append((r["strain"], vals))
    return out


# ---------------------------------------------------------------------------
# location-composite table parser
# ---------------------------------------------------------------------------
def is_loccomposite_page(text):
    tl = (text or "").lower()
    return bool(re.search(r"composition of soybean seed grown at each|"
                          r"at the individual loca", tl))


def parse_loccomposite(page, year):
    """Yield (City, State, group, {Protein,Oil,Iodine}) using the FIRST
    (single-year) numeric triple per location row."""
    lines = words_by_line(page)
    out, group = [], None
    for top, ws in lines:
        toks = [w["text"] for w in ws]
        joined = " ".join(toks)
        gm = re.search(r"Group\s+(0{1,2}|[IV]+)\b", joined, re.IGNORECASE)
        if gm and ("mean of" in joined.lower() or "composite" in joined.lower()
                   or "continued" in joined.lower()):
            group = gm.group(1).upper()
            continue
        # location row: leading text (city, state) then numbers
        nums = [(clean_num(w["text"]), cx(w)) for w in ws if NUMISH_RE.match(w["text"])]
        nums = [(v, x) for v, x in nums if v is not None]
        txt = [w["text"] for w in ws if not NUMISH_RE.match(w["text"])
               and re.search(r"[A-Za-z]", w["text"])]
        if len(nums) < 3 or not txt or group is None:
            continue
        loc = " ".join(txt).strip(" .,")
        if not re.search(r"[A-Za-z]{3,}", loc) or FOOTER_RE.match(loc):
            continue
        # first triple = single-year Protein, Oil, Iodine (leftmost three by x)
        nums_sorted = sorted(nums, key=lambda t: t[1])[:3]
        prot, oil, iod = (nums_sorted[0][0], nums_sorted[1][0], nums_sorted[2][0])
        rec = {}
        if RANGES["Protein"][0] <= prot <= RANGES["Protein"][1]:
            rec["Protein"] = prot
        if RANGES["Oil"][0] <= oil <= RANGES["Oil"][1]:
            rec["Oil"] = oil
        if RANGES["Oil_IodineNumber"][0] <= iod <= RANGES["Oil_IodineNumber"][1]:
            rec["Oil_IodineNumber"] = iod
        if rec:
            # split city / state on the last comma if present
            city, state = loc, ""
            m = re.match(r"^(.*),\s*([A-Za-z.\s]{1,12})$", loc)
            if m:
                city, state = m.group(1).strip(), m.group(2).strip()
            out.append((city, state, group, rec))
    return out


# ---------------------------------------------------------------------------
def main():
    exact, collapsed = build_strain_map()
    print(f"strain map: {len(exact)} 1947-1958 spellings")
    rows = []

    def emit(year, mg, agg, strain, city, state, trait, val):
        if trait in ("Protein", "Oil"):
            val = round(val * DRY_TO_13MC, 2)
        rows.append({"Year": year, "TestMG": mg, "Aggregation": agg,
                     "Strain": strain, "City": city, "State": state,
                     "Phenotype": trait, "Value_num": val,
                     "Units": UNITS[trait], "Source": SOURCE})

    for year in YEARS:
        pp = pdf_path(year)
        if pp is None:
            print(f"{year}: PDF not found"); continue
        sm_groups, lc_pages = {}, []
        with pdfplumber.open(pp) as pdf:
            pages = pdf.pages
            for i, pg in enumerate(pages):
                t = pg.extract_text() or ""
                g = single_year_group(t)
                if g and g not in sm_groups:
                    sm_groups[g] = i
                if is_loccomposite_page(t):
                    lc_pages.append(i)
            n_sm = n_lc = 0
            for g, idx in sm_groups.items():
                for strain, vals in parse_strainmean(pages[idx], year, g, exact, collapsed):
                    for tr, v in vals.items():
                        emit(year, g, "strain_mean", strain, "", "", tr, v); n_sm += 1
            for idx in lc_pages:
                for city, state, g, rec in parse_loccomposite(pages[idx], year):
                    for tr, v in rec.items():
                        emit(year, g, "location_composite", "", city, state, tr, v); n_lc += 1
        print(f"{year}: strain-mean groups {sorted(sm_groups)} -> {n_sm} vals | "
              f"loc-composite pages {len(lc_pages)} -> {n_lc} vals")

    df = pd.DataFrame(rows)
    if OUT.exists() and not OUT.with_suffix(".csv.bak").exists():
        shutil.copy2(OUT, OUT.with_suffix(".csv.bak"))
    df.to_csv(OUT, index=False)
    print(f"\nWrote {OUT.name}: {len(df):,} rows")
    if len(df):
        print("\nby Aggregation x Phenotype:")
        print(df.groupby(["Aggregation", "Phenotype"]).size().to_string())
        sm = df[df.Aggregation == "strain_mean"]
        print("\nstrain_mean: distinct strains recovered per Year x MG group "
              "(0 = OCR-unrecoverable or multi-year-only):")
        print(sm.groupby(["Year", "TestMG"]).Strain.nunique()
                .unstack(fill_value=0).to_string())
        print("\nNOTE: best-effort LOCAL OCR recovery; values validated exact vs PDF "
              "(1950 M9/Capital, 1955 Chippewa). Composite-only -> NOT for per-location RGG.")


if __name__ == "__main__":
    main()
