"""Green-direct (openpyxl, NO API) extraction of the 1974 Preliminary Test I (PT-I) from the Green
OCR XLSX -- part of the NUST test-map source-repair (C1, no-API path).

Context: 1974 PT-I was MERGED into the neighbor Uniform Test I because its tp2 parentage marker was
missing, so the combine step folded PT-I's ~30 strains into the F4U "UT-I" cell (a mix of the real
UT-I roster + the whole PT-I roster).  We re-inserted the missing tp2 marker, so the Green now
delimits PT-I correctly as Group_5 (xlsx rows 967-1220).  This script reads PT-I straight from the
Green with no model in the loop.

Section structure (verified empirically over rows 967-1220):
  tp2  @967   parentage roster : 30 strains (1. Hark .. 30. SD73-16)   <- canonical names
  tp3b @1002  disease reactions          (not a phenotype table -- skipped)
  tp3a @1037  descriptive codes          (not a phenotype table -- skipped)
  tp4  @1071  per-strain SUMMARY MEANS for Yield/Rank/Maturity/Lodging/Height/SeedQuality/SeedSize/
              Protein/Oil.  These are MEAN-only (no per-location breakdown).  NOT emitted -- the
              corpus schema is per-location, and emitting a mean under a pseudo-location would create
              a stray record.  Their existence is why the 6 secondary traits are an honest
              per-location GAP for 1974 PT-I (see report).
  tp6  @1105  YIELD block 1 : Strain + Mean + 5 locations (Ontario Ridgetown .. Wisconsin Madison)
  tp6  @1145  YIELD block 2 : CONTINUATION -- 7 more locations (Illinois Dekalb .. S.Dakota
              Brookings), NO Strain/Mean column, 30 data rows aligned BY INDEX to the roster.
              (5 + 7 = 12 locations == the "12 Tests" printed in block 1's Mean header.  This is a
              location continuation, NOT a multi-year summary -- it is KEPT.)
  tp8  @1183  MATURITY : Strain + Mean + 12 locations.  Printed as an anchor DATE row (Steele, entry
              #2, printed as absolute dates) + signed day OFFSETS for every other strain.  DOY is
              reconstructed as anchor_date_DOY + offset.  NB the Green OCR corrupts several of
              Steele's anchor-date cells (see report / validation) -- the OFFSETS are clean, but the
              absolute anchor is only as good as the OCR of Steele's date row.

The ONLY per-location trait tables present in the 1974 PT-I section are YIELD and MATURITY.  There
are no tp9/tp10/tp11/tp12 blocks -- Lodging/Height/SeedQuality/SeedSize/Protein/Oil exist only as
tp4 summary means.  This is confirmed by the F4U itself: the pure-PT-I strains merged into the F4U
"UT-I" cell carry non-null values ONLY for YieldBuA and Maturity.

Output: reextract_1974_pti_green.csv  (long schema identical to reextract_1984_pt_recovered.csv;
        TestType="PT", TestMG="I", Test="PT-I").
"""
import sys, re, datetime
from pathlib import Path
import openpyxl
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
GREEN = REPO / "input_files" / "input_1974" / "Sojabone-1974 (0-56 OR).xlsx"
OUT = REPO / "data_prep" / "stage2_corpus" / "reextract_1974_pti_green.csv"
F4U = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/"
           "NUST_Historical_Data_1941_1988/1974_Processing/Files4Upload/phenotypesTable1.csv")

YEAR, TESTTYPE, MG, CODE = 1974, "PT", "I", "PT-I"
SOURCE = "Green1974_PTI_direct"

# xlsx-row (1-based) anchors of the PT-I section blocks
ROSTER_ROWS = (969, 998)     # "1. Hark" .. "30. SD73-16"  (inclusive, 1-based)
YIELD_B1_TP = 1105           # tp6  (Strain + Mean + 5 loc)
YIELD_B2_TP = 1145           # tp6  (7 loc continuation, no Strain/Mean)
MAT_TP = 1183                # tp8  (Strain + Mean + 12 loc, anchor-date + offsets)
SECTION_END = 1220           # next tp2 (PT-II parentage)

UNITS = {"YieldBuA": "bu/a", "Maturity": "DOY"}
RANGE = {"YieldBuA": (2, 120), "Height": (5, 80), "Lodging": (1, 5), "SeedQuality": (1, 5),
         "SeedSize": (5, 40), "Protein": (25, 55), "Oil": (5, 30), "Maturity": (200, 330)}
FOOTER = re.compile(r"^\s*(C\.V|L\.S\.D|Mean|Row\s*sp|Rows?\s*/|Reps|Strain|Date\s*Pl|Date\s*plant|"
                    r"Days\s*to|No\.\s*of|tp\d|Swift|Corsoy|NS$)", re.I)

