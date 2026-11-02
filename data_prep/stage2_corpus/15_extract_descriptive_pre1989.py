"""
15_extract_descriptive_pre1989.py
=================================
Recover the pre-1989 "Descriptive and Other Data" block (Chlorosis / Shattering /
Hypocotyl / Descriptive Code) from the historical NUST Red PDFs — the block the
original extraction dropped (its fixed ~22-column schema had no slot for it). Feeds
the unified descriptive/disease file (script 16).

Approach — coordinate + content based, no API:
  * The Red PDFs carry a usable OCR text layer; pages are found by the
    "Descriptive and Other/Disease Data" header (+ a Chlorosis/Shattering trait row).
  * Within a descriptive table, columns are recovered by clustering word x-positions
    (the tables have no ruled lines but are cleanly x-aligned).
  * Each value column is classified by CONTENT, which is robust to OCR-noisy headers:
      - decimal score  (e.g. 3.3, 2.5)         -> Chlorosis  (1-5 IDC scale, one col per nursery)
      - bare 1-5 int   (e.g. 1, 3)             -> Shattering  (1-5 scale)
      - short alpha code (PCBr / SYY / WGBr)   -> DescriptiveCode / Hypocotyl colour
    Per-nursery location is taken from the header words above each column when legible,
    else recorded as loc{n} (the trait + value are always reliable; location is refined later).
  * Strain = the left-of-first-value words joined (handles "Clay (0)", "Maple Arrow").

PASS 1 = descriptive scores only. The co-located "Disease Data" reaction matrix
(BB/BP/BS/PM/BSR/Phytophthora/SMV…) is a later pass.

Output (analysis/data/_shared/): descriptive_pre1989_long.csv  (long; consumed by script 16)
  columns: Year, Source, Test, TestType, TestMG, Variant, City, State, Strain,
           Phenotype, Trait, Value_num, Units

STATUS (2026-06-23) — PROVISIONAL first pass; NOT yet merged into the curated unified file.
  * VALIDATED: the standard "Descriptive and Other Data" layout (1980 exact match — Clay(0)
    Chlorosis 3.3/2.5, Shattering 1/3, code PCBr, hypo SYY). Trait labelling is header-driven
    (x-position of the "Chlorosis"/"Shattering" header words), so it is correct even in years
    where chlorosis is integer-scored (1977-79) — the Value_num values are reliable.
  * KNOWN PER-YEAR GAPS (need the next iteration before corpus merge):
      - 1970-1972: a different early table format ("Shattering … Chlorosis … Illinois Kansas"),
        not yet parsed (1970-71 yield 0 rows; 1972 partial).
      - 1984: anomalously few rows (layout/OCR) — investigate.
      - tight-layout years (e.g. 1979): the Descriptive Code is absorbed into the Strain
        ("Altona PTBr") because the strain/code x-gap is small — Value_num is right but the
        Strain KEY needs cleanup before joining to corpus strains.
  Location is recorded as loc{n} (the per-nursery header label is refined later).

Run with a year (or comma list); default = the prototype year 1980.
  uv run python 15_extract_descriptive_pre1989.py 1980
"""
import sys
import re
from pathlib import Path
from collections import defaultdict
import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
RED = Path("R:/cfans_agro_lore0149_lorenzlabresearch/NUST_Historical_Data_1941_1988"
           "/Red-20260427T193444Z-3-001/Red")
OUT = SHARED / "descriptive_pre1989_long.csv"

DESC_HDR = re.compile(r"descriptive and (other|disease)\s*(data|pata)", re.I)
TEST_HDR = re.compile(r"(uniform|preliminary)\s+test\s+([0IVX]+)", re.I)
TRAIT_ROW = re.compile(r"chloros", re.I)            # the trait-group header line
DECIMAL = re.compile(r"^\d\.\d$")                    # 3.3  -> chlorosis score
SMALLINT = re.compile(r"^[1-5]$")                    # 1..5 -> shattering / chlorosis int
ALPHACODE = re.compile(r"^[A-Za-z][A-Za-z'+]{1,5}$") # PCBr / SYY -> descriptive / hypocotyl code

MG_FROM_TEST = {"00": "00", "0": "0", "I": "I", "II": "II", "III": "III", "IV": "IV"}


