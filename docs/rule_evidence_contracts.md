# DPDP Rules and Evidence Contracts

This document specifies the rule contracts for all active compliance rules in the system.

## Regulation & Risk Rules

---

### DPDP-001: Invalid or Missing Consent Before Processing
* **Rule ID**: DPDP-001
* **Required Tables & Fields**:
  - `consent_records`: `consent_hash`, `tenant_id`, `consent_status`, `expiry_date`, `consented_purpose`, `is_bundled`
  - `transaction_events`: `event_hash`, `tenant_id`, `consent_hash`, `processing_purpose`, `event_date`
* **Join Keys**:
  - `consent_records.consent_hash = transaction_events.consent_hash` AND `consent_records.tenant_id = transaction_events.tenant_id`
* **Evaluation Cases**:
  - **PASS**: `consent_status` is 'active', `expiry_date` >= `event_date`, `consented_purpose` matches `processing_purpose`, and `is_bundled` is `False`.
    - *Concrete Example*: `consent_status = 'active'`, `expiry_date = '2027-08-23'`, `event_date = '2026-08-23'`, `consented_purpose = 'loan_processing'`, `processing_purpose = 'loan_processing'`, `is_bundled = False`.
  - **VIOLATION**: Outdated, expired, mismatched, or bundled consent (score >= `0.6`).
    - *Concrete Example*: `consent_status = 'active'`, `expiry_date = '2025-08-23'` (expired relative to event date `2026-08-23`), or `consented_purpose = 'loan_processing'` and `processing_purpose = 'marketing'` (mismatch).
  - **NOT_APPLICABLE**: No matching transaction events for the tenant.
    - *Concrete Example*: Query returns 0 transaction rows for the evaluation tenant.
  - **NOT_ASSESSABLE**: Missing critical fields (`consent_status` or `event_date` is `NULL`).
    - *Concrete Example*: `consent_status = NULL` or `event_date = NULL`.
* **Finding Identity / Record ID**: `event_hash` (or `consent_hash`).

---

### DPDP-002: Processing Beyond Stated Purpose
* **Rule ID**: DPDP-002
* **Required Tables & Fields**:
  - `transaction_events`: `event_hash`, `tenant_id`, `consent_hash`, `processing_purpose`
  - `consent_records`: `consent_hash`, `tenant_id`, `consented_purpose`, `consent_version`, `notice_provided`
  - `policies`: `tenant_id`, `policy_type` ('privacy_policy'), `policy_value_numeric` (current policy version)
* **Join Keys**:
  - `consent_records.consent_hash = transaction_events.consent_hash` AND `consent_records.tenant_id = transaction_events.tenant_id`
* **Evaluation Cases**:
  - **PASS**: Processing purpose matches consented purpose, notice was provided, and consent version matches policy version.
    - *Concrete Example*: `consented_purpose = 'loan_processing'`, `processing_purpose = 'loan_processing'`, `notice_provided = True`, `consent_version = 'v1.0'`, policy version = `'v1.0'`.
  - **VIOLATION**: Purpose mismatched, or no notice provided, or outdated consent version (score >= `0.6`).
    - *Concrete Example*: `notice_provided = False` or `consent_version = 'v1.0'` and policy version = `'v2.0'` (outdated).
  - **NOT_APPLICABLE**: No transaction events.
    - *Concrete Example*: Query returns 0 rows.
  - **NOT_ASSESSABLE**: Missing consent or policy configurations.
    - *Concrete Example*: `notice_provided = NULL` or `consent_version = NULL`.
* **Finding Identity / Record ID**: `event_hash`.

---

### DPDP-003: Retention Beyond Allowed Period
* **Rule ID**: DPDP-003
* **Required Tables & Fields**:
  - `data_lifecycle`: `lifecycle_hash`, `tenant_id`, `retention_expiry_date`, `retention_status`, `legal_hold_flag`
* **Join Keys**: None (single table).
* **Evaluation Cases**:
  - **PASS**: Retention expiry date in future, and legal hold is not required.
    - *Concrete Example*: `retention_expiry_date = '2027-08-23'`, `retention_status = 'active'`, `event_date = '2026-08-23'`, `legal_hold_flag = False`.
  - **VIOLATION**: Expiry date has passed, or retention status is expired/pending, and `legal_hold_flag` is `False`.
    - *Concrete Example*: `retention_expiry_date = '2025-08-23'` (past) and `legal_hold_flag = False`.
  - **NOT_APPLICABLE**: No data lifecycle rows.
    - *Concrete Example*: Query returns 0 rows.
  - **NOT_ASSESSABLE**: `retention_expiry_date` is `NULL`.
    - *Concrete Example*: `retention_expiry_date = NULL`.
