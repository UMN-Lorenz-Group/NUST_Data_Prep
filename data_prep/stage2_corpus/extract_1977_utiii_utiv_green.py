"""Extract the 1977 Uniform Test III (UT-III) and Uniform Test IV (UT-IV) x 8 traits DIRECTLY from
the Green OCR XLSX, NO API calls -- the "green-direct, no-API" re-extraction (C1) for the 1977
test-map source repair.

Context: 1977 UT-III / UT-IV were "dropped" tests -- their tp2 parentage markers were missing, so
the combine step merged them into neighbour groups and the current F4U carries them mislabeled (the
110_relabel_year backward shift {UT-III->PT-III, PT-III->PT-IV}).  The missing tp2 markers were
re-inserted, so the Green now delimits them as Group_7 (UT-III, xlsx rows 2472-3613) and Group_9
(UT-IV, xlsx rows 3942-4592).  Their data was fully in the Green all along; this extracts it.

Layout (verified empirically -- a 1970s "state-group" page, MORE complex than the 1984/1985 Green):
  * multi-loc-group-per-trait: a trait's table spans SEVERAL location groups, each re-emitting its
    own tp marker (tp6=Yield, tp7=YieldRank[skip], tp8=Maturity, tp9=Lodging, tp10=Height,
    tp11a=SeedQuality, tp11b=SeedSize, tp12a=Protein, tp12b=Oil).  Each block is bounded at the
    NEXT marker of ANY kind -- tp7 rank AND tp5 (2-/3-year running means) sit between real-trait
    markers and must not leak in.
  * ONLY the FIRST group of a trait carries the "Strain" column, the "N Tests" count row (the row
    directly under the header) and the interspersed regional-Mean columns ("East (Mean) Coast",
    "(Mean) Central").  Those regional-mean columns are SKIPPED as locations (kept only to reconcile).
  * secondary groups usually DROP the Strain column entirely -> strains recovered by ROW INDEX from
    the canonical roster.  In those index-only groups the footer rows (C.V./L.S.D./Row sp/Reps) have
    a NUMERIC col-0 and so evade the label-based footer filter -> data is capped at the roster length.
  * location headers are STATE-PREFIXED and reversed vs 1984/85: "Pa. Landisville" = City Landisville
    / State PA; "S. Dakota Elk Point" = Elk Point / SD; a trailing lone "I" (irrigated) is dropped.
  * Maturity is "relative data": one check row (Woodworth / Cutler 71) is printed as absolute DATES
    and every other strain as a signed day OFFSET -> DOY = anchor_DOY(loc) + offset.
  * canonical roster = per-index MAJORITY VOTE over the strain-column groups (strains repeat per group
    with independent OCR variance but always the same order/count); data-group names are already the
    clean forms ("Elf", not the parentage's "Elf (L74D-611)").

Validation (the point):
  1. RECONCILE each trait: region row-mean over parsed locs (per strain) vs the printed regional
     "Mean N Tests" (East Coast / Central); Maturity reconciled on offsets.
  2. CROSS-CHECK vs the PDF-recovered oracles utiii_1977_alltraits.csv / utiv_1977_recovered.csv:
     per-strain value-multiset match rate per trait, both directions.  Maturity is cross-checked on
     OFFSETS (both oracles store maturity as offsets; green emits DOY, so a parallel offset multiset
     is kept for the compare).
  3. RANGE gate: out-of-range cells dropped and reported.

Value cleaning carries the split-decimal repair ('48 4' -> 48.4).  Merged-decimal OCR errors
('402' for 40.2, protein '57.6' for 37.6) are left to the range gate to flag/drop -- reported.

Output: reextract_1977_utiii_utiv_green.csv (both tests, long schema identical to
reextract_1985_utiii_green.csv; Test in {UT-III, UT-IV}).
"""
import sys, re, datetime
from collections import Counter, defaultdict
from pathlib import Path
import openpyxl
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
GREEN = REPO / "input_files" / "input_1977" / "Sojabone-1977 (0-143 OR).xlsx"
OUT = REPO / "data_prep" / "stage2_corpus" / "reextract_1977_utiii_utiv_green.csv"
_ARCH = REPO / "data_prep" / "stage2_corpus" / "_archive_superseded_2026-07"
ORACLE = {"UT-III": _ARCH / "utiii_1977_alltraits.csv",
          "UT-IV": _ARCH / "utiv_1977_recovered.csv"}  # oracles archived post green-direct supersede

