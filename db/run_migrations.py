"""
db/run_migrations.py
=====================
Applies every pending incremental schema migration in db/ to the database
named by the current environment (DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
in .env), and records what has been applied in a `schema_migrations` table so
re-running this script is always safe (already-applied files are skipped).

Why this exists: several real fixes (E-04 through E-13 style issue fixes)
were written as db/issue_*.sql files but were never applied to every
developer's local database, causing "column does not exist" crashes that
had nothing to do with the application code. This script closes that gap.

Usage:
    python db/run_migrations.py

Run this after every `git pull` that touches db/, and as part of first-time
setup. It is also called automatically at API startup (see src/api/main.py)
so a stale database self-heals instead of crashing deep inside a request.
"""

import os
import sys
from pathlib import Path

import psycopg
import dotenv

dotenv.load_dotenv()

DB_DIR = Path(__file__).resolve().parent

# Ordered, explicit list of incremental migrations. New migrations must be
# appended here (order matters: earlier entries must not depend on later
# ones). Deliberately NOT a glob over db/*.sql: this directory also holds
# base-schema/bootstrap files (schema.sql, create_tables (1).sql,
# create_users_table.sql, create_proposed_rules_table.sql) that are for
# creating a brand-new empty database, not for patching an existing one,
# and must never be auto-applied here.
#
# issue_3_guardian_consent_migration.sql is intentionally EXCLUDED: it would
# overwrite the current, more-refined live DPDP-005 evidence_signals
# definition with an older, single-signal version. DPDP-005 evaluation has
# a known, separate bug (see project notes) — resolve that in code first,
# then decide deliberately whether issue_3 is still needed.
MIGRATIONS = [
    "fix_join_keys.sql",
    "issue_4_evidence_preservation_migration.sql",
    "issue_5_access_logs_system_relation.sql",
    "issue_6_consent_sharing_permitted.sql",
    "issue_8_audit_run_migration.sql",
    "issue_9_internal_control_classification.sql",
    "issue_10_transfer_assessment_evidence.sql",
    "issue_11_sdf_applicability.sql",
    "issue_12_access_authorization_evidence.sql",
    # issue_15 must run before issue_13: issue_13 assumes the users table
    # already has name/email/authorized_tenants columns, which issue_15 is
    # what actually adds them (older databases don't have them yet).
    "issue_15_users_table_missing_columns.sql",
    "issue_13_authentication_constraints.sql",
    "issue_14_dpdp005_guardian_consent_fix.sql",
    "issue_16_widen_hash_columns.sql",
    "issue_17_data_brokering_purpose.sql",
]


def _connect():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "compliance_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        autocommit=True,
    )


def _ensure_tracking_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.schema_migrations (
            filename    VARCHAR(256) PRIMARY KEY,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def run_pending_migrations() -> list[str]:
    """Apply every migration in MIGRATIONS not yet recorded as applied.

    Returns the list of filenames actually applied in this call (empty if
    the database was already up to date).
    """
    applied_now: list[str] = []
    with _connect() as conn:
        with conn.cursor() as cur:
            _ensure_tracking_table(cur)
            cur.execute("SELECT filename FROM public.schema_migrations")
            already_applied = {row[0] for row in cur.fetchall()}

            failed: list[str] = []
            for filename in MIGRATIONS:
                if filename in already_applied:
                    continue
                path = DB_DIR / filename
                if not path.exists():
                    print(f"[run_migrations] WARNING: {filename} listed but not found, skipping.")
                    continue
                sql = path.read_text(encoding="utf-8")
                print(f"[run_migrations] Applying {filename} ...")
                try:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO public.schema_migrations (filename) VALUES (%s)",
                        (filename,),
                    )
                except Exception as e:
                    # One migration's failure (e.g. it assumes a table shape
                    # this database doesn't have yet) must never block every
                    # migration listed after it -- each file is independent.
                    # A failed statement can leave the session in an aborted
                    # transaction; roll back so the next migration starts clean.
                    print(f"[run_migrations] FAILED: {filename}: {e}")
                    conn.rollback()
                    failed.append(filename)
                    continue
                applied_now.append(filename)
                print(f"[run_migrations] OK: {filename}")

    if failed:
        print(f"[run_migrations] {len(failed)} migration(s) FAILED and were skipped: {failed}")
        print("[run_migrations] These need manual investigation -- they were not marked applied and will be retried next run.")

    return applied_now


if __name__ == "__main__":
    applied = run_pending_migrations()
    if applied:
        print(f"\n[run_migrations] Applied {len(applied)} migration(s): {applied}")
    else:
        print("\n[run_migrations] Database already up to date. Nothing to do.")
