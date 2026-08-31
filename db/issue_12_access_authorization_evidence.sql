-- Explicit authorization evidence for access-control assessment.
-- Employee role names are descriptive and must not be used as a universal
-- legal allowlist. NULL means the event is not assessable for DPDP-013.
ALTER TABLE access_logs
    ADD COLUMN IF NOT EXISTS access_authorized BOOLEAN;

COMMENT ON COLUMN access_logs.access_authorized IS
    'Explicit business/access-control authorization decision for this access event; NULL means not assessable.';
