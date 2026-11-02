"""
audit_ut_pt_current.py
======================
Re-derive the UT<->PT label state for a given year against the CURRENT corpus (the 2026-07-02
mislabel audit predates several rebuilds). For each Red-PDF section caption
"(UNIFORM|PRELIMINARY) TEST <MG>[A/B]", union its strain roster, then find the current-corpus
(Test) cell whose roster it most overlaps -- so we can see where each PDF section's data now
lives (or that it was DROPPED). Prints a PDF-section -> corpus-cell map with overlap + self
counts, plus the corpus cells that no PDF section maps to (candidate mislabels/drops).

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/audit_ut_pt_current.py 1985 [1977 1988 ...]
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pdfplumber

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SH = REPO / "analysis" / "data" / "_shared"
sys.path.insert(0, str(REPO / "data_prep" / "stage2_corpus"))
import importlib.util
_spec = importlib.util.spec_from_file_location("s114", REPO / "data_prep/stage2_corpus/114_extract_oil_perloc.py")
_m = importlib.util.module_from_spec(_spec); sys.modules["s114"] = _m; _spec.loader.exec_module(_m)

CAP = re.compile(r"\b(UNIFORM|PRELIMINARY)\s+TEST\b[,\s]*"
                 r"(0{1,2}|IV|III|II|I|V)\s*([AB])?\b", re.I)
NUMTOK = re.compile(r"^[+\-^(]?\d")


def norm_strain(s):
    s = re.sub(r"\([^)]*\)", "", str(s))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def sec_label(m):
    kind = "UT" if m.group(1).upper().startswith("U") else "PT"
    mg = m.group(2).upper()
    ab = (m.group(3) or "").upper()
    return f"{kind}-{mg}{ab}"


def pdf_rosters(year):
    path = _m._corrected_pdf(year)
    if not path:
        return {}
    rosters = defaultdict(set)
    cur = None
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            words = pg.extract_words(use_text_flow=False)
            rows = defaultdict(list)
            for w in words:
                rows[round(w["top"])].append(w)
            for top in sorted(rows):
                line = " ".join(x["text"] for x in sorted(rows[top], key=lambda w: w["x0"]))
                cm = CAP.search(line)
                if cm:
                    cur = sec_label(cm)
                    continue
                if cur is None:
                    continue
                # roster: leftmost token that is a name (starts alpha, x near left margin)
                left = [x for x in sorted(rows[top], key=lambda w: w["x0"]) if x["x0"] < 200]
                if not left:
                    continue
                tok = left[0]["text"].strip()
                if re.match(r"^[A-Za-z]", tok) and not NUMTOK.match(tok) and len(tok) >= 2:
                    # join a couple leading alpha tokens for multiword names
                    name = tok
                    if len(left) > 1 and re.match(r"^[A-Za-z]", left[1]["text"]) and left[1]["x0"] < 130:
                        name += left[1]["text"]
                    ns = norm_strain(name)
                    if len(ns) >= 2 and not re.match(r"^(mean|rank|tests?|strain|no|source|origin|"
                                                     r"table|group|uniform|preliminary|test|maturity|"
                                                     r"yield|oil|protein|seed|height|lodging|percentage|"
                                                     r"average|check)$", ns):
                        rosters[cur].add(ns)
    return {k: v for k, v in rosters.items() if len(v) >= 4}


def corpus_rosters(year):
    c = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
    c = c[(c.Year == str(year)) & (c.Phenotype == "YieldBuA")]
    out = defaultdict(set)
    for r in c.itertuples():
        out[str(r.Test)].add(norm_strain(r.Strain))
    return {k: {s for s in v if len(s) >= 2} for k, v in out.items()}


def main():
    years = [int(a) for a in sys.argv[1:]] or [1985]
    for year in years:
        print(f"\n{'='*70}\n{year}: PDF section -> current-corpus cell\n{'='*70}")
        pr = pdf_rosters(year)
        cr = corpus_rosters(year)
        used = set()
        for sec in sorted(pr):
            roster = pr[sec]
            best, bov = None, -1
            for cell, croster in cr.items():
                ov = len(roster & croster)
                if ov > bov:
                    best, bov = cell, ov
            self_ov = len(roster & cr.get(sec, set()))
            flag = "" if best == sec else f"  <== MISLABEL (self={self_ov})"
            if best == sec and self_ov >= max(4, len(roster) // 3):
                flag = "  OK"
            used.add(best)
            print(f"  PDF {sec:8s} ({len(roster):3d} strains) -> corpus {best:8s} ov={bov:3d}{flag}")
        missing = sorted(set(cr) - used)
        drops = sorted(s for s in pr if pr[s] and max((len(pr[s] & cr.get(c, set())) for c in cr), default=0) <= 6)
        print(f"  corpus cells no PDF section maps to: {missing}")
        print(f"  PDF sections that DROPPED (best overlap<=6): {drops}")


if __name__ == "__main__":
    main()
