import os
import psycopg
import dotenv

dotenv.load_dotenv()

TENANT_TABLES = [
    "evaluation_results",
    "dsar_requests",
    "security_events",
    "data_lifecycle",
    "access_logs",
    "transaction_events",
    "consent_records",
    "customer_master",
    "policies",
    "system_inventory",
    "governance_config"
]

def reset_db():
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "compliance_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "mysql@1703")

    print(f"Connecting to database '{dbname}' on {host}:{port}...")
    with psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    ) as conn:
        with conn.cursor() as cur:
            for table in TENANT_TABLES:
                try:
                    cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
                    print(f"  [TRUNCATED] {table}")
                except Exception as e:
                    print(f"  [ERROR] Could not truncate {table}: {e}")
            conn.commit()

        print("\n--- Verifying Row Counts ---")
        with conn.cursor() as cur:
            for table in TENANT_TABLES:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"  {table:20s}: {count} rows")

if __name__ == "__main__":
    reset_db()