YEAR = 1977
# (code, TestMG, scan_start_idx, section_end_idx, source_tag)  -- idx = xlsx_row - 1
SECTIONS = [
    ("UT-III", "III", 2699, 3613, "Green1977_UTIII_direct"),
    ("UT-IV",  "IV",  4062, 4592, "Green1977_UTIV_direct"),
]
TP2TRAIT = {"tp6": "YieldBuA", "tp8": "Maturity", "tp9": "Lodging", "tp10": "Height",
            "tp11a": "SeedQuality", "tp11b": "SeedSize", "tp12a": "Protein", "tp12b": "Oil"}
TRAIT_ORDER = ["YieldBuA", "Maturity", "Lodging", "Height", "SeedQuality", "SeedSize",
               "Protein", "Oil"]
UNITS = {"YieldBuA": "bu/a", "Maturity": "DOY", "Lodging": "score", "Height": "in",
         "SeedQuality": "score", "SeedSize": "g/100", "Protein": "%", "Oil": "%"}
RANGE = {"YieldBuA": (2, 120), "Height": (5, 80), "Lodging": (1, 5), "SeedQuality": (1, 5),
         "SeedSize": (5, 40), "Protein": (25, 55), "Oil": (5, 30), "Maturity": (200, 330)}
FOOTER = re.compile(r"^\s*(C\.V|L\.S\.D|Mean|Row\s*sp|Rows?\s*/|Reps|Strain|Date\s*planted|"
                    r"Days\s*to|tp\d|NS$)", re.I)
MEANCOL = re.compile(r"Mean|Tests", re.I)
FOOTNOTED = re.compile(r"[*¹†‡]")

# state-name / abbreviation prefix -> canonical two-letter state (headers are "State City").
# includes the common 1977 OCR variants ("Indians" for Indiana, "Ill." for Illinois).
STATE_MAP = {
    "pa": "PA", "nj": "NJ", "del": "DE", "de": "DE", "md": "MD", "ohio": "OH", "oh": "OH",
    "indiana": "IN", "indians": "IN", "ind": "IN", "in": "IN", "ky": "KY", "illinois": "IL",
    "ill": "IL", "il": "IL", "iowa": "IA", "ia": "IA", "missouri": "MO", "mo": "MO",
    "s dakota": "SD", "sdakota": "SD", "s d": "SD", "sd": "SD", "neb": "NE", "nebr": "NE",
    "ne": "NE", "kansas": "KS", "kan": "KS", "ks": "KS", "texas": "TX", "tex": "TX",
    "tx": "TX", "minn": "MN", "wis": "WI",
}
# bare city headers that lost their state prefix in OCR -> inferred state (from the same tables).
CITY_STATE = {"wooster": "OH"}


def load():
    wb = openpyxl.load_workbook(GREEN, read_only=True, data_only=True)
    rows = list(wb["Sheet1"].iter_rows(values_only=True))
    wb.close()
    return rows


def strip_rank(s):
    return re.sub(r"^\s*\d+\s*[.,)]\s*", "", str(s)).strip()


def normkey(s):
    """Fold OCR confusions (l/1/i, O/0), drop parenthetical + all whitespace so name variants
    collapse ('Un i on'->union, 'Elf (L74D-611)'->elf)."""
    k = re.sub(r"\(.*?\)", "", strip_rank(s).lower())
    k = re.sub(r"[^a-z0-9]", "", k)
    return k.translate(str.maketrans("lio", "110"))


