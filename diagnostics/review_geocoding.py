import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

ref = pd.read_csv("nust_locations_ref.csv")

print(f"=== Summary ===")
print(f"Total rows:          {len(ref)}")
print(f"Geocoded (lat set):  {ref['lat'].notna().sum()}")
print(f"Failed (lat=NULL):   {ref['lat'].isna().sum()}")
print(f"Needs verification:  {(ref['NeedsVerification']==1).sum()}")

print(f"\n=== Failed geocodes ===")
print(ref[ref['lat'].isna()][['City','State','Country']].to_string(index=False))

print(f"\n=== Likely duplicate state-abbreviation variants ===")
# Cities that appear more than once (same city, different state abbrev)
city_counts = ref.groupby('City')['State'].apply(list)
dups = city_counts[city_counts.apply(len) > 1]
for city, states in dups.items():
    rows = ref[ref['City'] == city][['City','State','lat','lon']]
    print(rows.to_string(index=False))
    print()

print(f"\n=== Possible wrong geocodes (extreme lat/lon for state) ===")
# Elkpoint SD got California coordinates
suspects = ref[ref['lat'].notna() & (
    ((ref['State'] == 'SD') & (ref['lat'] < 40)) |  # SD should be 42-46
    ((ref['State'] == 'MN') & (ref['lat'] < 43))
)]
print(suspects[['City','State','lat','lon','Geocoded_City']].to_string(index=False))

print(f"\n=== Research stations flagged for verification ({(ref['NeedsVerification']==1).sum()}) ===")
print(ref[ref['NeedsVerification']==1][['City','State','StationName','lat','lon']].to_string(index=False))
