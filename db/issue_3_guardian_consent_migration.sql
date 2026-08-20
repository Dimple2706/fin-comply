BEGIN;

DO $$
BEGIN
    IF current_database() NOT IN ('compliance_db', 'dpdp_test_isolated') THEN
        RAISE EXCEPTION 'This migration must only be run on the local compliance_db or dpdp_test_isolated. Current database: %', current_database();
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS rules_backup_dpdp_005 AS
SELECT * FROM rules WHERE rule_id = 'DPDP-005';

UPDATE rules
SET 
    evidence_signals = '[
      {
        "signal_id": "guardian_consent_missing_or_invalid",
        "field": "guardian_consent_hash",
        "operator": "equals",
        "value": true,
        "weight": 1.0,
        "description": "Minor without valid active guardian consent"
      }
    ]'::jsonb,
    violation_threshold = 1.0
WHERE rule_id = 'DPDP-005';


COMMIT;