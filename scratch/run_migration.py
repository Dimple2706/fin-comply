import os
import psycopg

db_url = os.environ.get("DPDP_TEST_DATABASE_URL", "postgresql://postgres:rasika23@localhost:5432/dpdp_test_isolated")
print("Connecting to:", db_url)

conn = psycopg.connect(db_url)
try:
    with conn.cursor() as cur:
        # Check if column already exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_schema='public' 
                  AND table_name='consent_records' 
                  AND column_name='third_party_sharing_permitted'
            );
        """)
        exists = cur.fetchone()[0]
        if not exists:
            print("Applying migration...")
            with open("db/issue_6_consent_sharing_permitted.sql", "r") as f:
                cur.execute(f.read())
            conn.commit()
            print("Migration applied successfully!")
        else:
            print("Migration already applied.")
finally:
    conn.close()
