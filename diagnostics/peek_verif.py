import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

v = pd.read_csv("output_1980/maturity_verification_1980.csv")
a = pd.read_csv("output_1980/maturity_anchors_1980.csv")

print("=== no_anchor rows ===")
na = v[v["Status"] == "no_anchor"]
print(na[["Strain","Test","City","OriginalMaturity","ComputedDOY"]].head(30).to_string(index=False))

print("\n=== Marshalltown anchors in anchor table ===")
print(a[a["City"].str.contains("arsh", case=False, na=False)].to_string(index=False))

print("\n=== Sample offset_converted rows ===")
conv = v[v["Status"] == "offset_converted"].head(20)
print(conv[["Strain","Test","City","OriginalMaturity","ComputedDOY"]].to_string(index=False))

print(f"\n=== DOY range for converted rows ===")
conv_all = v[v["ComputedDOY"].notna()]
print(f"min DOY: {conv_all['ComputedDOY'].min()}, max DOY: {conv_all['ComputedDOY'].max()}")
print(f"DOY 235 = Aug 23, DOY 281 = Oct 8 (expected range for 1980 harvest)")
