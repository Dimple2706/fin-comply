import os
import json
import psycopg
from psycopg.types.json import Jsonb

def sync_dpdp_015():
    db_url = os.environ.get("DPDP_TEST_DATABASE_URL")
    if db_url:
        conn = psycopg.connect(db_url)
    else:
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        dbname = os.getenv("DB_NAME", "tenant_db")
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "rasika23")
        conn = psycopg.connect(host=host, port=port, dbname=dbname, user=user, password=password)
        
    try:
        # Load approved country list from data/dpdp_kb/dpdp_rules.json
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rules_path = os.path.join(base_dir, "data", "dpdp_kb", "dpdp_rules.json")
        with open(rules_path, "r") as f:
            rules = json.load(f)
            
        dpdp_015_rule = next(r for r in rules if r["rule_id"] == "DPDP-015")
        evidence_signals = dpdp_015_rule["evidence_signals"]
        
        with conn.cursor() as cur:
            cur.execute('SET search_path TO public, "$user";')
            cur.execute("""
                UPDATE rules
                SET evidence_signals = %s
                WHERE rule_id = 'DPDP-015'
            """, (Jsonb(evidence_signals),))
            conn.commit()
            print("Successfully synchronized DPDP-015 rules to the database.")
    finally:
        conn.close()

if __name__ == "__main__":
    sync_dpdp_015()