# Green location headers are "<StateName> <City>" (state FIRST, full or abbreviated).
STATE_NAMES = {
    "ontario": "ONT", "ont": "ONT", "ohio": "OH", "michigan": "MI", "mich": "MI",
    "wisconsin": "WI", "wis": "WI", "illinois": "IL", "ill": "IL", "minnesota": "MN",
    "minn": "MN", "iowa": "IA", "southdakota": "SD", "sdakota": "SD",
}
CITY_FIX = {"Kanawa": "Kanawha", "Kana-wha": "Kanawha", "Dun dee": "Dundee", "Dundee": "Dundee"}
# only OCR garble in the parentage roster (27. SI//3-2 -> SD73-2; the 27-30 run is SD73-2/5/14/16)
ROSTER_FIX = {"SI//3-2": "SD73-2"}


def load():
    wb = openpyxl.load_workbook(GREEN, read_only=True, data_only=True)
    rows = list(wb["Sheet1"].iter_rows(values_only=True))
    wb.close()
    return rows


def strip_rank(s):
    return re.sub(r"^\s*\d+\s*[.,)]\s*", "", str(s)).strip()


def clean_strain(s):
    s = strip_rank(s)
    s = re.sub(r"\s*[)\]]\s*$", "", s).strip()      # 'SD73-16 )' -> 'SD73-16'
    return ROSTER_FIX.get(s, s)


def normkey(s):
    k = re.sub(r"\(.*?\)", "", strip_rank(s).lower())
    k = re.sub(r"[^a-z0-9]", "", k)
    return k.translate(str.maketrans("lio", "110"))


def parse_state_city(h):
    """'Ontario Ridgetown'->('Ridgetown','ONT'); 'S.Dakota Revillo'->('Revillo','SD');
    'Michigan Dun dee'->('Dundee','MI'); 'Iowa Kana-wha'->('Kanawha','IA')."""
    s = re.sub(r"\s+", " ", str(h)).strip()
    toks = s.split(" ")
    # try a two-token state name first ('South Dakota'), then one token
    for n in (2, 1):
        if len(toks) > n:
            cand = "".join(toks[:n]).lower().replace(".", "")
            if cand in STATE_NAMES:
                city = " ".join(toks[n:]).strip()
                city = CITY_FIX.get(city, city)
                return city, STATE_NAMES[cand]
    # fall back: leading token as state abbrev-ish
    return s, ""


