import json, pandas as pd, sys
sys.stdout.reconfigure(encoding="utf-8")

data = json.load(open("output_1980/qc/qc_1980_values_progress.json", encoding="utf-8"))
print(f"Already completed: {len(data['completed'])} combos")
print("Completed:", [f"{c['test']}/{c['city']}_{c['state']}" for c in data['completed']])

df = pd.read_csv("output_1980/validated/combined_1980_phenotypesTable_approved.csv")
combos = df.groupby("Test")["City"].nunique().sort_index()
print(f"\nAll tests and location counts:")
for test, n in combos.items():
    print(f"  {test}: {n} locations")
print(f"\nTotal combos: {combos.sum()}")
print(f"Remaining after UT-00: {combos.sum() - combos.get('UT-00', 0)}")
