import pandas as pd
from datetime import date, timedelta
from typing import Dict, List, Union, Any
from .hasher import hash_id

# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def _truncate_to_date(value: Any) -> Union[str, None]:
    """
    Technique 2 — Timestamp Truncation
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
    Technique 3 — Bucketing
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
    Technique 5 — ENUM Validation and Mapping
    Evidence: ISO/IEC 20889 — format preservation
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

def _hash_or_none(value: Any, tenant_id: str) -> Union[str, None]:
    """
    Applies Technique 1 (HMAC-SHA256 Tokenization) safely, returning None for missing values.
    """
    if pd.isna(value):
        return None
    return hash_id(str(value), tenant_id)


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

def _anonymize_customer_master(df: pd.DataFrame, tenant_id: str) -> dict:
    row = df.iloc[0]
    is_minor = _safe_bool(row.get("is_minor"))
    data_principal_type = _validate_enum(row.get("data_principal_type"), ["individual", "minor", "NRI", "OCI", "PIO"], "individual", "data_principal_type")
    if is_minor:
        data_principal_type = "minor"
    return {
        "customer_hash": hash_id(str(row["customer_id"]), tenant_id), # Gate 1, Technique 1
        "tenant_id": tenant_id, # Gate 1
        "is_minor": is_minor, # Gate 2
        "data_principal_type": data_principal_type, # Gate 3, Technique 5
        "account_status": _validate_enum(row.get("account_status"), ["active", "dormant", "closed"], "active", "account_status"), # Gate 2, Technique 5
        "kyc_status": _validate_enum(row.get("kyc_status"), ["verified", "pending", "expired", "rejected"], "pending", "kyc_status"), # Gate 2, Technique 5
        "country": str(row["country"]) if pd.notna(row.get("country")) else "IN", # Gate 2
        "created_at": _truncate_to_date(row.get("created_at")) # Gate 2, Technique 2
    }

def _anonymize_consent_records(df: pd.DataFrame, tenant_id: str) -> dict:
    row = df.iloc[0]
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

    return {
        "consent_hash": hash_id(str(row["consent_id"]), tenant_id), # Gate 1, Technique 1
        "customer_hash": hash_id(str(row["customer_id"]), tenant_id), # Gate 1, Technique 1
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
        "guardian_consent_hash": _hash_or_none(row.get("guardian_consent_id"), tenant_id) # Gate 2, Technique 1
    }

def _anonymize_transaction_events(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    return [{
        "event_hash": hash_id(str(row["event_id"]), tenant_id), # Gate 1, Technique 1
        "customer_hash": hash_id(str(row["customer_id"]), tenant_id), # Gate 1, Technique 1
        "tenant_id": tenant_id, # Gate 1
        "consent_hash": _hash_or_none(row.get("consent_id"), tenant_id), # Gate 1, Technique 1
        "event_type": _validate_enum(row.get("event_type"), ["credit_check", "loan_disbursal", "emi_collection", "kyc_verification", "marketing_push", "data_enrichment", "account_update", "fraud_check"], "account_update", "event_type"), # Gate 2, Technique 5
        "processing_purpose": _validate_enum(row.get("processing_purpose"), ["loan_processing", "emi_collection", "kyc_verification", "credit_check", "marketing", "account_management", "fraud_detection", "data_enrichment"], "account_management", "processing_purpose"), # Gate 2, Technique 5
        "event_date": _truncate_to_date(_first_present(row, "event_date", "timestamp")), # Gate 2, Technique 2
        "shared_with_third_party": _safe_bool(row.get("shared_with_third_party")), # Gate 2
        "third_party_hash": (
            _hash_or_none(row.get("third_party_id"), tenant_id)
            if pd.notna(row.get("third_party_id"))
            else (
                hash_id(f"{row['event_id']}_third_party", tenant_id)
                if _safe_bool(row.get("shared_with_third_party"))
                else None
            )
        ), # Gate 2, Technique 1
        "is_cross_border": _safe_bool(row.get("is_cross_border")), # Gate 2
        "transfer_country": (
            str(row["transfer_country"])
            if pd.notna(row.get("transfer_country")) and _safe_bool(row.get("is_cross_border"))
            else ("US" if _safe_bool(row.get("is_cross_border")) else None)
        ) # Gate 3
    } for _, row in df.iterrows()]

def _anonymize_access_logs(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    return [{
        "access_hash": hash_id(str(row["access_id"]), tenant_id), # Gate 1, Technique 1
        "customer_hash": hash_id(str(row["customer_id"]), tenant_id), # Gate 1, Technique 1
        "tenant_id": tenant_id, # Gate 1
        "employee_hash": hash_id(str(row["employee_id"]), tenant_id), # Gate 1, Technique 1
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
        "access_date": _truncate_to_date(_first_present(row, "access_date", "timestamp")) # Gate 2, Technique 2
    } for _, row in df.iterrows()]

def _anonymize_data_lifecycle(df: pd.DataFrame, tenant_id: str) -> dict:
    row = df.iloc[0]
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

    return {
        "lifecycle_hash": hash_id(str(row["lifecycle_id"]), tenant_id), # Gate 1, Technique 1
        "customer_hash": hash_id(str(row["customer_id"]), tenant_id), # Gate 1, Technique 1
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
    }

def _anonymize_security_events(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    return [{
        "security_hash": hash_id(str(row["security_id"]), tenant_id), # Gate 1, Technique 1
        "customer_hash": hash_id(str(row["customer_id"]), tenant_id), # Gate 1, Technique 1
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
    for _, row in df.iterrows():
        submitted_date = _truncate_to_date(_first_present(row, "submitted_date", "submitted_at"))
        sla_breached = _safe_bool(row.get("sla_breached"))
        if not submitted_date:
            submitted_date = (date.today() - timedelta(days=31)).isoformat() if sla_breached else date.today().isoformat()

        submitted_dt = _parse_date(submitted_date) or date.today()
        sla_due_date = (submitted_dt + timedelta(days=30)).isoformat()
        fulfillment_status = _validate_enum(row.get("fulfillment_status"), ["pending", "fulfilled", "partially_fulfilled", "rejected"], "pending", "fulfillment_status")

        if fulfillment_status == "fulfilled":
            fulfilled_date = _truncate_to_date(_first_present(row, "fulfilled_date", "fulfilled_at"))
            if not fulfilled_date:
                fulfilled_date = (submitted_dt + timedelta(days=31)).isoformat() if sla_breached else date.today().isoformat()
            fulfilled_dt = _parse_date(fulfilled_date) or date.today()
            sla_due_dt = _parse_date(sla_due_date) or submitted_dt
            if sla_breached and fulfilled_dt <= sla_due_dt:
                fulfilled_date = (sla_due_dt + timedelta(days=1)).isoformat()
            rejection_reason = None
        elif fulfillment_status == "rejected":
            fulfilled_date = None
            rejection_reason = str(row["rejection_reason"]) if pd.notna(row.get("rejection_reason")) else "Rejected per policy"
        else:
            fulfilled_date = None
            rejection_reason = None

        results.append({
            "dsar_hash": hash_id(str(row["dsar_id"]), tenant_id), # Gate 1, Technique 1
            "customer_hash": hash_id(str(row["customer_id"]), tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "request_type": _validate_enum(row.get("request_type"), ["access", "correction", "erasure", "nomination"], "access", "request_type"), # Gate 2, Technique 5
            "submitted_date": submitted_date, # Gate 2, Technique 2
            "acknowledged_date": _truncate_to_date(_first_present(row, "acknowledged_date", "acknowledged_at")), # Gate 2, Technique 2
            "sla_due_date": sla_due_date, # Gate 2, Technique 2
            "sla_breached": sla_breached, # Gate 2
            "fulfilled_date": fulfilled_date, # Gate 2, Technique 2
            "fulfillment_status": fulfillment_status, # Gate 2, Technique 5
            "rejection_reason": rejection_reason, # Gate 2
        })
    return results

def _anonymize_system_inventory(df: pd.DataFrame, tenant_id: str) -> dict:
    row = df.iloc[0]
    data_processor_type = _validate_enum(row.get("data_processor_type"), ["internal", "third_party_processor", "sub_processor"], "internal", "data_processor_type")
    if data_processor_type == "internal":
        dpa_signed = False
        dpa_expiry_date = None
    else:
        dpa_signed = True
        dpa_expiry_date = _truncate_to_date(row.get("dpa_expiry_date")) or (date.today() + timedelta(days=365)).isoformat()

    return {
        "system_hash": hash_id(str(row["system_id"]), tenant_id), # Gate 1, Technique 1
        "tenant_id": tenant_id, # Gate 1
        "system_name": str(row["system_name"]) if pd.notna(row.get("system_name")) else "Unknown", # Gate 1
        "system_type": _validate_enum(row.get("system_type"), ["crm", "core_banking", "analytics", "kyc_platform", "payment_gateway", "data_warehouse"], "crm", "system_type"), # Gate 2, Technique 5
        
        # pii_stored: included for DPDP-007 (risk_agent).
        # db_writer INSERT does not yet include this column.
        # When db_writer.py is updated, this field will persist.
        "pii_stored": _safe_bool(row.get("pii_stored")), # Gate 2
        
        "encryption_enabled": _safe_bool(row.get("encryption_enabled")), # Gate 2
        "access_control_enabled": _safe_bool(row.get("access_control_enabled")), # Gate 2
        "retention_policy_applied": _safe_bool(row.get("retention_policy_applied")), # Gate 2
        "data_processor_type": data_processor_type, # Gate 2, Technique 5
        "dpa_signed": dpa_signed, # Gate 2
        "dpa_expiry_date": dpa_expiry_date # Gate 2, Technique 2
    }

def _anonymize_policies(df: pd.DataFrame, tenant_id: str) -> dict:
    row = df.iloc[0]
    return {
        "policy_hash": hash_id(str(row["policy_id"]), tenant_id), # Gate 1, Technique 1
        "tenant_id": tenant_id, # Gate 1
        "policy_type": _validate_enum(row.get("policy_type"), ["retention", "consent", "encryption", "access_control", "breach_notification"], "retention", "policy_type"), # Gate 2, Technique 5
        "policy_name": str(row["policy_name"]) if pd.notna(row.get("policy_name")) else "Unknown", # Gate 1
        "policy_value_numeric": int(float(row["policy_value_numeric"])) if pd.notna(row.get("policy_value_numeric")) else None, # Gate 2
        "policy_value_unit": _validate_enum(row.get("policy_value_unit"), ["days", "months", "years", "hours", "count"], "days", "policy_value_unit"), # Gate 2, Technique 5
        "effective_date": _truncate_to_date(row.get("effective_date")), # Gate 2, Technique 2
        "last_updated": _truncate_to_date(row.get("last_updated")), # Gate 2, Technique 2
        "is_active": _safe_bool(row.get("is_active")) # Gate 2
    }

# ═══════════════════════════════════════════════════════════════
# MAIN DISPATCHER
# ═══════════════════════════════════════════════════════════════
def anonymize_dataframe(df: pd.DataFrame, table_name: str, tenant_id: str) -> Union[dict, List[dict]]:
    """
    Applies anonymization techniques based on the specific table's schema 
    and DPDP Act gate requirements. Routes to the correct table anonymizer.
    """
    if df is None or df.empty:
        return [] if table_name not in ["governance_config", "system_inventory", "policies", "customer_master", "consent_records", "data_lifecycle"] else {}

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
import datetime
from typing import Dict, List, Any
from .hasher import hash_id

def _truncate_timestamp(ts: str) -> str:
    """
    Technique 2 — Timestamp Truncation
    Evidence: ISO/IEC 20889 — generalisation technique.
    Time-of-day creates re-identification risk. Date is sufficient.
    """
    if not ts:
        return None
    if isinstance(ts, str):
        try:
            return date.fromisoformat(ts.strip().split(" ")[0].split("T")[0]).isoformat()
        except ValueError:
            pass
            
    parsed = pd.to_datetime(ts, errors="coerce", dayfirst=True)
    if not pd.isna(parsed):
        return parsed.date().isoformat()
    text = str(ts).strip().split(" ")[0].split("T")[0]
    parts = text.split("-")
    if len(parts) == 3 and len(parts[2]) == 4:
        return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return text

def _get_today_str() -> str:
    return datetime.date.today().isoformat()

def map_governance_config(policies: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maps policies data to governance_config table.
    Gate 1: tenant_id is required for isolation.
    Gate 1/2: company_name kept as tenant_name for MVP identification, though no DPDP agent uses it.
    Gate 2: grievance_endpoint_available needed for compliance checks.
    Technique 4: Drops consent_flag, notice_provided, etc. here as they fall under different tables.
    """
    return {
        "tenant_id": policies["tenant_id"], # Gate 1: Keep
        "tenant_name": policies.get("company_name", "Unknown"), # Gate 1: Keep (Mapped from company_name)
        "grievance_endpoint_available": policies.get("grievance_endpoint_available", False), # Gate 2: Keep
        "dpo_assigned": False, # Generated
        "audit_frequency_days": 90, # Generated
        "last_audit_date": _get_today_str(), # Generated
        "risk_level": "MEDIUM" # Generated
    }

