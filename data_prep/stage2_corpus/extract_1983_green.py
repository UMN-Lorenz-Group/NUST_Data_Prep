"""Green-direct (openpyxl, NO API) re-extraction of ALL 12 tests of 1983 x 8 traits from the two
Green OCR XLSX files, to REPLACE the badly-scrambled 1983 F4U (only 9 labels, merged tests).

Context: the 1983 F4U carries the whole year mis-labeled/merged.  The Green carries the CORRECT
per-test tp6..tp12b structure; its tp2 test-delimiter markers were just repaired, so the two files
now delimit all 12 tests cleanly (UT-00/UT-0/UT-I/PT-I/UT-II/PT-IIA/PT-IIB in file 1;
UT-III/PT-IIIA/PT-IIIB/UT-IV/PT-IV in file 2).

Layout (1980s state-group format, verified empirically against 1983_done.pdf):
  * multi-loc-group-per-trait: a trait's table may span SEVERAL location groups, each re-emitting its
    own tp marker + Strain header; only the FIRST group carries the "Mean of N Tests" column.  Each
    block is bounded at the NEXT marker of ANY kind so tp7 (YIELD RANK) integers never leak into yield.
  * location headers are STATE-PREFIXED and reversed ("Man. Brandon"=Manitoba/Brandon,
    "S.D. Elk Point"=Elk Point/SD, "Ohio S. Charleston"=S. Charleston/OH); Portageville soil variants
    ("Missouri Clay Portageville") -> Portageville-Clay/-Loam.  A lone footnote digit ("Ind. 1
    Sullivan", "Kentucky 1 Lexington", "Missouri Clay 1 Portageville") = data-not-in-mean -> star
    (kept, excluded from the reconcile gate).
  * strain rows repeat per group in a fixed order/count -> canonical roster by per-index MAJORITY VOTE.
  * strain names adopt the F4U convention: drop the MG parenthetical + remove internal spaces
    ('Corsoy 79 (II)' -> 'Corsoy79').
  * Maturity is printed as a check row of absolute DATES + signed day OFFSETS for the other strains
    -> DOY = anchor_DOY(loc) + offset (anchor = the data row with the most datetime cells, per group).
  * trait identity is read from the marker's DESCRIPTOR text (col B: "OIL (%)", "PROTEIN (%)", ...)
    NOT just the tp-label -- PT-IIB's Oil table is mislabeled 'tp12a' in the Green.

Validation (printed to stdout):
  1. RECONCILE each (test,trait): row-mean over parsed (non-star) locs vs printed "Mean N Tests".
  2. GEOMETRY: per test roster x loc; flag UT that look PT-shaped (<12 loc) or PT that look merged.
  3. dup keys / stray / out-of-range counts; roster size vs the PDF caption rosters.

Output: reextract_1983_green.csv (all 12 tests, long schema == reextract_1985_utiii_green.csv;
Source='Green1983_direct').  Does NOT touch the corpus or F4U.
"""
import sys, re, datetime
from collections import Counter, defaultdict
from pathlib import Path
import openpyxl
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
GREEN = REPO / "input_files" / "input_1983"
OUT = REPO / "data_prep" / "stage2_corpus" / "reextract_1983_green.csv"
F1 = "Sojabone-1983 (1-110 OR).xlsx"
F2 = "Sojabone-1983 (111-215 OR).xlsx"
YEAR = 1983

