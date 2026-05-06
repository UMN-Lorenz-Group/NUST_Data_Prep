import pandas as pd
src = pd.read_csv("output_1980/validated/combined_1980_phenotypesTable_approved.csv")
f4u = pd.read_csv("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/NUST_Historical_Data/1980_Processing/Files4Upload/phenotypesTable1.csv")
f4u = f4u[f4u["Year"]==1980]

print("Phenotypes in src:", sorted(src["Phenotype"].unique()))
print("Phenotypes in F4U:", sorted(f4u["Phenotype"].unique()))
print()
print("Src rows by phenotype:")
print(src.groupby("Phenotype").size().sort_index())
print()
print("F4U rows by phenotype:")
print(f4u.groupby("Phenotype").size().sort_index())
print()
# Check if F4U has multiple Units per phenotype
print("F4U Units per phenotype:")
print(f4u.groupby(["Phenotype","Units"]).size())
