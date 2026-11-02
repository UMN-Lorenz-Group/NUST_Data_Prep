"""
build_protein_agronomic_composite.py
====================================
Protein analogue of build_oil_agronomic_composite.py. For the early/mid-era UT cells that have
NO per-location protein and NO composite_1947_1958 entry, pull the per-strain Protein from the
chemical/agronomic summary (the FIRST value of the "...Protein Oil Iodine" triplet) and emit a
strain_mean composite that 32_secondary_trait_boxplots overlays as a composite-median diamond.

Candidate cells = the protein gap cells with no composite source (pre-1947 + scattered mid-era).
A cell is kept only if the extraction is credible: >=3 strains and 13%-mb median in [33, 40]
(protein). Cells that fail (no agronomic table, e.g. 1953 UT-I / 1962 UT-00, or out-of-range like
1958 UT-0 -> 28.5) are dropped and remain honest gaps.

Values: agronomic protein is DRY; the composite/diamond convention is 13% mb -> x0.87 here.
Strain labels are OCR-garbled (numeric cols bleed in) -> anonymized; only the median is used.

Output: data_prep/stage2_corpus/nust_protein_agronomic_composite.csv  (schema matches the
composition composite file). Then re-run 32.
"""
import importlib.util
import re
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
STAGE2 = REPO / "data_prep" / "stage2_corpus"
OUT = STAGE2 / "nust_protein_agronomic_composite.csv"
DRY_TO_MB = 0.87
# protein gap cells lacking any composite source (from the tiered gap audit)
CELLS = [(1962, "00"), (1963, "00"), (1958, "0"), (1953, "I"),
         (1942, "II"), (1946, "II"), (1950, "II"), (1954, "II"),
         (1941, "III"), (1942, "III"), (1945, "III"), (1946, "III"), (1949, "III"), (1951, "III"),
         (1941, "IV"), (1942, "IV"), (1945, "IV"), (1946, "IV"), (1948, "IV"), (1954, "IV"), (1956, "IV")]
MIN_STRAINS = 3
MB_LO, MB_HI = 33.0, 40.0


def load114():
    spec = importlib.util.spec_from_file_location("s114", STAGE2 / "114_extract_oil_perloc.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["s114"] = m
    spec.loader.exec_module(m)
    return m


def extract_protein(m, year, mg):
    import pdfplumber
    path = m._corrected_pdf(year)
    if not path:
        return []
    vals = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if "protein" not in t.lower() or "oil" not in t.lower():
                continue
            cur = None
            for ln in t.splitlines():
                g = m._AGRO_GRP.search(ln)
                if g:
                    cur = g.group(1).upper()
                s = ln.strip()
                if cur != mg or not re.match(r"^[A-Za-z]", s):
                    continue
                tri = m._AGRO_TRIPLET.search(s)
                if not tri:
                    continue
                prot, oil, iod = float(tri.group(1)), float(tri.group(2)), float(tri.group(3))
                if 30 <= prot <= 52 and 5 <= oil <= 30 and 100 <= iod <= 160:
                    vals.append(round(prot, 2))
    return vals


def main():
    m = load114()
    rows = []
    kept = dropped = 0
    for year, mg in CELLS:
        vals = extract_protein(m, year, mg)
        med = (sum(vals) / len(vals) * DRY_TO_MB) if vals else None
        ok = len(vals) >= MIN_STRAINS and med is not None and MB_LO <= med <= MB_HI
        if ok:
            kept += 1
            for i, p in enumerate(vals, 1):
                rows.append({"Year": year, "TestMG": mg, "Aggregation": "strain_mean",
                             "Strain": f"agr_{mg}_{year}_{i:02d}", "City": pd.NA, "State": pd.NA,
                             "Phenotype": "Protein", "Value_num": round(p * DRY_TO_MB, 2),
                             "Units": "%", "Source": "ProteinAgronomic_composite"})
            print(f"  KEEP {year} UT-{mg}: {len(vals)} strains, median {round(med,1)} (13% mb)")
        else:
            dropped += 1
            print(f"  drop {year} UT-{mg}: n={len(vals)} median={round(med,1) if med else '-'} "
                  f"-> honest gap")
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\nWrote {OUT.name}: {len(rows)} rows, {kept} cells kept, {dropped} dropped (remain gaps)")


if __name__ == "__main__":
    main()