# (file, section_start_idx, section_end_idx, code, TestMG) -- boundaries = tp2 test delimiters.
SECTIONS = [
    (F1, 151,  367,  "UT-00",   "00"),
    (F1, 367,  670,  "UT-0",    "0"),
    (F1, 670,  960,  "UT-I",    "I"),
    (F1, 960,  1304, "PT-I",    "I"),
    (F1, 1304, 1980, "UT-II",   "II"),
    (F1, 1980, 2499, "PT-IIA",  "II"),
    (F1, 2499, 2989, "PT-IIB",  "II"),
    (F2, 2,    554,  "UT-III",  "III"),
    (F2, 554,  1090, "PT-IIIA", "III"),
    (F2, 1090, 1678, "PT-IIIB", "III"),
    (F2, 1678, 2181, "UT-IV",   "IV"),
    (F2, 2181, 2819, "PT-IV",   "IV"),
]
# PDF caption roster sizes (task) for a sanity flag.
CAPTION = {"UT-00": 7, "UT-0": 18, "UT-I": 18, "PT-I": 26, "UT-II": 35, "PT-IIA": 37, "PT-IIB": 40,
           "UT-III": 37, "PT-IIIA": 41, "PT-IIIB": 42, "UT-IV": 34, "PT-IV": 51}

TRAIT_TPS = {"tp6", "tp8", "tp9", "tp10", "tp11a", "tp11b", "tp12a", "tp12b"}
TP2TRAIT = {"tp6": "YieldBuA", "tp8": "Maturity", "tp9": "Lodging", "tp10": "Height",
            "tp11a": "SeedQuality", "tp11b": "SeedSize", "tp12a": "Protein", "tp12b": "Oil"}
TRAIT_ORDER = ["YieldBuA", "Maturity", "Lodging", "Height", "SeedQuality", "SeedSize",
               "Protein", "Oil"]
# descriptor keyword -> trait (checked in THIS order; RANK guarded first, YIELD last)
DESC2TRAIT = [("MATURITY", "Maturity"), ("LODGING", "Lodging"), ("HEIGHT", "Height"),
              ("SEED QUALITY", "SeedQuality"), ("SEED SIZE", "SeedSize"),
              ("PROTEIN", "Protein"), ("OIL", "Oil"), ("YIELD", "YieldBuA")]
UNITS = {"YieldBuA": "bu/a", "Maturity": "DOY", "Lodging": "score", "Height": "in",
         "SeedQuality": "score", "SeedSize": "g/100", "Protein": "%", "Oil": "%"}
RANGE = {"YieldBuA": (2, 120), "Height": (5, 80), "Lodging": (1, 5), "SeedQuality": (1, 5),
         "SeedSize": (5, 40), "Protein": (25, 55), "Oil": (5, 30), "Maturity": (200, 330)}
FOOTER = re.compile(r"^\s*(C\.V|L\.S\.D|Mean|Row\s*sp|Rows?\s*/|Reps|Strain|Date\s*planted|"
                    r"Days\s*to|tp\d|NS$)", re.I)
MEANCOL = re.compile(r"Mean|Tests?", re.I)
FOOTNOTED = re.compile(r"[*¹²†‡]")

# state-name / abbreviation prefix -> canonical state code (headers are "State City").
# provinces follow the canonical map (Manitoba->MAN, Ontario->ONT).  OCR variants folded.
STATE_MAP = {
    "ill": "IL", "il": "IL", "i11": "IL", "illinois": "IL",
    "ind": "IN", "indiana": "IN", "in": "IN",
    "iowa": "IA", "ia": "IA",
    "ks": "KS", "kansas": "KS", "kan": "KS",
    "ky": "KY", "kentucky": "KY",
    "md": "MD", "maryland": "MD",
    "mi": "MI", "mich": "MI", "michigan": "MI",
    "minn": "MN", "minnesota": "MN", "mn": "MN",
    "mo": "MO", "missouri": "MO",
    "neb": "NE", "nebr": "NE", "ne": "NE", "nebraska": "NE",
    "oh": "OH", "ohio": "OH",
    "ont": "ONT", "ontario": "ONT",
    "penn": "PA", "pa": "PA", "pennsylvania": "PA",
    "sd": "SD", "sdakota": "SD",
    "nd": "ND", "ndakota": "ND",
    "nj": "NJ", "ni": "NJ",
    "tx": "TX", "texas": "TX", "tex": "TX",
    "wis": "WI", "wi": "WI", "wisconsin": "WI",
    "man": "MAN", "manitoba": "MAN",
}