def cluster_columns(xs, gap=14):
    """Cluster sorted x0 positions into column centers (gap-based 1-D clustering)."""
    xs = sorted(xs)
    cols, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] > gap:
            cols.append(sum(cur) / len(cur)); cur = [x]
        else:
            cur.append(x)
    cols.append(sum(cur) / len(cur))
    return cols


def lines_by_baseline(words, tol=5):
    """Cluster words into visual lines by y-baseline (robust to a value wrapping a
    hair off its row, which fixed-bucket rounding split into its own line)."""
    ws = sorted(words, key=lambda w: w["top"])
    lines, cur, base = [], [], None
    for w in ws:
        if base is None or abs(w["top"] - base) <= tol:
            cur.append(w)
            base = w["top"] if base is None else base
        else:
            lines.append(sorted(cur, key=lambda x: x["x0"]))
            cur, base = [w], w["top"]
    if cur:
        lines.append(sorted(cur, key=lambda x: x["x0"]))
    return lines


def strain_boundary(data_rows, lo=85, hi=210, default=145.0):
    """x dividing the (leftmost) strain column from the first data column — the largest
    token-x gap in the lo..hi band. Keeps word-strains (Clay/Maple) out of the data cols."""
    cand = sorted(w["x0"] for ws in data_rows for w in ws if lo < w["x0"] < hi)
    best_gap, bnd = 0.0, default
    for a, b in zip(cand, cand[1:]):
        if b - a > best_gap:
            best_gap, bnd = b - a, (a + b) / 2
    return bnd if best_gap > 18 else default


