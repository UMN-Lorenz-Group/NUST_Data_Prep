import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

ck = pd.read_csv("output_1980/combined_1980_checksTable.csv")
print("=== checksTable ===")
print(ck[["Test","Strain","Phenotype"]].to_string(index=False))

# Also show maturity rows from phenotypesTable for check strains only
print("\n=== Check strain maturity values (sample) ===")
ph = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
mat = ph[ph["Phenotype"] == "Maturity"]
check_strains = ck["Strain"].unique()
ck_mat = mat[mat["Strain"].isin(check_strains)]
print(ck_mat[["Strain","Test","City","Value"]].sort_values(["Test","Strain","City"]).to_string(index=False))
