"""Fold the HAND-AUDIT consensus corrections (hand_audit_worklist_v2.csv) into the corpus.

The 96-cell worklist is the user+Claude adjudication (2026-07-14) of the last extraction-accuracy OCR
errors; `consensus_checked` holds the resolved TRUE value (NOT `pdf_value`, which is often itself a
misread). This script translates the ACTIONABLE cells into the two existing correction vehicles:

  * VALUE corrections  -> append to qc_pdf_patches.csv  (10_assemble load_qc_pdf_patches supersedes the
    F4U cell on (Year,Test,City,State,Strain,Phenotype), raw + normalized key).
  * agree_NULL         -> append to qc_pdf_patches.csv with Value_num = NaN (supersede drops the F4U
    valued cell; the NaN patch nulls it). VERIFIED blank column: 1966 Table 63 p92 lodging rows carry
    one fewer value than location columns (Columbus column blank -> left-shift), both reviewers agree_NULL.

Classification is COMPUTED from the data (not hardcoded), so it is deterministic:
  - consensus_checked parses to a number that DIFFERS from the CURRENT corpus value  -> value patch
    (auto-skips no-change rows AND cells already fixed at source, e.g. 1988 UT-00 r95/r96 = recovery).
  - consensus_status == agree_NULL (consensus blank)                                 -> NULL patch
  - consensus_checked is a token (NEEDS_MANUAL/UNRESOLVED/DISPUTE) or status resolved_PT-III(no-change)
    or numeric==corpus                                                              -> no patch
  - NEEDS_MANUAL / UNRESOLVED / DISPUTE                                              -> open item (logged)

NOT handled here (flagged as open items): the 1986 UT-III backcross-name SCRAMBLE (corpus has ~13
scrambled designations AHarperBC/BCHarperA/HarperBCA/BCHCSprite/... — needs the 1986 PDF roster to fix
correctly, beyond what v2 adjudicates). BC-subscripts are ALREADY normalized in the corpus (verified:
'Williams BC6'/'Woodworth BC5'/'Beeson 80 BC6') -> no action.

Oil basis: the LONG corpus stores DRY oil (×0.87 -> 13%mb applied later in 11_build_wide), and the
worklist's corpus_value is read from the LONG corpus, so consensus (dry PDF value) is directly comparable
and the patch stores it as-is.

`--apply` backs up qc_pdf_patches.csv -> `.bak_pre_handaudit` and writes. Idempotent (patches keyed by
(Year,Test,City,State,Strain,Phenotype,note='hand_audit_v2') are de-duplicated on re-run).
"""
import sys
import re
import shutil
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
WL = REPO / "analysis/data/analysis_results/Extraction_Accuracy/hand_audit_worklist_v2.csv"
QC = REPO / "data_prep/stage2_corpus/qc_pdf_patches.csv"
CORPUS = REPO / "analysis/data/_shared/nust_1941_2025_combined.csv"
OPEN = REPO / "analysis/data/analysis_results/Extraction_Accuracy/hand_audit_open_items.csv"
TOL = 0.05
UNITS = {"YieldBuA": "bu/a", "Height": "in", "Lodging": "score", "SeedQuality": "score",
         "SeedSize": "g/100", "Protein": "%", "Oil": "%", "Maturity": "DOY"}


def lead_num(x):
    """Leading float of consensus_checked ('5 (LOW)'->5, '264'->264); None if not numeric."""
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(x))
    return float(m.group(1)) if m else None


def nmk(s):   # normalized strain key (mirrors 10_assemble _nmk): drop (), non-alnum, lower
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())


def nck(s):   # normalized city key
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def ntk(t):   # normalized test (UT-O==UT-0)
    return re.sub(r"[^a-z0-9]", "", str(t).lower()).replace("o", "0")


