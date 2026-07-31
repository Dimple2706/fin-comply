import json, pandas as pd
from pathlib import Path

metadata = pd.read_csv('data/training/training_metadata.csv')
config = json.loads(Path('data/generator_config.json').read_text())

profiles = pd.DataFrame(config)[
  ['tenant_id', 'profile_name']
].rename(columns={'profile_name': 'company_type'})

original_25 = [f'GEN-{str(i).zfill(3)}' for i in range(1, 26)]

subset = metadata[
  metadata['tenant_id'].isin(original_25)
].merge(profiles, on='tenant_id', how='left')

print(f"Rows in subset: {len(subset)}")
print(subset[['tenant_id', 'company_type',
              'label', 'label_name']].to_string())

print("\nLabel distribution in subset:")
print(subset['label_name'].value_counts())
