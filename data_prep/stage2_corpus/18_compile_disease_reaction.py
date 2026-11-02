"""
18_compile_disease_reaction.py   (PASS 2 — disease companion file)
=================================================================
Compile the SEPARATE disease-reaction companion to the descriptive-score file
(script 16). Disease reactions are kept apart from the descriptive scores because
their values are a different data type (per-pathogen, per-race reaction codes /
percentages / severity scores, captured verbatim as `Value` + parsed `Value_num`).

Two feeds:
  • HISTORICAL 1972-1988  — the "Disease Data" matrix recovered from the Red PDFs
    by 17_extract_disease_pre1989.py (PROVISIONAL: validated 1980; col{n} locations
    + a few abbrev artifacts pending QC). The 1958-1971 composite-reaction era and
    the 1985-88 merged-block era are a later sub-pass.
  • MODERN 1989-2016       — the sporadic digital disease panel already in the corpus
    (BSR / SDS / SCL / Frogeye / PM / SMV / Phytophthora / PodStemBlight / PurpleStain …).

Output (analysis/data/_shared/): nust_disease_reaction_1958_2025.csv  (long)
  Year, Era, Source, Test, TestType, TestMG, Strain, Disease, DiseaseAbbrev,
  Location, Value, Value_num, Units
"""
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
CORPUS = SHARED / "nust_1941_2025_combined.csv"
HIST = SHARED / "disease_pre1989_long.csv"
OUT = SHARED / "nust_disease_reaction_1958_2025.csv"

# Modern corpus disease/seed-health phenotype -> canonical disease (matches the
# historical canonical names so the file is coherent across eras).
MODERN_DISEASE_MAP = {
    "BSR": "BrownStemRot", "BSRPlant": "BrownStemRot", "BSRStem": "BrownStemRot",
    "BSR.Incid": "BrownStemRot", "BSR.Sev": "BrownStemRot", "BTSa": "BrownStemRot",
    "SDS": "SuddenDeathSyndrome", "SDSDI": "SuddenDeathSyndrome", "SDSDS": "SuddenDeathSyndrome",
    "SDSRank": "SuddenDeathSyndrome", "SDSS": "SuddenDeathSyndrome", "SDSI.": "SuddenDeathSyndrome",
    "SDSR6": "SuddenDeathSyndrome", "SDSR6Date": "SuddenDeathSyndrome", "SDSRDate": "SuddenDeathSyndrome",
    "SDSTest": "SuddenDeathSyndrome",
    "SCL": "Sclerotinia",
    "Frogeye": "Frogeye", "FE": "Frogeye", "FELS": "Frogeye",
    "PM": "PowderyMildew", "Mottle": "SeedMottling", "SMV": "SoybeanMosaicVirus",
    "Phytophthora": "PhytophthoraRot", "PhytoRot": "PhytophthoraRot", "PhytoTol": "PhytophthoraRot",
    "PRRace1": "PhytophthoraRot", "PRPhytoTol": "PhytophthoraRot", "RootRot": "PhytophthoraRot",
    "RootRotRace25": "PhytophthoraRot", "StemCanker": "StemCanker",
    "PSB": "PodAndStemBlight", "P.SB": "PodAndStemBlight", "PS": "PurpleStain",
    "HardSeed": "HardSeed", "SeedGerm": "Germination",
}

OUT_COLS = ["Year", "Era", "Source", "Test", "TestType", "TestMG", "Strain",
            "Disease", "DiseaseAbbrev", "Location", "Value", "Value_num", "Units"]


def from_corpus():
    df = pd.read_csv(CORPUS, low_memory=False)
    sub = df[df["Phenotype"].isin(MODERN_DISEASE_MAP)].copy()
    if not len(sub):
        return pd.DataFrame(columns=OUT_COLS)
    sub["Disease"] = sub["Phenotype"].map(MODERN_DISEASE_MAP)
    sub["DiseaseAbbrev"] = sub["Phenotype"]
    sub["Era"] = "modern_corpus"
    sub["Location"] = sub.get("City", "")
    sub["Value"] = sub["Value_num"].astype("string")
    sub["TestType"] = sub.get("TestType", "")
    sub["TestMG"] = sub.get("TestMG", "")
    for c in OUT_COLS:
        if c not in sub.columns:
            sub[c] = pd.NA
    return sub[OUT_COLS]


def from_historical():
    if not HIST.exists():
        print(f"  (historical file not present: {HIST.name})")
        return pd.DataFrame(columns=OUT_COLS)
    h = pd.read_csv(HIST, low_memory=False)
    h["Era"] = "historical_pdf_provisional"
    for c in OUT_COLS:
        if c not in h.columns:
            h[c] = pd.NA
    return h[OUT_COLS]


def main():
    if not CORPUS.exists():
        sys.exit(f"ERROR: missing {CORPUS}")
    modern = from_corpus()
    hist = from_historical()
    print(f"  modern (corpus) disease rows : {len(modern):,}"
          + (f" ({int(modern.Year.min())}-{int(modern.Year.max())})" if len(modern) else ""))
    print(f"  historical (PDF) disease rows: {len(hist):,}"
          + (f" ({int(hist.Year.min())}-{int(hist.Year.max())})" if len(hist) else ""))
    out = pd.concat([hist, modern], ignore_index=True)
    out = out.sort_values(["Year", "Disease", "Test", "Strain"]).reset_index(drop=True)
    out.to_csv(OUT, index=False)
    print(f"\nWrote {OUT.name}: {len(out):,} rows")
    print("\n  rows per Disease:")
    print(out.groupby("Disease").size().sort_values(ascending=False).to_string())
    print("\n  year span per Disease:")
    print(out.groupby("Disease")["Year"].agg(["min", "max", "nunique"]).to_string())


if __name__ == "__main__":
    main()
