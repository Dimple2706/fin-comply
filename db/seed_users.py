"""
Authentication bootstrap safety check.

FinComply deliberately does not install predictable demo usernames or
passwords. Create the first account through POST /auth/register (the existing
Create Account screen) or an approved deployment-specific administration
process.
"""

import os

import psycopg
from dotenv import load_dotenv


load_dotenv()


def main() -> None:
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "compliance_db"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD"),
    }
    with psycopg.connect(**db_config) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.users")
            user_count = cur.fetchone()[0]

    print(
        "Users table is ready. No predictable demo credentials were seeded. "
        f"Current account count: {user_count}."
    )


if __name__ == "__main__":
    main()
