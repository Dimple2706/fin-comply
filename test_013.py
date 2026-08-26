import os
import pytest
import psycopg
import json
from src.agent_layer.signal_evaluator import evaluate_signal

def test_dpdp_013():
    db_url = os.environ.get("DPDP_TEST_DATABASE_URL")
    if not db_url:
        pytest.fail("DPDP_TEST_DATABASE_URL environment variable is not set!")
        
    with open('data/dpdp_kb/dpdp_rules.json') as f:
        data = json.load(f)
        rules = {r['rule_id']: r for r in data}

    from psycopg.rows import dict_row
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        rows = conn.execute("SELECT * FROM access_logs WHERE tenant_id='tenant_a'").fetchall()

    print(f'Rows: {len(rows)}')
    for row in rows:
        print(f'Row employee_role: {row.get("employee_role")}')
        for sig in rules['DPDP-013']['evidence_signals']:
            res = evaluate_signal('DPDP-013', sig['signal_id'], sig, row)
            if res:
                print(f"Row employee_role: {row.get('employee_role')} -> {sig['signal_id']}: {res}")