def main():
    apply = "--apply" in sys.argv
    wl = pd.read_csv(WL)
    c = pd.read_csv(CORPUS, low_memory=False)
    # index the corpus by NORMALIZED key -> the exact (Strain,City,State,Value_num) it holds, so a
    # worklist cell in PDF form ('(III) Harper','Beeson 80 BC6','Corsoy 79 (II)') resolves to the
    # canonical corpus row and the patch supersedes EXACTLY (no phantom rows).
    def nsk(s):  # normalized state (disambiguates Columbus OH vs Columbus KS)
        return re.sub(r"[^a-z0-9]", "", str(s).lower())
    c["corpkey"] = list(zip(c.Year, c.Test.map(ntk), c.Strain.map(nmk), c.City.map(nck),
                       c.State.map(nsk), c.Phenotype.astype(str)))
    idx = {}
    for row in c.itertuples():
        idx.setdefault(row.corpkey, []).append(row)

    def resolve(r):
        """Exact corpus identity + the SET of current values (rounded) for this cell — NOT a mean, so
        duplicate rows (e.g. 1969) don't fabricate a phantom value."""
        k = (int(r.Year), ntk(r.Test), nmk(r.Strain), nck(r.City), nsk(r.State), str(r.Phenotype))
        rows = idx.get(k, [])
        if not rows:
            return None
        vals = {round(x.Value_num, 2) for x in rows if pd.notna(x.Value_num)}
        return dict(Strain=str(rows[0].Strain), City=str(rows[0].City), State=str(rows[0].State),
                    vals=vals)

    # Years GREEN-DIRECT re-extracted this session -> that fresh systematic read is AUTHORITATIVE and
    # more recent than the hand-audit (which was adjudicated vs the OLD corpus); do NOT overwrite it.
    RE_EXTRACTED = {1953, 1961, 1962, 1974, 1977, 1983, 1984, 1985}

    value_rows, null_rows, open_rows, noaction = [], [], [], 0
    for r in wl.itertuples():
        status = str(r.consensus_status)
        cc = lead_num(r.consensus_checked)          # the adjudicated TRUE value (the target)
        hit = resolve(r)
        base = dict(Year=int(r.Year), Test=str(r.Test),
                    City=(hit["City"] if hit else str(r.City)),
                    State=(hit["State"] if hit else str(r.State)),
                    Strain=(hit["Strain"] if hit else str(r.Strain)), Phenotype=str(r.Phenotype))
        curvals = hit["vals"] if hit else set()

        if status == "agree_NULL":
            if hit is None or not curvals:
                noaction += 1; continue            # nothing valued in corpus -> already NULL
            null_rows.append({**base, "Value_num": np.nan, "Units": UNITS.get(str(r.Phenotype), ""),
                              "old_value": sorted(curvals), "Source": "QC_PDF_patch", "note": "hand_audit_v2_NULL"})
            continue
        if cc is None:                              # NEEDS_MANUAL / UNRESOLVED / DISPUTE
            open_rows.append({**base, "consensus_status": status, "consensus_checked": str(r.consensus_checked),
                              "corpus_now": sorted(curvals), "reason": "needs_manual/unresolved/dispute"})
            continue
        # numeric consensus = the target the corpus SHOULD hold.
        if hit is None:
            open_rows.append({**base, "consensus_status": status, "consensus_checked": str(cc),
                              "corpus_now": None, "reason": "cell_not_in_corpus(name/loc variant)"})
        elif any(abs(cc - v) <= TOL for v in curvals):
            noaction += 1                            # corpus ALREADY == consensus
        elif int(r.Year) in RE_EXTRACTED:
            open_rows.append({**base, "consensus_status": status, "consensus_checked": str(cc),
                              "corpus_now": sorted(curvals), "reason": "superseded_by_green_direct(re-extracted year)"})
        else:
            value_rows.append({**base, "Value_num": cc, "Units": UNITS.get(str(r.Phenotype), ""),
                               "old_value": sorted(curvals), "Source": "QC_PDF_patch", "note": "hand_audit_v2"})

    print(f"worklist {len(wl)} cells -> VALUE {len(value_rows)} | NULL {len(null_rows)} | "
          f"no-action {noaction} | OPEN(unapplyable) {len(open_rows)}")
    print("\nVALUE corrections (Year Test Strain City Ph : old -> new):")
    for v in value_rows:
        print(f"  {v['Year']} {v['Test']:7s} {v['Strain']:16s} {v['City']:13s} {v['Phenotype']:11s}"
              f": {v['old_value']} -> {v['Value_num']}")
    print("\nNULL sets:")
    for v in null_rows:
        print(f"  {v['Year']} {v['Test']} {v['Strain']} {v['City']} {v['Phenotype']}: {v['old_value']} -> NaN")

    if apply:
        qc = pd.read_csv(QC, low_memory=False)
        bak = QC.with_suffix(".csv.bak_pre_handaudit")
        if not bak.exists():
            shutil.copy2(QC, bak); print(f"\nbacked up -> {bak.name}")
        if not (value_rows + null_rows):
            print("  nothing to apply (corpus already == consensus for all actionable cells).")
            pd.DataFrame(open_rows).to_csv(OPEN, index=False)
            return
        add = pd.DataFrame(value_rows + null_rows)[list(qc.columns)]
        # de-dup: drop any prior hand_audit_v2* rows for the same cell, then append
        prior = qc["note"].astype(str).str.startswith("hand_audit_v2")
        qc = qc[~prior]
        out = pd.concat([qc, add], ignore_index=True)
        out.to_csv(QC, index=False)
        print(f"wrote {QC.name}: {len(qc)} + {len(add)} = {len(out)} rows")
        pd.DataFrame(open_rows).to_csv(OPEN, index=False)
        print(f"wrote {OPEN.name}: {len(open_rows)} unapplyable open items")
    else:
        print("\n(dry run; --apply to write qc_pdf_patches.csv + open-items)")


if __name__ == "__main__":
    main()
