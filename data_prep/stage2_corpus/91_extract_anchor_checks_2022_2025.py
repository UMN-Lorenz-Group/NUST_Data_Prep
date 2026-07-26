"""
91_extract_anchor_checks_2022_2025.py
=====================================
Compile, for 2022-2025, the per-trial CHECKS and the maturity ANCHOR CHECK +
full per-entry maturity, from the NUST modern processing files on the R: drive.

Zero-API, fully local parsing. The R: drive is read ONLY (never written).

Per-trial report CSV (UT00/UT0/UTI/UTII/UTIII/UTIV[+TM], PTI/PTIIA/PTIIB/PTIIIA/
PTIIIB/PTIV[+TM]; 2024 uses PTII) contains a "MATURITY (date)" Strain x Location
matrix where:
  - a 3-row header gives each column's location: a name-fragment row + a name row
    (hyphen-split, "Suther-"+"land"->"Sutherland", "West"+"Lafayette"->"West Lafayette")
    + a state row (IA/IL/IN/...);
  - the FIRST data row is the ANCHOR CHECK: absolute maturity DATES (m/d) per location;
  - every other row is a relative day-offset to the anchor (-3, +2, -0, blank=not grown);
  - trailing "Date Planted" + "Days to Mature" rows give per-location planting date and
    the anchor's days-to-mature.
DOY is computed with datetime (year-aware / leap-safe); verified to reconcile:
anchorDOY(loc) == plantedDOY(loc) + DaysToMature(loc).

Outputs (analysis/data/):
  nust_checks_2022_2025.csv          Year,Test,MG,Strain,IsCheck,RM
  nust_anchor_checks_2022_2025.csv   Year,Test,MG,Location,State,AnchorStrain,
                                     AnchorDate,AnchorDOY,DatePlanted,DaysToMature
  nust_entry_maturity_2022_2025.csv  Year,Test,MG,Location,State,Strain,RelOffset,
                                     MaturityDOY,IsAnchor

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/91_extract_anchor_checks_2022_2025.py
"""
import csv
import datetime
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

RDRIVE = Path(r"R:\cfans_agro_lore0149_lorenzlabresearch\NUST_Data\NUST_Data")
OUT    = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/analysis/data/_shared")
DESIG  = OUT / "nust_check_designation_years_1941_2025.csv"   # cross-year fallback
YEARS  = [2022, 2023, 2024, 2025]

TRIAL_RE = re.compile(r"^(UT|PT)[0-9IVAB]*(TM)?\.csv$", re.IGNORECASE)
MG_FROM_TEST = re.compile(r"^(?:UT|PT)\s*-?\s*(00|0|IV|III|II|I)", re.IGNORECASE)
STATE_RE = re.compile(r"^[A-Za-z]{2,4}$")
NON_STATE = {"tests", "mean", "test", "no", "rank"}


def proc_dir(year):
    return RDRIVE / str(year) / f"{year}_NUST_Processing"


def parse_mg(test):
    m = MG_FROM_TEST.search(str(test).upper())
    return m.group(1).upper() if m else None


def norm_test(t):
    """Canonical trial key: 'UT0-TM' -> 'UT0TM', 'UTII' -> 'UTII'."""
    return re.sub(r"[^A-Z0-9]", "", str(t).upper())


def strip_paren(s):
    s = str(s).strip()
    prev = None
    while s != prev:
        prev = s
        s = re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()
    return s


def norm(s):
    """Alphanumeric-only match key: 'ND Dickey (0)' -> 'nddickey',
    'NDDickey' -> 'nddickey', 'MN0083 (00)' -> 'mn0083'. Used only for matching
    checks across files whose strain spacing/suffixes differ."""
    return re.sub(r"[^a-z0-9]", "", strip_paren(str(s)).lower())


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_RE = re.compile(r"^\s*(\d{1,2}/\d{1,2}|\d{1,2}-[A-Za-z]{3,}|[A-Za-z]{3,}-\d{1,2})\s*$")


