"""Extract the 6 REAL 1984 Uniform Tests (UT-00/UT-O/UT-I/UT-II/UT-III/UT-IV) x 8 traits from the
validated Green OCR, replacing the scrambled F4U UT labels.

Context: the 1984 F4U is a whole-year label PERMUTATION (positional Group_N assignment bug, see
audit_test_map_green.py). The Green carries the CORRECT per-test tp6..tp12b structure; section rows
come from the externalized test map (Corpus_QC/nust_test_map_1941_1988.csv).

Structure handled (verified empirically against the Red PDF, 1984_done.pdf):
  * a trait's table may span SEVERAL loc-groups, each re-emitting its own tp marker + header;
    only the FIRST group carries the "Mean of N Tests" column.
  * each trait is re-laid-out with its OWN per-group location subset (not a subset of yield's).
  * tp7 (YIELD RANK) sits between tp6 and tp8 -> bound every block at the next marker of ANY kind,
    else rank integers leak into yield.
  * strain rows repeat per group with independent OCR variance, but ALWAYS in the same order and
    count -> canonical roster by per-index MAJORITY VOTE (kills intra-test strain fragmentation).
  * some groups drop the Strain column entirely (UT-III protein) -> strains recovered by row index.
  * Maturity is printed as an anchor DATE row + signed offsets -> reconstruct DOY per location.
  * locations footnoted '*' are real data but EXCLUDED from the printed mean ("Data not included in
    mean") -> keep the values, exclude the loc from the reconcile gate.

Output: reextract_1984_ut_recovered.csv (long, same schema as reextract_1984_pt_recovered.csv).
"""
import sys, re, datetime
from collections import Counter, defaultdict
from pathlib import Path
import openpyxl
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
GREEN = REPO / "input_files" / "input_1984"
OUT = REPO / "data_prep" / "stage2_corpus" / "reextract_1984_ut_recovered.csv"
FILES = {"a": "Sojabone-1984 (1-88 OR).xlsx", "b": "Sojabone-1984 (89-186 OR).xlsx"}
# Strain-naming ORACLE: the PRE-SWAP F4U is the authoritative 1984 vocabulary -- it predates any of
# our edits and still carries every 1984 strain (the real UT-III/UT-IV rosters live there under the
# old scrambled PT labels). Its convention: NO MG parenthetical, NO internal spaces (sole exception
# 'OAC 81-2'). Matching through normkey() (which folds l/1/i and O/0 and drops the parenthetical)
# adopts that convention exactly and repairs OCR variants for free -- e.g. Ozzle->Ozzie,
# Md80-1L2-1->Md80-1L2-I, Elgin (11)->Elgin -- with no hand-written per-strain fix list.
F4U_PRESWAP = ("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/"
               "NUST_Historical_Data_1941_1988/1984_Processing/Files4Upload/"
               "phenotypesTable1.csv.bak_pre_1984pt_swap")

# (file, tp6_row, section_end, true_code, TestMG) -- rows from nust_test_map_1941_1988.csv
SECTIONS = [
    ("a", 208, 415, "UT-00", "00"),
    ("a", 415, 709, "UT-O", "O"),
    ("a", 709, 980, "UT-I", "I"),
    ("a", 1397, 2054, "UT-II", "II"),
    ("b", 383, 905, "UT-III", "III"),
    ("b", 1775, 2242, "UT-IV", "IV"),
]
TP2TRAIT = {"tp6": "YieldBuA", "tp8": "Maturity", "tp9": "Lodging", "tp10": "Height",
            "tp11a": "SeedQuality", "tp11b": "SeedSize", "tp12a": "Protein", "tp12b": "Oil"}
UNITS = {"YieldBuA": "bu/a", "Maturity": "DOY", "Lodging": "score", "Height": "in",
         "SeedQuality": "score", "SeedSize": "g/100", "Protein": "%", "Oil": "%"}
RANGE = {"YieldBuA": (2, 120), "Height": (5, 80), "Lodging": (1, 5), "SeedQuality": (1, 5),
         "SeedSize": (5, 40), "Protein": (25, 55), "Oil": (5, 30), "Maturity": (200, 330)}
FOOTER = re.compile(r"^\s*(C\.V|L\.S\.D|Mean|Row\s*sp|Rows?\s*/|Reps|Strain|Date\s*planted|"
                    r"Days\s*to|tp\d|NS$)", re.I)
MEANCOL = re.compile(r"Mean|Tests", re.I)

