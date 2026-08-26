# v2 Hash Migration Plan, Legacy Handling & Cutover Strategy

This document details the database schema and data migration design to support v2 cryptographically secure hashes (`v2:<64-hex-digest>`) across the Fin-Comply application.

---

## 1. Inventory of Hash Columns and Relationships

Every hash column in the schema is a pseudonymized identifier. They are currently configured as `character(12)` fields and have been migrated to `varchar(67)`:

| Table | Column | References / Relates To |
|---|---|---|
| `customer_master` | `customer_hash` | Primary Key for customer identity |
| `consent_records` | `consent_hash` | Primary Key for consent records |
| `consent_records` | `customer_hash` | `customer_master.customer_hash` |
| `consent_records` | `guardian_consent_hash` | Optional guardian consent record reference |
| `transaction_events` | `event_hash` | Primary Key for transactions |
| `transaction_events` | `customer_hash` | `customer_master.customer_hash` |
| `transaction_events` | `consent_hash` | `consent_records.consent_hash` |
| `transaction_events` | `third_party_hash` | `system_inventory.system_hash` |
| `access_logs` | `access_hash` | Primary Key for access log events |
| `access_logs` | `customer_hash` | `customer_master.customer_hash` |
| `access_logs` | `employee_hash` | Employee identity (hashed employee ID) |
| `access_logs` | `system_hash` | `system_inventory.system_hash` |
| `data_lifecycle` | `lifecycle_hash` | Primary Key for lifecycle rows |
| `data_lifecycle` | `customer_hash` | `customer_master.customer_hash` |
| `security_events` | `security_hash` | Primary Key for security logs |
| `security_events` | `customer_hash` | `customer_master.customer_hash` |
| `dsar_requests` | `dsar_hash` | Primary Key for DSAR logs |
| `dsar_requests` | `customer_hash` | `customer_master.customer_hash` |
| `policies` | `policy_hash` | Primary Key for retention policies |
| `system_inventory` | `system_hash` | Primary Key for components |

---

## 2. No-Mixing Rule & Version Boundaries

- **Persisted Hash Version**: Every audit run records a `hash_version` (either `'v1'` or `'v2'`) in the `audit_runs` table.
- **Strict Version Whitelisting**: The system enforces that all files in a single dataset or all runs for a single tenant must use the same hash version consistently.
- **Upload Validation**: Any file upload (`/analyze/upload`) containing a mix of `v1` (unprefixed or `v1:` prefixed) and `v2` (`v2:` prefixed) hashes will be immediately rejected with a `400 Bad Request` explaining that the tenant dataset must be migrated consistently.
- **Re-Analysis Validation**: Any re-analysis execution (`/analyze`) where the parent audit run used a different hash version than the currently configured engine default will be rejected to prevent mixing legacy and upgraded identities.

---

## 3. Legacy Handling & Compatibility Read Path

- **Legacy Reads**: Existing database rows containing legacy `v1` hashes (12 hex characters) remain readable. Type validation in `validate_hash_string` explicitly allows reading legacy `v1` hashes, ensuring no data corruption or join breakage during transitions.
- **No Silent Re-Hashing**: Old `v1` hashes are never silently re-hashed or updated to `v2` unless the raw source identifier is uploaded, which forces a clean server-side re-generation.

---

## 4. Rehashability Inventory: What is and is not Rehashable

- **What IS Rehashable**: Raw source identifiers (e.g. `CUST_123` or `ACC_999` uploaded in the raw identifier columns) are fully rehashable because we have the raw source data. They can be rehashed to `v2` on the server by running `hash_id` with the active tenant secret salt.
- **What IS NOT Rehashable**: Pre-hashed client-supplied keys (e.g. client uploading `customer_hash = 'v1:123456789012'` directly) are NOT rehashable because the raw identifier is unknown to the server. These must be preserved strictly as `v1` and are queried as-is.

---

## 5. Rollback & Failed Migration Recovery

- **Transactions**: All schema alterations are run inside a PostgreSQL transaction. If any part of the DDL alteration fails, the database automatically rolls back, leaving data intact.
- **Backup Command**:
  ```bash
  pg_dump -U postgres -d dpdp_db -F c -b -v -f /backups/pre_v2_hash_migration.backup
  ```
- **Recovery Command**:
  ```bash
  pg_restore -U postgres -d dpdp_db --clean --no-owner /backups/pre_v2_hash_migration.backup
  ```

---

## 6. Production Cutover Criteria

The application checks that the following are true before starting:
1. `ANONYMIZATION_HMAC_SECRET` is set to a strong key of at least 32 characters in production.
2. `check_database_migration_complete` queries `information_schema.columns` directly, confirming that `customer_master.customer_hash` has been expanded to a length of at least 67 characters.
