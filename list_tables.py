import psycopg
conn = psycopg.connect("dbname=compliance_db user=postgres password=mysql@1703")
rows = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name").fetchall()
for r in rows:
    print(r[0])