# City OCR repair -> (City, State) as PRINTED in the report. Deliberately does NOT merge
# Lanawee->Lenawee: the Red PDF prints "Lanawee", so that merge belongs in the location
# canonical map (reference/nust_location_canonical_map.csv), not in extraction.
CITY_FIX = {
    "Adelphla": "Adelphia", "Greenfleld": "Greenfield", "Greenfjeld": "Greenfield",
    "Landlsville": "Landisville", "Marshal Itown": "Marshalltown", "Pontlac": "Pontiac",
    "Rose- Mount": "Rosemount", "RoseMount": "Rosemount", "Smith- field": "Smithfield",
    "Sulllvan": "Sullivan", "Sul1ivan": "Sullivan",
}
STATE_FIX = {"Wl": "WI", "Ml": "MI", "Ont": "ONT", "0nt": "ONT"}
# Locations printed with a footnote marker: real data, excluded from the printed mean.
FOOTNOTED = re.compile(r"[*¹†]")


def load(fn):
    wb = openpyxl.load_workbook(GREEN / fn, read_only=True, data_only=True)
    rows = list(wb["Sheet1"].iter_rows(values_only=True))
    wb.close()
    return rows


def parse_loc(h):
    """'Hoytville,* OH' -> ('Hoytville','OH',True); 'Portage, ville, MO Loam' -> Portageville-Loam."""
    s = str(h).strip()
    star = bool(FOOTNOTED.search(s))
    s = FOOTNOTED.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    # soil-plot variants (Portageville Clay/Loam) -> corpus canonical 'Portageville-Clay'
    m = re.match(r"^Portage,?\s*ville,?\s*(\w{2})\s*(Clay|Loam)$", s, re.I)
    if m:
        return f"Portageville-{m.group(2).title()}", m.group(1).upper(), star
    parts = [p.strip() for p in s.split(",")]
    if len(parts) >= 2:
        city, state = ",".join(parts[:-1]).strip(), parts[-1].strip()
    else:                      # 'Ithaca MI' (comma lost by OCR)
        m = re.match(r"^(.*?)\s+([A-Za-z]{2,3})$", s)
        city, state = (m.group(1), m.group(2)) if m else (s, "")
    city = re.sub(r"\s+", " ", city).strip()
    city = CITY_FIX.get(city, city)
    state = STATE_FIX.get(state, state.upper())
    return city, state, star


def strip_rank(s):
    return re.sub(r"^\s*\d+\s*[.)]\s*", "", str(s)).strip()


def normkey(s):
    """Fold the OCR confusions that fragment one strain across loc-groups (l/1/i, O/0) and drop the
    MG parenthetical ('Elgin (11)' -> elgin), so variants collapse onto one identity."""
    k = strip_rank(s).lower()
    k = re.sub(r"\(.*?\)", "", k)
    k = re.sub(r"[^a-z0-9]", "", k)
    return k.translate(str.maketrans("lio", "110"))


def load_name_oracle():
    """normkey -> established 1984 strain name, from the pre-swap F4U."""
    b = pd.read_csv(F4U_PRESWAP, low_memory=False)
    names = b.loc[b.Year == 1984, "Strain"].dropna().astype(str).unique()
    oracle = {}
    for n in names:
        oracle.setdefault(normkey(n), n)
    return oracle


