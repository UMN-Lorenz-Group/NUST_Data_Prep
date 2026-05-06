import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
df = pd.read_csv(ROOT / "output_1980/qc/qc_1980_values.csv")
pt4 = df[df["Test"] == "PT-IV"].copy()

print(f"PT-IV total discrepancies: {len(pt4)}")
print()
for city in sorted(pt4["City"].unique()):
    rows = pt4[pt4["City"] == city]
    print(f"--- {city} ({len(rows)}) ---")
    for _, r in rows.iterrows():
        print(f"  {r['strain']} | {r['phenotype']} | csv={r['csv_value']} pdf={r['pdf_value']} | {r['verdict']}")
        note = str(r.get("note", ""))
        if note and note != "nan":
            print(f"    -> {note}")
    print()
