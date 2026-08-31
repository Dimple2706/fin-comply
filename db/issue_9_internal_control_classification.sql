-- Policy checks are internal controls, not statutory DPDP penalty tiers.
-- This migration is safe to apply repeatedly and upgrades existing databases.
ALTER TYPE penalty_tier ADD VALUE IF NOT EXISTS 'INTERNAL_CONTROL';