def is_date(s):
    return bool(DATE_RE.match(str(s)))


def to_doy(s, year):
    """Parse '9/20' (M/D) or '20-Sep' (D-Mon) or 'Sep-20' (Mon-D) to day-of-year."""
    s = str(s).strip()
    mo = da = None
    if "/" in s:
        p = s.split("/")
        try:
            mo, da = int(p[0]), int(p[1])
        except (ValueError, IndexError):
            return None
    elif "-" in s:
        a, b = (s.split("-", 1) + [""])[:2]
        a, b = a.strip(), b.strip()
        if a.isdigit() and b[:3].lower() in MONTHS:
            da, mo = int(a), MONTHS[b[:3].lower()]
        elif a[:3].lower() in MONTHS and b.isdigit():
            mo, da = MONTHS[a[:3].lower()], int(b)
    if mo and da:
        try:
            return datetime.date(year, mo, da).timetuple().tm_yday
        except ValueError:
            return None
    return None


def to_offset(s):
    s = str(s).strip()
    if s == "":
        return None
    try:
        return float(s)          # "-3", "2", "-0" -> 0.0
    except ValueError:
        return None


def read_rows(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return [row for row in csv.reader(f)]


# Cross-year check fallback: (MG, normStrain, Year) ever designated a check.
# Covers 2023, whose processing folder has no checksTable CSV — its checks live in
# nust_checks_2023_from_master.csv (script 89b); the main designation file (script
# 65) never got 2023.
DESIG_SET = set()
for _f in (DESIG, OUT / "nust_checks_2023_from_master.csv"):
    if _f.exists():
        for x in csv.DictReader(open(_f, encoding="utf-8", errors="replace")):
            try:
                DESIG_SET.add((str(x["MG"]).strip(), norm(x["Strain"]), int(float(x["Year"]))))
            except (KeyError, ValueError):
                pass


def is_designated(test, strain, year):
    return (parse_mg(test), norm(strain), int(year)) in DESIG_SET


# ── checks: derived from checksTable (authoritative per-trial check list), since
#    only some years' strainsTable carries a Check column ──────────────────────
def find_file(year, name):
    pdir = proc_dir(year)
    for cand in (pdir / name, pdir / "Files4Upload" / name, pdir / "Files4Upload_V1" / name):
        if cand.exists():
            return cand
    return None


def load_checks(year):
    """Return (checks_rows, check_set) where check_set = {(normTest, normStrain)} of checks.

    Checks come from checksTable1_RM / checksTable1 (these list ONLY checks).
    The full strain roster (for the IsCheck=0 rows + clean names) comes from
    strainsTable1. RM rating from the checksTable. Both files are located with a
    Files4Upload fallback (2024)."""
    check_set, rm_lut = set(), {}
    for cand in ("checksTable1_RM.csv", "checksTable1.csv"):
        fp = find_file(year, cand)
        if fp:
            for x in csv.DictReader(open(fp, encoding="utf-8", errors="replace")):
                t = norm_test(x.get("Test"))
                k = (t, norm(x.get("Strain")))
                if t and k[1]:
                    check_set.add(k)
                    if (x.get("RM") or "").strip():
                        rm_lut[k] = (x.get("RM") or "").strip()
            break

    checks = []
    st = find_file(year, "strainsTable1.csv")
    if st is None:
        print(f"  WARN {year}: strainsTable1.csv not found")
        return checks, check_set
    # Some years also carry a Check column; union it with the checksTable set.
    for x in csv.DictReader(open(st, encoding="utf-8", errors="replace")):
        t = (x.get("Test") or "").strip()
        strain = (x.get("Strain") or "").strip()
        if not t or not strain:
            continue
        k = (norm_test(t), norm(strain))
        is_chk = 1 if (k in check_set or (x.get("Check") or "").strip() == "1"
                       or is_designated(t, strain, year)) else 0
        if is_chk:
            check_set.add(k)
        checks.append((year, t, parse_mg(t), strain, is_chk, rm_lut.get(k, "")))
    return checks, check_set


# ── per-trial MATURITY (date) section ────────────────────────────────────────
def parse_trial(path, year):
    """Return (test, anchors[list], entries[list]) or None.

    anchors: dict location_idx -> {city,state,anchor_date,anchor_doy,planted,d2m}
    entries: list of {strain, is_anchor, col-> offset}
    """
    rows = read_rows(path)
    test = path.stem.upper()

    def cell(r, c):
        return r[c].strip() if c < len(r) else ""

    # locate "MATURITY (date)" in ANY column (some files have a leading blank col);
    # `lab` = the label column where section/strain/footer labels live.
    mi = lab = None
    for i, r in enumerate(rows):
        for j, c in enumerate(r):
            if c.strip().upper() == "MATURITY (DATE)":
                mi, lab = i, j; break
        if mi is not None:
            break
    if mi is None:
        return None
    # state header row = first row after mi whose label-col cell == "Strain"
    si = next((i for i in range(mi + 1, min(mi + 12, len(rows)))
               if cell(rows[i], lab).lower() == "strain"), None)
    if si is None or si < mi + 2:
        return None
    frag_row, name_row, state_row = rows[si - 2], rows[si - 1], rows[si]
    width = max(len(frag_row), len(name_row), len(state_row))

    # location columns: state cell looks like a state and name cell non-empty
    loc_cols = {}
    for c in range(lab + 1, width):
        stt = cell(state_row, c).rstrip("*")     # 'IA*' (frost footnote) -> 'IA'
        nm = cell(name_row, c)
        if not stt or stt.lower() in NON_STATE or not STATE_RE.match(stt) or not nm:
            continue
        frag = cell(frag_row, c)
        if frag.endswith("-"):
            city = frag[:-1] + nm
        elif frag:
            city = frag + " " + nm
        else:
            city = nm
        loc_cols[c] = {"city": city.strip(), "state": stt}
    if not loc_cols:
        return None

    # data rows from si+1 until "Date Planted"
    planted_row = days_row = None
    data = []
    for i in range(si + 1, len(rows)):
        r = rows[i]
        c0 = cell(r, lab)
        if c0.lower() == "date planted":
            planted_row = r; continue
        if c0.lower() == "days to mature":
            days_row = r
            break
        if c0.upper().startswith("UNIFORM TEST") or c0.upper().startswith("PRELIM"):
            break
        if not c0:
            continue
        data.append(r)
    if not data:
        return None

    # anchor = first data row with date-valued location cells (M/D or D-Mon)
    anchor_idx = next((k for k, r in enumerate(data)
                       if sum(1 for c in loc_cols if is_date(cell(r, c))) >= 2), None)
    if anchor_idx is None:
        return None
    anchor_row = data[anchor_idx]
    anchor_strain = cell(anchor_row, lab)

    anchors = {}
    for c, info in loc_cols.items():
        adate = cell(anchor_row, c)
        adoy = to_doy(adate, year)
        planted = cell(planted_row, c) if planted_row else ""
        d2m = cell(days_row, c) if days_row else ""
        anchors[c] = {
            "city": info["city"], "state": info["state"],
            "anchor_date": adate, "anchor_doy": adoy,
            "planted": planted, "planted_doy": to_doy(planted, year),
            "d2m": d2m,
        }

    entries = []
    for k, r in enumerate(data):
        strain = cell(r, lab)
        if not strain or strain.lower() in ("mean", "average"):
            continue
        is_anchor = (k == anchor_idx)
        offs = {}
        for c in loc_cols:
            offs[c] = 0.0 if is_anchor else to_offset(cell(r, c))
        entries.append({"strain": strain, "is_anchor": is_anchor, "off": offs})

    return test, anchors, entries


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    all_checks, all_anchor, all_entry = [], [], []
    anchor_not_check = []
    doy_resid = []   # |anchorDOY - (plantedDOY + d2m)|

    for year in YEARS:
        pdir = proc_dir(year)
        if not pdir.exists():
            print(f"{year}: processing dir not found ({pdir}) — skipped"); continue
        checks, check_set = load_checks(year)
        all_checks.extend(checks)

        trial_files = sorted(p for p in pdir.iterdir()
                             if p.is_file() and TRIAL_RE.match(p.name)
                             and "seed traits" not in p.name.lower())
        print(f"\n=== {year}: {len(trial_files)} trial files ===")
        for tf in trial_files:
            res = parse_trial(tf, year)
            if res is None:
                print(f"  {tf.name:12s} — no MATURITY section parsed"); continue
            test, anchors, entries = res
            mg = parse_mg(test)
            a_strain = next((e["strain"] for e in entries if e["is_anchor"]), "")
            is_chk = ((norm_test(test), norm(a_strain)) in check_set
                      or is_designated(test, a_strain, year))
            if not is_chk:
                anchor_not_check.append((year, test, a_strain))
            nloc = len(anchors)
            print(f"  {tf.name:12s} MG {mg or '?':3s} anchor={a_strain:22s} "
                  f"locs={nloc} entries={len(entries)} anchor_is_check={is_chk}")

            for c, a in anchors.items():
                all_anchor.append((year, test, mg, a["city"], a["state"], a_strain,
                                   a["anchor_date"], a["anchor_doy"], a["planted"], a["d2m"]))
                if a["anchor_doy"] is not None and a["planted_doy"] is not None:
                    try:
                        d2m = int(float(a["d2m"]))
                        doy_resid.append(abs(a["anchor_doy"] - (a["planted_doy"] + d2m)))
                    except (ValueError, TypeError):
                        pass
            for e in entries:
                for c, off in e["off"].items():
                    a = anchors[c]
                    mdoy = (a["anchor_doy"] + off) if (a["anchor_doy"] is not None and off is not None) else None
                    if off is None and not e["is_anchor"]:
                        continue   # not grown at this location
                    all_entry.append((year, test, mg, a["city"], a["state"], e["strain"],
                                      off, mdoy, int(e["is_anchor"])))

    # write outputs
    with open(OUT / "nust_checks_2022_2025.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Year", "Test", "MG", "Strain", "IsCheck", "RM"])
        w.writerows(all_checks)
    with open(OUT / "nust_anchor_checks_2022_2025.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Year", "Test", "MG", "Location", "State", "AnchorStrain",
                    "AnchorDate", "AnchorDOY", "DatePlanted", "DaysToMature"])
        w.writerows(all_anchor)
    with open(OUT / "nust_entry_maturity_2022_2025.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Year", "Test", "MG", "Location", "State", "Strain",
                    "RelOffset", "MaturityDOY", "IsAnchor"])
        w.writerows(all_entry)

    print(f"\n{'='*60}")
    print(f"checks rows : {len(all_checks):,}  (IsCheck=1: {sum(1 for c in all_checks if c[4]==1):,})")
    print(f"anchor rows : {len(all_anchor):,}  (Year x Test x Location)")
    print(f"entry rows  : {len(all_entry):,}")
    if doy_resid:
        ok = sum(1 for d in doy_resid if d <= 1)
        print(f"DOY sanity  : {ok}/{len(doy_resid)} cells |anchorDOY-(planted+d2m)|<=1 "
              f"({100*ok/len(doy_resid):.1f}%)")
    if anchor_not_check:
        print(f"\nAnchors NOT flagged as check ({len(anchor_not_check)}):")
        for y, t, s in anchor_not_check:
            print(f"  {y} {t}: {s}")
    print(f"\nWrote 3 CSVs to {OUT}")


if __name__ == "__main__":
    main()
