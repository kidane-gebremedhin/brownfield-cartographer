import pandas as pd
df = pd.read_parquet("s3://bucket/raw.parquet")
df.to_csv("data/loaded.csv", index=False)