* **Finding Identity / Record ID**: `lifecycle_hash`.

---

### DPDP-004: Missing Notice to Data Principal
* **Rule ID**: DPDP-004
* **Required Tables & Fields**:
  - `consent_records`: `consent_hash`, `tenant_id`, `notice_provided`, `consent_channel`
* **Join Keys**: None (single table).
* **Evaluation Cases**:
  - **PASS**: `notice_provided` is `True` and consent channel is explicit/valid.
    - *Concrete Example*: `notice_provided = True`, `consent_channel = 'app'`.
  - **VIOLATION**: `notice_provided` is `False`, or implicit/pre-ticked/inferred channel is used.
    - *Concrete Example*: `notice_provided = False` or `consent_channel = 'pre_ticked'`.
  - **NOT_APPLICABLE**: No consent records.
    - *Concrete Example*: Query returns 0 rows.
  - **NOT_ASSESSABLE**: `notice_provided` is `NULL`.
    - *Concrete Example*: `notice_provided = NULL`.
* **Finding Identity / Record ID**: `consent_hash`.

---

### DPDP-005: Children's Data Without Guardian Consent
* **Rule ID**: DPDP-005
* **Required Tables & Fields**:
  - `customer_master`: `customer_hash`, `tenant_id`, `is_minor`
  - `consent_records`: `consent_hash`, `customer_hash`, `tenant_id`, `consent_status`, `guardian_consent_hash`
* **Join Keys**:
  - `customer_master.customer_hash = consent_records.customer_hash` AND `customer_master.tenant_id = consent_records.tenant_id`
  - Join on minor/guardian consent `guardian_consent_hash` to target `consent_records.consent_hash` AND `tenant_id`.
* **Evaluation Cases**:
  - **PASS**: Customer is not a minor OR minor has a valid, active guardian consent.
    - *Concrete Example*: `is_minor = True`, `guardian_consent_hash = 'con_guard'`, `guardian_consent_status = 'active'`, `consent_status = 'active'`.
  - **VIOLATION**: Minor is missing guardian consent, or guardian consent is inactive.
    - *Concrete Example*: `is_minor = True`, `guardian_consent_hash = NULL` or `guardian_consent_status = 'inactive'`.
  - **NOT_APPLICABLE**: Customer is an adult.
    - *Concrete Example*: `is_minor = False`.
  - **NOT_ASSESSABLE**: `is_minor` is `NULL`.
    - *Concrete Example*: `is_minor = NULL`.
* **Finding Identity / Record ID**: `customer_hash`.

---

### DPDP-006: Unauthorised Third-Party Data Sharing
* **Rule ID**: DPDP-006
* **Required Tables & Fields**:
  - `transaction_events`: `event_hash`, `tenant_id`, `consent_hash`, `shared_with_third_party`, `third_party_hash`, `is_cross_border`
  - `consent_records`: `consent_hash`, `tenant_id`, `consented_purpose`, `third_party_sharing_permitted`
  - `system_inventory`: `system_hash`, `tenant_id`, `dpa_signed`
* **Join Keys**:
  - `consent_records.consent_hash = transaction_events.consent_hash` AND `consent_records.tenant_id = transaction_events.tenant_id`
  - `system_inventory.system_hash = transaction_events.third_party_hash` AND `system_inventory.tenant_id = transaction_events.tenant_id`
* **Evaluation Cases**:
  - **PASS**: Shared with third party is `False` OR (sharing permitted in consent, and DPA is signed).
    - *Concrete Example*: `shared_with_third_party = True`, `third_party_sharing_permitted = True`, `dpa_signed = True`.
  - **VIOLATION**: Shared without permission, or missing DPA, or cross-border sharing without safeguard.
    - *Concrete Example*: `shared_with_third_party = True`, `third_party_sharing_permitted = False`.
  - **NOT_APPLICABLE**: Transaction not shared with third party.
    - *Concrete Example*: `shared_with_third_party = False`.
  - **NOT_ASSESSABLE**: Missing third-party system or consent.
    - *Concrete Example*: `shared_with_third_party = NULL` or `third_party_sharing_permitted = NULL`.
