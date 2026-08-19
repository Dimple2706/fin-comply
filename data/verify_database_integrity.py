import os
import psycopg
import dotenv

dotenv.load_dotenv()

def verify():
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "compliance_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "mysql@1703")

    with psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    ) as conn:
        with conn.cursor() as cur:
            print("==================================================")
            print("DATABASE INTEGRITY & RE-INGESTION AUDIT (PHASE 3)")
            print("==================================================")

            # 1. Total row count across all tables
            print("\n1. Table Row Counts:")
            tables = [
                "governance_config", "system_inventory", "policies",
                "customer_master", "consent_records", "transaction_events",
                "access_logs", "data_lifecycle", "security_events", "dsar_requests"
            ]
            for t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"  - {t:20s}: {cur.fetchone()[0]} rows")

            # 2. Check for orphan foreign keys
            print("\n2. Foreign Key Integrity:")
            cur.execute("SELECT COUNT(*) FROM consent_records WHERE customer_hash NOT IN (SELECT customer_hash FROM customer_master)")
            print(f"  - Orphan consent_records customer FK: {cur.fetchone()[0]}")

            cur.execute("SELECT COUNT(*) FROM transaction_events WHERE customer_hash NOT IN (SELECT customer_hash FROM customer_master)")
            print(f"  - Orphan transaction customer FK:    {cur.fetchone()[0]}")

            cur.execute("SELECT COUNT(*) FROM transaction_events WHERE consent_hash IS NOT NULL AND consent_hash NOT IN (SELECT consent_hash FROM consent_records)")
            print(f"  - Orphan transaction consent FK:     {cur.fetchone()[0]}")

            cur.execute("SELECT COUNT(*) FROM transaction_events WHERE third_party_hash IS NOT NULL AND third_party_hash NOT IN (SELECT system_hash FROM system_inventory)")
            print(f"  - Orphan transaction 3rd party FK:   {cur.fetchone()[0]}")

            cur.execute("SELECT COUNT(*) FROM consent_records WHERE guardian_consent_hash IS NOT NULL AND guardian_consent_hash NOT IN (SELECT consent_hash FROM consent_records)")
            print(f"  - Orphan guardian consents:          {cur.fetchone()[0]}")

            # 3. DPA signed preservation check
            print("\n3. DPA Signed Preservation Check:")
            cur.execute("SELECT data_processor_type, dpa_signed, COUNT(*) FROM system_inventory GROUP BY data_processor_type, dpa_signed ORDER BY data_processor_type, dpa_signed")
            for r in cur.fetchall():
                print(f"  - Processor: {r[0]:25s} | dpa_signed: {str(r[1]):5s} | Count: {r[2]}")

            print("\n==================================================")
            print("ALL INTEGRITY CHECKS COMPLETED")
            print("==================================================")

if __name__ == "__main__":
    verify()
