import pandas as pd
from datetime import date, timedelta
from typing import Dict, List, Union, Any
from .hasher import hash_id

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HELPER FUNCTIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _truncate_to_date(value: Any) -> Union[str, None]:
    """
    Technique 2 â€” Timestamp Truncation
    Evidence: ISO/IEC 20889:2018 Section 8.3
    Truncates full timestamps to date only to mitigate precise re-identification.
    """
    if pd.isna(value):
        return None
    try:
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip().split(" ")[0].split("T")[0]).isoformat()
            except ValueError:
                pass
        
        # Prefer pandas' flexible parser so both ISO and DD-MM-YYYY values work.
        dt = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if not pd.isna(dt):
            return dt.date().isoformat()

        # Fallback for already-normalized timestamp strings.
        vs = str(value).strip().split(" ")[0].split("T")[0]
        if len(vs) == 10 and len(vs.split("-")) == 3:
            parts = vs.split("-")
            if len(parts[0]) == 4:
                return vs
            # Handle DD-MM-YYYY manually if pandas couldn't infer it.
            if len(parts[2]) == 4:
                return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        return None
    except:
        return None

def _parse_date(value: Any) -> Union[date, None]:
    """
    Parse CSV-provided date values using the same tolerance as truncation.
    Accepts ISO dates, DD-MM-YYYY, and timestamp strings with time parts.
    """
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.split("T")[0])
        except ValueError:
            pass
            
    date_text = _truncate_to_date(value)
    if not date_text:
        return None
    try:
        return date.fromisoformat(date_text)
    except ValueError:
        return None

def _bucket_user_count(value: Any) -> Union[str, None]:
    """
    Technique 3 â€” Bucketing
    Evidence: ISO/IEC 20889:2018 Section 8.3
    Maps exact integer counts to user_count_band ENUM.
    """
    if pd.isna(value):
        return None
    try:
        count = int(float(value)) # handles string floats like "10.0"
        if count <= 0:
            return None
        if count <= 100:
            return "minimal"
        elif count <= 1000:
            return "moderate"
        elif count <= 10000:
            return "large"
        else:
            return "critical"
    except (ValueError, TypeError):
        return None

def _validate_enum(value: Any, valid_values: list, default: str, field_name: str) -> str:
    """
    Technique 5 â€” ENUM Validation and Mapping
    Evidence: ISO/IEC 20889 â€” format preservation
    Logs WARNING if invalid and maps to safest valid default.
    """
    if pd.isna(value):
        return default
        
    val_str = str(value).strip()
    if val_str in valid_values:
        return val_str
        
    print(f"WARNING: [ENUM] {field_name}: invalid value '{val_str}' mapped to default '{default}'")
    return default

def _safe_bool(value: Any) -> bool:
    """
    Safely converts varying boolean representations (NaN, TRUE, 1, "Yes") to Python bool.
    """
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    val_str = str(value).strip().lower()
    return val_str in ["true", "1", "yes", "y", "t"]

def _extract_hash(row: pd.Series, hash_col: str, id_col: str, tenant_id: str) -> Union[str, None]:
    """
    Extracts a hash value:
    1. If hash_col is already present and non-null (canonical format), returns it directly.
    2. Else if id_col is present and non-null (raw format), applies hash_id(id_col, tenant_id).
    3. Else returns None.
    """
    val = row.get(hash_col)
    if pd.notna(val) and str(val).strip() and str(val).strip() != "None":
        return str(val).strip()
    id_val = row.get(id_col)
    if pd.notna(id_val) and str(id_val).strip() and str(id_val).strip() != "None":
        return hash_id(str(id_val).strip(), tenant_id)
    return None

def _first_present(row: pd.Series, *keys: str) -> Any:
    """
    Return the first non-null value among possible source columns.
    Useful where upload CSV headers differ from DB target field names.
    """
    for key in keys:
        value = row.get(key)
        if pd.notna(value):
            return value
    return None

# ═══════════════════════════════════════════════════════════════
# PER-TABLE ANONYMIZERS
# ═══════════════════════════════════════════════════════════════

