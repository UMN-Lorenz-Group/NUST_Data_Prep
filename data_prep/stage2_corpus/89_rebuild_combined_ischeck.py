"""
89_rebuild_combined_ischeck.py
==============================
Faithfully rebuild the IsCheck column of the combined long files for ALL years
1941-2025. (Replaces the throwaway 88_rebuild_combined_ischeck.py.)

PROBLEM: the original IsCheck (10_assemble_corpus.py) flagged checks from a small
HARDCODED ~80-variety list, so IsCheck=1 existed only for scattered historical
rows and was ALL-ZERO for the entire modern era (1989-2025). The curated per-year
designation file (nust_check_designation_years_1941_2025.csv, from script 65) is
also missing 8 years: 1941, 1974, 1987, 1988, 1989, 1991, 1992, 2023.

THIS SCRIPT builds an ENRICHED per-(MG, Strain-key, Year) check set =
  1. nust_check_designation_years_1941_2025.csv     (script 65 year-bearing sources)
  2. PRE-MODERN era assignment (1941-1977): each CHECK_VARIETIES_PREMODERN[mg]
     variety -> every year <=1977 it actually appears in the combined for that MG
     (the hardcoded pre-modern checks carry no year in source 1, which is why
     1941/1974 were empty and classic checks like Hawkeye/Clark dropped out).
  3. 1987-1988 strainsTables (output_files/output_1987|1988/...; Check==1 & UT)
     (script 65's strainsTable source stopped at 1986).
  4. 1989/1991/1992 checks from the Red PDFs (script 89a; zero-API local extract).
  5. 2023 checks from the master file (script 89b).
then sets, per combined row,
     IsCheck = 1  iff  (TestMG, mkey(Strain), Year) in the enriched set.
mkey() = script-65 canonical-name standardisation (norm_strain) reduced to an
alphanumeric key, applied identically to both the set and the combined Strain so
spacing/punctuation/OCR variants match. Evaluated per row => the flag applies
across every Location and Trial (UT and PT) of a designated (MG, Strain, Year),
matching the original UT+PT behaviour and extending it to the modern era.

NON-DESTRUCTIVE by default: writes <name>.ischeck_rebuilt.csv and prints
validation (per-year IsCheck=1 counts; asserts NO zero-check year 1941-2025).
With --replace, swaps the originals in place, keeping <name>.pre_ischeck_rebuild.bak.

NEVER open the combined CSVs in Excel: its 1,048,576-row cap silently truncates
the 3.77M-row file at ~1969 and a save would destroy the post-1969 data.

Usage:
    PYTHONUTF8=1 uv run python analysis/89_rebuild_combined_ischeck.py            # validate
    PYTHONUTF8=1 uv run python analysis/89_rebuild_combined_ischeck.py --replace  # commit
"""
import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
DATA = REPO / "analysis/data/_shared"
DESIG = DATA / "nust_check_designation_years_1941_2025.csv"
PDF_8992 = DATA / "nust_checks_1987_1992_from_pdf.csv"      # script 89a (1987-1992)
MASTER_2023 = DATA / "nust_checks_2023_from_master.csv"     # script 89b
TARGETS = ["nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"]

MG_ORDER = ["00", "0", "I", "II", "III", "IV"]
PREMODERN_MAX_YEAR = 1977
RECUR_MIN = 3   # established checks recur >= this many distinct years in combined

# Summary / non-variety row labels never treated as a check strain
STOPWORDS = {
    "mean", "means", "average", "avg", "median", "lsd", "cv", "se", "sd", "std",
    "total", "range", "grand", "check", "checks", "entry", "entries", "no",
    "number", "test", "tests", "location", "locations", "overall", "high", "low",
    "max", "min", "sum", "count", "strain", "variety",
}


def is_named_cultivar(s):
    """First token purely alphabetic and not a summary label (Mean, LSD, ...)."""
    toks = str(s).split()
    if not toks or not re.match(r"^[A-Za-z][A-Za-z.'\-]*$", toks[0]):
        return False
    return toks[0].lower().strip(".") not in STOPWORDS

# ---------------------------------------------------------------------------
# Canonical name standardisation — copied verbatim from 65_build_check_lookup.py
# (importing that module would execute its whole build pipeline). Keep in sync.
# ---------------------------------------------------------------------------
INVALID_NAMES = {"na", "nan", "n/a", "none", "unknown", ""}

