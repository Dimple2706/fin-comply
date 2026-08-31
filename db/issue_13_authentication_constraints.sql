BEGIN;

DO $$
BEGIN
    IF current_database() NOT IN (
        'compliance_db', 'dpdp_test_isolated', 'dpdp_test_isolated_temp'
    ) THEN
        RAISE EXCEPTION
            'Authentication migration refused for database %', current_database();
    END IF;
END $$;

-- Normalize values written by the older registration implementation before
-- adding constraints. Password hashes and tenant assignments are untouched.
UPDATE public.users
SET name = BTRIM(name),
    email = LOWER(BTRIM(email)),
    username = BTRIM(username);

CREATE UNIQUE INDEX IF NOT EXISTS users_username_ci_key
    ON public.users (LOWER(username));
CREATE UNIQUE INDEX IF NOT EXISTS users_email_ci_key
    ON public.users (LOWER(email));

-- Remove obsolete non-unique duplicates left by the earlier users-table DDL.
DROP INDEX IF EXISTS public.idx_users_username;
DROP INDEX IF EXISTS public.idx_users_email;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_name_valid'
    ) THEN
        ALTER TABLE public.users ADD CONSTRAINT users_name_valid CHECK (
            name = BTRIM(name) AND CHAR_LENGTH(name) BETWEEN 2 AND 128
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_email_valid'
    ) THEN
        ALTER TABLE public.users ADD CONSTRAINT users_email_valid CHECK (
            email = LOWER(BTRIM(email))
            AND CHAR_LENGTH(email) BETWEEN 3 AND 254
            AND email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_username_valid'
    ) THEN
        ALTER TABLE public.users ADD CONSTRAINT users_username_valid CHECK (
            username = BTRIM(username)
            AND username ~ '^[A-Za-z0-9_-]{3,64}$'
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_password_hash_valid'
    ) THEN
        ALTER TABLE public.users ADD CONSTRAINT users_password_hash_valid CHECK (
            password_hash ~ '^\$2[aby]\$'
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_role_valid'
    ) THEN
        ALTER TABLE public.users ADD CONSTRAINT users_role_valid CHECK (
            role IN ('admin', 'reviewer', 'auditor')
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_have_tenant'
    ) THEN
        ALTER TABLE public.users ADD CONSTRAINT users_have_tenant CHECK (
            CARDINALITY(authorized_tenants) > 0
        );
    END IF;
END $$;

COMMIT;
