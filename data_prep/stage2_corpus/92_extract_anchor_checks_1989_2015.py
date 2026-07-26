"""
92_extract_anchor_checks_1989_2015.py
=====================================
Extract maturity ANCHOR checks + relative day-offsets (and per-entry maturity DOY)
for 1989-2015 from the URT Phenotype Data folder, and VERIFY the reconstructed DOY
against the corpus's current Maturity values.

Source (read-only):
  R:/cfans_agro_lore0149_lorenzlabresearch/NUST_project_1989_2020/URT Phenotype Data/Years/<year>/

Two source formats (this file = PHASE 1, Format B only; Format A added next):
  Format B (granular) — <Trial>_Maturity.csv  or  _Maturity1/2/3.csv  (location halves):
    row0 header = Strain | [Mean N Tests] | "City State" ...
    first DATED row = anchor check (absolute dates); other rows = relative offsets;
    footer rows "Date Planted" + "Days to Mature" per location.
    Years: 2004, 2009-2014 (+ partial 2005, 2011).

The anchor is the DATED row (NOT necessarily the first row). Per-entry maturity:
  MaturityDOY(entry, loc) = anchorDOY(loc) + offset(entry, loc).
DOY via datetime (leap-safe); handles '9/17' and '17-Sep'.

Outputs (analysis/data/):
  nust_anchor_checks_1989_2020.csv    Year,Test,MG,Location,State,AnchorStrain,AnchorDate,AnchorDOY,DatePlanted,DaysToMature
  nust_entry_maturity_1989_2020.csv   Year,Test,MG,Location,State,Strain,RelOffset,MaturityDOY,IsAnchor
  + console verification vs corpus wide Maturity.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/92_extract_anchor_checks_1989_2015.py
"""
import csv
import datetime
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

URT  = Path(r"R:\cfans_agro_lore0149_lorenzlabresearch\NUST_project_1989_2020\URT Phenotype Data\Years")
OUT  = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/analysis/data/_shared")
WIDE = OUT / "NUST_1941_2025_data_wide.csv"

FORMAT_B_YEARS = [2004, 2009, 2010, 2011, 2012, 2013, 2014]   # granular _Maturity files
FORMAT_A_YEARS = (list(range(1989, 2004)) + [2005, 2006, 2007, 2008]
                  + [2017, 2018, 2019, 2020] + [2015])  # full multi-section CSVs
STATE_RE  = re.compile(r"^[A-Za-z]{2,4}$")
NON_STATE = {"tests", "mean", "test", "no", "rank", "strain"}
A_TRIAL_RE = re.compile(r"^(UT|PT)[0-9IVABR]*(-?TM)?\.csv$", re.IGNORECASE)

MG_FROM_TEST = re.compile(r"^(?:UT|PT)\s*-?\s*(00|0|IV|III|II|I)", re.IGNORECASE)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_RE = re.compile(r"^\s*(\d{1,2}/\d{1,2}|\d{1,2}-[A-Za-z]{3,}|[A-Za-z]{3,}-\d{1,2})\s*$")
STATE_TOK = re.compile(r"^[A-Za-z]{2,4}\.?$")   # IA, MI, ONT, Ont.


def parse_mg(test):
    m = MG_FROM_TEST.search(str(test).upper())
    return m.group(1).upper() if m else None


def strip_paren(s):
    s = str(s).strip()
    prev = None
    while s != prev:
        prev = s
        s = re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()
    return s


def norm(s):
    return re.sub(r"[^a-z0-9]", "", strip_paren(str(s)).lower())


def is_date(s):
    return bool(DATE_RE.match(str(s)))


def to_doy(s, year):
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


