import psycopg
conn = psycopg.connect("dbname=compliance_db user=postgres password=mysql@1703")

# Check clauses table structure
rows = conn.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='clauses' ORDER BY ordinal_position").fetchall()
print("=== clauses table schema ===")
for r in rows:
    print(f"  {r[0]}: {r[1]}")

print("\n=== clauses table contents ===")
rows = conn.execute("SELECT * FROM clauses ORDER BY clause_id").fetchall()
for r in rows:
    print(r)

print("\n=== evaluation_results schema ===")
rows = conn.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='evaluation_results' ORDER BY ordinal_position").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

print("\n=== evaluation_results count ===")
print(conn.execute("SELECT COUNT(*) FROM evaluation_results").fetchone())

print("\n=== sample result_json keys ===")
import json
row = conn.execute("SELECT result_json FROM evaluation_results LIMIT 1").fetchone()
rj = row[0]
if isinstance(rj, str):
    rj = json.loads(rj)
print("Top-level keys:", list(rj.keys()))
print("violation_report[0] keys:", list(rj['violation_report'][0].keys()) if rj.get('violation_report') else "empty")
print("risk_insights keys:", list(rj.get('risk_insights', {}).keys()))