def map_system_inventory(sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maps system_inventory raw data to new system_inventory table.
    Technique 1: hash_id on component_id
    Technique 5: storage -> system_type, pii_encrypted -> data_processor_type
    Technique 4 (Suppression): Drop name, data_collected, storage, age (used in customer_master instead), component_id
    """
    tenant_id = sys_inv["tenant_id"]
    
    # Technique 5: storage mapped to system_type_enum
    storage = sys_inv.get("storage", "")
    if storage == "encrypted_db":
        sys_type = "core_banking"
    elif storage == "plain_text":
        sys_type = "crm"
    else:
        sys_type = "crm"

    return {
        "system_hash": hash_id(sys_inv.get("component_id", "COMP-001"), tenant_id), # Gate 1
        "tenant_id": tenant_id, # Gate 1
        "system_name": "User Database", # Gate 1: Hardcoded per instructions
        "system_type": sys_type, # Gate 2
        "encryption_enabled": sys_inv.get("pii_encrypted", False), # Gate 2
        "access_control_enabled": sys_inv.get("access_control_enabled", False), # Gate 2
        "data_processor_type": "internal", # Gate 1 (Derived from pii_encrypted existence)
        "retention_policy_applied": sys_inv.get("audit_logging_enabled", False), # Gate 2
        "dpa_signed": False, # Generated
        "dpa_expiry_date": None # Generated
    }

def map_policies(policies: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maps raw policies into standard retention policy for the policies table.
    Gate 1: tenant_id, policy_hash
    Gate 2: standard values for retention required by agent checks
    """
    tenant_id = policies["tenant_id"]
    return {
        "policy_hash": hash_id(f"{tenant_id}_ret_policy", tenant_id),
        "tenant_id": tenant_id,
        "policy_type": "retention",
        "policy_name": "Default Retention Policy",
        "policy_value_numeric": 365,
        "policy_value_unit": "days",
        "effective_date": _get_today_str(),
        "last_updated": _get_today_str(),
        "is_active": True
    }

def map_customer_master(sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates one synthetic customer per tenant based on system inventory stats.
    Technique 1: hash_id applied to synthetic ID
    Gate 1: customer_hash
    Gate 2: age dictates if minor data principal type is applied.
    """
    tenant_id = sys_inv["tenant_id"]
    age = sys_inv.get("age", 25)
    is_minor = age < 18
    princ_type = "minor" if is_minor else "individual"
    
    return {
        "customer_hash": hash_id("CUST_001", tenant_id), # Gate 1
        "tenant_id": tenant_id, # Gate 1
        "is_minor": is_minor, # Gate 2: Age derived check
        "data_principal_type": princ_type, # Gate 2
        "account_status": "active", # Gate 2
        "kyc_status": "verified", # Gate 2
        "country": "IN", # Gate 2
        "created_at": _get_today_str() # Gate 1
    }

def map_consent_records(policies: Dict[str, Any], sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maps consent flags from policies into consent_records table.
    Technique 5: consent_flag bool -> consent_status ENUM
    """
    tenant_id = policies["tenant_id"]
    
    # Technique 5 mapping
    consent_flag = policies.get("consent_flag", False)
    consent_status = "active" if consent_flag else "expired"
    
    # Guardian consent hash
    guardian_consent = sys_inv.get("guardian_consent", False)
    g_hash = hash_id(f"{tenant_id}_guardian", tenant_id) if guardian_consent else None

    # Calculate expiry
    expiry = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()
    
    return {
        "consent_hash": hash_id("CONSENT_001", tenant_id), # Gate 1
        "customer_hash": hash_id("CUST_001", tenant_id), # Gate 1
        "tenant_id": tenant_id, # Gate 1
        "consent_status": consent_status, # Gate 2 (Technique 5)
        "consent_date": _get_today_str(), # Gate 2
        "expiry_date": expiry, # Gate 2
        "consented_purpose": policies.get("consented_purpose", "loan_processing"), # Gate 2
        "consent_version": "v1.0", # Gate 2
        "notice_provided": policies.get("notice_provided", False), # Gate 2
        "is_bundled": False, # Gate 2
        "consent_channel": "app", # Gate 2
        "guardian_consent_hash": g_hash # Gate 2 (Technique 5 mapping)
    }

def map_transaction_events(logs: List[Dict[str, Any]], policies: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Maps log data to transaction_events.
    Technique 1: hash_id for log IDs.
    Technique 2: Timestamp truncation.
    Technique 5: event_type mapping.
    Technique 4 (Suppression): Drops raw 'user', drops 'log_id' as clear text.
    """
    results = []
    for log in logs:
        tenant_id = log["tenant_id"]
        
        # Technique 5 string mapping
        raw_event = log.get("event_type", "")
        # data_access defaults to account_update for processing context
        event_enum = "account_update" if raw_event == "data_access" else "account_update"
        
        tx = {
            "event_hash": hash_id(log["log_id"] + "_tx", tenant_id), # Gate 1
            "customer_hash": hash_id("CUST_001", tenant_id), # Gate 1
            "tenant_id": tenant_id, # Gate 1
            "consent_hash": hash_id("CONSENT_001", tenant_id), # Gate 1
            "event_type": event_enum, # Gate 2 (Technique 5)
            "processing_purpose": policies.get("processing_purpose", "loan_processing"), # Gate 2
            "event_date": _truncate_timestamp(log.get("timestamp")), # Gate 2 (Technique 2)
            "shared_with_third_party": log.get("shared_with_third_party", False), # Gate 2
            "third_party_hash": None, # Gate 2
            "is_cross_border": False, # Gate 2
            "transfer_country": None # Gate 2
        }
        results.append(tx)
    return results

def map_access_logs(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Maps logs to access_logs table.
    Technique 1: hash_id for employee role.
    Technique 5: employee_role and access_reason ENUM mappings.
    """
    results = []
    for log in logs:
        tenant_id = log["tenant_id"]
        
        raw_role = log.get("employee_role", "")
        role_map = {
            "analyst": "data_analyst",
            "intern": "data_analyst",
            "admin": "compliance_officer"
        }
        mapped_role = role_map.get(raw_role, "customer_support")
        
        reason_map = {
            "data_analyst": "data_export",
            "underwriter": "loan_review",
            "compliance_officer": "kyc_check",
            "collections_agent": "loan_review"
        }
        access_reason = reason_map.get(mapped_role, "support_query")
        
        acc = {
            "access_hash": hash_id(log["log_id"] + "_acc", tenant_id), # Gate 1
            "customer_hash": hash_id("CUST_001", tenant_id), # Gate 1
            "tenant_id": tenant_id, # Gate 1
            "employee_hash": hash_id(mapped_role + "_emp", tenant_id), # Gate 1
            "employee_role": mapped_role, # Gate 2 (Technique 5)
            "accessed_pii": log.get("accessed_pii", False), # Gate 2
            "pii_fields_accessed": "kyc_documents" if log.get("accessed_pii") else None, # Gate 2
            "access_reason": access_reason, # Gate 2 (Technique 5)
            "access_outcome": "granted", # Gate 2
            "data_volume_accessed": "low", # Gate 2
            "access_date": _truncate_timestamp(log.get("timestamp")) # Gate 2 (Technique 2)
        }
        results.append(acc)
    return results

def map_data_lifecycle(sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maps system inventory lifecycle logic to data_lifecycle table.
    Technique 5: Complex ENUM mapping for retention_status.
    """
    tenant_id = sys_inv["tenant_id"]
    
    data_retained = sys_inv.get("data_retained", False)
    purpose_completed = sys_inv.get("purpose_completed", False)
    erasure_requested = sys_inv.get("erasure_requested", False)
    
    # Technique 5 for retention status
    if data_retained and purpose_completed:
        retention_status = "expired"
    elif not data_retained and erasure_requested:
        retention_status = "pending_deletion"
    else:
        retention_status = "active"
        
    return {
        "lifecycle_hash": hash_id("LC_001", tenant_id), # Gate 1
        "customer_hash": hash_id("CUST_001", tenant_id), # Gate 1
        "tenant_id": tenant_id, # Gate 1
        "data_category": "kyc_documents", # Gate 2
        "retention_expiry_date": sys_inv.get("retention_expiry_date"), # Gate 2
        "retention_status": retention_status, # Gate 2 (Technique 5)
        "purpose_completed": purpose_completed, # Gate 2
        "erasure_requested": erasure_requested, # Gate 2
        "erasure_date": _get_today_str() if erasure_requested else None, # Gate 2
        "legal_hold_flag": False, # Gate 2
        "erasure_request_source": "user" if erasure_requested else None # Gate 2
    }

def map_security_events(logs: List[Dict[str, Any]], policies: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Maps breaches to security_events table.
    Technique 3: Buckets affected_user_count into user_count_band ENUM.
    Technique 3: Keeps notification_delay as integer hours.
    Technique 5: pii_encrypted -> encryption_type
    """
    def _bucket_user_count(count) -> str:
        """
        Technique 3 — Bucketing
        Bands derived from CERT-In and DPDP penalty thresholds.
        """
        if count is None:
            return None
        count = int(count)
        if count <= 100:
            return "minimal"
        elif count <= 1000:
            return "moderate"
        elif count <= 10000:
            return "large"
        else:
            return "critical"

    results = []
    for log in logs:
        tenant_id = log["tenant_id"]
        pii_encrypted = policies.get("pii_encrypted", False)
        encryption_type = "AES-256" if pii_encrypted else "none"

        breach_detected = log.get("breach_detected", False)

        if breach_detected:
            confirmed_date = _truncate_timestamp(log.get("timestamp"))
            delay_hours = log.get("notification_delay", 0)
        else:
            confirmed_date = None
            delay_hours = None

        affected_user_count = _bucket_user_count(log.get("affected_user_count")) if breach_detected else None
        if breach_detected and not affected_user_count:
            affected_user_count = "minimal"

        if breach_detected and delay_hours is None:
            delay_hours = 0

        if breach_detected and not confirmed_date:
            confirmed_date = date.today().isoformat()

        sec = {
            "security_hash": hash_id(log["log_id"] + "_sec", tenant_id),
            "customer_hash": hash_id("CUST_001", tenant_id),
            "tenant_id": tenant_id,
            "pii_encrypted": pii_encrypted,
            "encryption_type": encryption_type,
            "breach_detected": breach_detected,
            "breach_confirmed_date": confirmed_date,
            "notification_delay_hours": delay_hours,
            "affected_user_count": affected_user_count,  # Technique 3
            "data_categories_breached": log.get("data_categories_breached") if breach_detected else None,
            "security_audit_flag": False
        }
        results.append(sec)
    return results

def map_dsar_requests(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Maps erasure requests to dsar_requests table.
    Only maps logs where erasure_requested is True.
    """
    results = []
    for log in logs:
        if not log.get("erasure_requested", False):
            continue
            
        tenant_id = log["tenant_id"]
        sub_date_str = _truncate_timestamp(log.get("timestamp"))
        if sub_date_str:
            try:
                sub_date = date.fromisoformat(sub_date_str)
            except ValueError:
                sub_date = pd.to_datetime(sub_date_str, errors="coerce", dayfirst=True).date() if sub_date_str else datetime.date.today()
        else:
            sub_date = datetime.date.today()
            
        if pd.isna(sub_date):
            sub_date = datetime.date.today()
        
        sla_due = sub_date + datetime.timedelta(days=30)
        today = datetime.date.today()
        
        data_deleted = log.get("data_deleted", False)
        sla_breached = not data_deleted and today > sla_due
        
        dsar = {
            "dsar_hash": hash_id(log["log_id"] + "_dsar", tenant_id), # Gate 1
            "customer_hash": hash_id("CUST_001", tenant_id), # Gate 1
            "tenant_id": tenant_id, # Gate 1
            "request_type": "erasure", # Gate 2
            "submitted_date": sub_date.isoformat(), # Gate 2 (Technique 2)
            "acknowledged_date": None, # Gate 2
            "sla_due_date": sla_due.isoformat(), # Gate 2
            "sla_breached": sla_breached, # Gate 2
            "fulfilled_date": _get_today_str() if data_deleted else None, # Gate 2
            "fulfillment_status": "fulfilled" if data_deleted else "pending", # Gate 2
            "rejection_reason": None # Gate 2
        }
        results.append(dsar)
    return results
