import os
import psycopg2
from psycopg2.extras import DictCursor

COLUMNS_TO_MIGRATE = [
    ("access_logs", ["access_hash", "customer_hash", "employee_hash", "system_hash"]),
    ("consent_records", ["consent_hash", "customer_hash", "guardian_consent_hash"]),
    ("customer_master", ["customer_hash"]),
    ("data_lifecycle", ["lifecycle_hash", "customer_hash"]),
    ("dsar_requests", ["dsar_hash", "customer_hash"]),
    ("policies", ["policy_hash"]),
    ("security_events", ["security_hash", "customer_hash"]),
    ("system_inventory", ["system_hash"]),
    ("transaction_events", ["event_hash", "customer_hash", "consent_hash", "third_party_hash"]),
]

def get_connection():
    db_url = os.getenv("DPDP_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        # Fallback to defaults
        db_name = os.getenv("DB_NAME", "dpdp_compliance")
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "rasika23")
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        return psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
    return psycopg2.connect(db_url)

def run_ddl_migration():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for table, cols in COLUMNS_TO_MIGRATE:
                for col in cols:
                    cur.execute(f"""
                        ALTER TABLE {table} 
                        ALTER COLUMN {col} TYPE varchar(67);
                    """)
            
            # Add hash_version column to audit_runs table
            cur.execute("""
                ALTER TABLE audit_runs 
                ADD COLUMN IF NOT EXISTS hash_version varchar(10) NOT NULL DEFAULT 'v1';
                ALTER TABLE audit_runs 
                ALTER COLUMN hash_version SET DEFAULT 'v2';
            """)

            # Log migration success
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_name varchar(100) PRIMARY KEY,
                    applied_at timestamp DEFAULT NOW()
                );
            """)
            cur.execute("""
                INSERT INTO schema_migrations (migration_name) 
                VALUES ('migrate_hash_v2')
                ON CONFLICT (migration_name) DO NOTHING;
            """)
            conn.commit()
            print("DDL migration completed successfully.")
    except Exception as e:
        conn.rollback()
        print(f"DDL migration failed: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    run_ddl_migration()
