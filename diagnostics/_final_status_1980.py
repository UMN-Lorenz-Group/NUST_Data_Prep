import sys, pandas as pd
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
OUT = Path("output_1980")

print("=" * 60)
print("1980 OUTPUT TABLE STATUS")
print("=" * 60)

# phenotypesTable
ph = pd.read_csv(OUT / "combined_1980_phenotypesTable.csv")
loc_ph = ph[ph["City"] != "Mean"].dropna(subset=["City"])
print(f"\nphenotypesTable:     {len(ph)} rows")
print(f"  Location rows:     {len(loc_ph)}")
print(f"  Mean rows:         {len(ph)-len(loc_ph)}")
print(f"  Phenotypes:        {sorted(ph['Phenotype'].unique())}")
print(f"  Non-canon State:   {ph[~ph['State'].isin({'IL','IN','IA','MN','WI','MI','OH','MO','ND','SD','KS','NE','KY','MD','VA','PA','NJ','NY','DE','GA','NC','SC','TX','OK','AR','TN','AL','MS','LA','WA','OR','CA','ONT','MAN','SK','AB','BC','QC','NS','NB'}) & ph['State'].notna()]['State'].unique().tolist()}")

# locationsTable
lo = pd.read_csv(OUT / "combined_1980_locationsTable.csv")
print(f"\nlocationsTable:      {len(lo)} rows")
print(f"  lat/lon filled:    {lo['lat'].notna().sum()}/{len(lo)}")
print(f"  PlantingDate:      {lo['PlantingDate'].notna().sum()}/{len(lo)}")
print(f"  MaturityDate:      {lo['MaturityDate'].notna().sum()}/{len(lo)}")
print(f"  Conductor:         {lo['Conductor'].notna().sum()}/{len(lo)}")
null_pd = lo[lo["PlantingDate"].isna()][["Test","City","State"]]
if not null_pd.empty:
    print(f"  [FLAG] Missing PlantingDate ({len(null_pd)} rows — not in supplemental):")
    for _, r in null_pd.iterrows():
        print(f"    {r['Test']} / {r['City']} {r['State']}")

# strainsTable
st = pd.read_csv(OUT / "combined_1980_strainsTable.csv")
print(f"\nstrainsTable:        {len(st)} rows")
print(f"  Check flag:        {st['Check'].notna().sum()} checks")

# checksTable
ck = pd.read_csv(OUT / "combined_1980_checksTable.csv")
print(f"\nchecksTable:         {len(ck)} rows")
print(f"  RM filled:         {ck['RM'].notna().sum()}/{len(ck)}  [FLAG: predates numeric RM]")

# parentageTable
pa = pd.read_csv(OUT / "combined_1980_parentageTable.csv")
print(f"\nparentageTable:      {len(pa)} rows")

# MetaTable
mt = pd.read_csv(OUT / "combined_1980_MetaTable.csv")
print(f"\nMetaTable:           {len(mt)} rows")
print(f"  Traits:            {sorted(mt['Trait'].unique())}")

# maturityVerification
mv = pd.read_csv(OUT / "combined_1980_maturityVerification.csv")
print(f"\nmaturityVerification:{len(mv)} rows")
print(f"  DOY filled:        {mv['ComputedDOY'].notna().sum()}/{len(mv)}")
print(f"  Null (orig=NaN):   {mv[mv['OriginalMaturity'].isna()].shape[0]}  [expected missing]")

print("\n" + "=" * 60)
print("FLAGS SUMMARY")
print("=" * 60)
print("  1. PlantingDate NULL for 5 rows (not in 1980 supplemental PDF):")
print("       PT-IV/Portageville MO, UT-II/Harrow OH, UT-III/Ashland KS,")
print("       UT-III/Greenfield IL, UT-III/Sullivan IL")
print("       -> Manual lookup from printed PDF needed")
print("  2. Conductor NULL for all 159 rows")
print("       -> Genuinely not reported in 1980 NUST publication")
print("  3. checksTable RM NULL for all rows")
print("       -> 1980 predates numeric RM; separate historical MG->RM table needed")
print("  4. 194 null-DOY in maturityVerification (OriginalMaturity also NaN)")
print("       -> Locations that did not report maturity (expected for Brandon MAN,")
print("          Fargo ND, Corwith IA, etc.); NOT a computation failure")
