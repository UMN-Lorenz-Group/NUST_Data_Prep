import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

v = pd.read_csv("output_1980/maturity_verification_1980.csv")

# Summary by test
print("=== Status by Test ===")
piv = v.groupby(["Test","Status"]).size().unstack(fill_value=0)
print(piv.to_string())

# DOY range per test
print("\n=== Computed DOY range per Test (offset_converted only) ===")
conv = v[v["Status"] == "offset_converted"]
for test, grp in conv.groupby("Test"):
    print(f"  {test}: DOY {int(grp['ComputedDOY'].min())}–{int(grp['ComputedDOY'].max())}  "
          f"(n={len(grp)})")

# Extreme values
print("\n=== DOY < 230 (possible outliers) ===")
low = v[v["ComputedDOY"].fillna(999) < 230]
print(low[["Strain","Test","City","OriginalMaturity","ComputedDOY"]].to_string(index=False))

print("\n=== DOY > 290 (possible outliers) ===")
high = v[v["ComputedDOY"].fillna(0) > 290]
print(high[["Strain","Test","City","OriginalMaturity","ComputedDOY"]].to_string(index=False))

# Marshalltown PT-II check
print("\n=== PT-II Marshalltown (no_anchor) ===")
marsh = v[(v["Test"]=="PT-II") & (v["City"]=="Marshalltown")]
print(marsh[["Strain","OriginalMaturity","ComputedDOY","Status"]].head(10).to_string(index=False))
