"""
17_extract_disease_pre1989.py   (PASS 2 — disease-reaction matrix, prototype)
============================================================================
Recover the pre-1989 DISEASE-REACTION matrix from the historical NUST Red PDFs —
the "Disease Data" table (1972-1984) / the disease columns of "DESCRIPTIVE AND
DISEASE DATA" (1985-1988). This is the companion to the descriptive-score
recovery (scripts 15/99 = PASS 1); together they reconstruct the full
"Descriptive and Disease Data" block the original yield-only extraction dropped.

Disease values are HETEROGENEOUS (this is the hard part, captured verbatim):
  - percentages           BSR 100, GERM 67, PSB 10
  - score+severity codes  SMV 3M / 3E,  PS 5S / 3E   (digit + M/E/S severity)
  - reaction codes         PR  R / S / MR / MS
So each cell is stored as a raw string `Value`, with the leading number parsed
into `Value_num` when present. Canonical disease name comes from the column
abbreviation header.

Approach — coordinate + header-driven, local (no API), mirrors scripts 15/99:
  * find the disease table (a "Disease Data" line, or the disease columns to the
    right of the descriptive block);
  * the abbreviation header row (>=2 known disease codes) gives column x-centres
    + the disease each column measures;
  * each value token is assigned to the nearest disease column by x;
  * strain = words left of the first data column (x-gap split).

STATUS: PROTOTYPE — validated on the clean 1980 "Disease Data" layout. Eras
1985-88 (merged block, race columns) and 1958-71 (composite reaction codes like
"3La,4Aa") are progressively harder and are a later sub-pass.

Output (analysis/data/_shared/): disease_pre1989_long.csv
  Year, Source, Test, TestType, TestMG, Strain, Disease, DiseaseAbbrev,
  Location, Value, Value_num, Units
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
OUT = SHARED / "disease_pre1989_long.csv"

# Disease abbreviation -> canonical name (NUST report conventions).
DISEASE_ABBREV = {
    "BB": "BacterialBlight", "BP": "BacterialPustule", "BS": "BrownSpot",
    "FE": "Frogeye", "FE2": "Frogeye", "FE1": "Frogeye",
    "PM": "PowderyMildew", "BSR": "BrownStemRot", "BTS": "BrownStemRot",
    "PR": "PhytophthoraRot", "PRR": "PhytophthoraRot",
    "SMV": "SoybeanMosaicVirus", "GERM": "Germination",
    "PSB": "PodAndStemBlight", "PS": "PurpleStain", "CR": "CharcoalRot",
    "SC": "StemCanker", "DM": "DownyMildew", "TS": "TargetSpot",
}
ABBREV_RE = re.compile(r"^(BB|BP|BS|FE\d?|PM|BSR|BTS|PRR?|SMV|GERM|PSB|PS|CR|SC|DM|TS)$", re.I)
# handles "Uniform Test 00" (1972+) and the early "Uniform Test, Group 00" (1958-71)
TEST_TITLE = re.compile(r"(uniform|preliminary)\s+test,?\s+(?:group\s+)?([0IVX]+)", re.I)
# disease cell value: leading 1-3 digit number, optional .d, optional severity letters,
# OR a bare reaction code (R/S/MR/MS/Seg)
VALUE_RE = re.compile(r"^(\d{1,3}([.,]\d)?[A-Za-z]{0,2}|MR|MS|R|S|Seg\.?|U)$")
NUMLEAD = re.compile(r"^(\d{1,3})([.,]\d)?")
MG_FROM = {"00": "00", "0": "0", "I": "I", "II": "II", "III": "III", "IV": "IV"}


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


def cluster(xs, gap=14):
    xs = sorted(xs); cols, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] > gap:
            cols.append(sum(cur) / len(cur)); cur = [x]
        else:
            cur.append(x)
    cols.append(sum(cur) / len(cur)); return cols


def to_num(tok):
    m = NUMLEAD.match(tok)
    return float(m.group(0).replace(",", ".")) if m else None


def parse_disease_block(page, year, test):
    lines = lines_by_baseline(page.extract_words())
    # find the abbreviation header line: >=2 tokens that are known disease codes
    hdr = None
    for ln in lines:
        codes = [w for w in ln if ABBREV_RE.match(w["text"])]
        if len(codes) >= 2:
            hdr = codes
            hdr_top = ln[0]["top"]
            break
    if not hdr:
        return []
    # strip a trailing race digit (FE2/FE9 -> FE -> Frogeye) for the canonical lookup
    def canon(txt):
        base = re.sub(r"\d+$", "", txt.upper()) or txt.upper()
        return DISEASE_ABBREV.get(base, DISEASE_ABBREV.get(txt.upper(), base))
    dcols = [(w["x0"], canon(w["text"]), w["text"].upper()) for w in hdr]
    dcols.sort()
    centers = [c[0] for c in dcols]

    def nearest(x):
        return min(range(len(centers)), key=lambda i: abs(centers[i] - x))

    # data rows: below the header, leftmost token a strain (x<130), with >=2 value tokens
    out = []
    for ln in lines:
        if ln[0]["top"] <= hdr_top:
            continue
        first = ln[0]["text"]
        if "_" in first or first.lower() in ("strain", "%", "score", "mean", "average"):
            continue
        vals = [w for w in ln if w["x0"] >= centers[0] - 20 and VALUE_RE.match(w["text"])]
        if len(vals) < 2 or ln[0]["x0"] > 130:
            continue
        strain = " ".join(w["text"] for w in ln if w["x0"] < centers[0] - 20).strip()
        strain = re.sub(r"\s+", " ", strain)
        if not strain or len(strain) < 2 or TEST_TITLE.search(strain):
            continue
        for w in vals:
            ci = nearest(w["x0"])
            abbr = dcols[ci][2]
            out.append(dict(Year=year, Source="Red_PDF_disease", Test=test,
                            TestType="UT" if test.startswith("UT") else "PT",
                            TestMG=MG_FROM.get(test.replace("UT", "").replace("PT", ""), ""),
                            Strain=strain, Disease=dcols[ci][1], DiseaseAbbrev=abbr,
                            Location=f"col{ci+1}", Value=w["text"], Value_num=to_num(w["text"]),
                            Units="reaction/score/%"))
    return out


# ---------------------------------------------------------------------------
# MODE 2 — full-disease-NAME header (1958-1971 composite-reaction era)
# ---------------------------------------------------------------------------
# Header words that are NOT disease names (drop from column reconstruction).
HDR_STOP = {"strain", "race", "group", "test", "table", "summary", "uniform", "preliminary",
            "number", "no", "tests", "of", "the", "data", "reaction", "for", "in", "score",
            "and", "year", "years"}
# composite reaction value (1958-71): starts with a digit or a reaction letter (R/S/U/M),
# then any mix of alnum/comma/dot/+- (e.g. 3La,3Aa | SCa | RCa | Seg.Ca | 4Nn | 3.5 | U).
# Strain is already separated by x-position, so this can be permissive on the value side.
DVALUE_RE = re.compile(r"^[0-9RSUM][A-Za-z0-9.,'+\-]{0,11}$")


def canon_disease_name(name):
    n = re.sub(r"[^a-z]+", " ", name.lower()).strip()
    n = n.replace("phytoph thora", "phytophthora").replace("frog eye", "frogeye")
    for kw, canon in [("bacterial blight", "BacterialBlight"), ("bacterial pustule", "BacterialPustule"),
                      ("brown stem", "BrownStemRot"), ("brown spot", "BrownSpot"),
                      ("stem canker", "StemCanker"), ("frog", "Frogeye"), ("phytoph", "PhytophthoraRot"),
                      ("cyst", "CystNematode"), ("downy", "DownyMildew"), ("powdery", "PowderyMildew"),
                      ("mosaic", "SoybeanMosaicVirus"), ("pod", "PodAndStemBlight"),
                      ("purple", "PurpleStain"), ("charcoal", "CharcoalRot"),
                      ("pustule", "BacterialPustule"), ("blight", "BacterialBlight")]:
        if kw in n:
            return canon
    return None


def parse_disease_name_header(page, year, test):
    lines = lines_by_baseline(page.extract_words())
    # locate the disease-reaction table title
    t_idx = next((i for i, ln in enumerate(lines)
                  if re.search(r"disease\s+(data|reaction)", " ".join(w["text"] for w in ln), re.I)), None)
    if t_idx is None:
        return []
    title_top = lines[t_idx][0]["top"]
    # first data row after the title: leftmost token a strain (alpha, x<70) + >=2 composite values
    data_start = None
    for i in range(t_idx + 1, len(lines)):
        ln = lines[i]
        if ln[0]["x0"] > 70:
            continue
        f = ln[0]["text"]
        if "_" in f or f.lower() in ("strain", "mean", "no") or not re.match(r"[A-Za-z]", f):
            continue
        vals = [w for w in ln if w["x0"] > 100 and DVALUE_RE.match(w["text"])]
        if len(vals) >= 2:
            data_start = i; break
    if data_start is None:
        return []
    # reconstruct disease columns from the header band (capitalized name fragments)
    hdr_words = []
    for ln in lines[t_idx + 1:data_start]:
        for w in ln:
            tk = w["text"]
            if re.match(r"[A-Z][A-Za-z*'.-]+$", tk) and tk.lower().rstrip(".") not in HDR_STOP and len(tk) > 1:
                hdr_words.append(w)
    if not hdr_words:
        return []
    hdr_words.sort(key=lambda w: w["x0"])
    clusters, cur = [], [hdr_words[0]]
    for w in hdr_words[1:]:
        if w["x0"] - cur[-1]["x0"] > 24:
            clusters.append(cur); cur = [w]
        else:
            cur.append(w)
    clusters.append(cur)
    cols = []
    for cl in clusters:
        name = " ".join(w["text"] for w in sorted(cl, key=lambda w: (w["top"], w["x0"])))
        canon = canon_disease_name(name)
        if canon:
            cols.append((sum(w["x0"] for w in cl) / len(cl), canon, name))
    if not cols:
        return []
    cols.sort()
    centers = [c[0] for c in cols]

    def nearest(x):
        return min(range(len(centers)), key=lambda i: abs(centers[i] - x))

    out = []
    for ln in lines[data_start:]:
        if ln[0]["x0"] > 70 or not re.match(r"[A-Za-z]", ln[0]["text"]):
            continue
        first = ln[0]["text"].lower()
        if first in ("mean", "no", "strain") or "_" in ln[0]["text"]:
            continue
        vals = [w for w in ln if w["x0"] > centers[0] - 30 and DVALUE_RE.match(w["text"])]
        if len(vals) < 1:
            continue
        strain = " ".join(w["text"] for w in ln if w["x0"] < centers[0] - 30).strip()
        strain = re.sub(r"\s*\(check\)\s*", "", strain, flags=re.I).strip()
        if not strain or len(strain) < 2 or TEST_TITLE.search(strain):
            continue
        for w in vals:
            ci = nearest(w["x0"])
            out.append(dict(Year=year, Source="Red_PDF_disease", Test=test,
                            TestType="UT" if test.startswith("UT") else "PT",
                            TestMG=MG_FROM.get(test.replace("UT", "").replace("PT", ""), ""),
                            Strain=strain, Disease=cols[ci][1], DiseaseAbbrev=cols[ci][2],
                            Location=f"col{ci+1}", Value=w["text"],
                            Value_num=to_num(w["text"]), Units="reaction/score/%"))
    return out


# ---------------------------------------------------------------------------
# MODE 3 — 1950-1957 combined "Disease reaction of Uniform and Preliminary Test
# strains" table: one full-name-header matrix with "Group N" MG sub-headers that
# switch the MG mid-table (no per-page Uniform/Preliminary test title).
# ---------------------------------------------------------------------------
GROUP_RE = re.compile(r"^Group\s+(00|0|I{1,3}|IV|V)\b", re.I)


def parse_disease_groups(page, year):
    lines = lines_by_baseline(page.extract_words())
    t_idx = next((i for i, ln in enumerate(lines)
                  if re.search(r"disease reaction", " ".join(w["text"] for w in ln), re.I)), None)
    if t_idx is None:
        return []
    # first Group line marks the end of the header band and the start of data
    g_idx = next((i for i in range(t_idx + 1, len(lines))
                  if GROUP_RE.match(" ".join(w["text"] for w in lines[i]).strip())), None)
    if g_idx is None:
        return []
    hdr_words = []
    for ln in lines[t_idx + 1:g_idx]:
        for w in ln:
            tk = w["text"]
            if re.match(r"[A-Z][A-Za-z*'.-]+$", tk) and tk.lower().rstrip(".") not in HDR_STOP and len(tk) > 1:
                hdr_words.append(w)
    if not hdr_words:
        return []
    hdr_words.sort(key=lambda w: w["x0"])
    clusters, cur = [], [hdr_words[0]]
    for w in hdr_words[1:]:
        if w["x0"] - cur[-1]["x0"] > 24:
            clusters.append(cur); cur = [w]
        else:
            cur.append(w)
    clusters.append(cur)
    cols = []
    for cl in clusters:
        canon = canon_disease_name(" ".join(w["text"] for w in sorted(cl, key=lambda w: (w["top"], w["x0"]))))
        if canon:
            cols.append((sum(w["x0"] for w in cl) / len(cl), canon))
    if not cols:
        return []
    cols.sort(); centers = [c[0] for c in cols]

    def nearest(x):
        return min(range(len(centers)), key=lambda i: abs(centers[i] - x))

    out, mg = [], None
    for ln in lines[g_idx:]:
        txt = " ".join(w["text"] for w in ln).strip()
        gm = GROUP_RE.match(txt)
        if gm:
            mg = gm.group(1).upper(); continue
        if mg is None or ln[0]["x0"] > 70 or not re.match(r"[A-Za-z]", ln[0]["text"]):
            continue
        if ln[0]["text"].lower() in ("strain", "mean", "no"):
            continue
        vals = [w for w in ln if w["x0"] > centers[0] - 30 and DVALUE_RE.match(w["text"])]
        if not vals:
            continue
        strain = re.sub(r"\s*\(check\)\s*", "", " ".join(w["text"] for w in ln if w["x0"] < centers[0] - 30),
                        flags=re.I).strip()
        if not strain or len(strain) < 2:
            continue
        for w in vals:
            ci = nearest(w["x0"])
            out.append(dict(Year=year, Source="Red_PDF_disease", Test=f"Grp-{mg}",
                            TestType="", TestMG=mg, Strain=strain, Disease=cols[ci][1],
                            DiseaseAbbrev=cols[ci][1], Location=f"col{ci+1}", Value=w["text"],
                            Value_num=to_num(w["text"]), Units="reaction/score/%"))
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
            if not re.search(r"disease\s+(data|reaction)", t, re.I):
                continue
            m = TEST_TITLE.search(t)
            if m:
                test = ("UT" if m.group(1).lower().startswith("u") else "PT") + m.group(2).upper()
                r = parse_disease_block(pg, year, test)             # MODE 1: abbreviations (1972+)
                if not r:
                    r = parse_disease_name_header(pg, year, test)   # MODE 2: full names (1958-71)
                rows += r
            elif re.search(r"\bGroup\s+(00|0|I{1,3}|IV|V)\b", t):   # MODE 3: 1950-57 combined "Group N"
                rows += parse_disease_groups(pg, year)
    return rows


def main():
    years = [int(y) for y in (sys.argv[1].split(",") if len(sys.argv) > 1 else ["1980"])]
    allrows = []
    for y in years:
        r = extract_year(y)
        allrows += r
        vc = pd.Series([x["Disease"] for x in r]).value_counts().to_dict() if r else "-"
        print(f"  {y}: {len(r)} disease cells  {vc}")
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
