import pandas as pd

tables = {
    "phenotypesTable": 3,
    "strainsTable":    4,
    "parentageTable":  4,
    "locationsTable":  4,
    "checksTable":     6,
}

for name, n in tables.items():
    df = pd.read_csv(f"output_1980/combined_1980_{name}.csv")
    print(f"\n=== {name} ({len(df)} rows) ===")
    print(f"Columns: {list(df.columns)}")
    print(df.head(n).to_string(index=False))
