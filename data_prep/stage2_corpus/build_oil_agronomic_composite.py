"""
build_oil_agronomic_composite.py
================================
Extract per-STRAIN agronomic-summary Oil for the early UT cells that have NO per-location
oil table and NO Table-65 location composite in the source -- only a per-strain
"Percentage of Oil" column in the chemical/agronomic summary. These cannot be folded into
the per-(strain,location) corpus (no location), so they are emitted as a strain_mean
composite that the boxplot (32_secondary_trait_boxplots) overlays as a composite-median
diamond -- the same convention used for the 1947-1958 composite gap.

Cells (the residual oil gaps after the location-composite fold + per-location recovery):
    1942 UT-II / UT-III / UT-IV, 1946 UT-II, 1951 UT-III
(1951 UT-II already carries a strain_mean composite in nust_composition_composite_1947_1958.csv;
 2011 UT-III/UT-IV are a genuine absence -- USDA lab not completed.)

Values: extract_agronomic_oil returns DRY oil; the composite file convention is 13% mb, so we
apply x0.87 here (NOT downstream) so the diamond sits on the same basis as the boxes.

Output: data_prep/stage2_corpus/nust_oil_agronomic_composite_1942_1951.csv
(schema matches nust_composition_composite_1947_1958.csv). Then re-run 32.
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
OUT = STAGE2 / "nust_oil_agronomic_composite_1942_1951.csv"
CELLS = [(1942, "II"), (1942, "III"), (1942, "IV"), (1946, "II"), (1951, "III")]
DRY_TO_MB = 0.87


def load114():
    spec = importlib.util.spec_from_file_location("s114", STAGE2 / "114_extract_oil_perloc.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["s114"] = m
    spec.loader.exec_module(m)
    return m


def extract_strain_oil(m, year, mg):
    """Per (strain, oil-dry) from the agronomic summary -- mirrors m.extract_agronomic_oil but
    keeps the leading strain label of each matched row."""
    import pdfplumber
    path = m._corrected_pdf(year)
    if not path:
        return []
    out = []
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
                if not (30 <= prot <= 52 and 5 <= oil <= 30 and 100 <= iod <= 160):
                    continue
                strain = s[:tri.start()].strip()
                strain = re.sub(r"[\d.]+\s+[\d.]+\s+[\d.]+.*$", "", strain).strip()  # drop any earlier numeric cols
                strain = re.sub(r"\s+", " ", strain)
                if strain:
                    out.append((strain, round(oil, 2)))
    return out


def main():
    m = load114()
    rows = []
    for year, mg in CELLS:
        pairs = extract_strain_oil(m, year, mg)
        # strain LABELS from this table are OCR-garbled (protein/iodine cols bleed in) and are
        # not used downstream -- only the per-cell median drives the boxplot diamond -- so store
        # an anonymous per-strain index rather than an unreliable name.
        for i, (_, oil) in enumerate(pairs, 1):
            rows.append({"Year": year, "TestMG": mg, "Aggregation": "strain_mean",
                         "Strain": f"agr_{mg}_{year}_{i:02d}", "City": pd.NA, "State": pd.NA,
                         "Phenotype": "Oil", "Value_num": round(oil * DRY_TO_MB, 2), "Units": "%",
                         "Source": "OilAgronomic_composite"})
        vals = [o for _, o in pairs]
        med = round(sum(vals) / len(vals) * DRY_TO_MB, 1) if vals else None
        print(f"  {year} UT-{mg}: {len(pairs)} strains, median {med} (13% mb)")
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f"\nWrote {OUT.name}: {len(out)} strain_mean oil rows across {out.groupby(['Year','TestMG']).ngroups} cells")


if __name__ == "__main__":
    main()
