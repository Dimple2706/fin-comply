# Authentication & Tenant Authorization Model

This document describes the design and configuration of the secure Authentication, Authorization, Endpoint Protection, and Input Validation systems.

## 1. Authentication & Hashing Policy

Fin-Comply enforces authentication using cryptographically secure tokens.
- **No Prefix Tokens**: Format-only tokens starting with prefixes (such as `admin:`, `reviewer:`, or `auditor:`) are strictly rejected.
- **Credential Hashing**: Only SHA-256 hashes of credential tokens are stored in the application's configuration. Raw tokens/secrets are never stored, logged, or checked in.
- **Constant-Time Comparison**: Comparison of computed token hashes uses `hmac.compare_digest` to prevent timing-attack leakage.
- **Fail-Closed Strategy**: If authentication configurations are missing or invalid, the system defaults to failing closed, preventing all access.

---

## 2. Authorization, Roles & Tenant Binding

Each credential is bound to a specific user identity containing:
- `username`: A unique identifier for audit logging.
- `role`: One of `admin`, `reviewer`, or `auditor`.
- `authorized_tenants`: An explicit whitelist of tenant IDs this credential has permission to access.

### Tenant Scope Rejection Policy (401 vs 403 vs 404)
To prevent cross-tenant resource leakage, the system enforces a strict lookup policy:
- **401 Unauthorized**: Returned for missing, invalid, or malformed credentials.
- **403 Forbidden**: Returned if a user provides valid credentials but requests access to a tenant ID that is not present in their `authorized_tenants` whitelist. This response is returned immediately before inspecting if a resource or run exists, ensuring a tenant cannot discover the existence of records for other tenants.
- **404 Not Found**: Returned only when the user is authenticated and authorized for the requested tenant, but the requested resource (such as a specific `audit_run_id`) does not exist for that tenant.

---

## 3. Protected Endpoints

All sensitive endpoints are protected by centralized authentication dependencies:
- `/analyze` (POST)
- `/analyze/upload` (POST)
- `/dashboard/{tenant_id}` (GET)
- `/report/history/{tenant_id}` (GET)
- `/report/pdf/{tenant_id}` (GET)
- `/rules`, `/rules/proposed`, `/rules/approve/{proposal_id}`, `/rules/reject/{proposal_id}`
- `/governance/bias-report` (GET)

---

## 4. Input Protection & Upload Limits

### Tenant ID Validation
- Maximum length is capped at **64 characters**.
- Only alphanumeric characters, dashes (`-`), and underscores (`_`) are allowed.
- Malformed inputs are rejected immediately with a `400 Bad Request` before invoking any database actions.

### File Upload Size Limits
- Capped at **5 MB** per file.
- Oversized files are rejected safely with a `400 Bad Request` prior to reading them into memory or writing to disk.

---

## 5. Local Test Setup & Provisioning

For development and test environments, credentials can be safely provisioned using the `FINCOMPLY_TEST_CREDENTIALS` environment variable, containing a JSON dictionary of SHA-256 hashed keys to user details.

Example:
```json
{
  "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8": {
    "username": "test_admin",
    "role": "admin",
    "authorized_tenants": ["tenant_a", "tenant_c"]
  }
}
```
*(Where the key represents the SHA-256 hash of the token `password`)*
