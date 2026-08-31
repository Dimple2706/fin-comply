-- Migration: Add third_party_sharing_permitted to consent_records
ALTER TABLE public.consent_records
    ADD COLUMN IF NOT EXISTS third_party_sharing_permitted boolean;
