"""
patch_phenotypes_1980.py
========================
Apply all confirmed PDF-vs-CSV cell patches to combined_1980_phenotypesTable.csv.

Source of truth for every patch value: printed Sojabone-1980 PDF report.
Each patch is matched by (Test, City, Strain, Phenotype); value is overwritten
with the PDF ground-truth value.  For rows where csv=nan, the null is filled.

Issues covered (95 cells total)
---------------------------------
ISSUE-1  : UT-00 Height Fargo/Morden column swap         (13 cells)
ISSUE-3  : UT-00 SeedQuality 2 cells                      (2 cells)
ISSUE-4  : UT-00 SeedSize Fargo 1 cell                    (1 cell)
ISSUE-6  : PT-II Yield Lafayette+Urbana                   (7 cells)
ISSUE-7  : PT-III Lafayette+Ottumwa                       (4 cells)
ISSUE-20 : UT-I  Lafayette column shift                  (11 cells)
ISSUE-21 : UT-III S. Charleston Lodging all strains      (20 cells)
ISSUE-22 : UT-IV Manhattan Lodging all strains           (12 cells)
ISSUE-23 : UT-IV Powhattan Yield                          (5 cells)
ISSUE-24 : UT-II Harrow Yield                             (3 cells)
ISSUE-25 : Scattered confirmed cells                      (17 cells)

Not handled here (separate scripts):
  ISSUE-10 : Insert 36 missing PT-IV Portageville Loam Maturity rows
  ISSUE-9  : PT-IV Lexington Oil — awaiting manual PDF verification

Run from project root:
  python fixes/patch_phenotypes_1980.py
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pathlib import Path

CSV_PATH = Path("output_1980/combined_1980_phenotypesTable.csv")

# (Test, City, Strain, Phenotype, pdf_value)
PATCHES = [
    # ------------------------------------------------------------------
    # ISSUE-1 — UT-00 Height: Fargo/Morden column swap
    # tp10 block header order (Morden->Brandon->Fargo) opposite to data
    # entry order (Fargo->Morden->Brandon); PDF is ground truth.
    # ------------------------------------------------------------------
    ("UT-00", "Fargo",  "Maple Presto",  "Height", 20),
    ("UT-00", "Fargo",  "OT80-1",        "Height", 26),
    ("UT-00", "Fargo",  "OT80-3",        "Height", 25),
    ("UT-00", "Fargo",  "Portage (00)",  "Height", 27),
    ("UT-00", "Morden", "Clay (0)",      "Height", 26),
    ("UT-00", "Morden", "M71-148",       "Height", 26),
    ("UT-00", "Morden", "Maple Arrow",   "Height", 28),
    ("UT-00", "Morden", "Maple Presto",  "Height", 22),
    ("UT-00", "Morden", "McCall",        "Height", 27),
    ("UT-00", "Morden", "OT80-1",        "Height", 24),
    ("UT-00", "Morden", "OT80-2",        "Height", 23),
    ("UT-00", "Morden", "OT80-3",        "Height", 24),
    ("UT-00", "Morden", "Portage (00)",  "Height", 24),

    # ------------------------------------------------------------------
    # ISSUE-3 — UT-00 SeedQuality individual cell errors
    # ------------------------------------------------------------------
    ("UT-00", "Ashland",   "Maple Presto", "SeedQuality", 3.5),
    ("UT-00", "Rosemount", "OT80-1",       "SeedQuality", 2.0),

    # ------------------------------------------------------------------
    # ISSUE-4 — UT-00 SeedSize Fargo individual cell error
    # ------------------------------------------------------------------
    ("UT-00", "Fargo", "Maple Presto", "SeedSize", 13.3),

    # ------------------------------------------------------------------
    # ISSUE-6 — PT-II Yield Lafayette + Urbana column shift
    # ------------------------------------------------------------------
    ("PT-II", "Urbana",    "A75D29",       "YieldBuA", 31.9),
    ("PT-II", "Urbana",    "Century",      "YieldBuA", 43.8),
    ("PT-II", "Lafayette", "Gnome",        "YieldBuA", 51.1),
    ("PT-II", "Urbana",    "Gnome",        "YieldBuA", 49.5),
    ("PT-II", "Urbana",    "Hardin (I)",   "YieldBuA", 41.9),
    ("PT-II", "Lafayette", "Pella (III)",  "YieldBuA", 57.1),
    ("PT-II", "Urbana",    "Pella (III)",  "YieldBuA", 45.3),

    # ------------------------------------------------------------------
    # ISSUE-7 — PT-III individual cell errors + L78-709 null fills
    # ------------------------------------------------------------------
    ("PT-III", "Ottumwa",  "HC76-3863", "Oil",     22.9),
    ("PT-III", "Lafayette","L77-443",   "Lodging",  1.8),
    ("PT-III", "Ottumwa",  "L78-709",   "Height",  33),
    ("PT-III", "Lafayette","L78-709",   "Lodging",  2.0),

    # ------------------------------------------------------------------
    # ISSUE-20 — UT-I Lafayette column shift (Height / Lodging /
    #            SeedQuality / SeedSize affected)
    # Note: "Hardin" renamed to "Hardin (I)" by fix_strain_ocr_1980.py
    # ------------------------------------------------------------------
    ("UT-I", "Lafayette", "Evans (0)",       "Height",      36),
    ("UT-I", "Lafayette", "Hardin (I)",      "Height",      37),
    ("UT-I", "Lafayette", "M72-3",           "Height",      29),
    ("UT-I", "Lafayette", "Hardin (I)",      "Lodging",      1.2),
    ("UT-I", "Lafayette", "Hodgson 78 (I)",  "Lodging",      1.9),
    ("UT-I", "Lafayette", "Corsoy 79 (II)",  "SeedQuality",  2.0),
    ("UT-I", "Lafayette", "Evans (0)",       "SeedQuality",  3.0),
    ("UT-I", "Lafayette", "Hodgson 78 (I)",  "SeedQuality",  2.0),
    ("UT-I", "Lafayette", "M71-80",          "SeedQuality",  1.8),
    ("UT-I", "Lafayette", "M75-2",           "SeedQuality",  1.6),
    ("UT-I", "Lafayette", "Hardin (I)",      "SeedSize",    14.9),

    # ------------------------------------------------------------------
    # ISSUE-21 — UT-III S. Charleston Lodging: all strains wrong
    # ------------------------------------------------------------------
    ("UT-III", "S. Charleston", "A78-227012",      "Lodging", 2.1),
    ("UT-III", "S. Charleston", "A78-321011",      "Lodging", 1.7),
    ("UT-III", "S. Charleston", "A78-322024",      "Lodging", 2.7),
    ("UT-III", "S. Charleston", "A78-324002",      "Lodging", 2.7),
    ("UT-III", "S. Charleston", "A78-325028",      "Lodging", 3.3),
    ("UT-III", "S. Charleston", "A78-326032",      "Lodging", 3.1),
    ("UT-III", "S. Charleston", "BSR 302",         "Lodging", 3.2),
    ("UT-III", "S. Charleston", "Century (II)",    "Lodging", 1.8),
    ("UT-III", "S. Charleston", "Cumberland (III)","Lodging", 2.0),
    ("UT-III", "S. Charleston", "HC76-4030",       "Lodging", 1.0),
    ("UT-III", "S. Charleston", "HW74-3384 Sprite","Lodging", 1.1),
    ("UT-III", "S. Charleston", "HW74-3385",       "Lodging", 1.2),
    ("UT-III", "S. Charleston", "L24A",            "Lodging", 2.1),
    ("UT-III", "S. Charleston", "L25A",            "Lodging", 2.5),
    ("UT-III", "S. Charleston", "L26",             "Lodging", 2.4),
    ("UT-III", "S. Charleston", "L75-8121",        "Lodging", 2.6),
    ("UT-III", "S. Charleston", "Pella",           "Lodging", 1.9),
    ("UT-III", "S. Charleston", "U36276",          "Lodging", 1.4),
    ("UT-III", "S. Charleston", "Union (IV)",      "Lodging", 2.9),
    ("UT-III", "S. Charleston", "Williams 79",     "Lodging", 2.5),

    # ------------------------------------------------------------------
    # ISSUE-22 — UT-IV Manhattan Lodging: all strains = 1.0 per PDF
    # ------------------------------------------------------------------
    ("UT-IV", "Manhattan", "Franklin",         "Lodging", 1.0),
    ("UT-IV", "Manhattan", "K1033",            "Lodging", 1.0),
    ("UT-IV", "Manhattan", "K1041",            "Lodging", 1.0),
    ("UT-IV", "Manhattan", "K1044",            "Lodging", 1.0),
    ("UT-IV", "Manhattan", "K1045",            "Lodging", 1.0),
    ("UT-IV", "Manhattan", "K1046",            "Lodging", 1.0),
    ("UT-IV", "Manhattan", "Ky75-146-74",      "Lodging", 1.0),
    ("UT-IV", "Manhattan", "L73-318",          "Lodging", 1.0),
    ("UT-IV", "Manhattan", "L74L-125",         "Lodging", 1.0),
    ("UT-IV", "Manhattan", "L74L-358",         "Lodging", 1.0),
    ("UT-IV", "Manhattan", "Union (IV)",       "Lodging", 1.0),
    ("UT-IV", "Manhattan", "Williams79 (III)", "Lodging", 1.0),

    # ------------------------------------------------------------------
    # ISSUE-23 — UT-IV Powhattan Yield: column shift / swap
    # ------------------------------------------------------------------
    ("UT-IV", "Powhattan", "HC76-3840",        "YieldBuA", 16.6),
    ("UT-IV", "Powhattan", "K1033",            "YieldBuA", 16.4),
    ("UT-IV", "Powhattan", "K1041",            "YieldBuA", 13.6),
    ("UT-IV", "Powhattan", "Ky75-146-74",      "YieldBuA", 19.6),
    ("UT-IV", "Powhattan", "Williams79 (III)", "YieldBuA", 13.5),

    # ------------------------------------------------------------------
    # ISSUE-24 — UT-II Harrow Yield: two adjacent rows appear swapped
    # ------------------------------------------------------------------
    ("UT-II", "Harrow", "A77-211021",  "YieldBuA", 55.4),
    ("UT-II", "Harrow", "A78-122031",  "YieldBuA", 60.4),
    ("UT-II", "Harrow", "Pella (III)", "YieldBuA", 51.6),

    # ------------------------------------------------------------------
    # ISSUE-10 — PT-IV Portageville Loam Maturity: 13 wrong DOY values
    # Rows exist in CSV but values differ from PDF.
    # XLSX tp7 offsets (ref Union(IV)=DOY 268) match PDF exactly for all 13.
    # ------------------------------------------------------------------
    ("PT-IV", "Portageville Loam", "HC77-982",      "Maturity", 264),
    ("PT-IV", "Portageville Loam", "K1033 Douglas",  "Maturity", 276),
    ("PT-IV", "Portageville Loam", "K1061",          "Maturity", 277),
    ("PT-IV", "Portageville Loam", "K1062",          "Maturity", 264),
    ("PT-IV", "Portageville Loam", "K1063",          "Maturity", 278),
    ("PT-IV", "Portageville Loam", "K1066",          "Maturity", 274),
    ("PT-IV", "Portageville Loam", "K1067",          "Maturity", 271),
    ("PT-IV", "Portageville Loam", "Ky78-405",       "Maturity", 277),
    ("PT-IV", "Portageville Loam", "Ky78-1214",      "Maturity", 277),
    ("PT-IV", "Portageville Loam", "L77-8209",       "Maturity", 278),
    ("PT-IV", "Portageville Loam", "LS78-229",       "Maturity", 291),
    ("PT-IV", "Portageville Loam", "LS78-335",       "Maturity", 290),
    ("PT-IV", "Portageville Loam", "LS78-344",       "Maturity", 285),

    # ------------------------------------------------------------------
    # ISSUE-25 — Scattered confirmed individual cell errors
    # ------------------------------------------------------------------
    # UT-0
    ("UT-0",   "Elora",           "M72-24",       "Protein",      43.2),
    # UT-I  (Hardin renamed to Hardin (I) by fix_strain_ocr_1980.py)
    ("UT-I",   "Oakes",           "Evans (0)",    "SeedQuality",   2.5),
    ("UT-I",   "Ridgetown",       "Hardin (I)",   "Protein",      41.7),
    ("UT-I",   "Lamberton",       "A78-121014",   "SeedSize",     19.6),
    ("UT-I",   "Dekalb",          "Evans (0)",    "YieldRank",     9),
    ("UT-I",   "Dekalb",          "M75-2",        "YieldRank",     7),
    # UT-II
    ("UT-II",  "Ridgetown",       "A78-227015",   "Lodging",       1.2),
    ("UT-II",  "Ridgetown",       "A78-227016",   "Lodging",       1.8),
    ("UT-II",  "Ames",            "A78-122028",   "Protein",      40.9),
    ("UT-II",  "Waseca",          "A78-227013",   "Lodging",       1.7),
    ("UT-II",  "Urbana",          "Pella (III)",  "SeedQuality",   2.0),
    # UT-III
    ("UT-III", "Elk Point",       "U36276",       "SeedQuality",   3.0),
    ("UT-III", "Manhattan",       "HW74-3385",    "Lodging",       1.0),
    # UT-IV  (H76-3840 renamed to HC76-3840 by fix_strain_ocr_1980.py)
    ("UT-IV",  "Portageville Clay","K1033",       "SeedQuality",   2.5),
    ("UT-IV",  "Queenstown",       "Franklin",    "SeedQuality",   1.2),
    ("UT-IV",  "Manhattan",        "HC76-3840",   "Protein",      42.2),
    ("UT-IV",  "Manhattan",        "HC76-3840",   "Oil",          19.1),
]


def main():
    df = pd.read_csv(CSV_PATH)
    total_rows = len(df)
    print(f"Loaded {total_rows} rows from {CSV_PATH.name}")

    matched = 0
    not_found = []
    already_correct = []

    for test, city, strain, phenotype, pdf_val in PATCHES:
        mask = (
            (df["Test"]      == test)     &
            (df["City"]      == city)     &
            (df["Strain"]    == strain)   &
            (df["Phenotype"] == phenotype)
        )
        n = mask.sum()
        if n == 0:
            not_found.append((test, city, strain, phenotype, pdf_val))
            continue

        current = df.loc[mask, "Value"].values[0]
        current_str = "null" if pd.isna(current) else str(current)
        pdf_str = str(pdf_val)

        if not pd.isna(current) and str(float(current)) == str(float(pdf_val)):
            already_correct.append((test, city, strain, phenotype, pdf_val))
        else:
            df.loc[mask, "Value"] = pdf_val
            matched += 1
            print(f"  PATCH  {test:6s} {city:22s} {strain:25s} {phenotype:14s}  {current_str:>8} -> {pdf_str}")

    df.to_csv(CSV_PATH, index=False)

    print(f"\n--- Summary ---")
    print(f"  Patched       : {matched}")
    print(f"  Already correct: {len(already_correct)}")
    if not_found:
        print(f"  NOT FOUND ({len(not_found)}) — check strain/city spelling:")
        for r in not_found:
            print(f"    {r[0]:6s} {r[1]:22s} {r[2]:25s} {r[3]}")
    print(f"\nRows before/after: {total_rows}/{len(df)} (should be equal)")
    print("\nNext: re-run validation")
    print("  python scripts/validate_nust_hist.py --input output_1980/combined_1980_phenotypesTable.csv --out_dir output_1980/validated/")


if __name__ == "__main__":
    main()
