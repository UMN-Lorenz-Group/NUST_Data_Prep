"""
107_label_integrity_audit.py
=============================
Reusable QC gate for TestMG LABEL integrity in the F4U-era source files (1941-1990).

Motivation: the 1959 corpus turned out to carry a whole-section "gap" (MG-0) that was
NOT a missing extraction but a SCRAMBLED set of Test labels in the upstream
`<year>_Processing/Files4Upload/phenotypesTable1.csv` (UT-0 mislabeled UT-I, ..., the
real PT-IV left unmapped as a raw "Group_11" and silently dropped by parse_test_code).
This gate detects that class of defect across every F4U-era year so we know whether 1959
is the only badly-scrambled year before fixing it.

Three independent signals (cheap → strong):
  (A) UNPARSEABLE Test codes  — any code not matching the canonical UT/PT-MG grammar
      (e.g. "Group_11"). A definitive sign of an unmapped/leaked group that gets dropped.
  (B) MISSING-INTERIOR-MG     — per (year, TestType), a Maturity-Group hole interior to
      that test's own 00..IV span (1959 UT missing "0"; 1977 UT missing "IV").
  (C) ROSTER-vs-PDF MISLABEL  — where the year's Red PDF exposes parseable per-group
      rosters, Jaccard-match each F4U Test's strain roster to the true PDF groups; flag
      any Test whose best match is a DIFFERENT group (the scramble, definitively).

Read-only. Output: analysis/data/analysis_results/Corpus_QC/label_integrity_report.csv
"""
import sys
import re
from collections import defaultdict
from pathlib import Path
import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
NUST_DATA = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
HIST = NUST_DATA / "NUST_Historical_Data_1941_1988"
INPUT = REPO / "input_files"
OUT = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC" / "label_integrity_report.csv"

# Same per-year F4U source map as 10_assemble_corpus.py (1941-1975 + 1980-1990 under HIST,
# 1976-1979 under NUST_DATA, plus 1990).
F4U_PATHS = {}
for y in list(range(1941, 1976)) + list(range(1980, 1989)) + [1990]:
    F4U_PATHS[y] = HIST / f"{y}_Processing" / "Files4Upload" / "phenotypesTable1.csv"
for y in range(1976, 1980):
    F4U_PATHS[y] = NUST_DATA / f"{y}_Processing" / "Files4Upload" / "phenotypesTable1.csv"

MG_ORDER = ["00", "0", "I", "II", "III", "IV", "V"]
# canonical Test grammar: UT/PT/UPT + MG (digits-as-0s or Roman) + optional A/B variant
CANON_RE = re.compile(r"^(UT|PT|UPT)-(0{1,2}|I{1,3}V?|IV|V|VI?)[AB]?$", re.IGNORECASE)
ROSTER_FOOT = {"MEAN", "C0EF", "BU", "R0W", "GRAND", "RANGE", "DAYS", "N0", "STRA1N",
               "YIE1D", "C0MP0S1TED", "TAB1E", "C0EFF1C1ENT"}


def norm(s):
    """OCR-tolerant strain key for roster comparison."""
    s = re.sub(r"\s*\([^)]*\)", "", str(s))
    s = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return s.replace("O", "0").replace("L", "1").replace("I", "1")


def mg_of(code):
    m = CANON_RE.match(str(code))
    return m.group(2).upper() if m else None


def tt_of(code):
    m = CANON_RE.match(str(code))
    return m.group(1).upper() if m else None


# --------------------------------------------------------------------------- PDF rosters
def pdf_rosters(year):
    """Best-effort per-group strain rosters from the year's Red PDF. Returns {code: set}.
    Handles the 1950s-60s per-location table captions ('yield and yield rank ... group X',
    'percentages of protein ... group X') and the title-page roster. Empty if unparseable."""
    p = INPUT / f"input_{year}" / f"{year}_done.pdf"
    if not p.exists():
        return {}
    cap = re.compile(
        r"(yield and yield rank|percentages? of protein|maturity[,.]? days) "
        r"for uniform (preliminary )?test,?\s*group\s+(0{1,2}|[ivx]+)", re.I)
    out = {}
    try:
        with pdfplumber.open(p) as pdf:
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
                        if n and n not in ROSTER_FOOT and len(n) >= 3:
                            ss.add(n)
                if len(ss) >= 3:
                    out[key] = ss
    except Exception as e:                                   # noqa: BLE001 — best-effort gate
        print(f"  {year}: PDF parse error ({e})")
    return out


