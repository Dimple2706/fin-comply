-- DPDP Act Section 16 permits the Central Government to notify transfer
-- restrictions. It does not establish a static country allowlist.
ALTER TABLE transaction_events
    ADD COLUMN IF NOT EXISTS transfer_restriction_compliant BOOLEAN;

ALTER TABLE transaction_events
    ADD COLUMN IF NOT EXISTS transfer_assessment_reference VARCHAR(256);

COMMENT ON COLUMN transaction_events.transfer_restriction_compliant IS
    'Recorded result of the organisation assessment against applicable Section 16 restrictions; NULL means not assessable.';

COMMENT ON COLUMN transaction_events.transfer_assessment_reference IS
    'Evidence reference for the transfer restriction assessment; not a hardcoded country allowlist.';
