import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

ref = pd.read_csv("nust_locations_ref.csv")
print(f"nust_locations_ref.csv: {len(ref)} rows, {ref['lat'].isna().sum()} null coords")
print(f"\nBy state ({ref['State'].nunique()} states):")
print(ref.groupby("State").size().sort_values(ascending=False).to_string())
print(f"\nSample — stations needing verification (first 8):")
print(ref[ref["NeedsVerification"]==1][["City","State","lat","lon","StationName"]].head(8).to_string(index=False))
print(f"\nSample — non-station rows (first 8):")
print(ref[ref["NeedsVerification"]==0][["City","State","lat","lon"]].head(8).to_string(index=False))
print(f"\nPortageville variants:")
print(ref[ref["City"].str.contains("Portage", case=False, na=False)][["City","State","lat","lon","StationName","NeedsVerification"]].to_string(index=False))
