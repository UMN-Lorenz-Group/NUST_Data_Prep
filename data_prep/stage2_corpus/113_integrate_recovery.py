"""
113_integrate_recovery.py
========================
⚠️ HISTORICAL — DO NOT RE-RUN (2026-07-16). This is the 2026-06-30 gap-campaign build of
`recovery_confirmed.csv`. Since then that file has ACCRETED later fixes (Phase-E folds + the 2026-07-16
GREEN-DIRECT integration via `integrate_greendirect_recovery.py`, which REPLACED the 1985 UT-III /
1977 UT-III / 1977 UT-IV sections with cleaner Green extractions and ADDED 1953/61/62/74 + 1983). Re-running
113 would OVERWRITE `recovery_confirmed.csv` with the stale PDF-recovered versions and silently undo all of
that. The superseded PDF-recovery source CSVs now live in `_archive_superseded_2026-07/`.
`recovery_confirmed.csv` is now a curated artefact (backup `.bak_pre_greendirect`); 10_assemble reads it
directly. Kept only for provenance. See [[project_nust_testmap_deriver_tp2repair]].

Final recovery integration for the gap campaign (deadline build, 2026-06-30):
  (1) 1984 UT-II   -> from the proven Green extractor (109), 6 trait tables.
  (2) 1977 UT-00..III CORRECTIONS -> the proven Green is correct where the corpus disagrees
      (the no-Mean second-page off-by-one + scattered errors); emit Green value as an OVERRIDE.
  (3) 1977 UT-IV, 1972 UT-III RECOVERY -> PDF-only (absent from Green); from the PDF parser
      (112), sanity-filtered (per-trait value ranges, footer-strain drop) and validated against
      the PDF Regional Summary strain-yield-mean.

Outputs:
  recovery_confirmed.csv  : new per-location rows (1984 UT-II Green + 1977 UT-IV/1972 UT-III PDF)
  recovery_overrides.csv  : (Year,Test,City,State,Strain,Phenotype,Value_num) corrections that
                            REPLACE existing corpus values (1977 UT-00..III, Green-correct).
Both consumed by the Phase-6 loader in 10_assemble_corpus.py.
"""
import sys
import re
import importlib
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
G = importlib.import_module("109_extract_green_section")
P = importlib.import_module("112_extract_pdf_perloc")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
CORPUS = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
OUT_CONF = REPO / "data_prep" / "stage2_corpus" / "recovery_confirmed.csv"
OUT_OVR = REPO / "data_prep" / "stage2_corpus" / "recovery_overrides.csv"

RANGE = {"YieldBuA": (5, 90), "Maturity": (200, 330), "Height": (12, 56), "Lodging": (1, 5.2),
         "Protein": (30, 50), "Oil": (13, 27), "SeedSize": (8, 30), "SeedQuality": (1, 5.2)}
TOL = {"YieldBuA": 0.05, "Maturity": 1, "Height": 0.5, "Lodging": 0.1, "Protein": 0.1,
       "Oil": 0.1, "SeedSize": 0.1, "SeedQuality": 0.1}
FOOTER = re.compile(r"^(C\.?V|L\.?S\.?D|Row|Rep|Coef|Mean|Grand|Range|Bu|No\.|Days|us|sp|"
                    r"C\.$|Reps|CV|LSD|Strain)", re.I)


