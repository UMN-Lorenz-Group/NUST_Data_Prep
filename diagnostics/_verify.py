import pandas as pd, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
r = pd.read_csv("nust_locations_ref.csv")
print(f"Rows: {len(r)}")
print(f"NeedsVerification=1 remaining: {(r['NeedsVerification']==1).sum()}")
print(f"Source=modern_plotinfo_2024:   {(r['Source']=='modern_plotinfo_2024').sum()}")
print()
print(r[r["Source"]=="modern_plotinfo_2024"][["City","State","lat","lon"]].to_string(index=False))
