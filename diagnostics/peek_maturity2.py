import pandas as pd, re

df = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
mat = df[df["Phenotype"] == "Maturity"].copy()

def classify(v):
    if pd.isna(v) or str(v).strip() in ("", "--", "nan"):
        return "null"
    s = str(v).strip().rstrip("*").strip()
    if re.match(r'^2026-\d{2}-\d{2}', s):
        return "iso2026"
    if re.match(r'^\d{1,2}-\d{1,2}$', s):
        return "M-DD"
    try:
        float(s.lstrip("+"))
        return "integer_offset"
    except:
        return "special"

mat["fmt"] = mat["Value"].apply(classify)

print("=== Format breakdown ===")
print(mat["fmt"].value_counts())

print("\n=== By Test + Format ===")
print(mat.groupby(["Test","fmt"]).size().to_string())

print("\n=== Sample: iso2026 ===")
print(mat[mat["fmt"]=="iso2026"][["Test","City","Value"]].drop_duplicates("Value").head(10).to_string(index=False))

print("\n=== Sample: M-DD ===")
print(mat[mat["fmt"]=="M-DD"][["Test","City","Value"]].drop_duplicates("Value").head(15).to_string(index=False))

print("\n=== All unique: integer_offset ===")
vals = sorted(mat[mat["fmt"]=="integer_offset"]["Value"].unique(), key=lambda x: float(str(x).rstrip("*").lstrip("+")))
print(vals)

print("\n=== specials ===")
print(mat[mat["fmt"]=="special"][["Test","City","Strain","Value"]].to_string(index=False))
