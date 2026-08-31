-- ── Users table for Fin-Comply registration & login ──────────────────────────
-- Run this once against your PostgreSQL compliance_db.
-- Passwords are stored as bcrypt hashes — never plain-text.

CREATE TABLE IF NOT EXISTS public.users (
    id                  SERIAL          PRIMARY KEY,
    name                VARCHAR(128)    NOT NULL,
    email               VARCHAR(256)    NOT NULL UNIQUE,
    username            VARCHAR(64)     NOT NULL UNIQUE,
    password_hash       TEXT            NOT NULL,
    role                VARCHAR(32)     NOT NULL DEFAULT 'admin',
    authorized_tenants  TEXT[]          NOT NULL DEFAULT '{}',
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT users_name_valid CHECK (
        name = BTRIM(name) AND CHAR_LENGTH(name) BETWEEN 2 AND 128
    ),
    CONSTRAINT users_email_valid CHECK (
        email = LOWER(BTRIM(email))
        AND CHAR_LENGTH(email) BETWEEN 3 AND 254
        AND email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
    ),
    CONSTRAINT users_username_valid CHECK (
        username = BTRIM(username)
        AND username ~ '^[A-Za-z0-9_-]{3,64}$'
    ),
    CONSTRAINT users_password_hash_valid CHECK (password_hash ~ '^\$2[aby]\$'),
    CONSTRAINT users_role_valid CHECK (role IN ('admin', 'reviewer', 'auditor')),
    CONSTRAINT users_have_tenant CHECK (CARDINALITY(authorized_tenants) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS users_username_ci_key
    ON public.users (LOWER(username));
CREATE UNIQUE INDEX IF NOT EXISTS users_email_ci_key
    ON public.users (LOWER(email));
