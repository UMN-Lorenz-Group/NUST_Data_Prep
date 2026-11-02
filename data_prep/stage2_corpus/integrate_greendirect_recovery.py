"""
Integrate the 8 green-direct NUST recovery sections into recovery_confirmed.csv.

REPLACE (drop existing PDF recovery rows, add green):
    (1985, UT-III)  <- reextract_1985_utiii_green.csv
    (1977, UT-III)  <- reextract_1977_utiii_utiv_green.csv
    (1977, UT-IV)   <- reextract_1977_utiii_utiv_green.csv
ADD (new cells):
    (1974, PT-I)    <- reextract_1974_pti_green.csv
    (1953, PT-IV)   <- reextract_early_pt_green.csv
    (1961, PT-III)  <- reextract_early_pt_green.csv
    (1962, PT-00)   <- reextract_early_pt_green.csv   (Yield only, no Maturity)
    (1962, PT-0)    <- reextract_early_pt_green.csv

Steps:
  1. REPLACE/ADD (concat all 8 green sections; Source="Recovered_1970_1988")
  2. Strain normalization (F4U convention) on all added green rows
  3. Maturity: 1974/1977/1985 already DOY (keep); early batch offsets -> DOY via
     per-section reference check corpus DOY (1953 Wabash, 1961 Shelby, 1962 PT-0 Grant)
  4. Validation report

STOP before any corpus rebuild. Writes recovery_confirmed.csv (backed up first) only.
"""
import csv
import re
import shutil
import sys
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
RECOVERY = HERE / "recovery_confirmed.csv"
BACKUP = HERE / "recovery_confirmed.csv.bak_pre_greendirect"
COMBINED = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
CANONMAP = REPO / "reference" / "nust_location_canonical_map.csv"

COLS = ["Year", "TestType", "TestMG", "Test", "Strain", "City", "State",
        "Phenotype", "Value_num", "Units", "Source"]

GREEN_FILES = [
    "reextract_1985_utiii_green.csv",
    "reextract_1977_utiii_utiv_green.csv",
    "reextract_1974_pti_green.csv",
    "reextract_early_pt_green.csv",
]

# (Year, Test) cells whose existing recovery rows must be removed before adding green
REPLACE_CELLS = {("1985", "UT-III"), ("1977", "UT-III"), ("1977", "UT-IV")}

ADDED_SOURCE = "Recovered_1970_1988"

# Per (year, test) offset-reconstruction reference checks (offset ~ 0)
REF_CHECK = {
    ("1953", "PT-IV"): "Wabash",
    ("1961", "PT-III"): "Shelby",
    ("1962", "PT-0"): "Grant",
}

RANGE_GATE = {
    "YieldBuA": (2, 120), "Height": (5, 80), "Lodging": (1, 5),
    "SeedQuality": (1, 5), "SeedSize": (5, 40), "Protein": (25, 55),
    "Oil": (5, 30), "Maturity": (210, 320),
}

STRAY_RE = re.compile(r"\b(mean|c\.?v\.?|l\.?s\.?d\.?|no\.?\s*of|reps?)\b", re.I)


# ---------------------------------------------------------------------------
# Strain normalization (F4U convention)
# ---------------------------------------------------------------------------
def norm_strain(s):
    s = re.sub(r"\s*\([^)]*\)", "", s).strip()   # drop MG parenthetical
    s = re.sub(r"\s+", "", s)                     # remove internal whitespace
    return s


def fold(s):
    """Fold l/1/i and O/0 for tolerant string comparison."""
    s = s.lower()
    s = s.replace("l", "1").replace("i", "1")
    s = s.replace("o", "0")
    return re.sub(r"\s+", "", s)


