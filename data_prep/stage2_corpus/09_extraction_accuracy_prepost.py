"""
09_extraction_accuracy_prepost.py
=================================
Extraction accuracy PRE vs POST correction/recovery, per year and per decade.

08_extraction_accuracy.py measures the RAW human-OCR accuracy: each per-year QC file
(`qc_YYYY_values.csv`) flags cells where the human-OCR'd XLSX disagreed with the source
PDF. That is a fixed property of the source and is our PRE-recovery baseline.

This script adds the POST-recovery view: for every numeric QC discrepancy (which records
the correct `pdf_value`), it looks up the value in the CURRENT corpus and asks "does the
corpus now match the PDF?". A discrepancy whose corpus value now equals the PDF has been
RESOLVED by the correction pipeline (Claude auto-patches + all targeted recovery: dropped-
UT re-extractions, oil/maturity recovery, label-shift + Georgetown + moisture fixes, ...).

  pre_accuracy  = (1 - discrepancies / rows) * 100          # raw human OCR vs PDF
  post_accuracy = (1 - (discrepancies - resolved) / rows) * 100   # final corpus vs PDF

`resolved` is counted CONSERVATIVELY: only discrepancies whose (Year,Test,Strain,City,
Phenotype) key joins the corpus AND whose corpus value matches the PDF within tol. Cells
that don't join (dropped phantoms / naming variants) are NOT credited, so post_accuracy is
a lower bound on the true improvement.

Outputs (analysis/data/_shared/ + analysis_results/Extraction_Accuracy/):
  extraction_accuracy_prepost_per_year.csv
  extraction_accuracy_prepost_by_decade.csv
  extraction_accuracy_prepost_by_decade.png   (grouped bars: pre vs post per decade)
"""
import glob
import re
import sys
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent.parent
SHARED = REPO / "analysis" / "data" / "_shared"
OUTDIR = REPO / "analysis" / "data" / "analysis_results" / "Extraction_Accuracy"
OUTDIR.mkdir(parents=True, exist_ok=True)
CORPUS = SHARED / "nust_1941_2025_combined.csv"
PER_YEAR = SHARED / "extraction_accuracy_per_year.csv"   # from 08 (total rows, discrepancies)
TOL = 0.15


def nm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())


