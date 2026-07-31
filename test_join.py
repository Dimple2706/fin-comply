"""Test join - simplified output for first 5 rows only"""
import json
import csv
from collections import Counter

with open("data/generator_config.json") as f:
    configs = json.load(f)

profile_map = {c["tenant_id"]: c["profile_name"] for c in configs}
print(f"Total profiles in config: {len(profile_map)}")

with open("data/training/training_metadata.csv") as f:
    rows = list(csv.DictReader(f))

print(f"Total training rows: {len(rows)}")
print(f"Columns: {list(rows[0].keys())}")
print()

print("=== FIRST 5 ROWS JOINED ===")
for r in rows[:5]:
    real = profile_map.get(r["tenant_id"], "NOT_FOUND")
    print(f"  {r['tenant_id']:>8} | csv_profile={r['profile_name']:<10} | real_profile={real:<30} | label={r['label']} ({r['label_name']})")

print()

# Better company_type derivation using prefix
def derive_company_type(profile_name):
    pn = profile_name.lower()
    if pn.startswith("low_risk_fintech"):
        return "low_risk_fintech"
    elif pn.startswith("medium_risk_fintech"):
        return "medium_risk_fintech"
    elif pn.startswith("high_risk_fintech"):
        return "high_risk_fintech"
    elif pn.startswith("topup_compliant"):
        return "topup_compliant"
    elif pn.startswith("topup_high"):
        return "topup_high"
    elif pn.startswith("topup_critical"):
        return "topup_critical"
    else:
        return pn  # use name as-is for the original 25

types = []
for r in rows:
    pname = profile_map.get(r["tenant_id"], "unknown")
    types.append(derive_company_type(pname))

print("=== company_type DISTRIBUTION ===")
for ctype, count in sorted(Counter(types).items(), key=lambda x: -x[1]):
    print(f"  {ctype:<35} {count:>5} rows")
