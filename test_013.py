import psycopg
from src.agent_layer.signal_evaluator import evaluate_signal
import json

with open('data/dpdp_kb/dpdp_rules.json') as f:
    data = json.load(f)
    rules = {r['rule_id']: r for r in data}

conn = psycopg.connect('dbname=compliance_db user=postgres host=localhost')
from psycopg.rows import dict_row
conn.row_factory = dict_row
rows = conn.execute("SELECT * FROM access_logs WHERE tenant_id='tenant_a'").fetchall()

print(f'Rows: {len(rows)}')
for row in rows:
    print(f'Row employee_role: {row.get("employee_role")}')
    for sig in rules['DPDP-013']['evidence_signals']:
        res = evaluate_signal('DPDP-013', sig['signal_id'], sig, row)
        if res:
            print(f"Row employee_role: {row.get('employee_role')} -> {sig['signal_id']}: {res}")