def parse_descriptive_page(page, year, test, variant):
    """Yield long rows for one descriptive-table page (PASS 1 = the descriptive-score
    block ABOVE the co-located 'Disease Data' reaction matrix, which is a later pass)."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    ordered = lines_by_baseline(words)
    # cut off at the "Disease Data" sub-table header — keep only the descriptive-score
    # block above it. Match at LINE level (text starts with "Disease …") so the page
    # TITLE "Descriptive and Disease Data" (starts with "Descriptive") is NOT a cutoff.
    cutoff = None
    for ln in ordered:
        txt = " ".join(w["text"] for w in ln).strip().lower()
        if re.match(r"disease\s+(data|reaction)", txt):
            cutoff = ln[0]["top"]
            break
    if cutoff is not None:
        ordered = [ln for ln in ordered if ln[0]["top"] < cutoff]

    # locate the data rows: leftmost token is a strain (not a header label) and the row
    # carries >=1 decimal/1-5 value. Exclude header lines (Strain____ / Code / location
    # names) whose stray tokens would otherwise pollute the column clustering.
    HEADER_WORDS = {"strain", "code", "score", "ames", "lamberton", "manhattan",
                    "weeks", "chlorosis", "hypocotyl", "shattering", "descriptive"}
    data_rows = []
    for ws in ordered:
        first = ws[0]["text"]
        if "_" in first or first.strip().lower() in HEADER_WORDS:
            continue
        vals = [w for w in ws if DECIMAL.match(w["text"]) or SMALLINT.match(w["text"])]
        if vals and ws[0]["x0"] < 130 and not TEST_HDR.search(" ".join(w["text"] for w in ws)):
            data_rows.append(ws)
    if not data_rows:
        return []

    # value-column centers from the decimal/int tokens across all data rows
    # The STRAIN column is the leftmost block; codes/values start to its right. Detect the
    # boundary as the largest x-gap between the strain cluster and the first data column
    # (word-strains like "Clay"/"Maple" otherwise match ALPHACODE and corrupt the columns).
    strain_x = strain_boundary(data_rows)

    def is_val(w):
        return w["x0"] >= strain_x and (DECIMAL.match(w["text"]) or SMALLINT.match(w["text"]))

    def is_code(w):
        return w["x0"] >= strain_x and ALPHACODE.match(w["text"])

    val_x = [w["x0"] for ws in data_rows for w in ws if is_val(w)]
    code_x = [w["x0"] for ws in data_rows for w in ws if is_code(w)]
    if not val_x:
        return []
    vcols = cluster_columns(val_x)
    ccols = cluster_columns(code_x) if code_x else []

    def nearest(x, centers):
        return min(range(len(centers)), key=lambda i: abs(centers[i] - x)) if centers else None

    # Label value columns by POSITION using the trait-group header ("Chlorosis … Shattering"),
    # NOT by content: in several years (1977-79) chlorosis is integer-scored, so a
    # decimal-vs-int heuristic mislabels it as Shattering. The header word x-positions give a
    # reliable Chlorosis|Shattering threshold. Fallback to content only if the header is absent.
    chlor_x = shat_x = None
    for ln in ordered:
        txt = " ".join(w["text"] for w in ln).lower()
        if "chloros" in txt and "shatter" in txt:
            for w in ln:
                lw = w["text"].lower()
                if lw.startswith("chloros"):
                    chlor_x = w["x0"]
                elif lw.startswith("shatter"):
                    shat_x = w["x0"]
            break
    col_kind = {}
    if chlor_x is not None and shat_x is not None and shat_x > chlor_x:
        thr = (chlor_x + shat_x) / 2
        for ci in range(len(vcols)):
            col_kind[ci] = "Chlorosis" if vcols[ci] < thr else "Shattering"
    else:
        for ci in range(len(vcols)):                       # fallback: content heuristic
            kinds = [("Chlorosis" if DECIMAL.match(w["text"]) else "Shattering")
                     for ws in data_rows for w in ws if is_val(w) and nearest(w["x0"], vcols) == ci]
            col_kind[ci] = max(set(kinds), key=kinds.count) if kinds else "Chlorosis"

    out = []
    for ws in data_rows:
        strain = " ".join(w["text"] for w in ws if w["x0"] < strain_x).strip()
        strain = re.sub(r"\s+", " ", strain)
        if not strain or len(strain) < 2:
            continue
        for w in ws:
            t = w["text"]
            if is_val(w):
                ci = nearest(w["x0"], vcols)
                trait = col_kind[ci]
                out.append(dict(Year=year, Source="Red_PDF_pre1989", Test=test,
                                TestType="UT" if test.startswith("UT") else "PT",
                                TestMG=MG_FROM_TEST.get(test.replace("UT", "").replace("PT", ""), ""),
                                Variant=variant, City=f"loc{ci+1}", State="", Strain=strain,
                                Phenotype=trait, Trait=trait, Value_num=float(t), Units="score"))
            elif is_code(w) and ccols:
                ci = nearest(w["x0"], ccols)
                trait = "DescriptiveCode" if ci == 0 else "Hypocotyl"
                out.append(dict(Year=year, Source="Red_PDF_pre1989", Test=test,
                                TestType="UT" if test.startswith("UT") else "PT", TestMG="",
                                Variant=variant, City="", State="", Strain=strain,
                                Phenotype=trait, Trait=trait, Value_num=pd.NA, Units=t))
    return out


def extract_year(year):
    fp = RED / f"{year}_done.pdf"
    if not fp.exists():
        fp = RED / f"{year}.pdf"
    if not fp.exists():
        print(f"  {year}: NO PDF"); return []
    rows = []
    with pdfplumber.open(fp) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if not (DESC_HDR.search(t) and TRAIT_ROW.search(t)):
                continue
            m = TEST_HDR.search(t)
            if not m:
                continue
            kind = "UT" if m.group(1).lower().startswith("u") else "PT"
            test = kind + m.group(2).upper()
            rows += parse_descriptive_page(pg, year, test, "Conventional")
    return rows


def main():
    years = sys.argv[1].split(",") if len(sys.argv) > 1 else ["1980"]
    years = [int(y) for y in years]
    allrows = []
    for y in years:
        r = extract_year(y)
        allrows += r
        print(f"  {y}: {len(r)} descriptive rows "
              f"({pd.Series([x['Trait'] for x in r]).value_counts().to_dict() if r else '-'})")
    df = pd.DataFrame(allrows)
    if OUT.exists() and df.shape[0]:
        prior = pd.read_csv(OUT, low_memory=False)
        prior = prior[~prior["Year"].isin(years)]
        df = pd.concat([prior, df], ignore_index=True)
    if df.shape[0]:
        df.to_csv(OUT, index=False)
        print(f"\nWrote {OUT.name}: {len(df):,} rows total")


if __name__ == "__main__":
    main()
