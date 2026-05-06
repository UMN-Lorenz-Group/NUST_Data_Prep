import pandas as pd
df = pd.read_csv("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/NUST_Historical_Data/1980_Processing/Files4Upload/phenotypesTable1.csv")
print("Years:", sorted(df["Year"].unique()))
print("1980 rows:", (df["Year"]==1980).sum())
print()

# City name differences: find all cities in F4U for 1980
src = pd.read_csv("output_1980/validated/combined_1980_phenotypesTable_approved.csv")
src_cities = set(src["City"].unique())
f4u_cities = set(df[df["Year"]==1980]["City"].unique())
print("Cities in src not in F4U:", sorted(src_cities - f4u_cities))
print("Cities in F4U not in src:", sorted(f4u_cities - src_cities))