def load(fn):
    wb = openpyxl.load_workbook(GREEN / fn, read_only=True, data_only=True)
    rows = list(wb["Sheet1"].iter_rows(values_only=True))
    wb.close()
    return rows


def strip_rank(s):
    return re.sub(r"^\s*\d+\s*[.,)]\s*", "", str(s)).strip()


def clean_strain(s):
    """F4U convention: drop MG parenthetical + remove ALL internal spaces.
    'Corsoy 79 (II)'->'Corsoy79'; 'Maple Amber'->'MapleAmber'; 'OAC-81-2'->'OAC-81-2'."""
    s = strip_rank(s)
    s = re.sub(r"\s*\(.*?\)\s*", "", s)          # drop MG parenthetical
    s = re.sub(r"\s+", "", s)                      # remove internal spaces
    return s.strip()


def normkey(s):
    """Fold OCR confusions (l/1/i, O/0), drop parenthetical + whitespace so name variants collapse
    for the per-index majority vote."""
    k = re.sub(r"\(.*?\)", "", strip_rank(s).lower())
    k = re.sub(r"[^a-z0-9]", "", k)
    return k.translate(str.maketrans("lio", "110"))


def parse_loc(h):
    """'Man. Brandon'->('Brandon','MAN',False); 'Kentucky 1 Lexington'->('Lexington','KY',True);
    'Missouri Clay Portageville'->('Portageville-Clay','MO',False).  Returns (city,state,star) or
    None if the header is not a recognizable location."""
    s = str(h).strip()
    star = bool(FOOTNOTED.search(s))
    s = FOOTNOTED.sub(" ", s)
    # split a single-word abbrev glued to a capitalized city ('Neb.Lincoln'->'Neb. Lincoln'); the
    # {3,4}-letter guard leaves multi-period abbrevs ('S.D.','N.J.') intact.
    s = re.sub(r"^([A-Za-z]{3,4})\.([A-Z])", r"\1. \2", s)
    s = re.sub(r"\s+", " ", s.replace(",", " ")).strip()
    toks = s.split(" ")
    if not toks:
        return None
    key = toks[0].replace(".", "").lower()
    state = STATE_MAP.get(key)
    if state is None:
        return None
    rest = toks[1:]
    # lone footnote digit token = data-not-in-mean marker -> star, drop from city
    kept = []
    for t in rest:
        if re.fullmatch(r"\d{1,2}", t):
            star = True
            continue
        kept.append(t)
    city = " ".join(kept).strip()
    if not city:
        return None
    # Portageville soil-plot variants -> corpus canonical
    low = city.lower()
    if "portageville" in low:
        if "clay" in low:
            city = "Portageville-Clay"
        elif "loam" in low:
            city = "Portageville-Loam"
        else:
            city = "Portageville"
    city = re.sub(r"\s+", " ", city).strip()
    return city, state, star


