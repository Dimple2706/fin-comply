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
    cur = conn.cursor()

    print("--- Tenant Scores ---")
    cur.execute("SELECT tenant_id, risk_score, result_json->>'risk_tier' as risk_tier FROM evaluation_results ORDER BY risk_score DESC;")
    for row in cur.fetchall():
        print(f"{row[0]:<25} | Score: {row[1]:<5} | Tier: {row[2]}")
        
    print("\n--- Tier Distribution ---")
    cur.execute("SELECT result_json->>'risk_tier' as risk_tier, COUNT(*) as count FROM evaluation_results GROUP BY result_json->>'risk_tier' ORDER BY count DESC;")
    for row in cur.fetchall():
        print(f"Tier: {row[0]:<10} | Count: {row[1]}")

    conn.close()
except Exception as e:
    print(f"DB Error: {e}")
