"""Pull all remaining confirmed-patch rows from qc_1980_values.csv."""
import sys, pandas as pd
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

df = pd.read_csv("output_1980/qc/qc_1980_values.csv")
disc = df[df["verdict"] == "discrepancy"].copy()

def show(label, mask):
    rows = disc[mask].sort_values(["strain","phenotype"])
    print(f"\n=== {label} ({len(rows)} cells) ===")
    for _, r in rows.iterrows():
        print(f"  {r['Test']:6s}  {r['City']:25s}  {str(r['strain']):30s}  {r['phenotype']:15s}  csv={r['csv_value']}  pdf={r['pdf_value']}")

# ISSUE-1: UT-00 Height at Fargo and Morden
show("ISSUE-1: UT-00 Height Fargo+Morden",
     (disc["Test"]=="UT-00") & (disc["phenotype"]=="Height") & (disc["City"].isin(["Fargo","Morden"])))

# ISSUE-3: UT-00 SeedQuality
show("ISSUE-3: UT-00 SeedQuality",
     (disc["Test"]=="UT-00") & (disc["phenotype"]=="SeedQuality"))

# ISSUE-4: UT-00 SeedSize
show("ISSUE-4: UT-00 SeedSize",
     (disc["Test"]=="UT-00") & (disc["phenotype"]=="SeedSize"))

# ISSUE-6: PT-II Lafayette + Urbana Yield
show("ISSUE-6: PT-II Yield Lafayette+Urbana",
     (disc["Test"]=="PT-II") & (disc["City"].isin(["Lafayette","Urbana"])) & (disc["phenotype"]=="YieldBuA"))

# ISSUE-7: PT-III
show("ISSUE-7: PT-III",
     (disc["Test"]=="PT-III") & (disc["City"].isin(["Lafayette","Ottumwa"])))

# ISSUE-23: UT-IV Powhattan Yield
show("ISSUE-23: UT-IV Powhattan Yield",
     (disc["Test"]=="UT-IV") & (disc["City"]=="Powhattan") & (disc["phenotype"]=="YieldBuA"))

# ISSUE-24: UT-II Harrow Yield
show("ISSUE-24: UT-II Harrow Yield",
     (disc["Test"]=="UT-II") & (disc["City"]=="Harrow") & (disc["phenotype"]=="YieldBuA"))

# ISSUE-25: scattered cells (all remaining discrepancies not already covered)
covered_tests  = {"UT-00","UT-III","UT-IV","UT-I","PT-II","PT-III","PT-IV"}
covered_cities = {"S. Charleston","Manhattan","Lafayette","Powhattan","Harrow","Fargo","Morden","Ottumwa"}
issue25_mask = (
    ~(
        ((disc["Test"]=="UT-00") & (disc["phenotype"].isin(["Height","SeedQuality","SeedSize"])) & (disc["City"].isin(["Fargo","Morden","Ashland","Rosemount"]))) |
        ((disc["Test"]=="PT-II") & (disc["City"].isin(["Lafayette","Urbana"])) & (disc["phenotype"]=="YieldBuA")) |
        ((disc["Test"]=="PT-III") & (disc["City"].isin(["Lafayette","Ottumwa"]))) |
        ((disc["Test"]=="PT-IV") & (disc["City"]=="Lexington") & (disc["phenotype"]=="Oil")) |
        ((disc["Test"]=="UT-I")  & (disc["City"]=="Lafayette")) |
        ((disc["Test"]=="UT-III") & (disc["City"]=="S. Charleston") & (disc["phenotype"]=="Lodging")) |
        ((disc["Test"]=="UT-IV") & (disc["City"]=="Manhattan") & (disc["phenotype"]=="Lodging")) |
        ((disc["Test"]=="UT-IV") & (disc["City"]=="Powhattan") & (disc["phenotype"]=="YieldBuA")) |
        ((disc["Test"]=="UT-II") & (disc["City"]=="Harrow") & (disc["phenotype"]=="YieldBuA"))
    )
)
show("ISSUE-25 + remaining discrepancies", issue25_mask)
