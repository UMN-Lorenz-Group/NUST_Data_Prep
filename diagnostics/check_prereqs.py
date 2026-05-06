from pathlib import Path

green = Path("R:/NUST_Historical_Data/Green-20260427T181938Z-3-001/Green")
print("R: accessible:", green.exists())
if green.exists():
    dirs = sorted(d for d in green.iterdir() if d.is_dir())
    print(f"Year dirs: {len(dirs)}, sample: {[d.name for d in dirs[:3]]}")

locs = sorted(Path(".").glob("output_*/combined_*_locationsTable.csv"))
print(f"\nlocationsTable files found: {len(locs)}")
for l in locs:
    import pandas as pd
    df = pd.read_csv(l)
    print(f"  {l} — {len(df)} rows, unique cities: {df['City'].nunique()}")
