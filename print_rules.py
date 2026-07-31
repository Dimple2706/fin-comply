import json
with open('data/dpdp_kb/dpdp_rules.json') as f:
    rules = json.load(f)
for r in rules:
    if r['rule_id'] in ['DPDP-002', 'DPDP-005', 'DPDP-011', 'DPDP-016']:
        print(f"{r['rule_id']} | Threshold: {r['violation_threshold']}")
        for s in r['evidence_signals']:
            print(f"  {s['signal_id']}: {s['field']} {s['operator']} {s['value']} (w={s['weight']})")
