import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
pd.set_option('display.max_colwidth', 35)
df = pd.read_csv('output_1980/validated/combined_1980_phenotypes_review_flagged.csv')
print(f"Total flagged: {len(df)}\n")
print(df.to_string(index=False))