* **Finding Identity / Record ID**: `event_hash`.

---

### DPDP-007: Data Minimisation Violation
* **Rule ID**: DPDP-007
* **Required Tables & Fields**:
  - `access_logs`: `access_hash`, `tenant_id`, `system_hash`, `data_volume_accessed`, `access_reason`, `pii_fields_justified`
  - `system_inventory`: `system_hash`, `tenant_id`, `pii_stored`
* **Join Keys**:
  - `system_inventory.system_hash = access_logs.system_hash` AND `system_inventory.tenant_id = access_logs.tenant_id`
* **Evaluation Cases**:
  - **PASS**: PII is accessed and access is fully justified.
    - *Concrete Example*: `accessed_pii = True`, `pii_fields_justified = True`.
  - **VIOLATION**: Volume is bulk, or PII is stored without justification.
    - *Concrete Example*: `accessed_pii = True`, `pii_fields_justified = False`.
  - **NOT_APPLICABLE**: Access did not touch PII.
    - *Concrete Example*: `accessed_pii = False`.
  - **NOT_ASSESSABLE**: `pii_fields_justified` is `NULL`.
    - *Concrete Example*: `pii_fields_justified = NULL`.
* **Finding Identity / Record ID**: `access_hash`.

---

### DPDP-008: Sensitive Data Stored Without Encryption
* **Rule ID**: DPDP-008
* **Required Tables & Fields**:
  - `security_events`: `security_hash`, `tenant_id`, `pii_encrypted`, `encryption_type`, `breach_detected`
* **Join Keys**: None (single table).
* **Evaluation Cases**:
  - **PASS**: PII is encrypted standard.
    - *Concrete Example*: `breach_detected = True`, `pii_encrypted = True`.
  - **VIOLATION**: Unencrypted sensitive data store or weak encryption.
    - *Concrete Example*: `breach_detected = True`, `pii_encrypted = False`.
  - **NOT_APPLICABLE**: No security breach detected.
    - *Concrete Example*: `breach_detected = False`.
  - **NOT_ASSESSABLE**: `pii_encrypted` is `NULL`.
    - *Concrete Example*: `pii_encrypted = NULL`.
* **Finding Identity / Record ID**: `security_hash`.

---

### DPDP-009: Missing Grievance Redressal Mechanism
* **Rule ID**: DPDP-009
* **Required Tables & Fields**:
  - `governance_config`: `tenant_id`, `grievance_endpoint_available`, `dpo_assigned`, `dpo_contact_masked`
* **Join Keys**: None (single table).
* **Evaluation Cases**:
  - **PASS**: Grievance endpoint is available, DPO is assigned, and DPO contact is present.
    - *Concrete Example*: `grievance_endpoint_available = True`, `dpo_assigned = True`, `dpo_contact_masked = 'd***@company.com'`.
  - **VIOLATION**: Missing endpoint, missing DPO, or missing contact masked.
    - *Concrete Example*: `dpo_assigned = False` or `grievance_endpoint_available = False`.
  - **NOT_APPLICABLE**: *State cannot occur*. DPO and grievance redressal mechanisms are universal statutory requirements under Section 9 of the DPDP Act and must apply to all registered compliance profiles.
  - **NOT_ASSESSABLE**: `dpo_assigned` is `NULL`.
    - *Concrete Example*: `dpo_assigned = NULL`.
* **Finding Identity / Record ID**: `tenant_id`.

---

### DPDP-010: Failure to Honour Data Erasure Request
* **Rule ID**: DPDP-010
* **Required Tables & Fields**:
  - `dsar_requests`: `dsar_hash`, `customer_hash`, `tenant_id`, `request_type`, `sla_breached`
  - `data_lifecycle`: `lifecycle_hash`, `customer_hash`, `tenant_id`, `retention_status`, `legal_hold_flag`
* **Join Keys**:
  - `data_lifecycle.customer_hash = dsar_requests.customer_hash` AND `data_lifecycle.tenant_id = dsar_requests.tenant_id`
* **Evaluation Cases**:
  - **PASS**: Request type is erasure and erasure request met within SLA.
    - *Concrete Example*: `request_type = 'erasure'`, `sla_breached = False`, `retention_status = 'deleted'`.
  - **VIOLATION**: Request type is erasure, SLA is breached, and retention status is not deleted, and no legal hold is applied.
    - *Concrete Example*: `request_type = 'erasure'`, `sla_breached = True`, `retention_status = 'active'`.
  - **NOT_APPLICABLE**: Request type is not erasure.
    - *Concrete Example*: `request_type = 'access'`.
  - **NOT_ASSESSABLE**: SLA status or customer mapping is missing.
    - *Concrete Example*: `sla_breached = NULL`.