def fnum(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    m = re.match(r"^\s*[+-]?\s*\d+(?:\.\d+)?", str(x).replace(" ", ""))
    return float(m.group().replace(" ", "")) if m else None


def doy(dt):
    return datetime.date(1984, dt.month, dt.day).timetuple().tm_yday


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
    """-> (locs[(col,city,state,star)], mean_col|None, strain_col|None, data[(row, text, cells)])"""
    hdr = rows[i + 1]
    strain_col = 0 if (hdr and hdr[0] and str(hdr[0]).strip().lower().startswith("strain")) else None
    locs, mean_col = [], None
    start = 1 if strain_col == 0 else 0
    for ci in range(start, len(hdr)):
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
        if strain_col is None and fnum(head) is None:
            continue
        data.append((ri, strip_rank(head) if strain_col == 0 else None, row))
    return locs, mean_col, strain_col, data


def main():
    recs, report = [], []
    oracle = load_name_oracle()
    print(f"naming oracle: {len(oracle)} established 1984 strain names (pre-swap F4U)\n")
    unmatched = []
    for f, a, b, code, mg in SECTIONS:
        rows = load(FILES[f])
        mk = markers(rows, a, b)
        groups = defaultdict(list)
        for gi, (i, tp) in enumerate(mk):
            if tp not in TP2TRAIT:
                continue
            end = mk[gi + 1][0] if gi + 1 < len(mk) else b
            groups[TP2TRAIT[tp]].append((i, end))

        # ---- canonical roster: per-index majority vote over every group that names strains ----
        votes = defaultdict(Counter)
        nrow = None
        for trait, gl in groups.items():
            for (i, end) in gl:
                _, _, sc, data = parse_group(rows, i, end)
                if sc is None:
                    continue
                if nrow is None:
                    nrow = len(data)
                if len(data) != nrow:
                    continue
                for k, (_, name, _) in enumerate(data):
                    votes[k][name] += 1
        # per-index majority vote collapses same-token OCR noise, but it CANNOT fix an error that
        # dominates (Ozzle 6 vs Ozzie 2) or one present in every group (roman numerals as digits,
        # 'Elgin (11)'). So resolve the voted name through the pre-swap-F4U oracle, which is both
        # the established convention and an independent reading of the same tables.
        roster, amb = [], {}
        for k in range(len(votes)):
            voted = votes[k].most_common(1)[0][0]
            canon = oracle.get(normkey(voted))
            if canon is None:
                unmatched.append((code, voted))
                canon = re.sub(r"\s*\(.*?\)\s*", "", voted).replace(" ", "")
            roster.append(canon)
            if len(votes[k]) > 1 or canon != voted:
                amb[k] = (dict(votes[k]), canon)

        # ---- emit ----
        for trait, gl in groups.items():
            for (i, end) in gl:
                locs, mean_col, sc, data = parse_group(rows, i, end)
                if not locs:
                    continue
                if len(data) != len(roster):
                    report.append(f"  ! {code} {trait} [{i}] SKIP: {len(data)} rows vs roster {len(roster)}")
                    continue
                anchor = {}
                if trait == "Maturity":
                    for (_, _, row) in data:
                        if any(ci < len(row) and isinstance(row[ci], datetime.datetime)
                               for ci, _, _, _ in locs):
                            for ci, city, st, _ in locs:
                                if ci < len(row) and isinstance(row[ci], datetime.datetime):
                                    anchor[(city, st)] = doy(row[ci])
                            break
                    if not anchor:
                        report.append(f"  ! {code} Maturity [{i}] SKIP: no anchor date row")
                        continue
                for k, (ri, _, row) in enumerate(data):
                    strain = roster[k]
                    for ci, city, st, star in locs:
                        if ci >= len(row):
                            continue
                        cell = row[ci]
                        if cell is None:
                            continue
                        if trait == "Maturity":
                            if isinstance(cell, datetime.datetime):
                                val = doy(cell)
                            else:
                                base, off = anchor.get((city, st)), fnum(cell)
                                if base is None or off is None:
                                    continue
                                val = base + off
                        else:
                            val = fnum(cell)
                        if val is None:
                            continue
                        lo, hi = RANGE[trait]
                        if not (lo <= val <= hi):
                            continue
                        recs.append((1984, "UT", mg, code, strain, city, st, trait,
                                     round(val, 1), UNITS[trait], "Green1984_UT_extract", star))
        print(f"{code}: roster {len(roster)} strains; groups " +
              ", ".join(f"{t}x{len(g)}" for t, g in sorted(groups.items())))
        for k, (v, canon) in sorted(amb.items()):
            print(f"     idx{k:2} {v} -> {canon!r}")

    df = pd.DataFrame(recs, columns=["Year", "TestType", "TestMG", "Test", "Strain", "City",
                                     "State", "Phenotype", "Value_num", "Units", "Source", "_star"])
    for line in report:
        print(line)
    if unmatched:
        print(f"\n! {len(unmatched)} strains absent from the naming oracle (fell back to rule):")
        for code, n in unmatched:
            print(f"    {code:7} {n!r}")
    print(f"\nextracted {len(df):,} rows")
    print(df.groupby(["Test", "Phenotype"]).size().unstack(fill_value=0).to_string())
    dup = df[df.duplicated(["Test", "Strain", "City", "State", "Phenotype"], keep=False)]
    print(f"\nduplicate keys: {len(dup)}")
    if len(dup):
        print(dup.head(12).to_string())
    df.drop(columns=["_star"]).to_csv(OUT, index=False)
    print(f"\nwrote {OUT.name}")
    return df


if __name__ == "__main__":
    main()
