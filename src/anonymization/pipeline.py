import json
import datetime
import pandas as pd
from typing import Dict, List, Any
from pathlib import Path
from src.config import tenant_raw_dir

# Import new CSV components
from .csv_loader import load_tenant_csvs
from .field_mapper import anonymize_dataframe
from .db_writer import write_tenant_data
from .hasher import hash_id

# ── LEGACY JSON MAPPER FUNCTIONS ─────────────────────
# (Retained for testing backward compatibility during sunset phase)

def _truncate_timestamp(ts: str) -> str:
    """
    Technique 2 — Timestamp Truncation
    Evidence: ISO/IEC 20889 — generalisation technique.
    Time-of-day creates re-identification risk. Date is sufficient.
    """
    if not ts:
        return None
    return ts.split("T")[0]

def _get_today_str() -> str:
    return datetime.date.today().isoformat()

def map_governance_config(policies: Dict[str, Any]) -> Dict[str, Any]:
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
    tenant_id = sys_inv["tenant_id"]
    storage = sys_inv.get("storage", "")
    if storage == "encrypted_db":
        sys_type = "core_banking"
    elif storage == "plain_text":
        sys_type = "crm"
    else:
        sys_type = "crm"

    return {
        "system_hash": hash_id(sys_inv.get("component_id", "COMP-001"), tenant_id),
        "tenant_id": tenant_id,
        "system_name": "User Database",
        "system_type": sys_type,
        "encryption_enabled": sys_inv.get("pii_encrypted", False),
        "access_control_enabled": sys_inv.get("access_control_enabled", False),
        "data_processor_type": "internal",
        "retention_policy_applied": sys_inv.get("audit_logging_enabled", False),
        "dpa_signed": False,
        "dpa_expiry_date": None
    }

def map_policies(policies: Dict[str, Any]) -> Dict[str, Any]:
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
    tenant_id = sys_inv["tenant_id"]
    age = sys_inv.get("age", 25)
    is_minor = age < 18
    princ_type = "minor" if is_minor else "individual"
    
    return {
        "customer_hash": hash_id("CUST_001", tenant_id),
        "tenant_id": tenant_id,
        "is_minor": is_minor,
        "data_principal_type": princ_type,
        "account_status": "active",
        "kyc_status": "verified",
        "country": "IN",
        "created_at": _get_today_str()
    }

