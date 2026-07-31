import psycopg
import os
import dotenv

dotenv.load_dotenv()

try:
    host = os.getenv("DB_HOST", "localhost")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "postgres")
    dbname = os.getenv("DB_NAME", "postgres")
    
    conn = psycopg.connect(f"dbname={dbname} user={user} password={password} host={host} port=5432")
    conn.autocommit = True
    cur = conn.cursor()

    print("Cleaning up duplicates from evaluation_results...")
    cur.execute("""
        DELETE FROM evaluation_results
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM evaluation_results
            GROUP BY tenant_id
        );
    """)
    print(f"Deleted {cur.rowcount} duplicate rows.")

    cur.execute("SELECT COUNT(*) FROM evaluation_results;")
    count = cur.fetchone()[0]
    print(f"Total remaining rows: {count}")

    conn.close()
except Exception as e:
    print(f"DB Error: {e}")