def parse_loc(h):
    """'Pa. Landisville'->('Landisville','PA'); 'S. Dakota Elk Point'->('Elk Point','SD').
    Returns (city, state, star) or None if the header is not a recognizable location."""
    s = str(h).strip()
    star = bool(FOOTNOTED.search(s))
    s = re.sub(r"[?]+", " ", FOOTNOTED.sub("", s))          # strip unreadable-OCR '?????' runs
    s = re.sub(r"\s+", " ", s).strip()
    toks = s.split(" ")
    if not toks:
        return None
    two = " ".join(toks[:2]).lower().replace(".", "").strip()
    one = toks[0].lower().replace(".", "").strip()
    if len(toks) >= 3 and two in STATE_MAP:
        state, city = STATE_MAP[two], " ".join(toks[2:])
    elif one in STATE_MAP:
        state, city = STATE_MAP[one], " ".join(toks[1:])
    elif one in CITY_STATE:                                  # bare city, state lost in OCR
        state, city = CITY_STATE[one], s
    else:
        return None
    city = re.sub(r"\s+[A-Z]$", "", city.strip()).strip()   # drop trailing lone 'I' (irrigated)
    city = re.sub(r"\s+", " ", city)
    return (city, state, star) if city else None


def region_of(h):
    """None if not a regional-mean header; else 'East' or 'Central'."""
    if not MEANCOL.search(str(h)):
        return None
    return "Central" if re.search("central", str(h), re.I) else "East"


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
    for i in range(a, b):
        c = rows[i]
        first = str(c[0]).strip() if c and c[0] else ""
        m = re.match(r"(tp\d+[ab]?)$", first)
        if m:
            out.append((i, m.group(1)))
    return out


def parse_group(rows, i, end):
    """-> (locs[(col,city,state,star,region)], mean_cols[(col,region)], strain_col|None,
           count_row_idx|None, data[(rowidx, name|None, row)])."""
    hdr = rows[i + 1]
    strain_col = 0 if (hdr and hdr[0] and str(hdr[0]).strip().lower().startswith("strain")) else None
    locs, mean_cols = [], []
    has_mean = any(region_of(h) for h in hdr[1:] if h) if hdr else False
    current = "East" if has_mean else "Central"       # secondary/no-mean groups are all Central
    start = 1 if strain_col == 0 else 0
    for ci in range(start, len(hdr)):
        h = hdr[ci]
        if not h:
            continue
        reg = region_of(h)
        if reg is not None:
            if reg == "Central":
                current = "Central"
            mean_cols.append((ci, reg))
            continue
        loc = parse_loc(h)
        if loc:
            locs.append((ci, loc[0], loc[1], loc[2], current))
    # the "N Tests" count row sits directly under the header (col0 empty) when mean cols exist
    count_row = i + 2 if (mean_cols and i + 2 < end and (rows[i + 2] and
                          (rows[i + 2][0] is None or str(rows[i + 2][0]).strip() == ""))) else None
    data = []
    for ri in range(i + 2, end):
        if count_row is not None and ri == count_row:
            continue
        row = rows[ri]
        if not row or all(v is None for v in row):
            continue
        head = str(row[0]).strip() if row[0] is not None else ""
        if FOOTER.match(head):
            continue
        if strain_col == 0:
            if not head:                       # blank-name row (stray count/spacer) in a named group
                continue
            data.append((ri, strip_rank(head), row))
        else:
            # index-only group: strains are in fixed roster order with NO interleaved non-data rows
            # until the (unlabeled) footer block, and a strain's first-column loc may be blank -> take
            # every non-blank row in order; caller caps at the roster length so footers drop off.
            data.append((ri, None, row))
    return locs, mean_cols, strain_col, count_row, data


def build_roster(rows, groups):
    """Per-index majority vote over the strain-column groups."""
    votes = defaultdict(Counter)
    counts = []
    for trait, gl in groups.items():
        for (i, end) in gl:
            _, _, sc, _, data = parse_group(rows, i, end)
            if sc is None:
                continue
            counts.append(len(data))
            for k, (_, name, _) in enumerate(data):
                votes[k][name] += 1
    nrow = Counter(counts).most_common(1)[0][0] if counts else 0
    roster = [votes[k].most_common(1)[0][0] for k in range(nrow)]
    return roster, nrow