def read_rows(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return [row for row in csv.reader(f)]


def cell(r, c):
    return r[c].strip() if c < len(r) else ""


# ── Format B: parse one <Trial>_Maturity*.csv file ───────────────────────────
def parse_B_file(path, year):
    """Return (anchor_strain, per_loc, per_entry).

    per_loc:   {(city,state): {anchor_date, anchor_doy, planted, days}}
    per_entry: list of (strain, (city,state), offset_or_None, is_anchor)
    """
    rows = read_rows(path)
    if not rows:
        return None, {}, []
    header = rows[0]
    # location columns: header cell = "City ... ST"; skip Strain (col0) + Mean/Tests
    loc_cols = {}
    for c in range(1, len(header)):
        h = header[c].replace("\n", " ").strip()
        if not h or "mean" in h.lower() or h.lower() == "tests":
            continue
        toks = h.split()
        if len(toks) >= 2 and STATE_TOK.match(toks[-1]):
            loc_cols[c] = (" ".join(toks[:-1]).strip(), toks[-1].rstrip("."))
        elif h:
            loc_cols[c] = (h, "")
    if not loc_cols:
        return None, {}, []

    planted_row = days_row = None
    data = []
    for r in rows[1:]:
        c0 = cell(r, 0)
        lc = c0.lower()
        if lc == "date planted":
            planted_row = r; continue
        if lc == "days to mature":
            days_row = r; break
        if not c0:
            continue
        data.append(r)

    anchor_idx = next((k for k, r in enumerate(data)
                       if sum(1 for c in loc_cols if is_date(cell(r, c))) >= 2), None)
    if anchor_idx is None:
        return None, {}, []
    anchor_row = data[anchor_idx]
    anchor_strain = cell(anchor_row, 0)

    per_loc = {}
    for c, key in loc_cols.items():
        adate = cell(anchor_row, c)
        per_loc[key] = {
            "anchor_date": adate,
            "anchor_doy": to_doy(adate, year),
            "planted": cell(planted_row, c) if planted_row else "",
            "days": cell(days_row, c) if days_row else "",
        }

    per_entry = []
    for k, r in enumerate(data):
        strain = cell(r, 0)
        if not strain or strain.lower() in ("mean", "average"):
            continue
        is_anchor = (k == anchor_idx)
        for c, key in loc_cols.items():
            v = cell(r, c)
            if is_anchor:
                off = 0.0
            else:
                try:
                    off = float(v) if v != "" else None
                except ValueError:
                    off = None
            per_entry.append((strain, key, off, is_anchor))
    return anchor_strain, per_loc, per_entry


def parse_A_file(path, year):
    """Parse the multi-block MATURITY(date) section of a full trial CSV.
    Returns (anchor_strain, per_loc, per_entry) — same shape as parse_B_file.
    Reuses script 91's section logic; the multi-block layout is handled because
    repeated 'Strain'/'Tests' separator columns fail the state test."""
    rows = read_rows(path)
    mi = lab = None
    for i, r in enumerate(rows):
        for j, c in enumerate(r):
            if c.strip().upper() == "MATURITY (DATE)":
                mi, lab = i, j; break
        if mi is not None:
            break
    if mi is None:
        return None, {}, []
    # state row = the row near MATURITY with the most state codes (robust to the
    # 'Strain' label sitting on either the state row or the name row above it)
    def n_states(r):
        n = 0
        for c in r:
            cc = c.strip().rstrip("*.")
            if STATE_RE.match(cc) and cc.lower() not in NON_STATE:
                n += 1
        return n
    cand = [(n_states(rows[i]), -i, i) for i in range(mi + 2, min(mi + 16, len(rows)))]
    cand = [t for t in cand if t[0] >= 2]   # >=2 so tiny MG-00/0 trials (2 locs) parse
    if not cand:
        return None, {}, []
    si = max(cand)[2]
    if si < mi + 2:
        return None, {}, []
    frag_row, name_row, state_row = rows[si - 2], rows[si - 1], rows[si]
    width = max(len(frag_row), len(name_row), len(state_row))

    loc_cols = {}
    for c in range(lab + 1, width):
        stt = cell(state_row, c).rstrip("*.").strip()
        nm = cell(name_row, c).rstrip("*").strip()
        if not stt or stt.lower() in NON_STATE or not STATE_RE.match(stt) or not nm:
            continue
        frag = cell(frag_row, c)
        if frag.endswith("-"):
            city = frag[:-1] + nm
        elif frag:
            city = frag + " " + nm
        else:
            city = nm
        loc_cols[c] = (city.strip(), stt)
    if not loc_cols:
        return None, {}, []

    planted_row = days_row = None
    data = []
    for i in range(si + 1, len(rows)):
        r = rows[i]
        c0 = cell(r, lab)
        lc = c0.lower()
        if lc == "date planted":
            planted_row = r; continue
        if lc == "days to mature":
            days_row = r; break
        if c0.upper().startswith("UNIFORM TEST") or c0.upper().startswith("PRELIM"):
            break
        if not c0 or c0 == "_":
            continue
        data.append(r)
    if not data:
        return None, {}, []

    anchor_idx = next((k for k, r in enumerate(data)
                       if sum(1 for c in loc_cols if is_date(cell(r, c))) >= 2), None)
    if anchor_idx is None:
        return None, {}, []
    anchor_row = data[anchor_idx]
    anchor_strain = cell(anchor_row, lab)

    per_loc = {}
    for c, key in loc_cols.items():
        adate = cell(anchor_row, c)
        per_loc[key] = {"anchor_date": adate, "anchor_doy": to_doy(adate, year),
                        "planted": cell(planted_row, c) if planted_row else "",
                        "days": cell(days_row, c) if days_row else ""}
    per_entry = []
    for k, r in enumerate(data):
        strain = cell(r, lab)
        if not strain or strain.lower() in ("mean", "average"):
            continue
        is_anchor = (k == anchor_idx)
        for c, key in loc_cols.items():
            v = cell(r, c)
            if is_anchor:
                off = 0.0
            else:
                try:
                    off = float(v) if v != "" else None
                except ValueError:
                    off = None
            per_entry.append((strain, key, off, is_anchor))
    return anchor_strain, per_loc, per_entry


def extract_year_A(year):
    d = URT / str(year)
    anchors, entries = [], []
    for p in sorted(x for x in d.iterdir() if x.is_file() and A_TRIAL_RE.match(x.name)):
        trial = p.stem.upper()
        mg = parse_mg(trial)
        a_strain, per_loc, per_entry = parse_A_file(p, year)
        if a_strain is None or not per_loc:
            print(f"  {year} {trial:9s} — no maturity parsed"); continue
        print(f"  {year} {trial:9s} MG {mg or '?':3s} anchor={a_strain:18s} locs={len(per_loc)}")
        for (city, state), info in per_loc.items():
            anchors.append((year, trial, mg, city, state, a_strain,
                            info["anchor_date"], info["anchor_doy"], info["planted"], info["days"]))
        for strain, (city, state), off, is_anchor in per_entry:
            adoy = per_loc.get((city, state), {}).get("anchor_doy")
            mdoy = (adoy + off) if (adoy is not None and off is not None) else None
            if off is None and not is_anchor:
                continue
            entries.append((year, trial, mg, city, state, strain, off, mdoy, int(is_anchor)))
    return anchors, entries


def trial_files_B(year):
    """Group a year's *_Maturity*.csv files by trial code."""
    d = URT / str(year)
    groups = defaultdict(list)
    for p in sorted(d.glob("*_Maturity*.csv")):
        trial = re.sub(r"_Maturity\d*$", "", p.stem)
        groups[trial].append(p)
    return groups


def extract_year_B(year):
    anchors, entries = [], []
    for trial, files in sorted(trial_files_B(year).items()):
        mg = parse_mg(trial)
        merged_loc, merged_entry, a_strain = {}, [], None
        for fp in sorted(files):
            a, per_loc, per_entry = parse_B_file(fp, year)
            if a is None:
                continue
            a_strain = a_strain or a
            merged_loc.update(per_loc)
            merged_entry.extend(per_entry)
        if a_strain is None or not merged_loc:
            print(f"  {year} {trial:9s} — no maturity parsed ({len(files)} files)")
            continue
        print(f"  {year} {trial:9s} MG {mg or '?':3s} anchor={a_strain:18s} locs={len(merged_loc)}")
        for (city, state), info in merged_loc.items():
            anchors.append((year, trial, mg, city, state, a_strain,
                            info["anchor_date"], info["anchor_doy"], info["planted"], info["days"]))
        for strain, (city, state), off, is_anchor in merged_entry:
            adoy = merged_loc.get((city, state), {}).get("anchor_doy")
            mdoy = (adoy + off) if (adoy is not None and off is not None) else None
            if off is None and not is_anchor:
                continue
            entries.append((year, trial, mg, city, state, strain, off, mdoy, int(is_anchor)))
    return anchors, entries


# ── Verification vs corpus wide Maturity ─────────────────────────────────────
def load_corpus_maturity(years):
    """(year, normStrain, normCity) -> Maturity (corpus DOY)."""
    lut = {}
    yrs = set(str(y) for y in years)
    with open(WIDE, newline="", encoding="utf-8", errors="replace") as f:
        for x in csv.DictReader(f):
            if x.get("Year") not in yrs:
                continue
            mat = (x.get("Maturity") or "").strip()
            if not mat:
                continue
            try:
                lut[(x["Year"], norm(x.get("Strain")), norm(x.get("Location")))] = float(mat)
            except ValueError:
                continue
    return lut


def verify(entries, years):
    lut = load_corpus_maturity(years)
    print(f"\nCorpus Maturity cells loaded (these years): {len(lut):,}")
    per_year = defaultdict(lambda: {"n": 0, "matched": 0, "d0": 0, "d1": 0, "d2": 0, "absum": 0.0})
    for (year, trial, mg, city, state, strain, off, mdoy, isa) in entries:
        if mdoy is None:
            continue
        st = per_year[year]; st["n"] += 1
        ns = norm(strain)
        # corpus locations are 'City_State' (norm 'citystate'); also try city-only
        cm = None
        for lk in (norm(city + state), norm(city)):
            cm = lut.get((str(year), ns, lk))
            if cm is not None:
                break
        if cm is None:
            continue
        st["matched"] += 1
        d = abs(mdoy - cm)
        st["absum"] += d
        if d <= 0.5: st["d0"] += 1
        if d <= 1.5: st["d1"] += 1
        if d <= 2.5: st["d2"] += 1
    print("\nVerification vs corpus Maturity DOY (reconstructed = anchorDOY + offset):")
    print(f"  {'Year':5s} {'entries':>8s} {'matched':>8s} {'==':>7s} {'<=1':>7s} {'<=2':>7s} {'meanAbs':>8s}")
    for y in sorted(per_year):
        s = per_year[y]; m = s["matched"] or 1
        print(f"  {y:5} {s['n']:8d} {s['matched']:8d} "
              f"{100*s['d0']/m:6.1f}% {100*s['d1']/m:6.1f}% {100*s['d2']/m:6.1f}% "
              f"{s['absum']/m:8.2f}")


def main():
    all_anchor, all_entry = [], []
    all_years = sorted(set(FORMAT_B_YEARS) | set(FORMAT_A_YEARS))
    for year in all_years:
        if not (URT / str(year)).exists():
            print(f"{year}: folder missing"); continue
        fmt = "B" if year in FORMAT_B_YEARS else "A"
        print(f"\n=== {year} (Format {fmt}) ===")
        a, e = extract_year_B(year) if fmt == "B" else extract_year_A(year)
        all_anchor.extend(a); all_entry.extend(e)

    with open(OUT / "nust_anchor_checks_1989_2020.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Year", "Test", "MG", "Location", "State", "AnchorStrain",
                    "AnchorDate", "AnchorDOY", "DatePlanted", "DaysToMature"])
        w.writerows(all_anchor)
    with open(OUT / "nust_entry_maturity_1989_2020.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Year", "Test", "MG", "Location", "State", "Strain",
                    "RelOffset", "MaturityDOY", "IsAnchor"])
        w.writerows(all_entry)

    print(f"\n{'='*60}")
    print(f"anchor rows: {len(all_anchor):,}   entry rows: {len(all_entry):,}")
    # internal DOY sanity: anchorDOY == plantedDOY + DaysToMature (per anchor cell)
    ok = tot = 0
    for (year, trial, mg, city, state, a, adate, adoy, planted, days) in all_anchor:
        pdoy = to_doy(planted, year)
        try:
            d2m = int(float(days))
        except (ValueError, TypeError):
            d2m = None
        if adoy is not None and pdoy is not None and d2m is not None:
            tot += 1
            if abs(adoy - (pdoy + d2m)) <= 1:
                ok += 1
    print(f"DOY sanity : {ok}/{tot} anchor cells |anchorDOY-(planted+d2m)|<=1 "
          f"({100*ok/tot:.1f}%)" if tot else "DOY sanity : n/a")
    verify(all_entry, all_years)
    print(f"\nWrote 2 CSVs to {OUT} (1989-2015)")


if __name__ == "__main__":
    main()
