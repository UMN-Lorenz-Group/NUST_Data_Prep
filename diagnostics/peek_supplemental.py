import pandas as pd

for name, cols in [
    ("locationsTable", ["Year","Test","City","State","lat","lon","Conductor","PlantingDate","MaturityDate"]),
    ("checksTable",    ["Year","Test","Strain","OriginalStrain","Phenotype","RM"]),
    ("MetaTable",      None),
]:
    df = pd.read_csv(f"output_1980/combined_1980_{name}.csv")
    print(f"\n=== {name} ({len(df)} rows) ===")
    print(f"Columns: {list(df.columns)}")
    print(df.head(4).to_string(index=False))
    if name == "MetaTable":
        print(f"Tests: {sorted(df['Year-Test'].unique())}")
        print(f"Types: {sorted(df['Meta_data_type'].unique())}")
        print(f"Traits: {sorted(df['Trait'].unique())}")
