import sys, pandas as pd
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

df = pd.read_csv("output_1980/qc/qc_1980_values.csv")

print("=== ISSUE-21: UT-III / S. Charleston / Lodging ===")
sc = df[(df["Test"]=="UT-III") & (df["City"]=="S. Charleston") & (df["phenotype"]=="Lodging") & (df["verdict"]=="discrepancy")]
for _, r in sc.sort_values("strain").iterrows():
    print(f"  {str(r['strain']):30s}  csv={r['csv_value']}  pdf={r['pdf_value']}")
print(f"\n  Total: {len(sc)} strains\n")

print("=== ISSUE-22: UT-IV / Manhattan / Lodging ===")
mn = df[(df["Test"]=="UT-IV") & (df["City"]=="Manhattan") & (df["phenotype"]=="Lodging") & (df["verdict"]=="discrepancy")]
for _, r in mn.sort_values("strain").iterrows():
    print(f"  {str(r['strain']):30s}  csv={r['csv_value']}  pdf={r['pdf_value']}")
print(f"\n  Total: {len(mn)} strains")

print("\n=== ISSUE-20: UT-I / Lafayette / all traits ===")
laf = df[(df["Test"]=="UT-I") & (df["City"]=="Lafayette") & (df["verdict"]=="discrepancy")]
for _, r in laf.sort_values(["phenotype","strain"]).iterrows():
    print(f"  {str(r['phenotype']):15s}  {str(r['strain']):30s}  csv={r['csv_value']}  pdf={r['pdf_value']}")
