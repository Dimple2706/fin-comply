-- Issue 15: Add missing users-table columns (safe, additive, no data loss).
--
-- Any teammate who hasn't touched this yet still has the OLDER users table
-- shape: (id, username, password_hash, role, full_name, is_active,
-- created_at). Without name/email/authorized_tenants, every registration
-- attempt crashes -- _ensure_users_table()'s CREATE UNIQUE INDEX on email
-- fails with "column email does not exist".
--
-- This migration ONLY adds columns. It never deletes or modifies an
-- existing row's identity, and it deliberately adds no DEFAULT value:
-- existing rows get NULL in the new columns, and a NULL safely passes the
-- CHECK constraints added later in issue_13_authentication_constraints.sql
-- (a NULL comparison evaluates to "unknown", not a violation) rather than
-- an empty-but-present value that would fail them outright.
--
-- Must run BEFORE issue_13_authentication_constraints.sql, which assumes
-- these columns already exist. See the MIGRATIONS list in run_migrations.py
-- for the enforced ordering.

ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(128);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(256);
ALTER TABLE users ADD COLUMN IF NOT EXISTS authorized_tenants TEXT[];

-- Recover what can be safely inferred from the old schema. Nothing is
-- invented for columns with no equivalent in the old shape (email, tenant).
-- Guarded: a database that never had the old full_name column (e.g. one
-- already recreated in the new shape) must not error on this step.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'full_name'
    ) THEN
        UPDATE users
        SET name = full_name
        WHERE name IS NULL AND full_name IS NOT NULL;
    END IF;
END $$;
