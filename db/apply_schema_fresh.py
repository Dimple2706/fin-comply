import os
import psycopg2
import sys

def apply_sql_file(cur, filepath):
    print(f"Applying SQL file: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # Filter out lines starting with backslash (psql commands)
    filtered_lines = [line for line in lines if not line.strip().startswith('\\')]
    sql = "SET search_path = public;\n" + "".join(filtered_lines)
    try:
        cur.execute(sql)
    except Exception as e:
        # Ignore "already exists" errors (duplicate table, column, type, relation, etc.)
        err_msg = str(e).lower()
        if "already exists" in err_msg or "duplicate" in err_msg:
            print(f"  [WARN] Ignored duplicate schema object error in {filepath}: {e}")
        else:
            raise e

def main():
    db_url = os.getenv("DPDP_TEST_DATABASE_URL")
    if not db_url:
        print("Error: DPDP_TEST_DATABASE_URL is not set.")
        sys.exit(1)
        
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            # 1. Clean existing tables/schema by dropping them
            # Let's get all tables and drop them.
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
            """)
            tables = [row[0] for row in cur.fetchall()]
            for table in tables:
                if table != 'spatial_ref_sys': # Skip spatial system tables if any
                    cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            
            # Drop views if any
            cur.execute("""
                SELECT table_name FROM information_schema.views 
                WHERE table_schema = 'public';
            """)
            views = [row[0] for row in cur.fetchall()]
            for view in views:
                cur.execute(f"DROP VIEW IF EXISTS {view} CASCADE;")

            # Drop custom enum types
            cur.execute("""
                SELECT t.typname FROM pg_type t 
                JOIN pg_namespace n ON n.oid = t.typnamespace 
                WHERE n.nspname = 'public' AND t.typtype = 'e';
            """)
            types = [row[0] for row in cur.fetchall()]
            for typ in types:
                cur.execute(f"DROP TYPE IF EXISTS public.{typ} CASCADE;")
            
            conn.commit()
            print("Dropped all tables/views/types successfully.")

            # 2. Run base schema and initial rules/clauses tables
            apply_sql_file(cur, "db/schema.sql")
            apply_sql_file(cur, "db/create_tables (1).sql")
            conn.commit()

            # 3. Apply versioned migration DDLs in order (except fix_join_keys which requires seeded data)
            migrations = [
                "db/create_proposed_rules_table.sql",
                "db/issue_3_guardian_consent_migration.sql",
                "db/issue_4_evidence_preservation_migration.sql",
                "db/issue_5_access_logs_system_relation.sql",
                "db/issue_6_consent_sharing_permitted.sql",
                "db/issue_8_audit_run_migration.sql"
            ]
            for mig in migrations:
                apply_sql_file(cur, mig)
                conn.commit()
            
            print("Base schema and all migrations applied successfully.")

    except Exception as e:
        conn.rollback()
        print(f"Error during schema setup: {e}")
        sys.exit(1)
    finally:
        conn.close()

    # 4. Apply python-based DDL migration
    print("Running DDL migration migrate_hash_v2.py...")
    import db.migrate_hash_v2 as migrate_hash_v2
    migrate_hash_v2.run_ddl_migration()

    # 5. Run seeds
    print("Running data seeds...")
    import subprocess

    seeds = [
        "db/migrate_rules_to_db.py",
        "db/migrate_policy_rules.py",
        "db/sync_dpdp_015_rules.py",
        "db/migrate_opportunity_queries.py",
        "db/seed_users.py"
    ]
    # Set env vars for seeds
    env = os.environ.copy()
    env["DB_NAME"] = "dpdp_test_isolated" # ensure they connect to test DB

    for seed in seeds:
        print(f"Running seed: {seed}")
        subprocess.check_call([sys.executable, seed], env=env)

    # 6. Apply fix_join_keys.sql to update seeded rules
    print("Applying fix_join_keys.sql updates...")
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            apply_sql_file(cur, "db/fix_join_keys.sql")
            conn.commit()
        print("fix_join_keys.sql updates applied successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error applying fix_join_keys.sql: {e}")
        sys.exit(1)
    finally:
        conn.close()

    print("Database seeding completed successfully.")

if __name__ == "__main__":
    main()
