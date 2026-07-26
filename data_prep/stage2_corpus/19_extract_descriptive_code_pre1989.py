"""
19_extract_descriptive_code_pre1989.py
======================================
Clean re-extraction of the pre-1989 NUST **Descriptive Code** — the compact
morphological code (flower / pubescence / pod / hilum colours, e.g. PCBr, PGBDYY,
WGNBr) printed in the "Descriptive and …Data" block right after the Strain. The
provisional PASS-1 pass (script 15) captured it split across columns (code bled
into the strain in tight layouts, stored in Units, parentage words leaked in
1988). This script anchors on the CODE COLUMN and captures the whole code.

Method (local, no API; mirrors 15/17/99):
  * page must be a descriptive-SCORE table (has the trait header Chlorosis/Score
    AND numeric chlorosis data) — this excludes the pure-parentage pages whose
    rows leaked into the 1988 provisional output.
  * the Descriptive Code is the FIRST alpha-code cluster to the right of the
    strain; its tokens are joined (handles the 1972 "WGN- SYBf" split). A second
    alpha cluster before the numerics is the Hypocotyl colour (kept separate).
  * a code must match the morphological-code alphabet (uppercase-led, only the
    letters used by the codes — no word vowels a/e/o/u or l/m/k/v/h…), which
    rejects parentage/strain words (Wilkin, Evans) that bled into the old output.
  * strain = words left of the code column (clean key for the corpus join).

Output (analysis/data/_shared/): descriptive_code_pre1989_long.csv
  Year, Source, Test, TestType, TestMG, Strain, Trait(=DescriptiveCode),
  Value(=code), Hypocotyl, Units
"""
import sys
import re
from pathlib import Path
import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
RED = Path("R:/cfans_agro_lore0149_lorenzlabresearch/NUST_Historical_Data_1941_1988"
           "/Red-20260427T193444Z-3-001/Red")
OUT = SHARED / "descriptive_block_pre1989_long.csv"   # DescriptiveCode + Hypocotyl + Shattering

DESC_HDR = re.compile(r"descriptive and (other|disease|shattering)\s*(data|pata)", re.I)
TEST_TITLE = re.compile(r"(uniform|preliminary)\s+test,?\s+(?:group\s+)?([0IVX]+)", re.I)
NUM = re.compile(r"^\d(\.\d)?$")                      # chlorosis/shattering score 0-9(.d)
# A morphological code: uppercase-led, only code letters; reject word vowels & l/m/k/v/h/j/q/x/z.
CODE_RE = re.compile(r"^[A-Z][A-Za-z+\-]{1,8}$")
BAD_CODE = re.compile(r"[aeiou]|[lmkvhjqxzwL]")       # lowercase word letters never in the codes
ROMAN = re.compile(r"^(I{1,3}|IV|VI{0,3}|IX|XI{0,3}|V|X)$")   # MG label, not a code
STRUCT = re.compile(r"[BTGNDSC]")                     # a real code carries a pubescence/pod/hilum letter
MG_FROM = {"00": "00", "0": "0", "I": "I", "II": "II", "III": "III", "IV": "IV"}


def is_code(tok):
    return (bool(CODE_RE.match(tok)) and not BAD_CODE.search(tok)
            and not ROMAN.match(tok) and bool(STRUCT.search(tok)))


def lines_by_baseline(words, tol=3):
    ws = sorted(words, key=lambda w: w["top"])
    out, cur, base = [], [], None
    for w in ws:
        if base is None or abs(w["top"] - base) <= tol:
            cur.append(w); base = w["top"] if base is None else base
        else:
            out.append(sorted(cur, key=lambda x: x["x0"])); cur, base = [w], w["top"]
    if cur:
        out.append(sorted(cur, key=lambda x: x["x0"]))
    return out


