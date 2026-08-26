import os
import psycopg
import dotenv
from pathlib import Path

dotenv.load_dotenv()

def apply_schema():
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "tenant_db")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD")

    print(f"Reading db/schema.sql...")
    schema_path = Path("db/schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Filter out client-side psql backslash commands (e.g. \restrict, \connect)
    sql_statements = []
    for line in lines:
        if line.strip().startswith("\\"):
            continue
        sql_statements.append(line)

    sql_content = "".join(sql_statements)

    print(f"Connecting to database '{dbname}' to apply schema...")
    with psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_content)
        conn.commit()
    print("Schema applied successfully!")

if __name__ == "__main__":
    apply_schema()
