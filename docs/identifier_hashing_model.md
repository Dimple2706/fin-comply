# Identifier Hashing Model & Trust Boundary

This document outlines the hardened identifier hashing design, validator trust boundaries, secret configuration rules, and migration paths for the compliance application.

## 1. Trust Boundary & Upload Identifier Policy

- **Acceptable Inputs**: Uploads accept **both** raw identifiers and pre-hashed identifiers.
- **Trust Boundary & Validation Method**:
  - When raw identifiers are provided (e.g. `CUST-001`), the server anonymizes them internally using the server-side HMAC-SHA-256 canonical hashing function.
  - When pre-hashed identifiers are provided, they must strictly follow the format: `v2:<64 hex characters>` or `v1:<12 hex characters>` (legacy mode). The server strictly validates:
    - Hex format matching the version length.
    - Tenant-scoped verification (pre-hashed identifiers must be computed with the target tenant's scope and verified).
  - Malformed or invalid hash formats are rejected immediately with a `400 Bad Request`.

## 2. Secrets & HMAC Algorithm

- **HMAC Algorithm**: HMAC-SHA-256 is the canonical hashing algorithm.
- **Secret Source**: The salt/secret is fetched from the `ANONYMIZATION_HMAC_SECRET` environment variable.
- **Production Setup**: In production (`ENV = 'production'`), a strong secret (at least 32 bytes) is required. The system will fail to start safely if the secret is missing, weak, or malformed.
- **No Hardcoded/Default Secrets**: Default fallback salts are disabled in production.

## 3. Hash Length & Compatibility Plan

- **Canonical Hash Format (v2)**: Hex encoded SHA-256 HMAC prefixed with `v2:`, yielding a total of 67 characters: `v2:<64-character-hex-digest>`.
- **Legacy Compatibility (v1)**: Hex encoded HMAC truncated to 12 characters, prefixed with `v1:`: `v1:<12-character-hex-digest>`.
- **Silently Mixed Formats Prevention**: The database fields store hashes prefixed with their version identifier. Unprefixed legacy hashes are strictly prohibited in production.
- **Migration & Schema Limitations**: Since the current schema utilizes `character(12)` columns in some tables, a database schema migration is required to expand these columns to `character(67)`. Production use of the system is strictly blocked unless the migration is run and hashes are fully updated to the `v2:` format.
