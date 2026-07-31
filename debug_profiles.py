import pandas as pd
df = pd.read_csv('data/training/training_metadata.csv')
for _, row in df[df['tenant_id'].isin(['GEN-251', 'GEN-266', 'GEN-267'])].iterrows():
    print(f"{row['tenant_id']} | Exposure: {row['total_penalty_exposure']} | Label: {row['label_name']} | Rules: {row['violated_rules']}")