* **Finding Identity / Record ID**: `dsar_hash`.

---

### DPDP-011: Excess Data Retention After Purpose Completion
* **Rule ID**: DPDP-011
* **Required Tables & Fields**:
  - `data_lifecycle`: `lifecycle_hash`, `tenant_id`, `purpose_completed`, `retention_status`, `legal_hold_flag`
* **Join Keys**: None.
* **Evaluation Cases**:
  - **PASS**: Retention status is deleted, or purpose not completed, or legal hold is applied.
    - *Concrete Example*: `purpose_completed = False` or (`purpose_completed = True` and `retention_status = 'deleted'`).
  - **VIOLATION**: Purpose completed, not deleted, and no legal hold exists.
    - *Concrete Example*: `purpose_completed = True`, `retention_status = 'active'`, `legal_hold_flag = False`.
  - **NOT_APPLICABLE**: *State cannot genuinely occur* as purpose completion and retention checking applies universally across all customer master lifecycle logs.
  - **NOT_ASSESSABLE**: `purpose_completed` is `NULL`.
    - *Concrete Example*: `purpose_completed = NULL`.
* **Finding Identity / Record ID**: `lifecycle_hash`.

---

### DPDP-012: Missing or Overdue Audit Logs
* **Rule ID**: DPDP-012
* **Required Tables & Fields**:
  - `governance_config`: `tenant_id`, `last_audit_date`, `audit_frequency_days`, `dpo_assigned`
  - `access_logs` (aggregated): `tenant_id`, `access_outcome`
* **Join Keys**:
  - Subquery aggregates `access_logs` grouped by `tenant_id` to join on `governance_config.tenant_id`
* **Evaluation Cases**:
  - **PASS**: Audit date is within threshold days, access outcomes are log-complete, and DPO is assigned.
    - *Concrete Example*: `last_audit_date = '2026-08-01'`, `audit_frequency_days = 90`.
  - **VIOLATION**: Overdue audit, incomplete outcomes, or no DPO.
    - *Concrete Example*: `last_audit_date = '2025-08-01'` (overdue).
  - **NOT_APPLICABLE**: *State cannot occur*. Regular audits are a mandatory obligation for all registered compliance tenants.
  - **NOT_ASSESSABLE**: `last_audit_date` is `NULL`.
    - *Concrete Example*: `last_audit_date = NULL`.
* **Finding Identity / Record ID**: `tenant_id`.

---

### DPDP-013: Unauthorised Employee Access to PII
* **Rule ID**: DPDP-013
* **Required Tables & Fields**:
  - `access_logs`: `access_hash`, `tenant_id`, `employee_role`, `accessed_pii`, `access_outcome`, `data_volume_accessed`
* **Join Keys**: None.
* **Evaluation Cases**:
  - **PASS**: Authorized roles or no PII accessed.
    - *Concrete Example*: `accessed_pii = True`, `employee_role = 'dpo'`.
  - **VIOLATION**: Unauthorized employee accessing PII.
    - *Concrete Example*: `accessed_pii = True`, `employee_role = 'marketing'`.
  - **NOT_APPLICABLE**: Access did not touch PII.
    - *Concrete Example*: `accessed_pii = False`.
  - **NOT_ASSESSABLE**: `accessed_pii` is `NULL`.
    - *Concrete Example*: `accessed_pii = NULL`.
* **Finding Identity / Record ID**: `access_hash`.

---

### DPDP-014: Delayed Breach Notification
* **Rule ID**: DPDP-014
* **Required Tables & Fields**:
  - `security_events`: `security_hash`, `tenant_id`, `breach_detected`, `notification_delay_hours`, `breach_confirmed_date`, `affected_user_count`
* **Join Keys**: None.
* **Evaluation Cases**:
  - **PASS**: Breach detected and delay <= 72 hours, with confirmed date available.
    - *Concrete Example*: `breach_detected = True`, `notification_delay_hours = 24`, `breach_confirmed_date = '2026-08-23'`.
  - **VIOLATION**: Delay > 72 hours, or missing breach confirmed date, or critical breach count.
    - *Concrete Example*: `breach_detected = True`, `notification_delay_hours = 80` (exceeds 72 hours).
  - **NOT_APPLICABLE**: No security breach detected.
    - *Concrete Example*: `breach_detected = False`.
  - **NOT_ASSESSABLE**: `breach_confirmed_date` is `NULL`.
    - *Concrete Example*: `breach_confirmed_date = NULL`.
