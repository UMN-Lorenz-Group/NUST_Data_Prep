"""
108_relabel_1959.py
===================
Authoritative fix for the 1959 TestMG label SCRAMBLE (see 107_label_integrity_audit.py).

The on-disk F4U `<NUST_Data>/.../1959_Processing/Files4Upload/phenotypesTable1.csv` carries
scrambled `Test` codes (UT-0 mislabeled UT-I, ... real PT-IV left unmapped as raw "Group_11"
and dropped by parse_test_code). This rewrites the `Test` column to the PDF-roster-verified
true codes. Values, locations, strains, DOY are untouched — labels only.

Safety:
  * The remap is DERIVED from PDF group rosters (coverage best-match) and then CROSS-CHECKED
    against the hand-verified EXPECTED map below. Any disagreement / non-bijective result
    ABORTS (no silent guessing).
  * Original is backed up to `phenotypesTable1.csv.orig_prelabel` (once).
  * Idempotent: if the file is already in true-label form (no scramble detected), no-op.

Read PDF rosters locally (pdfplumber, NO API). Run AFTER 107 (which confirmed 1959 is the
sole full-scramble year).
"""
import sys
import re
import shutil
from pathlib import Path
import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
NUST_DATA = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
HIST = NUST_DATA / "NUST_Historical_Data_1941_1988"
F4U = HIST / "1959_Processing" / "Files4Upload" / "phenotypesTable1.csv"
PDF = REPO / "input_files" / "input_1959" / "1959_done.pdf"
BACKUP = F4U.with_suffix(".csv.orig_prelabel")

# Hand-verified (PDF rosters + Jaccard, 107) F4U-code -> TRUE-code map for 1959.
EXPECTED = {
    "UT-00": "UT-00",     # correct already
    "PT-00": "PT-00",     # correct already
    "UT-I":  "UT-0",
    "UT-II": "UT-I",
    "UT-III": "PT-II",
    "UT-IV": "PT-III",
    "PT-II": "UT-II",
    "PT-III": "UT-III",
    "PT-IV": "UT-IV",
    "Group_11": "PT-IV",  # unmapped leftover = the real PT-IV (currently dropped)
}


def norm(s):
    s = re.sub(r"\s*\([^)]*\)", "", str(s))
    s = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return s.replace("O", "0").replace("L", "1").replace("I", "1")


def pdf_rosters():
    """{true_code: set(strain_norm)} from the 1959 Red PDF per-location tables."""
    cap = re.compile(
        r"(yield and yield rank|percentages? of protein|maturity[,.]? days) "
        r"for uniform (preliminary )?test,?\s*group\s+(0{1,2}|[ivx]+)", re.I)
    foot = {"MEAN", "C0EF", "BU", "R0W", "GRAND", "RANGE", "DAYS", "N0", "STRA1N",
            "YIE1D", "C0MP0S1TED", "TAB1E", "C0EFF1C1ENT"}
    out = {}
    with pdfplumber.open(PDF) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            m = cap.search(re.sub(r"\s+", " ", t).lower())
            if not m:
                continue
            key = f"{'PT' if m.group(2) else 'UT'}-{m.group(3).upper()}"
            if key in out:
                continue
            ss = set()
            for line in t.splitlines():
                tk = line.split()
                if len(tk) >= 3 and re.match(r"^[A-Za-z]", tk[0]) and re.match(r"^[+\-]?\d", tk[1]):
                    n = norm(tk[0])
                    if n and n not in foot and len(n) >= 3:
                        ss.add(n)
            if len(ss) >= 3:
                out[key] = ss
    return out


def derive_map(f4u_ros, true_ros):
    """For each F4U code, the true group covering the most of its roster (coverage =
    |F4U & true| / |F4U|). Returns {f4u_code: (true_code, coverage)}."""
    out = {}
    for c, fr in f4u_ros.items():
        if not fr:
            continue
        ranked = sorted(((len(fr & tr) / len(fr), tk) for tk, tr in true_ros.items()), reverse=True)
        out[c] = (ranked[0][1], round(ranked[0][0], 2)) if ranked else (None, 0.0)
    return out


def main():
    if not F4U.exists():
        sys.exit(f"ERROR: F4U not found: {F4U}")
    d = pd.read_csv(F4U, dtype=str, low_memory=False)
    tcol = next(c for c in d.columns if c.lower() == "test")
    scol = next(c for c in d.columns if c.lower() in ("strain", "germplasmid", "entry"))
    codes = sorted(d[tcol].dropna().unique())
    f4u_ros = {c: {norm(s) for s in d[d[tcol] == c][scol].dropna() if str(s).strip().lower() != "mean"}
               for c in codes}
    true_ros = pdf_rosters()
    print(f"F4U codes: {codes}")
    print(f"PDF true groups parsed: {sorted(true_ros)}")

    derived = derive_map(f4u_ros, true_ros)
    print("\nderived best-match (F4U -> true, coverage):")
    for c in codes:
        tk, cov = derived.get(c, (None, 0.0))
        print(f"  {c:9s} -> {tk}  ({cov})")

    # Idempotency: already-true if every code best-matches ITSELF.
    if all(derived.get(c, (c, 1))[0] == c for c in codes if c in derived):
        print("\nAlready in true-label form (no scramble) — no-op.")
        return

    # CROSS-CHECK derived vs EXPECTED for every code we have a roster for; coverage >= 0.6.
    problems = []
    for c in codes:
        exp = EXPECTED.get(c)
        if exp is None:
            problems.append(f"{c}: no EXPECTED entry")
            continue
        if c in derived:
            tk, cov = derived[c]
            if tk != exp:
                problems.append(f"{c}: derived {tk} != expected {exp}")
            elif cov < 0.6:
                problems.append(f"{c}: coverage {cov} < 0.6 for {exp}")
    # bijectivity of EXPECTED over the codes present
    targets = [EXPECTED[c] for c in codes if c in EXPECTED]
    if len(targets) != len(set(targets)):
        problems.append(f"EXPECTED not bijective over present codes: {targets}")
    if problems:
        print("\n".join(problems))
        sys.exit("ABORT: derived map disagrees with verified EXPECTED map — not writing.")

    print("\nderived == EXPECTED (verified). Applying relabel...")
    if not BACKUP.exists():
        shutil.copy2(F4U, BACKUP)
        print(f"  backup -> {BACKUP.name}")
    before = d[tcol].value_counts().to_dict()
    d[tcol] = d[tcol].map(lambda x: EXPECTED.get(x, x))
    d.to_csv(F4U, index=False)
    after = d[tcol].value_counts().to_dict()
    print(f"\nRewrote {F4U}")
    print("  Test code remap (old -> new : nrows):")
    for c in codes:
        print(f"    {c:9s} -> {EXPECTED[c]:7s} : {before.get(c, 0)} rows")
    print(f"\n  new Test codes: {sorted(after)}")


if __name__ == "__main__":
    main()