def main():
    rows = load()
    recs = []
    recon = {}                       # (code, trait, strain, region) -> [native vals] / printed mean
    mat_off = defaultdict(list)      # (code, strain) -> [green maturity offsets] for cross-check
    range_drops = []
    for code, mg, a, b, tag in SECTIONS:
        mk = markers(rows, a, b)
        groups = defaultdict(list)
        for gi, (i, tp) in enumerate(mk):
            if tp not in TP2TRAIT:
                continue
            endb = mk[gi + 1][0] if gi + 1 < len(mk) else b
            groups[TP2TRAIT[tp]].append((i, endb))
        roster, nrow = build_roster(rows, groups)
        print(f"\n{code}: roster {nrow} strains; groups " +
              ", ".join(f"{t}x{len(g)}" for t, g in sorted(groups.items())))

        printed = {}                 # (trait, strain, region) -> printed regional mean
        parsed = defaultdict(list)   # (trait, strain, region) -> [native vals]
        for trait in TRAIT_ORDER:
            for (i, end) in groups.get(trait, []):
                locs, mean_cols, sc, count_row, data = parse_group(rows, i, end)
                if not locs:
                    continue
                data = data[:nrow]                       # cap index-only groups at roster length
                if len(data) != nrow:
                    print(f"  ! {code} {trait} [{i+1}] {len(data)} rows vs roster {nrow} (kept)")
                # Maturity anchor: the single check row printed as absolute dates, per location
                anchor = {}
                if trait == "Maturity":
                    for (_, _, row) in data:
                        if any(ci < len(row) and isinstance(row[ci], datetime.datetime)
                               for ci, *_ in locs):
                            for ci, city, st, _, _ in locs:
                                if ci < len(row) and isinstance(row[ci], datetime.datetime):
                                    anchor[(city, st)] = doy(row[ci])
                            break
                # printed regional means live in the first (strain-col) group
                mean_by_region = {}
                for (ci, reg) in mean_cols:
                    mean_by_region.setdefault(reg, ci)
                for k, (ri, _, row) in enumerate(data):
                    strain = roster[k]
                    for reg, ci in mean_by_region.items():
                        if ci < len(row):
                            pv = fnum(row[ci])
                            if pv is not None:
                                printed[(trait, strain, reg)] = pv
                    for ci, city, st, star, reg in locs:
                        if ci >= len(row):
                            continue
                        cell = row[ci]
                        if cell is None:
                            continue
                        lo, hi = RANGE[trait]
                        if trait == "Maturity":
                            if isinstance(cell, datetime.datetime):
                                val, off = doy(cell), None         # anchor row: absolute date
                            else:
                                off = fnum(cell)
                                if off is None:
                                    continue
                                base = anchor.get((city, st))
                                val = base + off if base is not None else None
                            # reconcile/cross-check maturity on the anchor-independent OFFSET
                            if off is not None and not star:
                                parsed[(trait, strain, reg)].append(off)
                                mat_off[(code, strain)].append(off)
                            if val is None or not (lo <= val <= hi):    # no anchor -> no DOY to emit
                                continue
                        else:
                            val = fnum(cell)
                            if val is None:
                                continue
                            if not (lo <= val <= hi):
                                # merged-decimal OCR ('402'->40.2, '25'->2.5): an integer-like cell
                                # that lands in range once divided by 10 is a dropped decimal point.
                                intish = ("." not in str(cell)) if isinstance(cell, str) else \
                                         (float(cell) == int(cell))
                                if intish and lo <= val / 10 <= hi:
                                    val = val / 10
                                    range_drops.append((code, trait, strain, city, st, cell,
                                                        f"->recovered {round(val,1)}"))
                                else:
                                    range_drops.append((code, trait, strain, city, st, cell,
                                                        f"DROP {round(val,1)}"))
                                    continue
                            if not star:
                                parsed[(trait, strain, reg)].append(val)
                        recs.append((YEAR, "UT", mg, code, strain, city, st, trait,
                                     round(val, 1), UNITS[trait], tag))
        for kk, v in printed.items():
            recon[(code,) + kk] = (v, parsed.get(kk, []))

    df = pd.DataFrame(recs, columns=["Year", "TestType", "TestMG", "Test", "Strain", "City",
                                     "State", "Phenotype", "Value_num", "Units", "Source"])
    df.to_csv(OUT, index=False)

    print("\n=== per-test x per-trait row counts ===")
    print(df.groupby(["Test", "Phenotype"]).size().unstack(fill_value=0)
          .reindex(columns=TRAIT_ORDER, fill_value=0).to_string())

    print("\n=== reconcile: region row-mean vs printed 'Mean N Tests' (tol 0.15; Maturity=offsets) ===")
    for code, _, _, _, _ in SECTIONS:
        agg = defaultdict(lambda: [0, 0])          # (trait,region) -> [ok, tot]
        for (c, trait, strain, reg), (pv, vals) in recon.items():
            if c != code or not vals:
                continue
            tol = 0.56 if pv == round(pv) else 0.15    # Height/SeedSize means print as integers
            ok = abs(sum(vals) / len(vals) - pv) <= tol
            agg[(trait, reg)][0] += int(ok)
            agg[(trait, reg)][1] += 1
        print(f"  {code}:")
        for trait in TRAIT_ORDER:
            parts = [f"{reg}={agg[(trait, reg)][0]}/{agg[(trait, reg)][1]}"
                     for reg in ("East", "Central") if agg[(trait, reg)][1]]
            if parts:
                print(f"    {trait:12} " + "  ".join(parts))

    if range_drops:
        print(f"\n=== {len(range_drops)} out-of-range cells dropped (OCR merged-decimal etc.) ===")
        for d in range_drops[:30]:
            print(f"    {d[0]:6} {d[1]:10} {d[2]:12} {d[3]},{d[4]:3} cell={d[5]!r} -> {d[6]}")

    cross_check(df, mat_off)
    print(f"\nwrote {OUT.name}  ({len(df):,} rows)")
    return df


