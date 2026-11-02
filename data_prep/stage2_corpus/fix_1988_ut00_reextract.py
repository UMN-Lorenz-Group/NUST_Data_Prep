"""
fix_1988_ut00_reextract.py
==========================
Re-extract the 1988 UT-00 recovery block from the CLEAN source PDF (input_files/1988.pdf,
pp. 9-13), replacing the mis-parsed rows in recovery_confirmed.csv.

WHY: the 2026-07-13 green_pdf_conflict audit found the 1988 UT-00 `Recovered_1970_1988`
block was extracted wrong (print is clean, parse was bad):
  * Lodging / SeedQuality / YieldBuA (src PDFdropUT_115): GARBLED city headers -> the wrapped
    two-line column labels split into fragments 'land' (Ashland) / 'ston' (Crookston); values
    misaligned; only 4-5 of 7 locations captured.
  * Height / Oil (src PDF1988_UT00_review): 3 strains (Maple Presto, Maple Ridge, McCall)
    shifted ONE COLUMN LEFT (the printed Mean col read as location #1).
  * Maturity: the 16 non-anchor strains are correct (DOY = anchor + printed offset); only the
    McCall ANCHOR row was wrong (parser choked on the printed dates 09/06 etc.).
  * Protein: correct but INCOMPLETE (6 of 17 strains).

FIX: transcribe all 8 per-location tables from the rendered pages (ground truth below) and
regenerate clean long rows. Validate each strain's across-location mean against the PDF's
printed Mean column (catches transcription slips) before writing. Maturity DOY is reconstructed
from the McCall anchor dates + printed relative offsets. No corpus rebuild here -- this only
fixes the source; the correction flows in at the next batched 10->11->12 rebuild.

Usage:
    uv run python data_prep/stage2_corpus/fix_1988_ut00_reextract.py --check   # validate only
    uv run python data_prep/stage2_corpus/fix_1988_ut00_reextract.py --apply   # write recovery csv
"""
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(__file__).resolve().parent.parent.parent
REC = REPO / "data_prep" / "stage2_corpus" / "recovery_confirmed.csv"

STRAINS = ["Clay (0)", "Maple Presto", "Maple Ridge", "McCall (00)", "M84-93", "M84-456",
           "ND867", "ND868", "ND941", "ND2337", "ND2338", "ND2353", "OT84-12", "OT85-5",
           "OT87-7", "OT87-8", "OT87-12"]
STATE = {"Brandon": "MB", "Crookston": "MN", "Morris": "MN", "Casselton": "ND",
         "Elora": "ON", "Ottawa": "ON", "Ashland": "WI"}
AGRO_LOCS = ["Brandon", "Crookston", "Morris", "Casselton", "Elora", "Ottawa", "Ashland"]  # 7
COMP_LOCS = ["Crookston", "Morris", "Casselton", "Elora", "Ashland"]                        # 5
MAT_LOCS = ["Brandon", "Crookston", "Morris", "Casselton", "Elora", "Ottawa"]              # 6

