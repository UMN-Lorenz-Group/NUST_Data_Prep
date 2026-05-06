import pandas as pd, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ph = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")

# ── Missing YieldRank — are they truly absent or just zero rows? ─────────────
print("=== YieldRank presence by Test ===")
yr = ph[ph["Phenotype"] == "YieldRank"].groupby("Test")["Value"].count()
all_tests = sorted(ph["Test"].unique())
for t in all_tests:
    cnt = yr.get(t, 0)
    flag = "" if cnt > 0 else "  [MISSING]"
    print(f"  {t:<10} {cnt:>4} YieldRank rows{flag}")

# ── PT-III missing Maturity ──────────────────────────────────────────────────
print("\n=== Traits present in PT-III ===")
ptiii = ph[ph["Test"] == "PT-III"]
print(f"  Total rows: {len(ptiii)}")
print(f"  Phenotypes: {sorted(ptiii['Phenotype'].unique())}")

# ── UT-II strain count by trait ──────────────────────────────────────────────
print("\n=== UT-II strain counts by trait ===")
utii = ph[ph["Test"] == "UT-II"]
print(utii.groupby("Phenotype")["Strain"].nunique().sort_values().to_string())

# ── Detail on 'I' values ────────────────────────────────────────────────────
print("\n=== Rows with Value='I' in numeric phenotypes ===")
i_rows = ph[(ph["Value"].astype(str).str.strip() == "I") &
            (ph["Phenotype"].isin(["YieldBuA","YieldRank","Lodging","Height",
                                   "SeedQuality","SeedSize","Protein","Oil"]))]
print(i_rows[["id","Test","City","State","Strain","Phenotype","Value"]].to_string(index=False))