CHECK_VARIETIES_PREMODERN = {
    "00": ["Acme", "Flambeau", "Altona", "Norman", "Portage", "Morsoy",
           "Capital", "Renville", "Mandarin", "Ottawa", "Crest"],
    "0":  ["Grant", "Merit", "Clay", "Traverse", "Swift", "Wilkin", "Evans",
           "Norchief", "Manchu", "Earlyana", "Mandarin(Ottawa)",
           "Mandarin (Ottawa)"],
    "I":  ["Chippewa", "Chippewa 64", "Hark", "A-100", "Hodgson", "SL7",
           "SL8", "Steele", "Blackhawk", "Hawkeye", "Mukden"],
    "II": ["Amsoy", "Amsoy 71", "Harosoy", "Harosoy 63", "Beeson", "Corsoy",
           "Magna", "Provar", "Williams", "Adams", "Lincoln", "Lindarin",
           "Wabash", "Korean"],
    "III": ["Calland", "Wayne", "Williams", "Shelby", "C1421", "Adelphia",
            "Cumberland", "Ford", "Roanoke"],
    "IV": ["Clark", "Clark 63", "Kent", "Cutler", "Cutler 71", "Bonus",
           "L12A", "Custer", "Bethel", "Ogden", "Korean"],
}

CANONICAL_NAMES = {
    "Mandarin(Ottawa)": "Mandarin (Ottawa)", "Mand. (Ott.)": "Mandarin (Ottawa)",
    "Mand.(Ott.)": "Mandarin (Ottawa)", "Mand.(Ottawa)": "Mandarin (Ottawa)",
    "Mand. (Ottawa)": "Mandarin (Ottawa)", "Mandarin (Ott.)": "Mandarin (Ottawa)",
    "Mandarin (Ott)": "Mandarin (Ottawa)", "Mand. (Ott)": "Mandarin (Ottawa)",
    "Mandarin(Ottawa)Central": "Mandarin (Ottawa)", "Mand. (Ott. )": "Mandarin (Ottawa)",
    "Mandarin (Ott. )": "Mandarin (Ottawa)",
    "Wis.Manchu 3": "Wis. Manchu 3", "Vi s. Manchu 3": "Wis. Manchu 3",
    "Vis. Manchu 3": "Wis. Manchu 3", "Wis.Maneh u 606": "Wis. Manchu 606",
    "Vis. Manchu 606": "Wis. Manchu 606", "Uis. Manchu 606": "Wis. Manchu 606",
    "Wis.Manchu 3 Sel": "Wis. Manchu 3", "Wis. Manchu 3 Sel": "Wis. Manchu 3",
    "Wis. Mancu 3": "Wis. Manchu 3", "Manchukota": "Manchukota",
    "Illini 111": "Illini", "Illini 111.": "Illini", "Illin i": "Illini",
    "Illin 1": "Illini", "m in i": "Illini", "Lincoln 111": "Lincoln",
    "Lincoln I11.A.E.S": "Lincoln", "Viking 111": "Viking", "Chief 111": "Chief",
    "Norchlef": "Norchief", "M 65-217": "M65-217", "Gold soy": "Goldsoy",
    "Morsoy (CM30)": "Morsoy", "Altona (UM15)": "Altona",
    "Chippewa 64 (LI)": "Chippewa 64", "Hodgson 78 (1": "Hodgson 78",
    "(Al-939)": "Al-939", "(C1315)": "C1315", "Al-939)": "Al-939", "C1315)": "C1315",
    "Habaro U.S.Depti of": "Habaro", "Cl 128": "C1128", "Cl 301": "C1301",
    "A5-2683 (Adams)": "Adams", "Adams (A5—2683)": "Adams", "Perry (C612)": "Perry",
    "Swift(M59-121)": "Swift", "Steele(M59-213)": "Steele",
    "Maple Arrow (073-15)": "Maple Arrow", "Merit (0-•55-2065)": "Merit",
    "Group 0 was planted": None, "7/is.i.Ian.3 Sel. 7/isconsin": None,
    "Ills. Hanchu 3 Sel": None, "mo": None, "mo 2": None, "For the": None,
    "Mukden ;/4": "Mukden", "Cl 291": "C1291", "CIO 68": "C1068",
    "18-1O78O": "L8-10780", "C10**8": None, "19-5138": "L9-5138",
    "19-5142": "L9-5142", "l8-10946": "L8-10946", "Pennsoy Penn": "Pennsoy",
    "Corsoy79": "Corsoy 79", "Corsoy 79 (II)": "Corsoy 79", "Clark63": "Clark 63",
    "Harosoy63": "Harosoy 63", "Chippewa64": "Chippewa 64",
    "Chippewa 61+": "Chippewa 61+", "Cutler71": "Cutler 71", "Hodgson78": "Hodgson 78",
    "Scott (S2-7158)": "Scott", "Custer (S5)": "Custer",
    "L74L-125 Lawrence": "Lawrence", "Wye(Md63-3303-3)": "Wye",
}


