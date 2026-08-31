-- Explicit applicability evidence for DPDP Act Section 10.
-- NULL is intentional: designation as a Significant Data Fiduciary must be
-- supplied as evidence and must not be inferred from tenant size or risk.
ALTER TABLE governance_config
    ADD COLUMN IF NOT EXISTS is_significant_data_fiduciary BOOLEAN;

COMMENT ON COLUMN governance_config.is_significant_data_fiduciary IS
    'Explicit SDF designation/applicability evidence. NULL means Section 10 cannot be assessed.';
