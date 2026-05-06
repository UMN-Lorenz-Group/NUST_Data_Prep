import pandas as pd
df = pd.read_csv("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/NUST_Historical_Data/1980_Processing/Files4Upload/phenotypesTable1.csv")
print("Columns:", df.columns.tolist())
print("Shape:", df.shape)
print(df.head(8).to_string())