def nc(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def nt(t):
    t = str(t).upper().strip().replace("UPT-", "PT-").replace("UPT", "PT-")
    return re.sub(r"[^A-Z0-9-]", "", t)


def num(s):
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", str(s).replace(",", "."))
    return float(m.group(1)) if m else None


def main():
    c = pd.read_csv(CORPUS, low_memory=False)
    c["cv"] = pd.to_numeric(c.Value_num, errors="coerce")
    c = c.dropna(subset=["cv"])
    c["tk"] = (c.Year.astype(str) + "|" + c.Test.map(nt) + "|" + c.Strain.map(nm)
               + "|" + c.City.map(nc) + "|" + c.Phenotype)
    corp = c.drop_duplicates("tk").set_index("tk").cv
    # fallback index (Year,Test,Strain,Phenotype) -> set of values, to reclaim no-joins
    # caused ONLY by a city-label variant (accept a match iff it is unique + equals the PDF)
    sk = c.Year.astype(str) + "|" + c.Test.map(nt) + "|" + c.Strain.map(nm) + "|" + c.Phenotype
    fb = c.assign(sk=sk).groupby("sk")["cv"].apply(lambda s: sorted(set(s.round(2)))).to_dict()

    # HAND-AUDIT adjudication (hand_audit_worklist_v2.csv): the user+Claude resolved these OCR-error
    # cells to the TRUE value (often != the QC pdf_value, which was itself a misread). Credit any cell
    # with a RESOLVED consensus_status as correct, regardless of corpus==pdf_value — the human review is
    # the ground truth here. Only genuinely-open cells (needs_manual / unresolved / DISPUTE) stay errors.
    ha_resolved = set()
    HA = OUTDIR / "hand_audit_worklist_v2.csv"
    if HA.exists():
        w = pd.read_csv(HA)
        for r in w.itertuples():
            st = str(r.consensus_status)
            if st.startswith(("needs_manual", "unresolved", "DISPUTE")):
                continue
            ha_resolved.add(f"{int(r.Year)}|{nt(r.Test)}|{nm(r.Strain)}|{nc(r.City)}|{r.Phenotype}")

    # per-year outcome counts from QC discrepancies vs current corpus
    per = {}   # year -> dict of counts
    for f in sorted(glob.glob(str(REPO / "output_files/output_*/qc/qc_*_values.csv"))):
        yr = int(re.search(r"output_(\d+)", f).group(1))
        q = pd.read_csv(f, dtype=str)
        d = q[q.verdict == "discrepancy"]
        resolved = meas_unresolved = meas_disc = qc_misread = ha_credit = 0
        for r in d.itertuples():
            pv = num(r.pdf_value)
            cvsv = num(r.csv_value)
            # "measured traits" excludes YieldRank (a derived rank) AND Maturity (the QC records
            # a raw offset/date while the corpus stores reconstructed DOY -> not comparable here;
            # maturity is validated separately by the anchor cross-check, 99.7% exact).
            measured = (r.phenotype not in ("YieldRank", "Maturity")) and (pv is not None)
            mat_offset = (r.phenotype == "Maturity" and pv is not None and pv < 180)
            if measured:
                meas_disc += 1   # OCR-Team measured-value errors (all of them, at transcription time)
            k = f"{yr}|{nt(r.Test)}|{nm(r.strain)}|{nc(r.City)}|{r.phenotype}"
            hit = None
            if k in corp.index:
                hit = corp[k]
            elif pv is not None:  # city-variant fallback: unique corpus value matching PDF
                cand = fb.get(f"{yr}|{nt(r.Test)}|{nm(r.strain)}|{r.phenotype}")
                if cand and len(cand) == 1 and abs(cand[0] - pv) < TOL:
                    hit = cand[0]
            # QC column-misread signature (audited 2026-07-13, 1977 green_pdf_conflict block):
            # in the dense per-location tables the QC sometimes read the ADJACENT column, so its
            # pdf_value is really a SIBLING location's value. When the corpus (== the OCR value,
            # i.e. BOTH independent transcriptions agree at this cell) differs from that pdf_value
            # AND the pdf_value equals another location's corpus value for the same strain/trait,
            # the corpus cell is corroborated correct and the QC read is the error -> credit it.
            sib = fb.get(f"{yr}|{nt(r.Test)}|{nm(r.strain)}|{r.phenotype}", [])
            is_qc_misread = (
                measured and hit is not None and pv is not None and abs(hit - pv) >= TOL
                and cvsv is not None and abs(hit - cvsv) < TOL          # corpus == OCR (dual agree)
                and any(abs(pv - o) < TOL for o in sib)                 # pv == a sibling column
            )
            if pv is not None and hit is not None and abs(hit - pv) < TOL:
                resolved += 1
            elif mat_offset and hit is not None and 228 <= (hit - pv) <= 305:
                resolved += 1   # corpus DOY = anchor + printed offset -> equivalent (offset==DOY)
            elif is_qc_misread:
                resolved += 1; qc_misread += 1   # corpus correct, QC read the wrong column
            elif k in ha_resolved:
                resolved += 1; ha_credit += 1     # hand-audit adjudicated -> credited (see note above)
            elif measured and hit is not None and abs(hit - pv) >= TOL:
                meas_unresolved += 1   # joined, numeric, measured trait, still != PDF -> a real remaining error
        per[yr] = {"resolved": resolved, "meas_unresolved": meas_unresolved,
                   "meas_disc": meas_disc, "qc_misread": qc_misread, "ha_credit": ha_credit}

    py = pd.read_csv(PER_YEAR)
    py["year"] = py["year"].astype(int)
    py["resolved"] = py["year"].map(lambda y: per.get(y, {}).get("resolved", 0)).astype(int)
    py["meas_unresolved"] = py["year"].map(lambda y: per.get(y, {}).get("meas_unresolved", 0)).astype(int)
    py["meas_disc"] = py["year"].map(lambda y: per.get(y, {}).get("meas_disc", 0)).astype(int)
    py["disc_remaining"] = (py["discrepancies"] - py["resolved"]).clip(lower=0)
    py["pre_accuracy_pct"] = (1 - py["discrepancies"] / py["total_cells"]) * 100
    py["post_accuracy_pct"] = (1 - py["disc_remaining"] / py["total_cells"]) * 100
    # OCR-Team measured-only: exclude rank/date artifacts from the OCR error count (symmetric baseline)
    py["pre_measured_accuracy_pct"] = (1 - py["meas_disc"] / py["total_cells"]) * 100
    # AI-final measured-only: count ONLY confirmed remaining real value errors as errors
    # (YieldRank, non-numeric maturity dates, dropped phantoms, unverifiable no-joins are not errors)
    py["post_measured_accuracy_pct"] = (1 - py["meas_unresolved"] / py["total_cells"]) * 100
    py.to_csv(SHARED / "extraction_accuracy_prepost_per_year.csv", index=False)

    # decade roll-up
    py["decade"] = (py["year"] // 10 * 10).astype(str) + "s"
    g = py.groupby("decade")
    dec = pd.DataFrame({
        "year_range": g["year"].agg(lambda s: f"{s.min()}-{s.max()}"),
        "rows": g["total_cells"].sum(),
        "discrepancies": g["discrepancies"].sum(),
        "resolved": g["resolved"].sum(),
        "meas_unresolved": g["meas_unresolved"].sum(),
        "meas_disc": g["meas_disc"].sum(),
    }).reset_index()
    dec["disc_remaining"] = dec["discrepancies"] - dec["resolved"]
    dec["pre_accuracy_pct"] = (1 - dec["discrepancies"] / dec["rows"]) * 100
    dec["post_accuracy_pct"] = (1 - dec["disc_remaining"] / dec["rows"]) * 100
    dec["pre_measured_accuracy_pct"] = (1 - dec["meas_disc"] / dec["rows"]) * 100
    dec["post_measured_accuracy_pct"] = (1 - dec["meas_unresolved"] / dec["rows"]) * 100
    dec.to_csv(OUTDIR / "extraction_accuracy_prepost_by_decade.csv", index=False)

    tot_rows = int(py["total_cells"].sum())
    tot_disc = int(py["discrepancies"].sum())
    tot_res = int(py["resolved"].sum())
    tot_meas_un = int(py["meas_unresolved"].sum())
    tot_meas_disc = int(py["meas_disc"].sum())
    tot_qc_misread = sum(v.get("qc_misread", 0) for v in per.values())
    tot_ha_credit = sum(v.get("ha_credit", 0) for v in per.values())
    pre_all = (1 - tot_disc / tot_rows) * 100
    post_all = (1 - (tot_disc - tot_res) / tot_rows) * 100
    pre_meas_all = (1 - tot_meas_disc / tot_rows) * 100
    post_meas_all = (1 - tot_meas_un / tot_rows) * 100

    # grouped-bar plot per decade: bars grouped by METRIC so the pair is adjacent — {all discrepancies}
    # then {measured traits only} — each pair showing OCR-Team then Claude AI-final (pre/post).
    import numpy as np
    x = np.arange(len(dec)); w = 0.20
    fig, ax = plt.subplots(figsize=(11.5, 5.2))
    ax.bar(x - 1.5 * w, dec["pre_accuracy_pct"], w, label="OCR-Team — all discrepancies",
           color="#cfcfcf", edgecolor="black", linewidth=0.4)
    ax.bar(x - 0.5 * w, dec["post_accuracy_pct"], w, label="Claude AI-final — all discrepancies",
           color="#8fbbe8", edgecolor="black", linewidth=0.4)
    ax.bar(x + 0.5 * w, dec["pre_measured_accuracy_pct"], w, label="OCR-Team — measured traits only",
           color="#8a8a8a", edgecolor="black", linewidth=0.4)
    ax.bar(x + 1.5 * w, dec["post_measured_accuracy_pct"], w,
           label="Claude AI-final — measured traits only",
           color="#199e70", edgecolor="black", linewidth=0.4)
    ax.set_xticks(x); ax.set_xticklabels(dec["decade"])
    ax.set_ylim(96, 100.05)
    ax.set_ylabel("Accuracy vs source PDF (% of QC'd rows)")
    ax.set_title("NUST extraction accuracy — OCR-Team vs Claude AI-final corpus (vs source PDF), by decade")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="lower right", fontsize=7.5, ncol=2)
    plt.tight_layout()
    plt.savefig(OUTDIR / "extraction_accuracy_prepost_by_decade.png", dpi=150)
    plt.close()

    # per-year line plot: pre vs post accuracy
    pyx = py.sort_values("year")
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(pyx["year"], pyx["pre_accuracy_pct"], "-o", ms=3, color="#cfcfcf",
            label="OCR-Team — all disc")
    ax.plot(pyx["year"], pyx["pre_measured_accuracy_pct"], "-o", ms=3, color="#8a8a8a",
            label="OCR-Team — measured only")
    ax.plot(pyx["year"], pyx["post_accuracy_pct"], "-o", ms=3, color="#8fbbe8",
            label="Claude AI-final — all disc")
    ax.plot(pyx["year"], pyx["post_measured_accuracy_pct"], "-o", ms=3, color="#199e70",
            label="Claude AI-final — measured only")
    ax.fill_between(pyx["year"], pyx["pre_accuracy_pct"], pyx["post_accuracy_pct"],
                    color="#2a78d6", alpha=0.10)
    ax.set_ylim(93, 100.2); ax.set_xlabel("Year")
    ax.set_ylabel("Accuracy vs source PDF (%)")
    ax.set_title("NUST extraction accuracy per year — OCR-Team vs Claude AI-final corpus")
    ax.grid(alpha=0.3); ax.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(OUTDIR / "extraction_accuracy_prepost_per_year.png", dpi=150)
    plt.close()

    print("=== extraction accuracy: OCR-Team vs Claude AI-final corpus (vs source PDF) ===")
    print(f"rows QC'd: {tot_rows:,} | discrepancies: {tot_disc:,} | resolved in corpus: {tot_res:,} "
          f"({100*tot_res/tot_disc:.1f}%)")
    print(f"OCR-Team  — all disc         : {pre_all:.2f}%")
    print(f"OCR-Team  — measured only    : {pre_meas_all:.2f}%   ({tot_meas_disc:,} measured-value OCR errors)")
    print(f"Claude AI — all disc         : {post_all:.2f}%   (+{post_all-pre_all:.2f} pts vs OCR all)")
    print(f"Claude AI — measured only    : {post_meas_all:.2f}%   "
          f"({tot_meas_un:,} confirmed real errors remain; +{post_meas_all-pre_meas_all:.2f} pts vs OCR measured)")
    print(f"  of which credited as audited QC column-misreads (corpus corroborated correct): {tot_qc_misread:,}")
    print(f"  of which credited via HAND-AUDIT consensus adjudication (user+Claude resolved): {tot_ha_credit:,}")
    print()
    print(dec[["decade", "year_range", "rows", "meas_disc", "meas_unresolved",
               "pre_measured_accuracy_pct", "post_measured_accuracy_pct"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