def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


# --------------------------------------------------------------------------- main
def main():
    rows = []
    for year in sorted(F4U_PATHS):
        path = F4U_PATHS[year]
        if not path.exists():
            rows.append({"Year": year, "signal": "no_f4u", "detail": str(path)})
            continue
        d = pd.read_csv(path, dtype=str, low_memory=False)
        tcol = next(c for c in d.columns if c.lower() == "test")
        scol = next(c for c in d.columns if c.lower() in ("strain", "germplasmid", "entry"))
        codes = sorted(d[tcol].dropna().unique())
        f4u_ros = {c: {norm(s) for s in d[d[tcol] == c][scol].dropna() if str(s).strip().lower() != "mean"}
                   for c in codes}

        # (A) unparseable codes
        bad = [c for c in codes if not CANON_RE.match(c)]
        for c in bad:
            rows.append({"Year": year, "signal": "unparseable_code", "test": c,
                         "n_strains": len(f4u_ros[c]), "detail": "dropped by parse_test_code"})

        # (B) missing-interior MG per TestType
        for tt in ("UT", "PT"):
            present = [mg_of(c) for c in codes if tt_of(c) == tt]
            present = [m for m in present if m]
            idx = [MG_ORDER.index(m) for m in present if m in MG_ORDER]
            if len(idx) >= 2:
                holes = [MG_ORDER[i] for i in range(min(idx), max(idx) + 1) if MG_ORDER[i] not in present]
                for h in holes:
                    rows.append({"Year": year, "signal": "missing_interior_mg", "test": f"{tt}-{h}",
                                 "detail": f"{tt} present={present}"})

        # (C) roster-vs-PDF mislabel
        pr = pdf_rosters(year)
        if not pr:
            rows.append({"Year": year, "signal": "no_pdf_roster", "detail": "PDF captions unparsed"})
        else:
            for c in codes:
                fr = f4u_ros[c]
                if not fr:
                    continue
                ranked = sorted(((jaccard(fr, ps), pk) for pk, ps in pr.items()), reverse=True)
                bestj, bestk = ranked[0]
                if bestj < 0.5:
                    continue                                  # weak / no PDF counterpart -> skip (not a confident claim)
                if bestk != c:
                    rows.append({"Year": year, "signal": "MISLABEL", "test": c,
                                 "true_group": bestk, "jaccard": round(bestj, 2),
                                 "n_strains": len(fr)})

    rep = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rep.to_csv(OUT, index=False)

    print(f"\n=== label-integrity report -> {OUT.name} ({len(rep)} findings) ===")
    for sig in ["MISLABEL", "unparseable_code", "missing_interior_mg", "no_pdf_roster", "no_f4u"]:
        sub = rep[rep["signal"] == sig] if len(rep) else rep
        n = len(sub)
        tag = {"MISLABEL": "  <-- SCRAMBLE", "unparseable_code": "  <-- dropped group"}.get(sig, "")
        print(f"\n[{sig}] {n}{tag}")
        if sig in ("MISLABEL", "unparseable_code") and n:
            cols = [c for c in ("Year", "test", "true_group", "jaccard", "n_strains", "detail") if c in sub.columns]
            print(sub[cols].to_string(index=False))
        elif sig == "missing_interior_mg" and n:
            print(sub.groupby("Year")["test"].apply(lambda s: ",".join(s)).to_string())
        elif sig == "no_pdf_roster" and n:
            print("  years:", ",".join(str(y) for y in sorted(sub["Year"])))

    scrambled_years = sorted(set(rep[rep["signal"] == "MISLABEL"]["Year"])) if len(rep) else []
    print(f"\nFULL-SCRAMBLE years (roster-confirmed mislabels): {scrambled_years or 'none'}")


if __name__ == "__main__":
    main()
