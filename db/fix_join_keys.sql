-- fix_join_keys.sql
-- ==================
-- Standalone patch: sets the join_key column for every rule in the rules table.
-- Source of truth: data/dpdp_kb/dpdp_rules.json
-- Can be re-run safely at any time (idempotent UPDATE statements).
-- Run with:
--   psql -U postgres -d compliance_db -f db/fix_join_keys.sql

UPDATE rules SET join_key = 'consent_id'    WHERE rule_id = 'DPDP-001';
UPDATE rules SET join_key = 'consent_id'    WHERE rule_id = 'DPDP-002';
UPDATE rules SET join_key = NULL            WHERE rule_id = 'DPDP-003';
UPDATE rules SET join_key = NULL            WHERE rule_id = 'DPDP-004';
UPDATE rules SET join_key = 'customer_id'   WHERE rule_id = 'DPDP-005';
UPDATE rules SET join_key = 'consent_id'    WHERE rule_id = 'DPDP-006';
UPDATE rules SET join_key = 'system_id'     WHERE rule_id = 'DPDP-007';
UPDATE rules SET join_key = 'system_id'     WHERE rule_id = 'DPDP-008';
UPDATE rules SET join_key = NULL            WHERE rule_id = 'DPDP-009';
UPDATE rules SET join_key = 'customer_id'   WHERE rule_id = 'DPDP-010';
UPDATE rules SET join_key = NULL            WHERE rule_id = 'DPDP-011';
UPDATE rules SET join_key = 'tenant_id'     WHERE rule_id = 'DPDP-012';
UPDATE rules SET join_key = NULL            WHERE rule_id = 'DPDP-013';
UPDATE rules SET join_key = NULL            WHERE rule_id = 'DPDP-014';
UPDATE rules SET join_key = 'third_party_id' WHERE rule_id = 'DPDP-015';
UPDATE rules SET join_key = NULL            WHERE rule_id = 'DPDP-016';