# ---- ground-truth grids transcribed from rendered pages (col order as listed above) ----
# p9 YIELD (bu/a), 7 locs
YIELD = {
"Clay (0)":[8.7,18.0,25.4,14.9,49.8,34.6,22.4],"Maple Presto":[12.3,11.2,11.6,11.6,31.9,30.8,8.5],
"Maple Ridge":[12.5,13.5,16.2,12.0,38.0,37.6,12.0],"McCall (00)":[10.5,14.3,15.5,13.3,43.6,36.6,19.5],
"M84-93":[8.2,17.8,18.2,12.8,43.8,43.6,17.1],"M84-456":[6.9,16.3,15.8,17.3,44.5,41.4,19.1],
"ND867":[10.9,16.6,15.8,13.0,46.6,35.0,13.7],"ND868":[12.2,17.9,15.3,16.3,43.6,36.9,17.8],
"ND941":[11.5,16.8,14.8,10.2,40.5,36.6,16.3],"ND2337":[11.7,12.7,15.4,18.4,38.6,36.9,13.9],
"ND2338":[10.0,15.2,16.7,14.2,43.5,34.6,15.9],"ND2353":[10.3,12.5,13.8,9.8,39.1,31.3,8.9],
"OT84-12":[7.8,18.6,19.6,15.2,49.2,40.6,15.2],"OT85-5":[11.7,15.5,13.6,14.6,46.3,31.7,14.1],
"OT87-7":[13.0,17.0,19.6,16.2,42.0,44.6,18.0],"OT87-8":[8.6,18.3,17.9,13.2,44.5,39.2,16.4],
"OT87-12":[11.6,13.8,12.2,17.2,33.7,32.3,13.4]}
YIELD_MEAN = {"Clay (0)":24.8,"Maple Presto":16.8,"Maple Ridge":20.3,"McCall (00)":21.9,"M84-93":23.1,
"M84-456":23.0,"ND867":21.7,"ND868":22.9,"ND941":21.0,"ND2337":21.1,"ND2338":21.4,"ND2353":18.0,
"OT84-12":23.7,"OT85-5":21.1,"OT87-7":24.3,"OT87-8":22.6,"OT87-12":19.2}
# p11 LODGING (score), 7 locs
LODGING = {
"Clay (0)":[1.0,1.0,1.0,1.0,1.4,4.1,1.0],"Maple Presto":[1.0,1.0,1.0,1.0,1.0,2.9,1.0],
"Maple Ridge":[1.0,1.0,1.0,1.0,1.0,2.8,1.0],"McCall (00)":[1.0,1.0,1.0,1.0,1.3,3.2,1.0],
"M84-93":[1.0,1.0,1.0,1.0,1.0,1.8,1.0],"M84-456":[1.0,1.0,1.0,1.0,1.0,1.9,1.0],
"ND867":[1.0,1.0,1.0,1.0,1.4,2.5,1.0],"ND868":[1.0,1.0,1.0,1.0,1.0,3.4,1.0],
"ND941":[1.0,1.0,1.0,1.0,1.0,2.1,1.0],"ND2337":[1.5,1.0,1.0,1.0,1.0,3.6,1.0],
"ND2338":[1.0,1.0,1.0,1.0,1.1,2.8,1.0],"ND2353":[1.0,1.0,1.0,1.0,1.1,3.0,1.0],
"OT84-12":[1.0,1.0,1.0,1.0,1.1,2.8,1.0],"OT85-5":[1.0,1.0,1.0,1.0,1.1,3.5,1.0],
"OT87-7":[1.5,1.0,1.0,1.0,1.0,2.1,1.0],"OT87-8":[1.5,1.0,1.0,1.0,1.3,2.6,1.0],
"OT87-12":[1.0,1.0,1.0,1.0,1.0,4.4,1.0]}
LODGING_MEAN = {"Clay (0)":1.5,"Maple Presto":1.3,"Maple Ridge":1.3,"McCall (00)":1.4,"M84-93":1.1,
"M84-456":1.1,"ND867":1.3,"ND868":1.3,"ND941":1.2,"ND2337":1.4,"ND2338":1.3,"ND2353":1.3,
"OT84-12":1.3,"OT85-5":1.4,"OT87-7":1.2,"OT87-8":1.3,"OT87-12":1.5}
# p11 PLANT HEIGHT (inches), 7 locs
HEIGHT = {
"Clay (0)":[16,18,15,16,30,40,20],"Maple Presto":[11,17,12,12,20,38,16],
"Maple Ridge":[12,15,14,13,21,36,17],"McCall (00)":[13,14,13,15,29,41,19],
"M84-93":[13,16,13,15,31,40,18],"M84-456":[13,15,13,17,31,40,19],
"ND867":[14,18,11,12,28,37,19],"ND868":[14,18,14,15,28,41,20],
"ND941":[15,14,12,12,28,36,17],"ND2337":[11,15,12,12,22,32,16],
"ND2338":[15,15,13,14,25,38,18],"ND2353":[13,17,12,11,28,37,17],
"OT84-12":[14,18,16,15,26,39,17],"OT85-5":[15,16,12,14,26,35,18],
"OT87-7":[13,19,15,13,22,38,18],"OT87-8":[11,21,16,15,25,43,18],
"OT87-12":[13,17,11,12,17,34,18]}
HEIGHT_MEAN = {"Clay (0)":22,"Maple Presto":18,"Maple Ridge":18,"McCall (00)":21,"M84-93":21,
"M84-456":21,"ND867":20,"ND868":21,"ND941":19,"ND2337":17,"ND2338":20,"ND2353":19,
"OT84-12":21,"OT85-5":19,"OT87-7":20,"OT87-8":21,"OT87-12":17}
# p12 SEED QUALITY (score), 7 locs
SEEDQUAL = {
"Clay (0)":[2.9,3.8,4.0,3.7,1.5,2.0,2.0],"Maple Presto":[3.0,4.0,4.7,5.0,2.0,2.0,4.7],
"Maple Ridge":[3.0,4.5,4.3,5.0,1.5,1.5,3.0],"McCall (00)":[3.0,3.5,4.3,3.0,1.5,2.0,3.0],
"M84-93":[3.1,3.0,4.0,3.0,1.5,1.0,3.0],"M84-456":[2.9,3.0,3.0,3.0,1.5,1.0,2.7],
"ND867":[3.0,4.5,4.7,5.0,1.5,1.3,3.3],"ND868":[2.5,4.0,4.7,4.3,1.5,1.8,4.0],
"ND941":[2.5,2.8,4.3,3.7,1.5,1.5,3.7],"ND2337":[3.1,3.8,3.7,5.0,1.5,2.0,2.7],
"ND2338":[3.0,4.0,4.3,5.0,1.5,2.0,3.0],"ND2353":[3.5,4.8,4.3,5.0,2.5,2.0,4.3],
"OT84-12":[2.5,3.0,3.3,3.7,1.5,2.0,1.7],"OT85-5":[3.0,4.0,4.3,4.7,1.5,1.7,3.3],
"OT87-7":[2.4,4.3,3.7,3.0,1.5,1.8,4.0],"OT87-8":[2.5,4.0,4.0,3.0,1.5,2.0,4.7],
"OT87-12":[2.9,4.0,4.3,4.0,2.0,1.7,4.0]}
SEEDQUAL_MEAN = {"Clay (0)":2.8,"Maple Presto":3.6,"Maple Ridge":3.3,"McCall (00)":2.9,"M84-93":2.7,
"M84-456":2.4,"ND867":3.3,"ND868":3.3,"ND941":2.9,"ND2337":3.1,"ND2338":3.3,"ND2353":3.8,
"OT84-12":2.5,"OT85-5":3.2,"OT87-7":3.0,"OT87-8":3.1,"OT87-12":3.3}
# p12 SEED SIZE (g/100), 7 locs
SEEDSIZE = {
"Clay (0)":[13.3,15.8,16.9,13.7,15.6,18.1,17.5],"Maple Presto":[11.5,11.3,14.0,10.8,15.9,17.3,18.0],
"Maple Ridge":[11.3,11.2,12.7,9.9,16.1,17.6,20.0],"McCall (00)":[12.3,14.0,13.9,11.8,14.6,16.9,18.8],
"M84-93":[12.5,14.5,14.8,11.9,14.3,17.0,16.2],"M84-456":[10.2,13.4,13.0,13.0,13.2,15.3,16.7],
"ND867":[14.7,14.3,14.3,13.0,19.4,20.8,18.4],"ND868":[14.3,15.6,15.5,14.7,18.1,20.7,18.9],
"ND941":[13.1,13.8,13.3,11.7,13.9,16.6,15.2],"ND2337":[11.3,10.5,11.1,11.2,12.4,15.4,15.8],
"ND2338":[15.1,15.0,14.8,13.5,17.9,14.9,18.6],"ND2353":[10.9,12.0,13.5,11.9,15.7,18.3,17.2],
"OT84-12":[13.4,15.5,17.2,14.9,18.3,21.9,19.4],"OT85-5":[13.0,13.0,15.4,11.4,15.8,19.3,19.1],
"OT87-7":[10.0,13.0,12.9,10.9,14.3,15.8,17.3],"OT87-8":[10.8,13.5,12.7,10.8,14.3,15.7,17.2],
"OT87-12":[13.2,13.2,14.1,12.6,17.4,17.6,20.6]}
SEEDSIZE_MEAN = {"Clay (0)":15.8,"Maple Presto":14.1,"Maple Ridge":14.1,"McCall (00)":14.6,"M84-93":14.5,
"M84-456":13.5,"ND867":16.4,"ND868":16.8,"ND941":13.9,"ND2337":12.5,"ND2338":15.7,"ND2353":14.2,
"OT84-12":17.2,"OT85-5":15.3,"OT87-7":13.5,"OT87-8":13.6,"OT87-12":15.5}
# p13 PROTEIN (%), 5 locs (Crookston, Morris, Casselton, Elora, Ashland)
PROTEIN = {
"Clay (0)":[41.6,39.7,41.1,40.7,38.7],"Maple Presto":[38.0,38.7,39.3,38.8,43.4],
"Maple Ridge":[40.8,40.0,38.9,40.0,43.7],"McCall (00)":[39.3,39.4,39.1,40.4,42.0],
"M84-93":[41.3,40.3,39.1,38.8,40.3],"M84-456":[43.3,40.8,40.6,41.6,40.8],
"ND867":[40.1,38.1,39.7,40.0,41.7],"ND868":[40.3,39.1,39.3,40.3,40.6],
"ND941":[41.9,39.7,38.9,40.6,39.4],"ND2337":[41.3,39.5,38.6,39.6,41.8],
"ND2338":[41.6,38.9,39.4,39.0,40.9],"ND2353":[38.3,39.4,39.6,39.6,44.1],
"OT84-12":[41.4,40.1,39.5,41.7,44.0],"OT85-5":[41.1,40.0,40.3,39.4,42.0],
"OT87-7":[39.2,37.7,37.5,38.0,39.6],"OT87-8":[38.7,37.4,36.9,38.5,40.8],
"OT87-12":[39.1,37.1,38.6,39.9,41.3]}
PROTEIN_MEAN = {"Clay (0)":40.4,"Maple Presto":39.6,"Maple Ridge":40.7,"McCall (00)":40.0,"M84-93":40.0,
"M84-456":41.4,"ND867":39.9,"ND868":39.9,"ND941":40.1,"ND2337":40.2,"ND2338":40.0,"ND2353":40.2,
"OT84-12":41.3,"OT85-5":40.6,"OT87-7":38.4,"OT87-8":38.5,"OT87-12":39.2}
# p13 OIL (%), 5 locs
OIL = {
"Clay (0)":[22.2,23.9,21.4,20.2,19.6],"Maple Presto":[22.5,22.6,21.8,21.9,17.0],
"Maple Ridge":[19.6,21.3,20.2,21.0,17.2],"McCall (00)":[21.8,22.3,21.5,20.0,17.5],
"M84-93":[22.1,22.1,22.5,20.7,18.3],"M84-456":[21.4,23.9,22.0,19.6,19.1],
"ND867":[22.1,23.7,21.9,20.4,18.4],"ND868":[22.5,23.1,22.6,20.7,19.4],
"ND941":[21.2,22.5,22.4,19.2,18.7],"ND2337":[20.6,22.4,21.9,20.4,18.2],
"ND2338":[21.3,22.6,21.8,21.2,18.3],"ND2353":[22.1,22.7,21.3,21.2,17.4],
"OT84-12":[22.0,23.0,22.3,20.4,17.9],"OT85-5":[21.9,23.6,22.8,20.9,18.1],
"OT87-7":[22.9,24.7,23.9,22.0,20.6],"OT87-8":[23.6,24.2,24.4,21.9,20.4],
"OT87-12":[21.9,23.5,22.3,23.1,19.3]}
OIL_MEAN = {"Clay (0)":21.5,"Maple Presto":21.2,"Maple Ridge":19.9,"McCall (00)":20.6,"M84-93":21.1,
"M84-456":21.2,"ND867":21.3,"ND868":21.7,"ND941":20.8,"ND2337":20.7,"ND2338":21.0,"ND2353":20.9,
"OT84-12":21.1,"OT85-5":21.5,"OT87-7":22.8,"OT87-8":22.9,"OT87-12":22.0}
# p10 MATURITY (relative offsets, days), 6 locs. McCall = anchor (printed dates -> DOY).
MAT_OFFSET = {
"Clay (0)":[23,4,9,16,5,4],"Maple Presto":[-14,-22,-14,-17,-16,-13],
"Maple Ridge":[-8,-12,-7,-7,-6,-7],"M84-93":[23,4,7,11,4,5],"M84-456":[22,5,7,13,4,5],
"ND867":[-1,-9,-10,-6,3,-1],"ND868":[0,-8,-2,-2,3,-1],"ND941":[18,1,0,5,4,4],
"ND2337":[0,-20,-13,-10,-1,-7],"ND2338":[0,-7,-6,-8,1,0],"ND2353":[-14,-18,-14,-14,-11,-8],
"OT84-12":[12,4,10,11,2,5],"OT85-5":[0,-8,-2,-3,4,-3],"OT87-7":[0,-2,-1,-4,-2,-3],
"OT87-8":[11,-7,-2,-4,-2,-2],"OT87-12":[-6,-21,-9,-9,-15,-11]}
# McCall anchor DOY from printed dates: Brandon 09/06, Crookston 08/24, Morris 08/17,
# Casselton 08/18, Elora 09/09, Ottawa 09/20  (1988 leap year: Aug31=244)
MCCALL_DOY = {"Brandon": 250, "Crookston": 237, "Morris": 230, "Casselton": 231,
              "Elora": 253, "Ottawa": 264}

