"""Extract the 1985 Uniform Test III (UT-III) x 8 traits DIRECTLY from the Green OCR XLSX,
with NO API calls -- the "green-direct, no-API" re-extraction pilot (C1) for the test-map repair.

Context: 1985 UT-III was a "dropped" test.  Its section sits at the TOP of split Green file 2
(`Sojabone-1985 (105-220 OR).xlsx`), but its parentage opener was mislabeled `tp1` instead of
`tp2`, so the combine step folded it into the pre-tp2 region and never emitted it.  A `tp2` marker
was inserted at row 2 of file 2 to fix the source; UT-III's data was FULLY present all along.

Structure (verified empirically, simpler than 1984 -- ONE location-group per trait):
  parentage : tp1@3  -> header@4 -> 27 roster rows 5..31 (canonical strain names, w/ MG parenthet.)
  tp6  @153  YieldBuA    (Mean 21 Tests)
  tp8  @189  Maturity    (Mean 20 Tests)  <- anchor DATE row (Harper) + signed day offsets -> DOY
  tp9  @222  Lodging     (Mean 21 Tests)
  tp10 @253  Height      (Mean Tests)
  tp11a@284  SeedQuality (Mean 20 Tests)
  tp11b@315  SeedSize    (Mean 20 Tests)
  tp12a@346  Protein     (Mean 5 Tests)   <- 5 locations only
  tp12b@376  Oil         (Mean 5 Tests)   <- 5 locations only ; MUST bound at next marker (tp2@406)
                                             so PT-IIIA's parentage roster does not leak in.
There is NO tp7 in this section.  Section (trait data) ends by row 577; PT-IIIA parentage opens at
tp2@406, which is the bound for the Oil block.

Naming: the Green parentage roster names ("Century 84 (II)", "Harper (III)", "Sparks (IV)", plain
names for the rest) already match the prior PDF-recovered oracle (utiii_1985_alltraits.csv) verbatim,
so they are used as canonical -- no external oracle needed.  Data-row names are checked against the
roster by normalized key (folds l/1/i, O/0, drops parenthetical) and any drift is logged.

Value cleaning, footer filtering, per-location parsing, Maturity DOY reconstruction and the RANGE
gate are carried over from extract_1984_ut_green.py (the proven 1980s-Green engine).

Output: reextract_1985_utiii_green.csv  (schema identical to reextract_1984_ut_recovered.csv).
"""
import sys, re, datetime
from pathlib import Path
import openpyxl
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
GREEN = REPO / "input_files" / "input_1985" / "Sojabone-1985 (105-220 OR).xlsx"
OUT = REPO / "data_prep" / "stage2_corpus" / "reextract_1985_utiii_green.csv"
ORACLE = REPO / "data_prep" / "stage2_corpus" / "_archive_superseded_2026-07" / "utiii_1985_alltraits.csv"

YEAR, CODE, MG = 1985, "UT-III", "III"
PARENT_ROWS = (5, 31)          # xlsx rows of the 27 canonical roster strains (inclusive)
SECTION_END_IDX = 576          # rows[576] == xlsx row 577

TP2TRAIT = {"tp6": "YieldBuA", "tp8": "Maturity", "tp9": "Lodging", "tp10": "Height",
            "tp11a": "SeedQuality", "tp11b": "SeedSize", "tp12a": "Protein", "tp12b": "Oil"}
UNITS = {"YieldBuA": "bu/a", "Maturity": "DOY", "Lodging": "score", "Height": "in",
         "SeedQuality": "score", "SeedSize": "g/100", "Protein": "%", "Oil": "%"}
RANGE = {"YieldBuA": (2, 120), "Height": (5, 80), "Lodging": (1, 5), "SeedQuality": (1, 5),
         "SeedSize": (5, 40), "Protein": (25, 55), "Oil": (5, 30), "Maturity": (200, 330)}
FOOTER = re.compile(r"^\s*(C\.V|L\.S\.D|Mean|Row\s*sp|Rows?\s*/|Reps|Strain|Date\s*planted|"
                    r"Days\s*to|tp\d|NS$)", re.I)
MEANCOL = re.compile(r"Mean|Tests", re.I)
FOOTNOTED = re.compile(r"[*¹†]")
STATE_FIX = {"Wl": "WI", "Ml": "MI", "Ont": "ONT", "0nt": "ONT"}


def load():
    wb = openpyxl.load_workbook(GREEN, read_only=True, data_only=True)
    rows = list(wb["Sheet1"].iter_rows(values_only=True))
    wb.close()
    return rows


def strip_rank(s):
    return re.sub(r"^\s*\d+\s*[.)]\s*", "", str(s)).strip()


def normkey(s):
    """Fold OCR confusions (l/1/i, O/0) and drop the MG parenthetical so name variants collapse."""
    k = re.sub(r"\(.*?\)", "", strip_rank(s).lower())
    k = re.sub(r"[^a-z0-9]", "", k)
    return k.translate(str.maketrans("lio", "110"))


