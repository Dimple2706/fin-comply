-- Issue 16: Widen legacy 12-character hash columns to fit the real hash format.
--
-- Every *_hash column across the tenant-scoped tables was still sized
-- character(12), a leftover from an older, shorter hash scheme. The current
-- hashing implementation (src/anonymization/hasher.py: hash_id(), default
-- version "v2") produces "v2:" + 64 hex characters = 67 characters total.
-- This was never a generator bug -- it only surfaced when data with raw,
-- unhashed IDs (rather than IDs pre-hashed by a different generator into
-- the old short format) was ingested for the first time.
--
-- Safe by construction: this only WIDENS each column (12 -> 67), never
-- narrows it, so no existing value can be truncated or corrupted. Verified
-- against a full snapshot of real data before and after applying this.

ALTER TABLE access_logs
    ALTER COLUMN access_hash    TYPE VARCHAR(67),
    ALTER COLUMN customer_hash  TYPE VARCHAR(67),
    ALTER COLUMN employee_hash  TYPE VARCHAR(67),
    ALTER COLUMN system_hash    TYPE VARCHAR(67);

ALTER TABLE consent_records
    ALTER COLUMN consent_hash          TYPE VARCHAR(67),
    ALTER COLUMN customer_hash         TYPE VARCHAR(67),
    ALTER COLUMN guardian_consent_hash TYPE VARCHAR(67);

ALTER TABLE customer_master
    ALTER COLUMN customer_hash TYPE VARCHAR(67);

ALTER TABLE data_lifecycle
    ALTER COLUMN customer_hash  TYPE VARCHAR(67),
    ALTER COLUMN lifecycle_hash TYPE VARCHAR(67);

ALTER TABLE dsar_requests
    ALTER COLUMN customer_hash TYPE VARCHAR(67),
    ALTER COLUMN dsar_hash     TYPE VARCHAR(67);

ALTER TABLE policies
    ALTER COLUMN policy_hash TYPE VARCHAR(67);

ALTER TABLE security_events
    ALTER COLUMN customer_hash  TYPE VARCHAR(67),
    ALTER COLUMN security_hash  TYPE VARCHAR(67);

ALTER TABLE system_inventory
    ALTER COLUMN system_hash TYPE VARCHAR(67);

ALTER TABLE transaction_events
    ALTER COLUMN consent_hash     TYPE VARCHAR(67),
    ALTER COLUMN customer_hash    TYPE VARCHAR(67),
    ALTER COLUMN event_hash       TYPE VARCHAR(67),
    ALTER COLUMN third_party_hash TYPE VARCHAR(67);