DENSE = {  # trait -> (grid, mean, locs, units, tol_for_mean_reconcile)
    "YieldBuA": (YIELD, YIELD_MEAN, AGRO_LOCS, "bu/a", 0.8),
    "Lodging": (LODGING, LODGING_MEAN, AGRO_LOCS, "score", 0.15),
    "Height": (HEIGHT, HEIGHT_MEAN, AGRO_LOCS, "in", 0.8),
    "SeedQuality": (SEEDQUAL, SEEDQUAL_MEAN, AGRO_LOCS, "score", 0.15),
    "SeedSize": (SEEDSIZE, SEEDSIZE_MEAN, AGRO_LOCS, "g/100", 0.35),
    "Protein": (PROTEIN, PROTEIN_MEAN, COMP_LOCS, "%", 0.35),
    "Oil": (OIL, OIL_MEAN, COMP_LOCS, "%", 0.35),
}


def build_rows():
    rows, problems = [], []
    for ph, (grid, mean, locs, units, tol) in DENSE.items():
        for s in STRAINS:
            vals = grid[s]
            assert len(vals) == len(locs), f"{ph}/{s}: {len(vals)} vals for {len(locs)} locs"
            # reconcile row-mean vs printed Mean
            rm = sum(vals) / len(vals)
            if abs(rm - mean[s]) > tol:
                problems.append(f"{ph:11} {s:14} rowmean={rm:.2f} vs printed={mean[s]}  (Δ={rm-mean[s]:+.2f})")
            for loc, v in zip(locs, vals):
                rows.append(dict(Year=1988, TestType="UT", TestMG="00", Test="UT-00", Strain=s,
                                 City=loc, State=STATE[loc], Phenotype=ph, Value_num=float(v),
                                 Units=units, Source="PDF1988_UT00_reextract"))
    # Maturity: DOY = anchor(McCall) + offset ; McCall row = anchor DOY
    for loc in MAT_LOCS:
        rows.append(dict(Year=1988, TestType="UT", TestMG="00", Test="UT-00", Strain="McCall (00)",
                         City=loc, State=STATE[loc], Phenotype="Maturity", Value_num=float(MCCALL_DOY[loc]),
                         Units="date", Source="PDF1988_UT00_reextract"))
    for s, offs in MAT_OFFSET.items():
        for loc, off in zip(MAT_LOCS, offs):
            rows.append(dict(Year=1988, TestType="UT", TestMG="00", Test="UT-00", Strain=s,
                             City=loc, State=STATE[loc], Phenotype="Maturity",
                             Value_num=float(MCCALL_DOY[loc] + off), Units="date",
                             Source="PDF1988_UT00_reextract"))
    return pd.DataFrame(rows), problems


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    new, problems = build_rows()
    print(f"built {len(new)} clean 1988 UT-00 rows across {new.Phenotype.nunique()} traits")
    print(new.groupby("Phenotype").size().to_string())
    if problems:
        print("\n*** MEAN-RECONCILE MISMATCHES (transcription check) ***")
        print("\n".join(problems))
    else:
        print("\nrow-mean vs printed-Mean reconciliation: ALL PASS")

    if mode == "--apply":
        if problems:
            print("\nREFUSING to apply: fix transcription mismatches first.")
            sys.exit(1)
        rec = pd.read_csv(REC)
        bak = REC.with_suffix(".csv.bak_pre_1988ut00")
        if not bak.exists():
            rec.to_csv(bak, index=False)
            print(f"backup -> {bak.name}")
        mask = (rec.Year == 1988) & (rec.Test == "UT-00")
        print(f"dropping {int(mask.sum())} old 1988 UT-00 rows; adding {len(new)}")
        out = pd.concat([rec[~mask], new[rec.columns.intersection(new.columns).tolist()]
                         .reindex(columns=rec.columns)], ignore_index=True)
        out.to_csv(REC, index=False)
        print(f"wrote {REC.name}: {len(out)} rows total")


if __name__ == "__main__":
    main()
