import pandas as pd
from pathlib import Path
from typing import Dict, List, Set, Any

# ═══════════════════════════════════════════════════════════════
# EXPECTED FILES
# ═══════════════════════════════════════════════════════════════
EXPECTED_FILES: Dict[str, str] = {
    "governance_config": "governance_config.csv",
    "customer_master": "customer_master.csv",
    "consent_records": "consent_records.csv",
    "transaction_events": "transaction_events.csv",
    "access_logs": "access_logs.csv",
    "data_lifecycle": "data_lifecycle.csv",
    "security_events": "security_events.csv",
    "dsar_requests": "dsar_requests.csv",
    "system_inventory": "system_inventory.csv",
    "policies": "policies.csv"
}

# tables that must have exactly 1 row per tenant_id
SINGLE_ROW_TABLES: Set[str] = {
    "governance_config"
}

# ═══════════════════════════════════════════════════════════════
# COLUMN SCHEMAS (KEEP + RAW IDs)
# ═══════════════════════════════════════════════════════════════
REQUIRED_COLUMNS: Dict[str, List[str]] = {
    "governance_config": [
        "tenant_id", "tenant_name", "grievance_endpoint_available", 
        "dpo_assigned", "audit_frequency_days", "last_audit_date", "risk_level"
    ],
    "customer_master": [
        "customer_id", "tenant_id", "is_minor", "data_principal_type", 
        "account_status", "kyc_status", "country", "created_at","dob"
    ],
    "consent_records": [
        "consent_id", "customer_id", "tenant_id", "consent_status", 
        "consent_timestamp", "expiry_timestamp", "consented_purpose", "consent_version", 
        "notice_provided", "is_bundled", "consent_channel", "withdrawal_timestamp"
    ],
    "transaction_events": [
        "event_id", "customer_id", "tenant_id", "consent_id", "event_type", 
        "processing_purpose", "timestamp", "shared_with_third_party", 
        "third_party_id", "is_cross_border", "transfer_country"
    ],
    "access_logs": [
        "access_id", "customer_id", "tenant_id", "employee_id", "employee_role", 
        "accessed_pii", "pii_fields_accessed", "access_reason", "access_outcome", 
        "data_volume_accessed", "timestamp"
    ],
    "data_lifecycle": [
        "lifecycle_id", "customer_id", "tenant_id", "data_category", 
        "retention_expiry_date", "retention_status", "purpose_completed", 
        "erasure_requested", "erasure_timestamp", "legal_hold_flag", "erasure_request_source"
    ],
    "security_events": [
        "security_id", "customer_id", "tenant_id", "pii_encrypted", "encryption_type", 
        "breach_detected", "breach_confirmed_at", "notification_delay_hours", 
        "affected_user_count", "data_categories_breached", "security_audit_flag"
    ],
    "dsar_requests": [
        "dsar_id", "customer_id", "tenant_id", "request_type", "submitted_at", 
        "acknowledged_at", "sla_due_date", "sla_breached",
        "fulfillment_status", "rejection_reason"
    ],
    "system_inventory": [
        "system_id", "tenant_id", "system_name", "system_type", "data_types_stored", "pii_stored", 
        "encryption_enabled", "access_control_enabled", "retention_policy_applied", 
        "third_party_integrations", "data_processor_type", "dpa_signed", "dpa_expiry_date"
    ],
    "policies": [
        "policy_id", "tenant_id", "policy_type", "policy_name", "policy_value_numeric", 
        "policy_value_unit", "effective_date", "last_updated", "is_active"
    ]
}

# ═══════════════════════════════════════════════════════════════
# COLUMNS TO DROP (Suppression - Technique 4)
# ═══════════════════════════════════════════════════════════════
DROP_COLUMNS: Dict[str, List[str]] = {
    "customer_master": ["name,age,gender,email,phone,address"],
    "transaction_events": ["account", "device_id", "ip_address"],
    "data_lifecycle": ["data_deleted", "data_retained"],
    "governance_config": ["dpo_contact_masked"],
    "policies": ["policy_value_text"]
}

def validate_csv_directory(csv_dir: Path) -> Dict[str, Any]:
    """
    Checks which CSV files exist in the target directory and which are missing.
    Returns dict: {"valid": bool, "missing": list, "found": list}
    """
    found = []
    missing = []
    
    if not csv_dir.exists():
        return {"valid": False, "missing": list(EXPECTED_FILES.values()), "found": []}
        
    for table_name, filename in EXPECTED_FILES.items():
        if (csv_dir / filename).exists():
            found.append(filename)
        else:
            missing.append(filename)
            
    return {
        "valid": len(missing) == 0,
        "missing": missing,
        "found": found
    }

def load_tenant_csvs(csv_dir: Path, tenant_id: str) -> Dict[str, pd.DataFrame]:
    """
    Loads all 10 CSV files, drops suppressed columns, filters by tenant_id, 
    and validates required columns and single-row constraints.
    """
    dfs = {}
    
    for table_name, filename in EXPECTED_FILES.items():
        file_path = csv_dir / filename
        
        # 1. Load CSV
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            raise ValueError(f"Failed to read {filename}: {str(e)}")
            
        # 2. Filter rows by tenant_id (Critical to avoid cross-tenant pollution)
        if "tenant_id" not in df.columns:
            raise ValueError(f"CRITICAL: {filename} is missing 'tenant_id' column.")
            
        df = df[df["tenant_id"] == tenant_id].copy()
        
        # 3. Drop suppression columns (Technique 4)
        cols_to_drop = DROP_COLUMNS.get(table_name, [])
        for col in cols_to_drop:
            if col in df.columns:
                df = df.drop(columns=[col])
                
        # 4. Validate required columns exist
        missing_cols = [c for c in REQUIRED_COLUMNS[table_name] if c not in df.columns]
        if missing_cols:
            raise ValueError(f"File {filename} is missing required columns: {missing_cols}")
            
        # Preserve flexible JSONB extension field.
        # Older uploads may not contain it, so default to empty JSON.
        if "additional_attributes" not in df.columns:
            df["additional_attributes"] = "{}"

        df = df[REQUIRED_COLUMNS[table_name] + ["additional_attributes"]]
            
        # 5. Validate single-row constraints
        if table_name in SINGLE_ROW_TABLES:
            row_count = len(df)
            if row_count == 0:
                raise ValueError(f"{table_name} has no rows for tenant_id={tenant_id}")
            elif row_count > 1:
                raise ValueError(
                    f"{table_name} expects exactly 1 row for tenant_id={tenant_id}, found {row_count}. "
                    f"Single-row tables enforce a one-record-per-tenant constraint matching "
                    f"db_writer.py's data contract."
                )
                
        dfs[table_name] = df
        
    return dfs
