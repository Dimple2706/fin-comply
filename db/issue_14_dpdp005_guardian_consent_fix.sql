-- Issue 14: DPDP-005 false-positive fix.
--
-- Two separate live-data bugs, found by testing DPDP-005 against real
-- uploaded data:
--
-- 1. clauses.max_penalty_crore for DPDP-005 was 250, but the correct
--    statutory maximum for children's-data violations (DPDP Act Section 9)
--    is 200 crore. data/dpdp_kb/clauses.json already had the correct value;
--    only the live database table had drifted.
--
-- 2. rules.evidence_signals for DPDP-005 referenced a field named
--    "guardian_consent_id", which does not exist on the evaluated row (the
--    actual column, after anonymization, is "guardian_consent_hash"). Since
--    the evaluator treats a missing field as NULL, the "is_null" check on
--    this signal always fired -- flagging every minor as a violation even
--    when a valid guardian consent record existed.
--
-- The actual VIOLATION/PASS decision for DPDP-005 is made in
-- src/agent_layer/outcome_evaluator.py, not by evidence_signals directly;
-- that code-level fix ships separately in this same change. This migration
-- only corrects the two pieces of live data that were wrong.

UPDATE clauses
SET max_penalty_crore = 200
WHERE clause_id = 'DPDP-005'
  AND max_penalty_crore <> 200;

UPDATE rules
SET evidence_signals = '[
  {
    "signal_id": "S1",
    "field": "is_minor",
    "operator": "equals",
    "value": true,
    "weight": 0.4,
    "description": "Customer is flagged as a minor — heightened obligations apply under Section 9"
  },
  {
    "signal_id": "S2",
    "field": "guardian_consent_hash",
    "operator": "is_null",
    "value": null,
    "weight": 0.4,
    "description": "No guardian consent record linked to this minor''s account"
  },
  {
    "signal_id": "S3",
    "field": "consent_status",
    "operator": "not_in",
    "value": ["active"],
    "weight": 0.2,
    "description": "Consent on file is not in active state even if a record exists"
  }
]'::jsonb,
    violation_threshold = 0.7
WHERE rule_id = 'DPDP-005';