def ks(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def sanity(df):
    """drop footer strains + out-of-range values."""
    df = df[~df["Strain"].astype(str).str.match(FOOTER)].copy()
    keep = df.apply(lambda r: RANGE[r.Phenotype][0] <= r.Value_num <= RANGE[r.Phenotype][1]
                    if r.Phenotype in RANGE and pd.notna(r.Value_num) else False, axis=1)
    return df[keep].copy()


def rs_yield_means(year, code):
    """{strain_norm: yield-mean} from the PDF Regional Summary (for a coarse validation)."""
    import pdfplumber
    mg = re.sub(r"^(UT|PT)-", "", code)
    want = re.compile(rf"uniform test\s+{re.escape(mg)}\b", re.I)
    out = {}
    with pdfplumber.open(REPO / "input_files" / f"input_{year}" / f"{year}_done.pdf") as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            tl = re.sub(r"\s+", " ", t).lower()
            if "regional summary" not in tl or not want.search(tl):
                continue
            for line in t.splitlines():
                toks = line.split()
                if len(toks) >= 3 and re.match(r"^[A-Za-z]", toks[0]):
                    si = 0
                    while si < len(toks) and not re.match(r"^\d{1,2}\.\d$", toks[si]):
                        si += 1
                    if 1 <= si <= 4 and si < len(toks):
                        nm = G.norm("".join(toks[:si]))
                        if len(nm) >= 3:
                            out.setdefault(nm, float(toks[si]))
            if out:
                break
    return out


def pdf_recover(year, code):
    """sanity-filtered PDF section, dropping strains whose per-loc yield-mean is far from the
    Regional Summary (coarse fold-vs-hold gate)."""
    df = sanity(P.extract_pdf_section(year, code))
    if not len(df):
        return df
    rs = rs_yield_means(year, code)
    if rs:
        gm = df[df.Phenotype == "YieldBuA"].groupby("Strain").Value_num.mean()
        ok = {s for s in gm.index if G.norm(s) not in rs or abs(gm[s] - rs[G.norm(s)]) <= 4}
        df = df[df.Strain.isin(ok)].copy()
    return df


def main():
    corpus = pd.read_csv(CORPUS, low_memory=False)
    conf, ovr = [], []

    # (1) 1984 UT-II from Green (proven) — the 6 trait tables the F4U skipped (yield+maturity were
    # already in the F4U, so exclude them). Emitted explicitly (independent of the corpus state).
    g84 = G.extract_section(1984, "UT-II", G._roster_from_f4u_or_pdf(1984, "UT-II"))
    conf.append(g84[~g84.Phenotype.isin(["YieldBuA", "Maturity", "YieldRank"])])
    print(f"1984 UT-II Green: {len(conf[-1])} rows")

    # (2) 1977 UT-00..III Green corrections — emit the full Green rows for cells where the corpus
    # disagrees (the proven Green is correct: no-Mean 2nd-page off-by-one + scattered errors). These
    # become recovery rows that SUPERSEDE the (wrong-valued) F4U cell.
    for code in ["UT-00", "UT-0", "UT-I", "UT-II", "UT-III"]:
        gd = G.extract_section(1977, code, G._roster_from_f4u_or_pdf(1977, code)).copy()
        cd = corpus[(corpus.Year == 1977) & (corpus.Test == code) & corpus.Value_num.notna()].copy()
        gd["k"] = gd.Strain.map(ks) + "|" + gd.City.map(ks) + "|" + gd.Phenotype
        cd["k"] = cd.Strain.map(ks) + "|" + cd.City.map(ks) + "|" + cd.Phenotype
        cmap = dict(zip(cd["k"], cd["Value_num"]))
        keep = gd[gd.apply(lambda r: r["k"] in cmap
                           and abs(r.Value_num - cmap[r["k"]]) > TOL.get(r.Phenotype, 0.1), axis=1)]
        conf.append(keep.drop(columns=["k"]))
        ovr.append(len(keep))
        print(f"1977 {code}: {len(keep)} Green corrections")

    # (3) PDF-only recoveries
    for year, code in [(1977, "UT-IV"), (1972, "UT-III")]:
        pr = pdf_recover(year, code)
        conf.append(pr)
        print(f"{year} {code} PDF: {len(pr)} rows ({sorted(pr.Phenotype.unique()) if len(pr) else []})")

    confdf = pd.concat([c for c in conf if len(c)], ignore_index=True)
    confdf["Source"] = "Recovered_1970_1988"
    confdf = confdf[["Year", "TestType", "TestMG", "Test", "Strain", "City", "State",
                     "Phenotype", "Value_num", "Units", "Source"]]
    confdf.to_csv(OUT_CONF, index=False)
    print(f"\nrecovery_confirmed.csv: {len(confdf)} rows  {confdf.groupby(['Year','Test']).size().to_dict()}")
    print(f"  (incl. {sum(ovr)} 1977 UT-00..III corrections that supersede wrong F4U cells)")


if __name__ == "__main__":
    main()
