"""Check why 39 patches are MISSING in F4U: city rename or strain drop."""
import sys, pandas as pd
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

f4u = pd.read_csv("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/NUST_Historical_Data/1980_Processing/Files4Upload/phenotypesTable1.csv")
f4u = f4u[f4u["Year"]==1980]
src = pd.read_csv("output_1980/validated/combined_1980_phenotypesTable_approved.csv")

# Strain presence check
src_strains = set(src["Strain"].unique())
f4u_strains = set(f4u["Strain"].unique())
print("Strains in src not in F4U:", sorted(src_strains - f4u_strains))
print("Strains in F4U not in src:", sorted(f4u_strains - src_strains))
print()

# City name mapping — show all cities in src and F4U
src_cities = sorted(src["City"].unique())
f4u_cities = sorted(f4u["City"].unique())
print("Src cities not in F4U:", [c for c in src_cities if c not in f4u_cities])
print()

# Spot-check the MISSING cases: look up by strain+test+city+phenotype directly
missing_samples = [
    ("UT-00","Fargo","Maple Presto","Height"),
    ("UT-00","Morden","Clay (0)","Height"),
    ("PT-II","Lafayette","Gnome","YieldBuA"),
    ("UT-I","Lafayette","Evans (0)","Height"),
    ("UT-III","S. Charleston","BSR 302","Lodging"),
    ("UT-IV","Manhattan","Union (IV)","Lodging"),
]
print("Direct F4U lookup for sample MISSING rows:")
for test,city,strain,ph in missing_samples:
    # try original city
    m1 = f4u[(f4u["Test"]==test)&(f4u["City"]==city)&(f4u["Strain"]==strain)&(f4u["Phenotype"]==ph)]
    # try West Lafayette
    city2 = "West Lafayette" if city=="Lafayette" else city
    m2 = f4u[(f4u["Test"]==test)&(f4u["City"]==city2)&(f4u["Strain"]==strain)&(f4u["Phenotype"]==ph)]
    val1 = m1["Value"].values[0] if len(m1) else "NOT FOUND"
    val2 = m2["Value"].values[0] if city2!=city and len(m2) else "-"
    print(f"  {test} {city:20s} {strain:20s} {ph:14s} -> orig={val1}  WL={val2}")
