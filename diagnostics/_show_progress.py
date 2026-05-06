import json, sys
data = json.load(open("output_1980/qc/qc_1980_values_progress.json", encoding="utf-8"))
print(f"Completed: {len(data['completed'])} combos")
all_disc = data["discrepancies"]
real = [d for d in all_disc if d["verdict"] == "discrepancy" and d["phenotype"] != "Maturity"]
maturity_fp = [d for d in all_disc if d["verdict"] == "discrepancy" and d["phenotype"] == "Maturity"]
ambiguous = [d for d in all_disc if d["verdict"] == "ambiguous"]
print(f"Total flagged:        {len(all_disc)}")
print(f"  discrepancy:        {len([d for d in all_disc if d['verdict']=='discrepancy'])}")
print(f"    (non-Maturity):   {len(real)}  <-- real candidates")
print(f"    (Maturity):       {len(maturity_fp)}  <-- false positives (Claude uses non-leap calendar)")
print(f"  ambiguous:          {len(ambiguous)}")
print()
print("=== REAL DISCREPANCY CANDIDATES (non-Maturity) ===")
for d in real:
    print(f"  {d['Test']}/{d['City']}_{d['State']} | {d['strain']} | {d['phenotype']} | "
          f"csv={d['csv_value']} pdf={d['pdf_value']} | {d.get('note','')}")
