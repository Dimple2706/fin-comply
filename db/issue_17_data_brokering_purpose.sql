-- Issue 17: "data_brokering" is a deliberate, intentional processing_purpose
-- value used by 50 of the 315 synthetic company profiles (representing
-- companies that sell/broker personal data beyond any consented purpose --
-- a genuine DPDP-002 violation scenario), not a typo. The enum just never
-- had it added. Safe to apply repeatedly.
ALTER TYPE processing_purpose ADD VALUE IF NOT EXISTS 'data_brokering';
