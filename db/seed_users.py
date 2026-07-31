"""
db/seed_users.py
================
Creates the users table and inserts three default dev/demo users.
Safe to run multiple times (uses INSERT ... ON CONFLICT DO NOTHING).
"""

import os
import sys

# Add project root so src.config is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg
from psycopg.rows import dict_row
from passlib.context import CryptContext  # pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20)  NOT NULL
                  CHECK (role IN ('admin', 'reviewer', 'viewer')),
    full_name     VARCHAR(100),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""

SEED_USERS = [
    ("admin",    "admin123",    "admin",    "System Administrator"),
    ("reviewer", "reviewer123", "reviewer", "Compliance Reviewer"),
    ("viewer",   "viewer123",   "viewer",   "Report Viewer"),
]

def main():
    print("Connecting to database...")
    db_config = {
        "host":     os.getenv("DB_HOST", "localhost"),
        "port":     int(os.getenv("DB_PORT", "5432")),
        "dbname":   os.getenv("DB_NAME", "compliance_db"),
        "user":     os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD"),
    }
    with psycopg.connect(**db_config, row_factory=dict_row) as conn:
        print("Creating users table...")
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()
        print("Table created (or already exists).")

        print("\nInserting default users...")
        for username, plain_password, role, full_name in SEED_USERS:
            existing = conn.execute(
                "SELECT id FROM users WHERE username = %s", [username]
            ).fetchone()
            if existing:
                print(f"  skipped (already exists): {username} ({role})")
            else:
                hashed = pwd_context.hash(plain_password)
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role, full_name)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [username, hashed, role, full_name],
                )
                print(f"  inserted: {username} ({role})")

        conn.commit()

        print("\nVerifying users in database:")
        rows = conn.execute(
            "SELECT id, username, role, full_name, is_active FROM users ORDER BY id"
        ).fetchall()

        print(f"{'ID':<5} {'Username':<12} {'Role':<10} {'Full Name':<25} {'Active'}")
        print("-" * 65)
        for r in rows:
            print(f"{r['id']:<5} {r['username']:<12} {r['role']:<10} {r['full_name']:<25} {r['is_active']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
