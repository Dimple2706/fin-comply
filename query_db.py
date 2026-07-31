import psycopg, os
from dotenv import load_dotenv

load_dotenv()
conn = psycopg.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    dbname=os.getenv('DB_NAME', 'compliance_db'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD')
)
with conn.cursor() as cur:
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
    print('--- PUBLIC TABLES ---')
    for row in cur.fetchall():
        print(row[0])
    
    print('\n--- GOVERNANCE CONFIG SAMPLE ---')
    try:
        cur.execute('SELECT * FROM governance_config LIMIT 3;')
        cols = [desc.name for desc in cur.description]
        print(cols)
        for row in cur.fetchall():
            print(row)
    except Exception as e:
        print('Error reading governance_config:', e)