def fnum(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    m = re.match(r"^\s*[+-]?\s*\d+(?:\.\d+)?", str(x).replace(" ", ""))
    return float(m.group().replace(" ", "")) if m else None


def doy(dt):
    return datetime.date(YEAR, dt.month, dt.day).timetuple().tm_yday


def build_roster(rows):
    return [clean_strain(rows[i - 1][0]) for i in range(ROSTER_ROWS[0], ROSTER_ROWS[1] + 1)]


def data_rows(rows, first_idx, end_idx, has_strain):
    """Collect real data rows (footers dropped).  Returns list of (rowidx, headtext, row)."""
    out = []
    for ri in range(first_idx, end_idx):
        row = rows[ri]
        if not row or all(v is None for v in row):
            continue
        head = str(row[0]).strip() if row[0] is not None else ""
        if has_strain and FOOTER.match(head):
            continue
        if not has_strain:                        # continuation block: numeric-only rows
            if fnum(row[0]) is None:
                continue
        out.append((ri, head, row))
    return out


def main():
    rows = load()
    roster = build_roster(rows)
    print(f"PT-I parentage roster: {len(roster)} strains")
    print("  " + ", ".join(roster))

    recs, reconcile = [], {}

    # ---------------- YIELD ----------------
    # block 1: Strain + Mean + 5 loc.  1-based tp6 anchor -> 0-based marker index;
    # header is the row right after the marker, data starts after header + "12 Tests" subheader.
    b1_marker = YIELD_B1_TP - 1
    b1_head = b1_marker + 1
    b1_data0 = b1_head + 2                         # skip header + "12 Tests" subheader row
    hdr = rows[b1_head]
    mean_col = 1
    locs1 = []
    for ci in range(2, len(hdr)):
        if hdr[ci]:
            city, st = parse_state_city(hdr[ci])
            if city:
                locs1.append((ci, city, st))
    d1 = data_rows(rows, b1_data0, YIELD_B2_TP - 1, has_strain=True)[:len(roster)]

    # block 2: 7 loc, no strain/mean, aligned by index
    b2_head = YIELD_B2_TP                          # 1-based marker == row; header at +1
    b2_marker = YIELD_B2_TP - 1
    b2_headrow = rows[b2_marker + 1]
    b2_data0 = b2_marker + 2
    locs2 = []
    for ci in range(0, len(b2_headrow)):
        if b2_headrow[ci]:
            city, st = parse_state_city(b2_headrow[ci])
            if city:
                locs2.append((ci, city, st))
    d2 = data_rows(rows, b2_data0, MAT_TP - 1, has_strain=False)[:len(roster)]

    n_ok = n_tot = 0
    for k in range(len(roster)):
        strain = roster[k]
        vals_for_mean = []
        # block-1 locations
        if k < len(d1):
            row = d1[k][2]
            for ci, city, st in locs1:
                v = fnum(row[ci]) if ci < len(row) and row[ci] is not None else None
                if v is None:
                    continue
                lo, hi = RANGE["YieldBuA"]
                if not (lo <= v <= hi):
                    print(f"  ! Yield {strain} @ {city},{st} out of range: {v}")
                    continue
                vals_for_mean.append(v)
                recs.append((YEAR, TESTTYPE, MG, CODE, strain, city, st, "YieldBuA",
                             round(v, 1), UNITS["YieldBuA"], SOURCE))
        # block-2 continuation locations
        if k < len(d2):
            row = d2[k][2]
            for ci, city, st in locs2:
                v = fnum(row[ci]) if ci < len(row) and row[ci] is not None else None
                if v is None:
                    continue
                lo, hi = RANGE["YieldBuA"]
                if not (lo <= v <= hi):
                    print(f"  ! Yield {strain} @ {city},{st} out of range: {v}")
                    continue
                recs.append((YEAR, TESTTYPE, MG, CODE, strain, city, st, "YieldBuA",
                             round(v, 1), UNITS["YieldBuA"], SOURCE))
        # reconcile block-1 loc mean vs printed Mean (block 2 not in printed mean col here)
        if k < len(d1):
            printed = fnum(d1[k][2][mean_col]) if mean_col < len(d1[k][2]) else None
            if printed is not None and vals_for_mean:
                # printed mean is over all 12 tests; block-1 partial mean won't equal it, so we
                # reconcile the FULL 12-loc row-mean instead (computed below).
                pass
    # full 12-loc reconcile for yield
    n_ok = n_tot = 0
    ydf_tmp = pd.DataFrame([r for r in recs if r[7] == "YieldBuA"],
                           columns=["Year", "TT", "MG", "Test", "Strain", "City", "State",
                                    "Ph", "V", "U", "Src"])
    for k in range(len(roster)):
        strain = roster[k]
        if k >= len(d1):
            continue
        printed = fnum(d1[k][2][mean_col]) if mean_col < len(d1[k][2]) else None
        got = ydf_tmp[ydf_tmp.Strain == strain].V.tolist()
        if printed is not None and got:
            n_tot += 1
            if abs(sum(got) / len(got) - printed) <= 0.6:
                n_ok += 1
    reconcile["YieldBuA"] = (n_ok, n_tot, len(locs1) + len(locs2))

    # ---------------- MATURITY ----------------
    m_marker = MAT_TP - 1
    m_head = m_marker + 1
    m_data0 = m_marker + 3                         # skip header + "8 Tests" subheader
    mhdr = rows[m_head]
    mlocs = []
    for ci in range(2, len(mhdr)):
        if mhdr[ci]:
            city, st = parse_state_city(mhdr[ci])
            if city:
                mlocs.append((ci, city, st))
    md = data_rows(rows, m_data0, SECTION_END - 1, has_strain=True)[:len(roster)]

    # anchor: the roster row that is printed as absolute DATES (Steele, entry #2)
    anchor = {}
    anchor_strain = None
    for (ri, head, row) in md:
        if any(ci < len(row) and isinstance(row[ci], datetime.datetime) for ci, _, _ in mlocs):
            anchor_strain = clean_strain(head)
            for ci, city, st in mlocs:
                if ci < len(row) and isinstance(row[ci], datetime.datetime):
                    anchor[(city, st)] = doy(row[ci])
            break
    print(f"\nMaturity anchor row = {anchor_strain!r}; anchor DOY per loc: "
          f"{ {f'{c},{s}': d for (c, s), d in anchor.items()} }")

    m_ok = m_tot = 0
    for k in range(min(len(md), len(roster))):
        strain = roster[k]
        row = md[k][2]
        offs_for_mean = []
        for ci, city, st in mlocs:
            if ci >= len(row) or row[ci] is None:
                continue
            cell = row[ci]
            if isinstance(cell, datetime.datetime):        # anchor row: value IS the date
                val, recon = doy(cell), None
            else:
                base, off = anchor.get((city, st)), fnum(cell)
                if base is None or off is None:
                    continue
                val, recon = base + off, off
            lo, hi = RANGE["Maturity"]
            if not (lo <= val <= hi):
                print(f"  ! Maturity {strain} @ {city},{st} out of range: {val}")
                continue
            if recon is not None:
                offs_for_mean.append(recon)
            recs.append((YEAR, TESTTYPE, MG, CODE, strain, city, st, "Maturity",
                         round(val, 1), UNITS["Maturity"], SOURCE))
        printed = fnum(row[1]) if len(row) > 1 else None    # printed Mean = mean OFFSET
        if printed is not None and offs_for_mean and strain != anchor_strain:
            m_tot += 1
            if abs(sum(offs_for_mean) / len(offs_for_mean) - printed) <= 0.6:
                m_ok += 1
    reconcile["Maturity"] = (m_ok, m_tot, len(mlocs))

    df = pd.DataFrame(recs, columns=["Year", "TestType", "TestMG", "Test", "Strain", "City",
                                     "State", "Phenotype", "Value_num", "Units", "Source"])
    df.to_csv(OUT, index=False)

    print("\n=== per-trait extraction ===")
    print(df.groupby("Phenotype").size().to_string())
    print(f"\nyield locations b1={len(locs1)} {[c for _,c,_ in locs1]}")
    print(f"yield locations b2={len(locs2)} {[c for _,c,_ in locs2]}")
    print(f"maturity locations={len(mlocs)} {[c for _,c,_ in mlocs]}")
    print("\n=== reconcile (row-mean vs printed 'Mean'; Maturity = offset-mean) ===")
    for t in ["YieldBuA", "Maturity"]:
        ok, tot, nl = reconcile[t]
        print(f"  {t:10} {ok}/{tot} strains reconcile  ({nl} locations)")

    cross_check(df, roster, anchor_strain)
    print(f"\nwrote {OUT.name}  ({len(df):,} rows)")
    return df


def cross_check(df, roster, anchor_strain):
    """KEY EVIDENCE: PT-I's data currently lives in the F4U MISLABELED as 'UT-I'.  For the pure PT-I
    strains, confirm the green-direct values MATCH the F4U 'UT-I' values (same underlying data).
    Match by (Strain, City, trait) on normalized keys; report match rate + examples."""
    f = pd.read_csv(F4U, low_memory=False)
    u = f[f.Test == "UT-I"].copy()
    u["V"] = pd.to_numeric(u.Value, errors="coerce")
    u = u.dropna(subset=["V"])
    # pure PT-I strains = roster minus the shared checks that also live in the real UT-I
    shared = {"Hark", "Steele", "SD73-2"}          # Hark/Steele are common checks; ambiguous origin
    pure = [s for s in roster if s not in shared]

    def ck(s):
        return normkey(s)

    def ckcity(s):
        return re.sub(r"[^a-z0-9]", "", str(s).lower())

    fidx = {}
    for _, r in u.iterrows():
        fidx[(ck(r.Strain), ckcity(r.City), r.Phenotype)] = r.V

    print("\n=== CROSS-CHECK vs F4U 'UT-I' (where PT-I currently lives, mislabeled) ===")
    for trait in ["YieldBuA", "Maturity"]:
        g = df[(df.Phenotype == trait) & (df.Strain.isin(pure))]
        matched = mism = only_green = 0
        examples = []
        mismex = []
        for _, r in g.iterrows():
            key = (ck(r.Strain), ckcity(r.City), trait)
            fv = fidx.get(key)
            if fv is None:
                only_green += 1
                continue
            tol = 0.15 if trait == "YieldBuA" else 1.5
            if abs(fv - r.Value_num) <= tol:
                matched += 1
                if len(examples) < 4:
                    examples.append(f"{r.Strain}@{r.City}: green {r.Value_num} == F4U {fv}")
            else:
                mism += 1
                if len(mismex) < 6:
                    mismex.append(f"{r.Strain}@{r.City}: green {r.Value_num} vs F4U {fv} "
                                  f"(d={r.Value_num-fv:+.1f})")
        denom = matched + mism
        rate = 100 * matched / denom if denom else 0
        print(f"\n  {trait}: {matched}/{denom} overlapping cells match "
              f"({rate:.1f}%); {only_green} green-only cells NOT in F4U (newly recovered)")
        for e in examples:
            print(f"      OK  {e}")
        for e in mismex:
            print(f"      XX  {e}")


if __name__ == "__main__":
    main()