def map_consent_records(policies: Dict[str, Any], sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    tenant_id = policies["tenant_id"]
    consent_flag = policies.get("consent_flag", False)
    consent_status = "active" if consent_flag else "expired"
    guardian_consent = sys_inv.get("guardian_consent", False)
    g_hash = hash_id(f"{tenant_id}_guardian", tenant_id) if guardian_consent else None
    expiry = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()
    
    return {
        "consent_hash": hash_id("CONSENT_001", tenant_id),
        "customer_hash": hash_id("CUST_001", tenant_id),
        "tenant_id": tenant_id,
        "consent_status": consent_status,
        "consent_date": _get_today_str(),
        "expiry_date": expiry,
        "consented_purpose": policies.get("consented_purpose", "loan_processing"),
        "consent_version": "v1.0",
        "notice_provided": policies.get("notice_provided", False),
        "is_bundled": False,
        "consent_channel": "app",
        "guardian_consent_hash": g_hash
    }

def map_transaction_events(logs: List[Dict[str, Any]], policies: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    for log in logs:
        tenant_id = log["tenant_id"]
        raw_event = log.get("event_type", "")
        event_enum = "account_update" if raw_event == "data_access" else "account_update"
        
        tx = {
            "event_hash": hash_id(log["log_id"] + "_tx", tenant_id),
            "customer_hash": hash_id("CUST_001", tenant_id),
            "tenant_id": tenant_id,
            "consent_hash": hash_id("CONSENT_001", tenant_id),
            "event_type": event_enum,
            "processing_purpose": policies.get("processing_purpose", "loan_processing"),
            "event_date": _truncate_timestamp(log.get("timestamp")),
            "shared_with_third_party": log.get("shared_with_third_party", False),
            "third_party_hash": None,
            "is_cross_border": False,
            "transfer_country": None
        }
        results.append(tx)
    return results

def map_access_logs(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for log in logs:
        tenant_id = log["tenant_id"]
        raw_role = log.get("employee_role", "")
        role_map = {
            "analyst": "data_analyst", "intern": "data_analyst", "admin": "compliance_officer"
        }
        mapped_role = role_map.get(raw_role, "customer_support")
        reason_map = {
            "data_analyst": "data_export", "underwriter": "loan_review", 
            "compliance_officer": "kyc_check", "collections_agent": "loan_review"
        }
        access_reason = reason_map.get(mapped_role, "support_query")
        
        acc = {
            "access_hash": hash_id(log["log_id"] + "_acc", tenant_id),
            "customer_hash": hash_id("CUST_001", tenant_id),
            "tenant_id": tenant_id,
            "employee_hash": hash_id(mapped_role + "_emp", tenant_id),
            "employee_role": mapped_role,
            "accessed_pii": log.get("accessed_pii", False),
            "pii_fields_accessed": "kyc_documents" if log.get("accessed_pii") else None,
            "access_reason": access_reason,
            "access_outcome": "granted",
            "data_volume_accessed": "low",
            "access_date": _truncate_timestamp(log.get("timestamp"))
        }
        results.append(acc)
    return results

def map_data_lifecycle(sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    tenant_id = sys_inv["tenant_id"]
    data_retained = sys_inv.get("data_retained", False)
    purpose_completed = sys_inv.get("purpose_completed", False)
    erasure_requested = sys_inv.get("erasure_requested", False)
    
    if data_retained and purpose_completed:
        retention_status = "expired"
    elif not data_retained and erasure_requested:
        retention_status = "pending_deletion"
    else:
        retention_status = "active"
        
    return {
        "lifecycle_hash": hash_id("LC_001", tenant_id),
        "customer_hash": hash_id("CUST_001", tenant_id),
        "tenant_id": tenant_id,
        "data_category": "kyc_documents",
        "retention_expiry_date": sys_inv.get("retention_expiry_date"),
        "retention_status": retention_status,
        "purpose_completed": purpose_completed,
        "erasure_requested": erasure_requested,
        "erasure_date": _get_today_str() if erasure_requested else None,
        "legal_hold_flag": False,
        "erasure_request_source": "user" if erasure_requested else None
    }

def map_security_events(logs: List[Dict[str, Any]], policies: Dict[str, Any]) -> List[Dict[str, Any]]:
    def _bucket_user_count(count) -> str:
        if count is None: return None
        count = int(count)
        if count <= 100: return "minimal"
        elif count <= 1000: return "moderate"
        elif count <= 10000: return "large"
        else: return "critical"

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
            confirmed_date = datetime.date.today().isoformat()

        sec = {
            "security_hash": hash_id(log["log_id"] + "_sec", tenant_id),
            "customer_hash": hash_id("CUST_001", tenant_id),
            "tenant_id": tenant_id,
            "pii_encrypted": pii_encrypted,
            "encryption_type": encryption_type,
            "breach_detected": breach_detected,
            "breach_confirmed_date": confirmed_date,
            "notification_delay_hours": delay_hours,
            "affected_user_count": affected_user_count,
            "data_categories_breached": log.get("data_categories_breached") if breach_detected else None,
            "security_audit_flag": False
        }
        results.append(sec)
    return results

def map_dsar_requests(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for log in logs:
        if not log.get("erasure_requested", False): continue
        tenant_id = log["tenant_id"]
        sub_date_str = _truncate_timestamp(log.get("timestamp"))
        sub_date = pd.to_datetime(sub_date_str, errors="coerce", dayfirst=True).date() if sub_date_str else datetime.date.today()
        if pd.isna(sub_date):
            sub_date = datetime.date.today()
        sla_due = sub_date + datetime.timedelta(days=30)
        today = datetime.date.today()
        data_deleted = log.get("data_deleted", False)
        sla_breached = not data_deleted and today > sla_due
        
        dsar = {
            "dsar_hash": hash_id(log["log_id"] + "_dsar", tenant_id),
            "customer_hash": hash_id("CUST_001", tenant_id),
            "tenant_id": tenant_id,
            "request_type": "erasure",
            "submitted_date": sub_date.isoformat(),
            "acknowledged_date": None,
            "sla_due_date": sla_due.isoformat(),
            "sla_breached": sla_breached,
            "fulfilled_date": _get_today_str() if data_deleted else None,
            "fulfillment_status": "fulfilled" if data_deleted else "pending",
            "rejection_reason": None
        }
        results.append(dsar)
    return results

# ─────────────────────────────────────────────────────────────────

def run_anonymization_pipeline(tenant_id: str) -> dict:
    """
    Orchestrates the full anonymization pipeline.
    
    NEW WORKFLOW (CSV -> DB):
    1. Locates 10 CSVs for the tenant.
    2. Loads them securely via csv_loader enforcing suppression columns.
    3. Routes each dataframe via field_mapper applying Technique 1-5 and Gate logic.
    4. Writes payload via DB writer and handles PostgreSQL connections and errors.
    """
    try:
        csv_dir = tenant_raw_dir(tenant_id)
        
        dfs = load_tenant_csvs(csv_dir, tenant_id)
        
        mapped_data = {}
        for table_name, df in dfs.items():
            mapped_data[table_name] = anonymize_dataframe(df, table_name, tenant_id)
            
        rows_written = write_tenant_data(tenant_id, mapped_data)
        
        return {
            "tenant_id": tenant_id,
            "tables_written": len(mapped_data),
            "rows_written": rows_written,
            "status": "success"
        }
        
    except FileNotFoundError as e:
        return {"tenant_id": tenant_id, "status": "error", "message": str(e)}
    except Exception as e:
        return {"tenant_id": tenant_id, "status": "error", "message": f"Pipeline execution error: {str(e)}"}

if __name__ == "__main__":
    import sys
    tenant_identifier = sys.argv[1] if len(sys.argv) > 1 else "tenant_a"
    result_dict = run_anonymization_pipeline(tenant_identifier)
    print(json.dumps(result_dict, indent=2))

