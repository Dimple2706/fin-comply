import os
import psycopg
import dotenv

dotenv.load_dotenv()

OPPORTUNITY_QUERIES = {
    "DPDP-001": "SELECT COUNT(*) FROM transaction_events WHERE tenant_id = %s",
    "DPDP-002": "SELECT COUNT(*) FROM transaction_events WHERE tenant_id = %s",
    "DPDP-004": "SELECT COUNT(*) FROM consent_records WHERE tenant_id = %s",
    "DPDP-005": "SELECT COUNT(*) FROM customer_master WHERE tenant_id = %s AND is_minor = TRUE",
    "DPDP-006": "SELECT COUNT(*) FROM transaction_events WHERE tenant_id = %s AND shared_with_third_party = TRUE",
    "DPDP-008": "SELECT COUNT(*) FROM security_events WHERE tenant_id = %s",
    "DPDP-013": "SELECT COUNT(*) FROM access_logs WHERE tenant_id = %s",
    "DPDP-014": "SELECT COUNT(*) FROM security_events WHERE tenant_id = %s AND breach_detected = TRUE",
    "DPDP-015": "SELECT COUNT(*) FROM transaction_events WHERE tenant_id = %s AND is_cross_border = TRUE",
    "DPDP-016": "SELECT COUNT(*) FROM system_inventory WHERE tenant_id = %s AND data_processor_type != 'internal'"
}

def migrate():
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "compliance_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD")

    with psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    ) as conn:
        with conn.cursor() as cur:
            print("1. Adding opportunity_query column to rules table if not exists...")
            cur.execute("ALTER TABLE rules ADD COLUMN IF NOT EXISTS opportunity_query TEXT;")
            conn.commit()
            print("  [OK] Column verified/added.")

            print("\n2. Updating opportunity_query definitions for subset/join rules...")
            for rid, query in OPPORTUNITY_QUERIES.items():
                cur.execute(
                    "UPDATE rules SET opportunity_query = %s WHERE rule_id = %s",
                    (query, rid)
                )
                print(f"  [OK] Set opportunity_query for {rid}")
            conn.commit()

            print("\n3. Verifying rules table configuration:")
            cur.execute("SELECT rule_id, primary_table, opportunity_query FROM rules ORDER BY rule_id")
            for r in cur.fetchall():
                q_summary = r[2][:40] + "..." if r[2] else "None (default to whole table)"
                print(f"  - {r[0]:12s} | Table: {r[1]:20s} | Opportunity Query: {q_summary}")

if __name__ == "__main__":
    migrate()