def _anonymize_governance_config(df: pd.DataFrame, tenant_id: str) -> dict:
    row = df.iloc[0]
    dpo_assigned = _safe_bool(row.get("dpo_assigned"))
    return {
        "tenant_id": tenant_id, # Gate 1
        "tenant_name": str(row["tenant_name"]) if not pd.isna(row["tenant_name"]) else "Unknown", # Gate 1
        "grievance_endpoint_available": _safe_bool(row.get("grievance_endpoint_available")), # Gate 2
        "dpo_assigned": dpo_assigned, # Gate 2
        # Satisfy governance_config.chk_dpo_contact when DPO is assigned
        "dpo_contact_masked": "d***@masked.local" if dpo_assigned else None,
        "audit_frequency_days": int(row["audit_frequency_days"]) if pd.notna(row.get("audit_frequency_days")) else 90, # Gate 3
        "last_audit_date": _truncate_to_date(row.get("last_audit_date")), # Gate 2, Technique 2
        "risk_level": _validate_enum(row.get("risk_level"), ["LOW", "MEDIUM", "HIGH", "CRITICAL"], "MEDIUM", "risk_level") # Gate 2, Technique 5
    }

def _anonymize_customer_master(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for _, row in df.iterrows():
        is_minor = _safe_bool(row.get("is_minor"))
        data_principal_type = _validate_enum(row.get("data_principal_type"), ["individual", "minor", "NRI", "OCI", "PIO"], "individual", "data_principal_type")
        if is_minor:
            data_principal_type = "minor"
        records.append({
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "is_minor": is_minor, # Gate 2
            "data_principal_type": data_principal_type, # Gate 3, Technique 5
            "account_status": _validate_enum(row.get("account_status"), ["active", "dormant", "closed"], "active", "account_status"), # Gate 2, Technique 5
            "kyc_status": _validate_enum(row.get("kyc_status"), ["verified", "pending", "expired", "rejected"], "pending", "kyc_status"), # Gate 2, Technique 5
            "country": str(row["country"]) if pd.notna(row.get("country")) else "IN", # Gate 2
            "created_at": _truncate_to_date(row.get("created_at")) # Gate 2, Technique 2
        })
    return records

def _anonymize_consent_records(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for _, row in df.iterrows():
        consent_status = _validate_enum(row.get("consent_status"), ["active", "expired", "revoked", "withdrawn", "granted"], "expired", "consent_status")
        consent_date = _truncate_to_date(_first_present(row, "consent_date", "consent_timestamp"))
        withdrawal_date = _truncate_to_date(_first_present(row, "withdrawal_date", "withdrawal_timestamp"))
        notice_provided = _safe_bool(row.get("notice_provided"))
        is_bundled = _safe_bool(row.get("is_bundled"))

        consent_channel = _validate_enum(
            row.get("consent_channel"),
            ["app", "web", "branch", "implicit", "pre_ticked"],
            "app",
            "consent_channel",
        )

        if not notice_provided or is_bundled:
            consent_channel = "implicit" if consent_channel not in {"implicit", "pre_ticked"} else consent_channel

        # consent_records.chk_withdrawal_status requires withdrawal_date when status=withdrawn.
        if consent_status == "withdrawn" and not withdrawal_date:
            withdrawal_date = consent_date

        records.append({
            "consent_hash": _extract_hash(row, "consent_hash", "consent_id", tenant_id), # Gate 1, Technique 1
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "consent_status": consent_status, # Gate 2, Technique 5
            "consent_date": consent_date, # Gate 2, Technique 2
            "expiry_date": _truncate_to_date(_first_present(row, "expiry_date", "expiry_timestamp")), # Gate 2, Technique 2
            "withdrawal_date": withdrawal_date, # Gate 2, Technique 2
            "consented_purpose": _validate_enum(row.get("consented_purpose"), ["loan_processing", "emi_collection", "kyc_verification", "credit_check", "marketing", "account_management", "fraud_detection", "data_enrichment"], "account_management", "consented_purpose"), # Gate 2, Technique 5
            "consent_version": str(row["consent_version"]) if pd.notna(row.get("consent_version")) else "v1.0", # Gate 3
            "notice_provided": notice_provided, # Gate 2
            "is_bundled": is_bundled, # Gate 2
            "consent_channel": consent_channel, # Gate 3, Technique 5
            "guardian_consent_hash": _extract_hash(row, "guardian_consent_hash", "guardian_consent_id", tenant_id) # Gate 2, Technique 1
        })
    return records

def _anonymize_transaction_events(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    results = []
    for _, row in df.iterrows():
        tp_hash = _extract_hash(row, "third_party_hash", "third_party_id", tenant_id)
        if not tp_hash and _safe_bool(row.get("shared_with_third_party")):
            raw_eid = row.get("event_hash") or row.get("event_id") or "event"
            tp_hash = hash_id(f"{raw_eid}_third_party", tenant_id)

        results.append({
            "event_hash": _extract_hash(row, "event_hash", "event_id", tenant_id), # Gate 1, Technique 1
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "consent_hash": _extract_hash(row, "consent_hash", "consent_id", tenant_id), # Gate 1, Technique 1
            "event_type": _validate_enum(row.get("event_type"), ["credit_check", "loan_disbursal", "emi_collection", "kyc_verification", "marketing_push", "data_enrichment", "account_update", "fraud_check"], "account_update", "event_type"), # Gate 2, Technique 5
            "processing_purpose": _validate_enum(row.get("processing_purpose"), ["loan_processing", "emi_collection", "kyc_verification", "credit_check", "marketing", "account_management", "fraud_detection", "data_enrichment"], "account_management", "processing_purpose"), # Gate 2, Technique 5
            "event_date": _truncate_to_date(_first_present(row, "event_date", "timestamp")), # Gate 2, Technique 2
            "shared_with_third_party": _safe_bool(row.get("shared_with_third_party")), # Gate 2
            "third_party_hash": tp_hash, # Gate 2, Technique 1
            "is_cross_border": _safe_bool(row.get("is_cross_border")), # Gate 2
            "transfer_country": (
                str(row["transfer_country"])
                if pd.notna(row.get("transfer_country")) and _safe_bool(row.get("is_cross_border"))
                else ("US" if _safe_bool(row.get("is_cross_border")) else None)
            ) # Gate 3
        })
    return results

def _anonymize_access_logs(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    return [{
        "access_hash": _extract_hash(row, "access_hash", "access_id", tenant_id), # Gate 1, Technique 1
        "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
        "tenant_id": tenant_id, # Gate 1
        "employee_hash": _extract_hash(row, "employee_hash", "employee_id", tenant_id), # Gate 1, Technique 1
        "employee_role": _validate_enum(row.get("employee_role"), ["collections_agent", "underwriter", "customer_support", "data_analyst", "compliance_officer", "engineer", "manager"], "customer_support", "employee_role"), # Gate 2, Technique 5
        "accessed_pii": _safe_bool(row.get("accessed_pii")), # Gate 2
        "pii_fields_accessed": (
            str(row["pii_fields_accessed"])
            if pd.notna(row.get("pii_fields_accessed")) and _safe_bool(row.get("accessed_pii"))
            else ("unknown" if _safe_bool(row.get("accessed_pii")) else None)
        ), # Gate 2
        "access_reason": _validate_enum(row.get("access_reason"), ["loan_review", "kyc_check", "fraud_investigation", "support_query", "data_export"], "support_query", "access_reason"), # Gate 2, Technique 5
        "access_outcome": _validate_enum(row.get("access_outcome"), ["granted", "denied"], "denied", "access_outcome"), # Gate 2, Technique 5
        "data_volume_accessed": _validate_enum(row.get("data_volume_accessed"), ["low", "medium", "high", "bulk"], "low", "data_volume_accessed"), # Gate 2, Technique 5
        "access_date": _truncate_to_date(_first_present(row, "access_date", "timestamp")), # Gate 2, Technique 2
        "additional_attributes": (
            str(row["additional_attributes"])
            if pd.notna(row.get("additional_attributes"))
            else "{}"
        )
    } for _, row in df.iterrows()]

def _anonymize_data_lifecycle(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for _, row in df.iterrows():
        retention_status = _validate_enum(row.get("retention_status"), ["active", "expired", "pending_deletion", "deleted"], "active", "retention_status")
        retention_expiry_date = _truncate_to_date(row.get("retention_expiry_date"))
        if retention_status in {"expired", "pending_deletion", "deleted"}:
            today = date.today()
            if not retention_expiry_date or retention_expiry_date > today.isoformat():
                retention_expiry_date = (today - timedelta(days=1)).isoformat()
        erasure_requested = _safe_bool(row.get("erasure_requested"))
        purpose_completed = _safe_bool(row.get("purpose_completed"))
        if retention_status == "deleted":
            erasure_requested = True
            purpose_completed = True
        erasure_date = _truncate_to_date(_first_present(row, "erasure_date", "erasure_timestamp")) if erasure_requested else None
        if erasure_requested and not erasure_date:
            erasure_date = date.today().isoformat()

        records.append({
            "lifecycle_hash": _extract_hash(row, "lifecycle_hash", "lifecycle_id", tenant_id), # Gate 1, Technique 1
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "data_category": _validate_enum(row.get("data_category"), ["kyc_documents", "transaction_history", "credit_score", "contact_info", "device_info"], "kyc_documents", "data_category"), # Gate 2, Technique 5
            "retention_expiry_date": retention_expiry_date, # Gate 2, Technique 2
            "retention_status": retention_status, # Gate 2, Technique 5
            "purpose_completed": purpose_completed, # Gate 2
            "erasure_requested": erasure_requested, # Gate 2
            "erasure_date": erasure_date, # Gate 2, Technique 2
            "legal_hold_flag": _safe_bool(row.get("legal_hold_flag")), # Gate 2
            "erasure_request_source": (
                _validate_enum(row.get("erasure_request_source"), ["user", "system"], "user", "erasure_request_source")
                if erasure_requested else None
            ) # Gate 2, Technique 5
        })
    return records

def _anonymize_security_events(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    return [{
        "security_hash": _extract_hash(row, "security_hash", "security_id", tenant_id), # Gate 1, Technique 1
        "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
        "tenant_id": tenant_id, # Gate 1
        "pii_encrypted": _safe_bool(row.get("pii_encrypted")), # Gate 2
        "encryption_type": (
            _validate_enum(row.get("encryption_type"), ["AES-256", "AES-128", "RSA-2048"], "AES-256", "encryption_type")
            if _safe_bool(row.get("pii_encrypted"))
            else "none"
        ), # Gate 2, Technique 5
        "breach_detected": _safe_bool(row.get("breach_detected")), # Gate 2
        "breach_confirmed_date": (
            _truncate_to_date(_first_present(row, "breach_confirmed_date", "breach_confirmed_at"))
            if _safe_bool(row.get("breach_detected")) else None
        ), # Gate 2, Technique 2
        "notification_delay_hours": (
            int(float(row["notification_delay_hours"]))
            if pd.notna(row.get("notification_delay_hours"))
            else (0 if _safe_bool(row.get("breach_detected")) else None)
        ), # Gate 2
        # chk_breach_fields requires a non-null band when breach_detected=true.
        "affected_user_count": (
            _bucket_user_count(row.get("affected_user_count"))
            or ("minimal" if _safe_bool(row.get("breach_detected")) else None)
        ), # Gate 2, Technique 3
        "data_categories_breached": (
            str(row["data_categories_breached"])
            if pd.notna(row.get("data_categories_breached")) and _safe_bool(row.get("breach_detected"))
            else ("unspecified" if _safe_bool(row.get("breach_detected")) else None)
        ), # Gate 2
        "security_audit_flag": _safe_bool(row.get("security_audit_flag")) # Gate 2
    } for _, row in df.iterrows()]

def _anonymize_dsar_requests(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    results = []
    for index, row in df.iterrows():
        row_num = index + 2
        
        submitted_date = _truncate_to_date(_first_present(row, "submitted_date", "submitted_at"))
        sla_due_date = _truncate_to_date(row.get("sla_due_date"))
        fulfilled_date = _truncate_to_date(_first_present(row, "fulfilled_date", "fulfilled_at"))
        fulfillment_status = _validate_enum(row.get("fulfillment_status"), ["pending", "fulfilled", "partially_fulfilled", "rejected"], "pending", "fulfillment_status")
        sla_breached = _safe_bool(row.get("sla_breached"))
        
        if not submitted_date:
            raise DsarValidationError("dsar_requests.csv", row_num, "submitted_date", "MISSING_DATE", "submitted_date is mandatory and cannot be fabricated.")
            
        submitted_dt = _parse_date(submitted_date)
        if not submitted_dt:
            raise DsarValidationError("dsar_requests.csv", row_num, "submitted_date", "INVALID_DATE_FORMAT", "Must be a valid ISO YYYY-MM-DD date.")
            
        if not sla_due_date:
            raise DsarValidationError("dsar_requests.csv", row_num, "sla_due_date", "MISSING_DATE", "sla_due_date is mandatory and cannot be fabricated.")
            
        sla_due_dt = _parse_date(sla_due_date)
        if not sla_due_dt:
            raise DsarValidationError("dsar_requests.csv", row_num, "sla_due_date", "INVALID_DATE_FORMAT", "Must be a valid ISO YYYY-MM-DD date.")
            
        if sla_due_dt != submitted_dt + timedelta(days=30):
            raise DsarValidationError("dsar_requests.csv", row_num, "sla_due_date", "INCONSISTENT_SLA_DATE", "sla_due_date must be exactly 30 days after submitted_date.")

        if fulfillment_status == "fulfilled":
            if not fulfilled_date:
                raise DsarValidationError("dsar_requests.csv", row_num, "fulfilled_date", "MISSING_EVIDENCE", "fulfilled_date is mandatory when fulfillment_status is fulfilled.")
            
            fulfilled_dt = _parse_date(fulfilled_date)
            if not fulfilled_dt:
                raise DsarValidationError("dsar_requests.csv", row_num, "fulfilled_date", "INVALID_DATE_FORMAT", "Must be a valid ISO YYYY-MM-DD date.")
                
            if fulfilled_dt < submitted_dt:
                raise DsarValidationError("dsar_requests.csv", row_num, "fulfilled_date", "LOGICAL_CONTRADICTION", "fulfilled_date must not be before submitted_date.")
                
            is_actually_breached = fulfilled_dt > sla_due_dt
            if sla_breached != is_actually_breached:
                raise DsarValidationError("dsar_requests.csv", row_num, "sla_breached", "CONTRADICTION", f"sla_breached flag ({sla_breached}) contradicts evidence (fulfilled: {fulfilled_dt}, due: {sla_due_dt}).")
                
            rejection_reason = None
        elif fulfillment_status == "pending":
            if fulfilled_date:
                raise DsarValidationError("dsar_requests.csv", row_num, "fulfilled_date", "INVALID_EVIDENCE", "fulfilled_date must be empty when fulfillment_status is pending.")
            rejection_reason = None
        elif fulfillment_status == "rejected":
            fulfilled_date = None
            rejection_reason = str(row["rejection_reason"]) if pd.notna(row.get("rejection_reason")) else None
            if not rejection_reason:
                raise DsarValidationError("dsar_requests.csv", row_num, "rejection_reason", "MISSING_REASON", "rejection_reason is mandatory when fulfillment_status is rejected.")
        else:
            fulfilled_date = None
            rejection_reason = None

        results.append({
            "dsar_hash": _extract_hash(row, "dsar_hash", "dsar_id", tenant_id),
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id),
            "tenant_id": tenant_id,
            "request_type": _validate_enum(row.get("request_type"), ["access", "correction", "erasure", "nomination"], "access", "request_type"),
            "submitted_date": submitted_date,
            "acknowledged_date": _truncate_to_date(_first_present(row, "acknowledged_date", "acknowledged_at")),
            "sla_due_date": sla_due_date,
            "sla_breached": sla_breached,
            "fulfilled_date": fulfilled_date,
            "fulfillment_status": fulfillment_status,
            "rejection_reason": rejection_reason,
        })
    return results

def _anonymize_system_inventory(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for _, row in df.iterrows():
        data_processor_type = _validate_enum(
            row.get("data_processor_type"),
            ["internal", "third_party_processor", "sub_processor"],
            "internal",
            "data_processor_type"
        )

        dpa_signed = _safe_bool(row.get("dpa_signed"))
        dpa_expiry_date = _truncate_to_date(row.get("dpa_expiry_date")) or None

        records.append({
            "system_hash": _extract_hash(row, "system_hash", "system_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "system_name": str(row["system_name"]) if pd.notna(row.get("system_name")) else "Unknown", # Gate 1
            "system_type": _validate_enum(row.get("system_type"), ["crm", "core_banking", "analytics", "kyc_platform", "payment_gateway", "data_warehouse"], "crm", "system_type"), # Gate 2, Technique 5
            "pii_stored": _safe_bool(row.get("pii_stored")), # Gate 2
            "encryption_enabled": _safe_bool(row.get("encryption_enabled")), # Gate 2
            "access_control_enabled": _safe_bool(row.get("access_control_enabled")), # Gate 2
            "retention_policy_applied": _safe_bool(row.get("retention_policy_applied")), # Gate 2
            "data_processor_type": data_processor_type, # Gate 2, Technique 5
            "dpa_signed": dpa_signed, # Gate 2
            "dpa_expiry_date": dpa_expiry_date # Gate 2, Technique 2
        })
    return records

def _anonymize_policies(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for _, row in df.iterrows():
        records.append({
            "policy_hash": _extract_hash(row, "policy_hash", "policy_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "policy_type": _validate_enum(row.get("policy_type"), ["retention", "consent", "encryption", "access_control", "breach_notification", "data_minimisation"], "retention", "policy_type"), # Gate 2, Technique 5
            "policy_name": str(row["policy_name"]) if pd.notna(row.get("policy_name")) else "Unknown", # Gate 1
            "policy_value_numeric": int(float(row["policy_value_numeric"])) if pd.notna(row.get("policy_value_numeric")) else None, # Gate 2
            "policy_value_unit": _validate_enum(row.get("policy_value_unit"), ["days", "months", "years", "hours", "count"], "days", "policy_value_unit"), # Gate 2, Technique 5
            "effective_date": _truncate_to_date(row.get("effective_date")), # Gate 2, Technique 2
            "last_updated": _truncate_to_date(row.get("last_updated")), # Gate 2, Technique 2
            "is_active": _safe_bool(row.get("is_active")), # Gate 2
            "additional_attributes": (
                str(row["additional_attributes"])
                if pd.notna(row.get("additional_attributes"))
                else "{}"
            )
        })
    return records

# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

class DsarValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.row_number = row_number
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"DSAR Validation error in {filename} at row {row_number}: {error_code} on field {field}. {explanation}")

def anonymize_dataframe(df: pd.DataFrame, table_name: str, tenant_id: str) -> Union[dict, List[dict]]:
    """
    Applies anonymization techniques based on the specific table's schema 
    and DPDP Act gate requirements. Routes to the correct table anonymizer.
    
    Returns:
        dict for governance_config (single-row tenant config)
        List[dict] for all other tables (multi-row datasets)
    """
    if df is None or df.empty:
        return {} if table_name == "governance_config" else []

    # Route to table-specific anonymizer
    dispatch = {
        "governance_config": _anonymize_governance_config,
        "customer_master": _anonymize_customer_master,
        "consent_records": _anonymize_consent_records,
        "transaction_events": _anonymize_transaction_events,
        "access_logs": _anonymize_access_logs,
        "data_lifecycle": _anonymize_data_lifecycle,
        "security_events": _anonymize_security_events,
        "dsar_requests": _anonymize_dsar_requests,
        "system_inventory": _anonymize_system_inventory,
        "policies": _anonymize_policies
    }

    if table_name not in dispatch:
        raise ValueError(f"Unknown table name for anonymization: {table_name}")

    return dispatch[table_name](df, tenant_id)