def _oracle(code):
    o = pd.read_csv(ORACLE[code])
    by = defaultdict(lambda: defaultdict(list))     # trait -> normkey -> [values]
    for _, r in o.iterrows():
        if pd.isna(r.Value_num):
            continue
        by[r.Phenotype][normkey(r.Strain)].append(round(float(r.Value_num), 1))
    return by


def _multiset_match(gvals, ovals, tol=0.1):
    o_hit = 0
    pool = list(gvals)
    for v in ovals:
        h = next((w for w in pool if abs(w - v) <= tol), None)
        if h is not None:
            pool.remove(h); o_hit += 1
    g_hit = 0
    pool = list(ovals)
    for v in gvals:
        h = next((w for w in pool if abs(w - v) <= tol), None)
        if h is not None:
            pool.remove(h); g_hit += 1
    return o_hit, g_hit


def cross_check(df, mat_off):
    """Value-multiset cross-check vs the PDF-recovered oracle, per (strain, trait), both directions.
    Maturity is compared on OFFSETS (oracle stores offsets, green emits DOY -> use parallel offsets).
    Join strains by normkey to fold oracle OCR variants ('Un i on'->union)."""
    print("\n=== cross-check vs PDF-recovered oracles (value-multiset per strain, tol 0.1) ===")
    print("  oracle-reproduced = of the oracle's values, how many green reproduces (direct evidence)")
    print("  Maturity compared on OFFSETS (both oracles store offsets; green emits DOY).\n")
    for code in ("UT-III", "UT-IV"):
        by = _oracle(code)
        g = df[df.Test == code]
        gkey = {}
        for strain, gg in g.groupby("Strain"):
            for trait, ggg in gg.groupby("Phenotype"):
                if trait == "Maturity":
                    continue
                gkey[(normkey(strain), trait)] = sorted(round(v, 1) for v in ggg.Value_num)
        for (code2, strain), offs in mat_off.items():
            if code2 == code:
                gkey[(normkey(strain), "Maturity")] = sorted(round(v, 1) for v in offs)
        print(f"  {code}:")
        for trait in TRAIT_ORDER:
            o_m = o_t = g_m = g_t = 0
            okeys = set(by.get(trait, {}))
            gkeys = set(k for (k, t) in gkey if t == trait)
            for nk in okeys | gkeys:
                gv = gkey.get((nk, trait), [])
                ov = by.get(trait, {}).get(nk, [])
                oh, gh = _multiset_match(gv, ov)
                o_m += oh; o_t += len(ov); g_m += gh; g_t += len(gv)
            op = 100 * o_m / o_t if o_t else 0
            gp = 100 * g_m / g_t if g_t else 0
            unmatched = okeys - gkeys
            extra = f"  [oracle strains absent from green: {sorted(unmatched)}]" if unmatched else ""
            print(f"    {trait:12} oracle-reproduced {o_m:4}/{o_t:4} ({op:5.1f}%)   "
                  f"green-in-oracle {g_m:4}/{g_t:4} ({gp:5.1f}%){extra}")


if __name__ == "__main__":
    main()