def parse_loc(h):
    """'Ottumwa IA' -> ('Ottumwa','IA',False); 'S. Charleston OH' -> ('S. Charleston','OH')."""
    s = str(h).strip()
    star = bool(FOOTNOTED.search(s))
    s = re.sub(r"\s+", " ", FOOTNOTED.sub("", s)).strip()
    parts = [p.strip() for p in s.split(",")]
    if len(parts) >= 2:
        city, state = ",".join(parts[:-1]).strip(), parts[-1].strip()
    else:                                       # space-separated 'City ST' (comma lost / never there)
        m = re.match(r"^(.*?)\s+([A-Za-z]{2,3})$", s)
        city, state = (m.group(1), m.group(2)) if m else (s, "")
    city = re.sub(r"\s+", " ", city).strip()
    state = STATE_FIX.get(state, state.upper())
    return city, state, star


def fnum(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    m = re.match(r"^\s*[+-]?\s*\d+(?:\.\d+)?", str(x).replace(" ", ""))
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


def parse_block(rows, i, end):
    """-> (locs[(col,city,state,star)], mean_col|None, data[(rowidx, strain_text, cells)])."""
    hdr = rows[i + 1]
    locs, mean_col = [], None
    for ci in range(1, len(hdr)):               # col 0 is always the Strain header here
        h = hdr[ci]
        if not h:
            continue
        if MEANCOL.search(str(h)):
            if mean_col is None:
                mean_col = ci
            continue
        city, state, star = parse_loc(h)
        if city:
            locs.append((ci, city, state, star))
    data = []
    for ri in range(i + 2, end):
        row = rows[ri]
        if not row or all(v is None for v in row):
            continue
        head = str(row[0]).strip() if row[0] is not None else ""
        if FOOTER.match(head):
            continue
        data.append((ri, strip_rank(head), row))
    return locs, mean_col, data


def build_roster(rows):
    names = []
    for ri in range(PARENT_ROWS[0] - 1, PARENT_ROWS[1]):
        v = rows[ri][0]
        names.append(FOOTNOTED.sub("", str(v)).strip())
    return names


def main():
    rows = load()
    roster = build_roster(rows)
    print(f"parentage roster: {len(roster)} strains\n  " + ", ".join(roster))

    mk = markers(rows, 150, SECTION_END_IDX + 1)      # tp6.. plus tp2@406 that bounds Oil
    trait_blocks = {}
    for gi, (i, tp) in enumerate(mk):
        if tp in TP2TRAIT:
            end = mk[gi + 1][0] if gi + 1 < len(mk) else SECTION_END_IDX + 1
            trait_blocks[TP2TRAIT[tp]] = (i, end)

    recs, reconcile, name_drift = [], {}, []
    for trait, (i, end) in trait_blocks.items():
        locs, mean_col, data = parse_block(rows, i, end)
        if len(data) != len(roster):
            print(f"  ! {trait} [{i+1}] SKIP: {len(data)} data rows vs roster {len(roster)}")
            continue

        # maturity anchor: the single strain row printed as absolute dates
        anchor = {}
        if trait == "Maturity":
            for (_, _, row) in data:
                if any(ci < len(row) and isinstance(row[ci], datetime.datetime) for ci, *_ in locs):
                    for ci, city, st, _ in locs:
                        if ci < len(row) and isinstance(row[ci], datetime.datetime):
                            anchor[(city, st)] = doy(row[ci])
                    break
            if not anchor:
                print(f"  ! Maturity [{i+1}] SKIP: no anchor date row")
                continue

        n_ok = n_tot = 0
        for k, (ri, sname, row) in enumerate(data):
            strain = roster[k]
            if normkey(sname) != normkey(strain):
                name_drift.append((trait, k, sname, strain))
            vals_for_mean = []            # (value_in_native_rep_for_reconcile)
            for ci, city, st, star in locs:
                if ci >= len(row):
                    continue
                cell = row[ci]
                if cell is None:
                    continue
                raw = fnum(cell)
                if trait == "Maturity":
                    if isinstance(cell, datetime.datetime):
                        val = doy(cell)
                        recon_v = None          # anchor row: printed mean is a date, skip reconcile
                    else:
                        base = anchor.get((city, st))
                        if base is None or raw is None:
                            continue
                        val = base + raw
                        recon_v = raw           # reconcile offsets against printed offset-mean
                else:
                    val = raw
                    recon_v = raw
                if val is None:
                    continue
                lo, hi = RANGE[trait]
                if not (lo <= val <= hi):
                    print(f"  ! {trait} {strain} @ {city},{st} out of range: {val}")
                    continue
                if not star and recon_v is not None:
                    vals_for_mean.append(recon_v)
                recs.append((YEAR, "UT", MG, CODE, strain, city, st, trait, round(val, 1),
                             UNITS[trait], "Green1985_UTIII_direct"))
            # reconcile row-mean vs printed "Mean N Tests".  Tolerance follows the printed decimals:
            # Height prints its mean as an INTEGER (e.g. 32) so the rounding slack is ~0.5; the other
            # traits print one decimal (44.4, 1.4, 20.3) so 0.15 suffices.
            if mean_col is not None and mean_col < len(row) and vals_for_mean:
                printed = fnum(row[mean_col])
                if printed is not None:
                    tol = 0.56 if printed == round(printed) else 0.15
                    n_tot += 1
                    if abs(sum(vals_for_mean) / len(vals_for_mean) - printed) <= tol:
                        n_ok += 1
        reconcile[trait] = (n_ok, n_tot, len(locs))

    df = pd.DataFrame(recs, columns=["Year", "TestType", "TestMG", "Test", "Strain", "City",
                                     "State", "Phenotype", "Value_num", "Units", "Source"])
    df.to_csv(OUT, index=False)

    print("\n=== per-trait extraction ===")
    print(df.groupby("Phenotype").size().to_string())
    print("\n=== reconcile (row-mean vs printed 'Mean N Tests'; Maturity=offset-mean) ===")
    for t in ["YieldBuA", "Maturity", "Lodging", "Height", "SeedQuality", "SeedSize",
              "Protein", "Oil"]:
        if t in reconcile:
            ok, tot, nl = reconcile[t]
            print(f"  {t:12} {ok}/{tot} strains reconcile  ({nl} locations)")
    if name_drift:
        print(f"\n! {len(name_drift)} data-row name drifts (used roster name):")
        for tr, k, got, used in name_drift[:20]:
            print(f"    {tr:10} idx{k:2} OCR {got!r} -> {used!r}")
    else:
        print("\nname check: all 8x27 data-row names match the roster by normkey")

    cross_check(df)
    print(f"\nwrote {OUT.name}  ({len(df):,} rows)")
    return df


def _oracle_values(trait):
    """Return per-strain value lists from the PDF-recovered oracle, with two documented fixes:
      * Oil is not in utiii_1985_alltraits.csv -- it lives in oil_1985_UTIII_true.csv.
      * the oracle's Height is systematically scaled by 1/10 (a decimal misread in the PDF recovery:
        green 36 -> oracle 3.6, green mean 32 -> 3.2), so it is multiplied back by 10 to compare.
    Oracle strain names carry occasional OCR garbage ('f?', 'ft*'); only real roster names join."""
    if trait == "Oil":
        o = pd.read_csv(REPO / "data_prep" / "stage2_corpus" / "_archive_superseded_2026-07" / "oil_1985_UTIII_true.csv")
        o = o.rename(columns={"Test": "_t"})
    else:
        oa = pd.read_csv(ORACLE)
        o = oa[oa.Phenotype == trait].copy()
    scale = 10.0 if trait == "Height" else 1.0
    out = {}
    for strain, gg in o.groupby("Strain"):
        out[strain] = sorted(round(v * scale, 1) for v in gg.Value_num.dropna())
    return out


def cross_check(df):
    """Value-multiset cross-check vs the PDF-recovered oracle, per (Strain, trait).  The oracle's City
    names are OCR-fragmented (hattan/town/ville) so we compare the SET of values per strain rather
    than joining on City.  We report BOTH directions: oracle-side coverage (of the oracle's values,
    how many does green reproduce -- the direct 'green == PDF-recovery' evidence) and green-side.
    Maturity is skipped for value cross-check: the oracle stores raw day-OFFSETS, green stores DOY."""
    print("\n=== cross-check vs PDF-recovered oracle (utiii_1985_alltraits.csv + oil_1985_UTIII_true.csv) ===")
    print("  match by value-multiset per strain (tol 0.1); oracle Height rescaled x10 (its /10 decimal")
    print("  bug); Oil from oil_1985_UTIII_true.csv; Maturity N/A (oracle=offsets, green=DOY).\n")
    for trait in ["YieldBuA", "Lodging", "Height", "SeedQuality", "SeedSize", "Protein", "Oil"]:
        g = df[df.Phenotype == trait]
        ovals_by = _oracle_values(trait)
        o_matched = o_total = g_matched = g_total = 0
        for strain, gg in g.groupby("Strain"):
            gvals = sorted(round(v, 1) for v in gg.Value_num)
            ovals = ovals_by.get(strain, [])
            # oracle-side: every oracle value should be reproduced by a green value
            pool = list(gvals)
            for v in ovals:
                hit = next((w for w in pool if abs(w - v) <= 0.1), None)
                o_total += 1
                if hit is not None:
                    pool.remove(hit); o_matched += 1
            # green-side
            pool = list(ovals)
            for v in gvals:
                hit = next((w for w in pool if abs(w - v) <= 0.1), None)
                g_total += 1
                if hit is not None:
                    pool.remove(hit); g_matched += 1
        opct = 100 * o_matched / o_total if o_total else 0
        gpct = 100 * g_matched / g_total if g_total else 0
        print(f"  {trait:12} oracle-reproduced {o_matched}/{o_total} ({opct:5.1f}%)   "
              f"green-in-oracle {g_matched}/{g_total} ({gpct:5.1f}%)")


if __name__ == "__main__":
    main()