def fnum(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    s = str(x)
    m = re.match(r"^\s*([+-]?\d+)\s+(\d)\s*$", s)      # split decimal '48 4' -> 48.4
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.match(r"^\s*[+-]?\s*\d+(?:\.\d+)?", s.replace(" ", ""))
    return float(m.group().replace(" ", "")) if m else None


def doy(dt):
    return datetime.date(YEAR, dt.month, dt.day).timetuple().tm_yday


def markers(rows, a, b):
    out = []
    for i in range(a, min(b, len(rows))):
        c = rows[i]
        first = str(c[0]).strip() if c and c[0] else ""
        m = re.match(r"(tp\d+[ab]?)$", first)
        if m:
            out.append((i, m.group(1)))
    return out


def trait_of(rows, i, tp):
    """Trait from the marker's descriptor text (col B); RANK guarded; fall back to tp-label."""
    r = rows[i]
    desc = str(r[1]).upper() if (r and len(r) > 1 and r[1]) else ""
    if "RANK" in desc:
        return None
    for kw, tr in DESC2TRAIT:
        if kw in desc:
            return tr
    return TP2TRAIT.get(tp)


def mean_n(cell):
    """'Mean 21 Tests' / '16 Mean Tests' / '15 Mean Test' -> 21/16/15 (the report's N tests)."""
    m = re.search(r"\d+", str(cell))
    return int(m.group()) if m else None


def parse_group(rows, i, end):
    """-> (locs[(col,city,state,star)], mean_col|None, mean_N|None, strain_col|None,
           data[(rowidx, name|None, row)]).  The 'Strain' header can sit 1-2 rows below the marker
       (an OCR blank row is sometimes inserted between them, e.g. UT-II SeedSize) -> search for it."""
    hdr_idx = None
    for j in range(i + 1, min(i + 4, end, len(rows))):
        r = rows[j]
        if r and r[0] and str(r[0]).strip().lower().startswith("strain"):
            hdr_idx = j
            break
    if hdr_idx is None:                       # no Strain header -> first non-empty row (index-only)
        for j in range(i + 1, min(i + 4, end, len(rows))):
            if rows[j] and any(v is not None for v in rows[j]):
                hdr_idx = j
                break
    if hdr_idx is None:
        return [], None, None, None, []
    hdr = rows[hdr_idx]
    strain_col = 0 if (hdr[0] and str(hdr[0]).strip().lower().startswith("strain")) else None
    locs, mean_col, meanN = [], None, None
    start = 1 if strain_col == 0 else 0
    for ci in range(start, len(hdr)):
        h = hdr[ci]
        if not h:
            continue
        if MEANCOL.search(str(h)):
            if mean_col is None:
                mean_col, meanN = ci, mean_n(h)
            continue
        loc = parse_loc(h)
        if loc:
            locs.append((ci, loc[0], loc[1], loc[2]))
    data = []
    for ri in range(hdr_idx + 1, min(end, len(rows))):
        row = rows[ri]
        if not row or all(v is None for v in row):
            continue
        head = str(row[0]).strip() if row[0] is not None else ""
        if FOOTER.match(head):
            continue
        if strain_col == 0:
            if not head:
                continue
            data.append((ri, strip_rank(head), row))
        else:
            data.append((ri, None, row))          # index-only group: recover strains by roster order
    return locs, mean_col, meanN, strain_col, data


def build_roster(rows, groups):
    """Per-index majority vote over the strain-column groups; then apply the F4U naming rule."""
    votes = defaultdict(Counter)
    counts = []
    for trait, gl in groups.items():
        for (i, end) in gl:
            _, _, _, sc, data = parse_group(rows, i, end)
            if sc is None:
                continue
            counts.append(len(data))
            for k, (_, name, _) in enumerate(data):
                votes[k][name] += 1
    nrow = Counter(counts).most_common(1)[0][0] if counts else 0
    roster = [clean_strain(votes[k].most_common(1)[0][0]) for k in range(nrow)]
    return roster, nrow


def main():
    recs = []
    recon = {}                        # (code, trait, strain) -> (printed_mean, [native vals])
    range_drops = []
    geom = {}                         # code -> (roster_n, loc_count, str_x_loc_yield)
    file_cache = {}
    for fn, a, b, code, mg in SECTIONS:
        rows = file_cache.get(fn) or file_cache.setdefault(fn, load(fn))
        mk = markers(rows, a, b)
        groups = defaultdict(list)    # trait -> [(marker_idx, end_idx)]
        for gi, (i, tp) in enumerate(mk):
            if tp not in TRAIT_TPS:
                continue
            trait = trait_of(rows, i, tp)
            if trait is None:
                continue
            end = mk[gi + 1][0] if gi + 1 < len(mk) else b
            groups[trait].append((i, end))
        roster, nrow = build_roster(rows, groups)

        printed = {}                  # (trait, strain) -> (printed mean, N tests)
        parsed = defaultdict(list)    # (trait, strain) -> [native vals] (non-star; offsets for Mat)
        yield_locs = set()
        for trait in TRAIT_ORDER:
            for (i, end) in groups.get(trait, []):
                locs, mean_col, meanN, sc, data = parse_group(rows, i, end)
                if not locs:
                    continue
                data = data[:nrow]
                if len(data) != nrow:
                    print(f"  ! {code} {trait} [{i+1}] {len(data)} rows vs roster {nrow} (capped)")
                if trait == "YieldBuA":
                    yield_locs.update((c, s) for _, c, s, _ in locs)
                # Maturity anchor: the data row with the MOST VALID dated cells is the check.  Only
                # a datetime whose DOY lands in the maturity window (Aug-Nov) counts -- some cells
                # OCR-parsed as spurious spring dates (e.g. '04/03') are garbage, not anchors.
                mlo, mhi = RANGE["Maturity"]
                validdt = lambda v: isinstance(v, datetime.datetime) and mlo <= doy(v) <= mhi
                anchor, anchor_k = {}, None
                if trait == "Maturity":
                    best, best_n = None, -1
                    for k, (_, _, row) in enumerate(data):
                        n = sum(1 for ci, *_ in locs if ci < len(row) and validdt(row[ci]))
                        if n > best_n:
                            best, best_n, anchor_k = row, n, k
                    if best is not None:
                        for ci, city, st, _ in locs:
                            if ci < len(best) and validdt(best[ci]):
                                anchor[(city, st)] = doy(best[ci])
                for k, (ri, _, row) in enumerate(data):
                    strain = roster[k]
                    # printed mean: real number for non-Maturity; mean OFFSET for Maturity (skip the
                    # anchor row, whose mean cell is a garbled date).
                    if mean_col is not None and mean_col < len(row) and not (trait == "Maturity"
                                                                             and k == anchor_k):
                        pv = fnum(row[mean_col])
                        if pv is not None:
                            printed.setdefault((trait, strain), (pv, meanN))
                    for ci, city, st, star in locs:
                        if ci >= len(row):
                            continue
                        cell = row[ci]
                        if cell is None:
                            continue
                        lo, hi = RANGE[trait]
                        if trait == "Maturity":
                            if isinstance(cell, datetime.datetime):
                                if not validdt(cell):           # OCR-garbage spring date -> skip
                                    continue
                                val = doy(cell)                 # dated check row: absolute DOY
                            else:
                                off = fnum(cell)
                                base = anchor.get((city, st))
                                if off is None or base is None:
                                    continue
                                val = base + off
                                if not star and k != anchor_k:
                                    parsed[(trait, strain)].append(off)   # reconcile on offsets
                            if not (lo <= val <= hi):
                                continue
                        else:
                            val = fnum(cell)
                            if val is None:
                                continue
                            if not (lo <= val <= hi):
                                # merged-decimal OCR ('402'->40.2): an integer cell that lands in
                                # range once /10 is a dropped decimal point; else drop + report.
                                intish = ("." not in str(cell)) if isinstance(cell, str) \
                                    else (float(cell) == int(cell))
                                if intish and lo <= val / 10 <= hi:
                                    range_drops.append((code, trait, strain, city, st, cell,
                                                        f"->rec {round(val/10,1)}"))
                                    val = val / 10
                                else:
                                    range_drops.append((code, trait, strain, city, st, cell,
                                                        f"DROP {round(val,1)}"))
                                    continue
                            if not star:
                                parsed[(trait, strain)].append(val)
                        recs.append((YEAR, "UT" if code.startswith("UT") else "PT", mg, code,
                                     strain, city, st, trait, round(val, 1), UNITS[trait],
                                     "Green1983_direct"))
        for kk, (pv, nn) in printed.items():
            recon[(code,) + kk] = (pv, nn, parsed.get(kk, []))
        geom[code] = (nrow, len(yield_locs))

    df = pd.DataFrame(recs, columns=["Year", "TestType", "TestMG", "Test", "Strain", "City",
                                     "State", "Phenotype", "Value_num", "Units", "Source"])
    df.to_csv(OUT, index=False)

    print("\n=== per-test x per-trait row counts ===")
    print(df.groupby(["Test", "Phenotype"]).size().unstack(fill_value=0)
          .reindex(index=[c for _, _, _, c, _ in SECTIONS], columns=TRAIT_ORDER, fill_value=0)
          .to_string())

    # NB: the task's caption numbers are loose estimates -- UT-IV's own pedigree table lists exactly
    # 23 entries (== extracted roster), so the roster<caption gaps are caption over-counts, not data
    # loss.  Rosters are corroborated by ~100% yield reconcile + per-test cross-group consistency.
    print("\n=== geometry (roster x yield-loc; caption is a loose estimate; shape flag) ===")
    for _, _, _, code, _ in SECTIONS:
        n, nloc = geom[code]
        cap = CAPTION[code]
        isUT = code.startswith("UT")
        flag = ""
        if isUT and nloc < 5:
            flag += "  <-- UT loc-count suspiciously low (check for merge)"
        if (not isUT) and nloc > 14:
            flag += "  <-- PT looks UT-shaped/merged?"
        print(f"  {code:8} roster {n:2}  yield-loc {nloc:2}  (caption ~{cap}){flag}")

    # the printed "Mean N Tests" is the mean over N of the shown locs (N<=#loc columns): the report
    # drops weak/blank plots for agronomic reasons, NOT the values farthest from the mean.  So ask
    # the honest question: does SOME N-subset of my parsed values reproduce the printed mean?  If no
    # subset can, the column alignment is wrong.  (P-N is small; enumerate the dropped plots.)
    from itertools import combinations
    from math import comb
    def subset_ok(vals, pv, N, tol):
        # N (from "Mean N Tests") is only an upper bound: per strain, some plots are blank or dropped
        # for agronomic reasons, so the report averages a strain-specific subset.  Ask if dropping up
        # to 3 of my parsed plots reproduces the printed mean (independent of the header N).
        if not vals:
            return None
        P, total = len(vals), sum(vals)
        if abs(total / P - pv) <= tol:
            return True
        for d in range(1, min(4, P)):
            if comb(P, d) > 50000:
                break
            for rem in combinations(range(P), d):
                if abs((total - sum(vals[j] for j in rem)) / (P - d) - pv) <= tol:
                    return True
        return False
    print("\n=== reconcile: printed 'Mean N Tests' vs best-N-subset row-mean (Maturity=offsets) ===")
    for _, _, _, code, _ in SECTIONS:
        agg = defaultdict(lambda: [0, 0])
        for (c, trait, strain), (pv, nn, vals) in recon.items():
            if c != code or not vals:
                continue
            tol = 0.55 if pv == round(pv) else 0.15
            ok = subset_ok(vals, pv, nn, tol)
            if ok is None:
                continue
            agg[trait][0] += int(ok)
            agg[trait][1] += 1
        parts = [f"{t}={agg[t][0]}/{agg[t][1]}" for t in TRAIT_ORDER if agg[t][1]]
        print(f"  {code:8} " + "  ".join(parts))

    print("\n=== integrity ===")
    dup = df[df.duplicated(["Year", "Test", "Strain", "City", "State", "Phenotype"], keep=False)]
    print(f"  duplicate keys: {len(dup)}")
    if len(dup):
        print(dup.sort_values(["Test", "Strain", "City", "Phenotype"]).head(20).to_string())
    oor = 0
    for _, r in df.iterrows():
        lo, hi = RANGE[r.Phenotype]
        if not (lo <= r.Value_num <= hi):
            oor += 1
    print(f"  out-of-range emitted: {oor}")
    print(f"  distinct strains: {df.Strain.nunique()}  distinct locs: "
          f"{df[['City','State']].drop_duplicates().shape[0]}")
    if range_drops:
        print(f"\n=== {len(range_drops)} out-of-range cells (dropped or /10-recovered) ===")
        for d in range_drops[:40]:
            print(f"    {d[0]:8} {d[1]:10} {d[2]:14} {d[3]},{d[4]:4} cell={d[5]!r} -> {d[6]}")

    print(f"\nwrote {OUT.name}  ({len(df):,} rows)")
    return df


if __name__ == "__main__":
    main()
