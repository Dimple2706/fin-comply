BEGIN;

DO $$
BEGIN
    IF current_database() NOT IN ('compliance_db', 'dpdp_test_isolated', 'dpdp_test_isolated_temp') THEN
        RAISE EXCEPTION 'This migration must only be run on the local compliance_db, dpdp_test_isolated or dpdp_test_isolated_temp. Current database: %', current_database();
    END IF;
END $$;

-- 1. Add system_hash to access_logs (nullable, since we don't invent one if missing)
ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS system_hash character(12);

-- 2. Add pii_fields_justified to access_logs (nullable boolean)
ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS pii_fields_justified boolean;

COMMIT;