def _norm_key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


_CANONICAL_KEY_MAP = {}
for _k, _v in CANONICAL_NAMES.items():
    if _v is not None:
        _CANONICAL_KEY_MAP[_norm_key(_k)] = _v
_SOJABONE_TO_DISPLAY = {
    "mandarinottawa": "Mandarin (Ottawa)", "mandott": "Mandarin (Ottawa)",
    "mandottawa": "Mandarin (Ottawa)", "mandarinott": "Mandarin (Ottawa)",
    "chippewa64": "Chippewa 64", "corsoy79": "Corsoy 79", "harosoy63": "Harosoy 63",
    "clark63": "Clark 63", "cutler71": "Cutler 71", "hodgson78": "Hodgson 78",
    "wismanchu3": "Wis. Manchu 3", "wismanchu606": "Wis. Manchu 606",
}
_CANONICAL_KEY_MAP.update(_SOJABONE_TO_DISPLAY)


def norm_strain(s):
    if not isinstance(s, str):
        return None
    s = s.strip()
    s = re.sub(r"^\d+\s*\.\s*", "", s)
    s = re.sub(r"\s*\*\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s or s.lower() in INVALID_NAMES:
        return None
    if s in CANONICAL_NAMES:
        return CANONICAL_NAMES[s]
    key = _norm_key(s)
    if key in _CANONICAL_KEY_MAP:
        return _CANONICAL_KEY_MAP[key]
    return s


PAREN_MG_RE = re.compile(r"^(.*?)\s*\((\d{1,2}|[IV]{1,4})\)\s*$")


def parse_strain_with_paren_mg(s):
    if not isinstance(s, str):
        return None, None
    m = PAREN_MG_RE.match(s.strip())
    if m:
        return norm_strain(m.group(1)), m.group(2).upper()
    return norm_strain(s), None


def mkey(s):
    """Canonical alphanumeric match key shared by the set and the combined rows."""
    cs = norm_strain(s)
    if not cs:
        return None
    return _norm_key(cs)


# ---------------------------------------------------------------------------
# Build the enriched (MG, mkey, Year) check set
# ---------------------------------------------------------------------------
def add(check_set, prov, mg, strain, year, source):
    mg = (mg or "").strip().upper()
    k = mkey(strain)
    try:
        y = int(float(year))
    except (TypeError, ValueError):
        return
    if mg in MG_ORDER and k:
        check_set.add((mg, k, y))
        prov[source] += 1


def load_designation(check_set, prov):
    with open(DESIG, newline="", encoding="utf-8") as f:
        for x in csv.DictReader(f):
            add(check_set, prov, x.get("MG"), x.get("Strain"), x.get("Year"),
                "1_designation")


def load_csv_checks(path, check_set, prov, source):
    if not path.exists():
        print(f"  WARN missing {path.name} — run its builder first")
        return
    with open(path, newline="", encoding="utf-8") as f:
        for x in csv.DictReader(f):
            add(check_set, prov, x.get("MG"), x.get("Strain"), x.get("Year"), source)


def premodern_keys():
    """mg -> set of mkey for each pre-modern hardcoded check name."""
    out = defaultdict(set)
    for mg, names in CHECK_VARIETIES_PREMODERN.items():
        for nm in names:
            k = mkey(nm)
            if k:
                out[mg].add(k)
    return out


def scan_combined(master):
    """Single pass over the master combined file collecting everything the
    enrichment + backfill need:
      recur[key]          -> number of distinct years the strain appears
      named_present       -> {year: {(mg, key, example_spelling)}} for NAMED
                             cultivars only (recurrence-backfill candidates)
      present[(mg,key,yr)]-> True for every combo present (to find zero years)
    """
    recur_years = defaultdict(set)
    named_present = defaultdict(set)
    present = set()
    old_checks = set()
    with open(master, newline="", encoding="utf-8", errors="replace") as f:
        for x in csv.DictReader(f):
            try:
                y = int(float(x["Year"]))
            except (TypeError, ValueError, KeyError):
                continue
            mg = (x.get("TestMG") or "").strip().upper()
            raw = x.get("Strain")
            k = mkey(raw)
            if not k or mg not in MG_ORDER:
                continue
            recur_years[k].add(y)
            present.add((mg, k, y))
            if (x.get("IsCheck") or "").strip() == "1":
                old_checks.add((mg, k, y))
            if is_named_cultivar(raw):
                named_present[y].add((mg, k, str(raw).strip()))
    recur = {k: len(ys) for k, ys in recur_years.items()}
    return recur, named_present, present, old_checks


def build_check_set():
    check_set = set()
    prov = Counter()
    print("Building enriched check set:")
    load_designation(check_set, prov)
    print(f"  1. designation file: {prov['1_designation']} records")

    master = DATA / TARGETS[0]
    print("  (scanning combined for recurrence / presence ...)")
    recur, named_present, present, old_checks = scan_combined(master)

    # 2. pre-modern era assignment (<=1977): hardcoded checks -> years present
    pm = premodern_keys()
    n_pm = 0
    for (mg, k, y) in present:
        if y <= PREMODERN_MAX_YEAR and k in pm.get(mg, ()) and (mg, k, y) not in check_set:
            check_set.add((mg, k, y)); prov["2_premodern_era"] += 1; n_pm += 1
    print(f"  2. pre-modern era (<= {PREMODERN_MAX_YEAR}): {n_pm} (MG,Strain,Year) added")

    # 3/4. 1987-1992 checks from the Red PDFs (script 89a, local, zero-API)
    load_csv_checks(PDF_8992, check_set, prov, "4_pdf_8792")
    print(f"  4. 1987-1992 PDF (89a): {prov['4_pdf_8792']} records")

    # 5. 2023 checks from the master file (script 89b)
    load_csv_checks(MASTER_2023, check_set, prov, "5_master_2023")
    print(f"  5. 2023 master (89b): {prov['5_master_2023']} records")

    # 6. recurrence backfill — ONLY for years that are STILL zero after 1-5.
    #    A named cultivar present that year recurring >= RECUR_MIN years is an
    #    established check (same rule validated on 1990 in script 89a). This
    #    resolves ERA-A years (e.g. 1941) with no extractable per-year source.
    years_with_check = {y for (mg, k, y) in check_set}
    all_years = {y for (_, _, y) in present}
    zero_years = sorted(all_years - years_with_check)
    n_bf = 0
    bf_examples = defaultdict(list)
    for y in zero_years:
        for (mg, k, spelling) in named_present.get(y, ()):
            if recur.get(k, 0) >= RECUR_MIN and (mg, k, y) not in check_set:
                check_set.add((mg, k, y)); prov["6_recurrence_backfill"] += 1; n_bf += 1
                if len(bf_examples[y]) < 12:
                    bf_examples[y].append(spelling)
    print(f"  6. recurrence backfill (still-zero years {zero_years}): {n_bf} added")
    for y in sorted(bf_examples):
        print(f"       {y}: {sorted(set(bf_examples[y]))}")

    # 7. preserve original pre-strainsTable-era checks: the old hardcoded list
    #    flagged some established checks (Wells, Hodgson, Beeson, Cumberland)
    #    in 1972-1980 that predate strainsTables and slipped through the PDF
    #    sweep. Keep an OLD check only if it is clearly established (recurs
    #    >= PRESERVE_RECUR_MIN years) and year <= PRESERVE_MAX_YEAR, so genuine
    #    corrections (e.g. a pre-release variety entered before becoming a
    #    check) are NOT resurrected in the modern era.
    PRESERVE_MAX_YEAR = 1980
    PRESERVE_RECUR_MIN = 5
    n_pres = 0
    pres_examples = set()
    for (mg, k, y) in old_checks:
        if y <= PRESERVE_MAX_YEAR and recur.get(k, 0) >= PRESERVE_RECUR_MIN \
                and (mg, k, y) not in check_set:
            check_set.add((mg, k, y)); prov["7_preserve_old"] += 1; n_pres += 1
            pres_examples.add((mg, y))
    print(f"  7. preserve old pre-{PRESERVE_MAX_YEAR} established checks: {n_pres} added")

    print(f"  ENRICHED SET: {len(check_set)} unique (MG, key, Year)")
    return check_set


# ---------------------------------------------------------------------------
# Rebuild a combined file
# ---------------------------------------------------------------------------
def rebuild(fname, check_set):
    src = DATA / fname
    if not src.exists():
        print(f"  SKIP missing {fname}"); return None
    out = DATA / (src.stem + ".ischeck_rebuilt.csv")
    n = old1 = new1 = chg_01 = chg_10 = 0
    by_year_new = Counter(); by_year_old = Counter()
    by_tt = Counter()
    with open(src, newline="", encoding="utf-8", errors="replace") as fi, \
         open(out, "w", newline="", encoding="utf-8") as fo:
        r = csv.DictReader(fi); cols = r.fieldnames
        w = csv.DictWriter(fo, fieldnames=cols); w.writeheader()
        for x in r:
            n += 1
            try:
                y = int(float(x["Year"]))
            except (TypeError, ValueError, KeyError):
                y = None
            old = (x.get("IsCheck") or "").strip()
            k = mkey(x.get("Strain"))
            mg = (x.get("TestMG") or "").strip().upper()
            new = 1 if (y is not None and k and (mg, k, y) in check_set) else 0
            if old == "1":
                old1 += 1; by_year_old[y] += 1
            if new == 1:
                new1 += 1; by_year_new[y] += 1; by_tt[(x.get("TestType") or "").strip()] += 1
            if old != "1" and new == 1: chg_01 += 1
            if old == "1" and new == 0: chg_10 += 1
            x["IsCheck"] = new
            w.writerow(x)
    print(f"\n=== {fname} ===")
    print(f"  rows={n:,}  IsCheck=1 old={old1:,} -> new={new1:,}  (0->1: {chg_01:,}  1->0: {chg_10:,})")
    print(f"  new IsCheck=1 by TestType: {dict(by_tt)}")
    return {"out": out, "src": src, "n": n, "by_year_new": by_year_new,
            "by_year_old": by_year_old, "chg_10": chg_10}


def validate(stats):
    by_new = stats["by_year_new"]; by_old = stats["by_year_old"]
    years = [y for y in range(1941, 2026)]
    zero_new = [y for y in years if by_new.get(y, 0) == 0]
    print("\n  Per-year IsCheck=1 (old -> new):")
    for y in years:
        o, nw = by_old.get(y, 0), by_new.get(y, 0)
        flag = "  <-- ZERO" if nw == 0 else ("  (was 0)" if o == 0 and nw > 0 else "")
        if o == 0 or nw == 0 or y % 5 == 0 or y >= 1986:
            print(f"    {y}: {o:>6} -> {nw:>6}{flag}")
    if zero_new:
        print(f"\n  ** ACCEPTANCE TEST FAILED: zero-check years remain: {zero_new}")
    else:
        print("\n  ** ACCEPTANCE TEST PASSED: every year 1941-2025 has IsCheck=1 rows.")
    return not zero_new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", action="store_true",
                    help="commit: swap originals in place (keeps .pre_ischeck_rebuild.bak)")
    args = ap.parse_args()

    check_set = build_check_set()

    first_stats = None
    outputs = []
    for t in TARGETS:
        st = rebuild(t, check_set)
        if st is None:
            continue
        outputs.append(st)
        if first_stats is None:
            first_stats = st

    ok = validate(first_stats) if first_stats else False

    if args.replace:
        if not ok:
            sys.exit("\nRefusing --replace: acceptance test failed.")
        import shutil
        for st in outputs:
            bak = st["src"].with_suffix(".pre_ischeck_rebuild.bak")
            if not bak.exists():
                shutil.copy2(st["src"], bak)
            shutil.move(str(st["out"]), str(st["src"]))
            print(f"  replaced {st['src'].name}  (backup: {bak.name})")
        print("\nReplaced originals. Backups kept. DO NOT open these in Excel.")
    else:
        print("\nNon-destructive run complete. Review the .ischeck_rebuilt.csv files,")
        print("then re-run with --replace to commit.")


if __name__ == "__main__":
    main()
