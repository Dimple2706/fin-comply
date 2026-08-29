BEGIN;

DO $$
BEGIN
    IF current_database() NOT IN ('compliance_db', 'dpdp_test_isolated', 'dpdp_test_isolated_temp') THEN
        RAISE EXCEPTION 'This migration must only be run on the local compliance_db, dpdp_test_isolated or dpdp_test_isolated_temp. Current database: %', current_database();
    END IF;
END $$;

-- 1. Remove chk_breach_fields constraint from security_events
ALTER TABLE security_events DROP CONSTRAINT IF EXISTS chk_breach_fields;

-- 2. Make system_inventory.system_name nullable
ALTER TABLE system_inventory ALTER COLUMN system_name DROP NOT NULL;

-- 3. Make policies.policy_name nullable
ALTER TABLE policies ALTER COLUMN policy_name DROP NOT NULL;

COMMIT;
