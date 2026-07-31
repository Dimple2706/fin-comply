"""
verify_migration.py
===================
Run after migrate_rules_to_db.py to confirm everything landed correctly.
Checks counts, FK integrity, signal weight sums, and prints a summary.

Usage:
    python db/verify_migration.py
"""

import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "tenant_db")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

def get_connection():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        row_factory=dict_row,
    )

def run(cur, sql, label):
    cur.execute(sql)
    rows = cur.fetchall()
    print(f"\n-- {label} --")
    for row in rows:
        print(dict(row))
    return rows

conn = get_connection()
cur  = conn.cursor()

# 1. Counts
run(cur, "SELECT COUNT(*) AS total_clauses FROM clauses;", "Clause count")
run(cur, "SELECT COUNT(*) AS total_rules  FROM rules;",   "Rule count")
run(cur, "SELECT COUNT(*) AS active_rules FROM rules WHERE enabled = TRUE;", "Active rules")

# 2. Rules per agent — confirms your agents are loaded
run(cur, """
    SELECT assigned_agent, COUNT(*) AS rule_count
    FROM rules GROUP BY assigned_agent ORDER BY assigned_agent;
""", "Rules per agent")

# 3. FK integrity — every rule's clause_id must exist in clauses
run(cur, """
    SELECT r.rule_id, r.clause_id,
           CASE WHEN c.clause_id IS NULL THEN 'MISSING' ELSE 'OK' END AS fk_status
    FROM rules r
    LEFT JOIN clauses c ON r.clause_id = c.clause_id
    ORDER BY r.rule_id;
""", "FK integrity check (all should be OK)")

# 4. Signal weight sums — catches any rule where weights don't sum to ~1.0
run(cur, """
    SELECT
        rule_id,
        ROUND(
            (SELECT SUM((sig->>'weight')::NUMERIC)
             FROM jsonb_array_elements(evidence_signals) AS sig)
        , 3) AS signal_weight_sum
    FROM rules
    ORDER BY rule_id;
""", "Signal weight sums (each should be 1.000 ± 0.02)")

# 5. Threshold sanity — risk_threshold must be below violation_threshold
run(cur, """
    SELECT rule_id, risk_threshold, violation_threshold,
           CASE WHEN risk_threshold < violation_threshold
                THEN 'OK' ELSE 'THRESHOLD ERROR' END AS threshold_status
    FROM rules ORDER BY rule_id;
""", "Threshold check (all should be OK)")

# 6. Full rule summary
run(cur, """
    SELECT r.rule_id, r.rule_name, r.severity, r.assigned_agent,
           r.enabled, r.version,
           jsonb_array_length(r.evidence_signals) AS signal_count
    FROM rules r ORDER BY r.rule_id;
""", "Full rule summary")

cur.close()
conn.close()
print("\nDONE Verification complete.")