def parse_page(page, year, test):
    """Emit the descriptive-block traits per row: DescriptiveCode + Hypocotyl (alpha
    codes right of the strain) and Shattering (numeric columns right of the
    Chlorosis|Shattering header threshold). Chlorosis itself is owned by script 99."""
    lines = lines_by_baseline(page.extract_words())
    # cut at Disease-Data subtable (keep descriptive-score block above it)
    cut = None
    for ln in lines:
        if re.match(r"disease\s+(data|reaction)", " ".join(w["text"] for w in ln).strip().lower()):
            cut = ln[0]["top"]; break
    if cut is not None:
        lines = [ln for ln in lines if ln[0]["top"] < cut]
    # Chlorosis|Shattering threshold from the trait-group header (x of the header words),
    # so shattering scores are split from chlorosis scores by position (not value).
    chlor_x = shat_x = None
    for ln in lines:
        txt = " ".join(w["text"] for w in ln).lower()
        if "chloros" in txt and "shatter" in txt:
            for w in ln:
                lw = w["text"].lower()
                if lw.startswith("chloros"):
                    chlor_x = w["x0"]
                elif lw.startswith("shatter"):
                    shat_x = w["x0"]
            break
    # threshold midway between the two header words; shattering may sit on EITHER side
    # of chlorosis (1972+ shattering is right; 1970-71 it precedes chlorosis on the left).
    thr = (chlor_x + shat_x) / 2 if (chlor_x and shat_x) else None
    shat_on_right = (shat_x > chlor_x) if (chlor_x and shat_x) else True

    HEADER = {"strain", "code", "score", "ames", "lamberton", "manhattan", "crookston",
              "chlorosis", "hypocotyl", "shattering", "descriptive", "weeks", "emergence"}
    mg = MG_FROM.get(test.replace("UT", "").replace("PT", ""), "")
    base = dict(Year=year, Source="Red_PDF_descblock", Test=test,
                TestType="UT" if test.startswith("UT") else "PT", TestMG=mg)
    out = []
    for ln in lines:
        if ln[0]["x0"] > 130 or "_" in ln[0]["text"] or ln[0]["text"].strip().lower() in HEADER:
            continue
        if not re.match(r"[A-Za-z]", ln[0]["text"]) or TEST_TITLE.search(" ".join(w["text"] for w in ln)):
            continue
        nums = [w for w in ln if NUM.match(w["text"])]
        if not nums:                                  # confirms a descriptive-score row (not parentage)
            continue
        first_num_x = min(w["x0"] for w in nums)
        codes = [w for w in ln if w["x0"] < first_num_x - 4 and is_code(w["text"])]
        if not codes:
            continue
        codes.sort(key=lambda w: w["x0"])
        clusters, cur = [], [codes[0]]
        for w in codes[1:]:
            if w["x0"] - cur[-1]["x0"] > 22:
                clusters.append(cur); cur = [w]
            else:
                cur.append(w)
        clusters.append(cur)
        code = "".join(w["text"] for w in clusters[0])
        hypo = "".join(w["text"] for w in clusters[1]) if len(clusters) > 1 else ""
        strain = " ".join(w["text"] for w in ln if w["x0"] < clusters[0][0]["x0"] - 4).strip()
        strain = re.sub(r"\s+", " ", strain)
        if not strain or len(strain) < 2:
            continue
        out.append({**base, "Strain": strain, "Trait": "DescriptiveCode",
                    "Value": code, "Value_num": None, "Units": "code"})
        if hypo:
            out.append({**base, "Strain": strain, "Trait": "Hypocotyl",
                        "Value": hypo, "Value_num": None, "Units": "code"})
        if thr is not None:
            for w in nums:                            # shattering = score columns on the shattering side
                if (w["x0"] > thr) if shat_on_right else (w["x0"] < thr):
                    out.append({**base, "Strain": strain, "Trait": "Shattering",
                                "Value": w["text"], "Value_num": float(w["text"].replace(",", ".")),
                                "Units": "score"})
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
            if not (DESC_HDR.search(t) and re.search("chloros", t, re.I)):
                continue
            m = TEST_TITLE.search(t)
            if not m:
                continue
            test = ("UT" if m.group(1).lower().startswith("u") else "PT") + m.group(2).upper()
            rows += parse_page(pg, year, test)
    return rows


def main():
    years = [int(y) for y in (sys.argv[1].split(",") if len(sys.argv) > 1 else range(1970, 1989))]
    allrows = []
    for y in years:
        r = extract_year(y)
        allrows += r
        vc = pd.Series([x["Trait"] for x in r]).value_counts().to_dict() if r else {}
        print(f"  {y}: {len(r):3d} rows  {vc}")
    df = pd.DataFrame(allrows)
    if OUT.exists() and len(df):
        prior = pd.read_csv(OUT, low_memory=False)
        prior = prior[~prior["Year"].isin(years)]
        df = pd.concat([prior, df], ignore_index=True)
    if len(df):
        df.to_csv(OUT, index=False)
        print(f"\nWrote {OUT.name}: {len(df):,} rows")


if __name__ == "__main__":
    main()
