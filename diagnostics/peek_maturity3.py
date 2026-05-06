import pandas as pd, re

df = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
mat = df[df["Phenotype"] == "Maturity"]

vals = mat["Value"].dropna().unique()

doy_vals = [v for v in vals if str(v).lstrip("+-").isdigit() and abs(float(str(v))) > 50]
rel_vals = [v for v in vals if str(v).lstrip("+-").isdigit() and abs(float(str(v))) <= 50]
other    = [v for v in vals if not str(v).lstrip("+-").isdigit()]

print(f"Total Maturity rows: {len(mat)}, null: {mat['Value'].isna().sum()}")
print(f"\nDOY values ({len(doy_vals)} unique): min={min(doy_vals)}, max={max(doy_vals)}")
print(f"Relative offsets ({len(rel_vals)} unique): {sorted(rel_vals, key=lambda x: float(x))}")
print(f"Other (non-numeric): {other}")

print("\nDOY range check (should be Aug-Oct for soybeans):")
doy_int = [int(v) for v in doy_vals]
print(f"  DOY {min(doy_int)} = day {min(doy_int)} of 1980")
print(f"  DOY {max(doy_int)} = day {max(doy_int)} of 1980")
from datetime import date
print(f"  Min date: {date(1980, 1, 1).__class__(1980, 1, 1).replace() if False else 'see below'}")
import datetime
for d in [min(doy_int), max(doy_int)]:
    dt = datetime.date(1980, 1, 1) + datetime.timedelta(days=d-1)
    print(f"  DOY {d} -> {dt}")