# ---------------------------------------------------------------------------
# Location canonicalization (mirror the assemble-pipeline map)
# ---------------------------------------------------------------------------
def build_canonicalizer():
    by_raw = {}
    by_normkey = {}
    state_norm = {}
    with open(CANONMAP, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rc, rs = r["raw_city"].strip(), r["raw_state"].strip()
            ns, nk = r["norm_state"].strip(), r["normkey"].strip()
            cc, cs = r["canon_city"].strip(), r["canon_state"].strip()
            if rs:
                state_norm[rs.upper()] = ns
            by_raw.setdefault((rc.lower(), rs.upper()), (cc, cs))
            if nk:
                by_normkey.setdefault((nk, ns.upper()), (cc, cs))
    return by_raw, by_normkey, state_norm


def make_canon(by_raw, by_normkey, state_norm):
    def canon(city, state):
        city = (city or "").strip()
        st = (state or "").strip().upper()
        hit = by_raw.get((city.lower(), st))
        if hit:
            return hit
        nk = re.sub(r"[^a-z0-9]", "", city.lower())
        ns = state_norm.get(st, st).upper()
        hit = by_normkey.get((nk, ns))
        if hit:
            return hit
        return (city, state_norm.get(st, st))
    return canon


# ---------------------------------------------------------------------------
# Corpus reference-check DOY anchors
# ---------------------------------------------------------------------------
def load_ref_anchors(canon):
    """
    For each (year, refcheck) return {(canon_city, canon_state): DOY}, choosing the
    companion test whose TestMG matches the target section MG, else a UT test, else any.
    """
    target = {("1953", "Wabash"): "IV",
              ("1961", "Shelby"): "III",
              ("1962", "Grant"): "0"}
    want_years = {"1953", "1961", "1962"}
    want_checks = {"Wabash", "Shelby", "Grant"}

    # (year, check) -> canon_loc -> list of (mg, testtype, doy)
    cand = defaultdict(lambda: defaultdict(list))
    with open(COMBINED, newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        for r in rd:
            if r["Year"] not in want_years:
                continue
            if r["Phenotype"] != "Maturity":
                continue
            if r["Strain"] not in want_checks:
                continue
            v = r["Value_num"].strip()
            if not v:
                continue
            try:
                doy = float(v)
            except ValueError:
                continue
            key = (r["Year"], r["Strain"])
            cloc = canon(r["City"], r["State"])
            cand[key][cloc].append((r["TestMG"].strip(), r["TestType"].strip(), doy))

    anchors = {}
    disagree = defaultdict(list)  # for reporting
    for key, locs in cand.items():
        want_mg = target.get(key)
        out = {}
        for cloc, lst in locs.items():
            # priority: same MG, then UT, then anything
            same_mg = [x for x in lst if x[0] == want_mg]
            pool = same_mg if same_mg else lst
            ut = [x for x in pool if x[1] == "UT"]
            pool2 = ut if ut else pool
            doys = sorted({x[2] for x in pool2})
            if len(doys) > 1:
                disagree[key].append((cloc, doys))
            out[cloc] = pool2[0][2]
        anchors[key] = out
    return anchors, disagree


# ---------------------------------------------------------------------------
# Load green rows
# ---------------------------------------------------------------------------
def load_green():
    rows = []
    for fn in GREEN_FILES:
        with open(HERE / fn, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.append({c: r[c] for c in COLS})
    return rows


def main():
    if not RECOVERY.exists():
        sys.exit(f"missing {RECOVERY}")

    # backup
    shutil.copy2(RECOVERY, BACKUP)

    by_raw, by_normkey, state_norm = build_canonicalizer()
    canon = make_canon(by_raw, by_normkey, state_norm)

    # ---- existing recovery: keep everything except the 3 REPLACE cells --------
    kept = []
    removed_counts = defaultdict(int)
    before_total = 0
    with open(RECOVERY, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            before_total += 1
            if (r["Year"], r["Test"]) in REPLACE_CELLS:
                removed_counts[(r["Year"], r["Test"], r["Phenotype"])] += 1
                continue
            kept.append({c: r[c] for c in COLS})

    # ---- green rows ----------------------------------------------------------
    green = load_green()

    # step 2: normalize strain on all green rows; set Source
    for r in green:
        r["Strain"] = norm_strain(r["Strain"])
        r["Source"] = ADDED_SOURCE

    # step 3: Maturity reconstruction for early offset sections
    anchors, disagree = load_ref_anchors(canon)
    recon_report = {}   # (year,test) -> dict(reconstructed, dropped_nolocanchor, dropped_outlier, drop_details)
    final_green = []
    for r in green:
        yt = (r["Year"], r["Test"])
        if r["Phenotype"] == "Maturity" and r["Units"] == "offset_days":
            check = REF_CHECK.get(yt)
            rep = recon_report.setdefault(
                yt, {"recon": 0, "drop_noanchor": 0, "drop_outlier": 0, "drop_locs": set()})
            if check is None:
                rep["drop_noanchor"] += 1
                rep["drop_locs"].add((r["City"], r["State"], "no_refcheck_defined"))
                continue
            amap = anchors.get((r["Year"], check), {})
            cloc = canon(r["City"], r["State"])
            base = amap.get(cloc)
            if base is None:
                rep["drop_noanchor"] += 1
                rep["drop_locs"].add((r["City"], r["State"]))
                continue
            try:
                off = float(r["Value_num"])
            except ValueError:
                rep["drop_noanchor"] += 1
                continue
            doy = base + off
            lo, hi = RANGE_GATE["Maturity"]
            if not (lo <= doy <= hi):
                rep["drop_outlier"] += 1
                rep["drop_locs"].add((r["City"], r["State"], f"DOY={doy}"))
                continue
            r = dict(r)
            r["Value_num"] = f"{doy:.1f}"
            r["Units"] = "DOY"
            rep["recon"] += 1
            final_green.append(r)
        else:
            final_green.append(r)

    # ---- combine + dedup -----------------------------------------------------
    all_rows = kept + final_green
    seen = {}
    dup_keys = []
    deduped = []
    for r in all_rows:
        k = (r["Year"], r["Test"], r["Strain"], r["City"], r["State"], r["Phenotype"])
        if k in seen:
            dup_keys.append(k)
            continue
        seen[k] = True
        deduped.append(r)

    # ---- write ---------------------------------------------------------------
    with open(RECOVERY, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in deduped:
            w.writerow({c: r[c] for c in COLS})

    # =====================================================================
    # VALIDATION REPORT
    # =====================================================================
    def cell_pheno_counts(rows, cells):
        out = defaultdict(int)
        for r in rows:
            if (r["Year"], r["Test"]) in cells:
                out[(r["Year"], r["Test"], r["Phenotype"])] += 1
        return out

    green_after = cell_pheno_counts(
        deduped,
        {("1985", "UT-III"), ("1977", "UT-III"), ("1977", "UT-IV"),
         ("1974", "PT-I"), ("1953", "PT-IV"), ("1961", "PT-III"),
         ("1962", "PT-00"), ("1962", "PT-0")})

    print("=" * 70)
    print("GREEN-DIRECT RECOVERY INTEGRATION — VALIDATION REPORT")
    print("=" * 70)
    print(f"Backup written: {BACKUP.name}")
    print(f"recovery_confirmed rows BEFORE: {before_total}")
    print(f"recovery_confirmed rows AFTER : {len(deduped)}")
    print()

    print("--- REPLACE cells: OLD (removed) vs NEW (green) per phenotype ---")
    for cell in [("1985", "UT-III"), ("1977", "UT-III"), ("1977", "UT-IV")]:
        old = {k[2]: v for k, v in removed_counts.items() if (k[0], k[1]) == cell}
        new = {k[2]: v for k, v in green_after.items() if (k[0], k[1]) == cell}
        phenos = sorted(set(old) | set(new))
        print(f"  {cell[0]} {cell[1]}:  OLD_total={sum(old.values())}  NEW_total={sum(new.values())}")
        for p in phenos:
            print(f"      {p:14s} old={old.get(p,0):5d}  new={new.get(p,0):5d}")
    print()

    print("--- ADD cells: green phenotype counts (final) ---")
    for cell in [("1974", "PT-I"), ("1953", "PT-IV"), ("1961", "PT-III"),
                 ("1962", "PT-00"), ("1962", "PT-0")]:
        new = {k[2]: v for k, v in green_after.items() if (k[0], k[1]) == cell}
        print(f"  {cell[0]} {cell[1]}: total={sum(new.values())}")
        for p in sorted(new):
            print(f"      {p:14s} {new[p]:5d}")
    print()

    print("--- Maturity reconstruction (early offset sections) ---")
    for yt, rep in sorted(recon_report.items()):
        print(f"  {yt[0]} {yt[1]} (ref={REF_CHECK.get(yt)}): "
              f"reconstructed={rep['recon']}  dropped_no_anchor={rep['drop_noanchor']}  "
              f"dropped_outlier={rep['drop_outlier']}")
        if rep["drop_locs"]:
            for d in sorted(str(x) for x in rep["drop_locs"]):
                print(f"        DROP: {d}")
    if disagree:
        print("  anchor multi-test DOY disagreements (chosen = same-MG/UT priority):")
        for key, lst in disagree.items():
            for cloc, doys in lst:
                print(f"      {key} {cloc}: {doys}")
    print()

    # dup keys
    print(f"--- Duplicate keys on (Year,Test,Strain,City,State,Phenotype): {len(dup_keys)} ---")
    for k in dup_keys[:20]:
        print(f"      {k}")
    print()

    # stray strains / locations
    strays = [r for r in deduped
              if STRAY_RE.search(r["Strain"]) or STRAY_RE.search(r["City"])]
    print(f"--- Stray strains/locations (Mean/C.V./L.S.D./No. of/Reps): {len(strays)} ---")
    for r in strays[:20]:
        print(f"      {r['Year']} {r['Test']} strain='{r['Strain']}' city='{r['City']}'")
    print()

    # value range gate (all rows written)
    oob = []
    for r in deduped:
        gate = RANGE_GATE.get(r["Phenotype"])
        if not gate:
            continue
        try:
            v = float(r["Value_num"])
        except ValueError:
            continue
        lo, hi = gate
        if not (lo <= v <= hi):
            oob.append((r["Year"], r["Test"], r["Strain"], r["City"], r["State"],
                        r["Phenotype"], r["Value_num"]))
    print(f"--- Value-range gate violations (all recovery rows): {len(oob)} ---")
    for r in oob[:30]:
        print(f"      {r}")
    print()
    print("DONE. recovery_confirmed.csv written. NO corpus rebuild performed.")


if __name__ == "__main__":
    main()