* **Finding Identity / Record ID**: `security_hash`.

---

### DPDP-015: Cross-Border Transfer Without Authorisation
* **Rule ID**: DPDP-015
* **Required Tables & Fields**:
  - `transaction_events`: `event_hash`, `tenant_id`, `third_party_hash`, `is_cross_border`, `transfer_country`
  - `system_inventory`: `system_hash`, `tenant_id`, `dpa_signed`
* **Join Keys**:
  - `system_inventory.system_hash = transaction_events.third_party_hash` AND `system_inventory.tenant_id = transaction_events.tenant_id`
* **Evaluation Cases**:
  - **PASS**: Cross-border, country is approved, and DPA is signed.
    - *Concrete Example*: `is_cross_border = True`, `transfer_country = 'SG'`, `dpa_signed = True`.
  - **VIOLATION**: Destination country is not on approved list or DPA is missing.
    - *Concrete Example*: `is_cross_border = True`, `transfer_country = 'CN'` (unapproved), or `dpa_signed = False`.
  - **NOT_APPLICABLE**: Transaction is not cross-border.
    - *Concrete Example*: `is_cross_border = False`.
  - **NOT_ASSESSABLE**: Missing destination country or DPA safeguards.
    - *Concrete Example*: `is_cross_border = NULL` or `transfer_country = NULL` or `dpa_signed = NULL`.
* **Finding Identity / Record ID**: `event_hash`.

---

### DPDP-016: Processor Accountability Failure
* **Rule ID**: DPDP-016
* **Required Tables & Fields**:
  - `system_inventory`: `system_hash`, `tenant_id`, `dpa_signed`, `dpa_expiry_date`, `pii_stored`
* **Join Keys**: None.
* **Evaluation Cases**:
  - **PASS**: DPA is signed and unexpired.
    - *Concrete Example*: `dpa_signed = True`, `dpa_expiry_date = '2027-08-23'`, `pii_stored = True`.
  - **VIOLATION**: DPA not signed or expired.
    - *Concrete Example*: `dpa_signed = False` or `dpa_expiry_date = '2025-08-23'` (expired).
  - **NOT_APPLICABLE**: *State cannot occur*. Processor checklist applies uniformly to all systems registered under the system inventory table.
  - **NOT_ASSESSABLE**: `dpa_signed` is `NULL`.
    - *Concrete Example*: `dpa_signed = NULL`.
* **Finding Identity / Record ID**: `system_hash`.

---

## Policy Rules

---

### POLICY-001: Retention Policy Compliance
* **Rule ID**: POLICY-001
* **Required Tables & Fields**:
  - `policies`: `policy_id`, `tenant_id`, `policy_type` ('retention'), `is_active`, `policy_value_numeric`
* **Join Keys**: None.
* **Evaluation Cases**:
  - **PASS**: Policy is active and value <= 730 days.
  - **VIOLATION**: Policy inactive or value > 730 days.
* **Finding Identity / Record ID**: `policy_id`.

---

### POLICY-002: Encryption Policy Compliance
* **Rule ID**: POLICY-002
* **Required Tables & Fields**:
  - `policies`: `policy_id`, `tenant_id`, `policy_type` ('encryption'), `is_active`, `policy_value_text`
* **Join Keys**: None.
* **Evaluation Cases**:
  - **PASS**: Policy is active and value standard.
  - **VIOLATION**: Inactive or weak standard (e.g. 'none', 'md5', 'sha1', 'des', 'rc4').
* **Finding Identity / Record ID**: `policy_id`.

---

### POLICY-003: Consent Mechanism Policy
* **Rule ID**: POLICY-003
* **Required Tables & Fields**:
  - `policies`: `policy_id`, `tenant_id`, `policy_type` ('consent'), `is_active`, `policy_value_text`
* **Join Keys**: None.
* **Evaluation Cases**:
  - **PASS**: Policy active and channel compliant.
  - **VIOLATION**: Inactive or non-compliant channel (e.g. 'implicit', 'pre_ticked', 'inferred', 'bundled').
* **Finding Identity / Record ID**: `policy_id`.
