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
# REQUIRED COLUMN GROUPS (Supports both Canonical Hashed & Raw IDs)
# ═══════════════════════════════════════════════════════════════
REQUIRED_COLUMN_GROUPS: Dict[str, List[List[str]]] = {
    "governance_config": [
        ["tenant_id"],
        ["tenant_name"],
        ["grievance_endpoint_available"],
        ["dpo_assigned"]
    ],
    "customer_master": [
        ["customer_hash", "customer_id"],
        ["tenant_id"],
        ["is_minor"],
        ["data_principal_type"]
    ],
    "consent_records": [
        ["consent_hash", "consent_id"],
        ["customer_hash", "customer_id"],
        ["tenant_id"],
        ["consent_status"],
        ["consented_purpose"]
    ],
    "transaction_events": [
        ["event_hash", "event_id"],
        ["customer_hash", "customer_id"],
        ["tenant_id"],
        ["event_type"],
        ["processing_purpose"]
    ],
    "access_logs": [
        ["access_hash", "access_id"],
        ["customer_hash", "customer_id"],
        ["tenant_id"],
        ["employee_role"]
    ],
    "data_lifecycle": [
        ["lifecycle_hash", "lifecycle_id"],
        ["customer_hash", "customer_id"],
        ["tenant_id"],
        ["data_category"]
    ],
    "security_events": [
        ["security_hash", "security_id"],
        ["customer_hash", "customer_id"],
        ["tenant_id"]
    ],
    "dsar_requests": [
        ["dsar_hash", "dsar_id"],
        ["customer_hash", "customer_id"],
        ["tenant_id"],
        ["request_type"]
    ],
    "system_inventory": [
        ["system_hash", "system_id"],
        ["tenant_id"],
        ["system_name"],
        ["system_type"]
    ],
    "policies": [
        ["policy_hash", "policy_id"],
        ["tenant_id"],
        ["policy_type"],
        ["policy_name"]
    ]
}

# ═══════════════════════════════════════════════════════════════
# COLUMNS TO DROP (Suppression - Technique 4)
# ═══════════════════════════════════════════════════════════════
DROP_COLUMNS: Dict[str, List[str]] = {
    "customer_master": ["name", "age", "gender", "email", "phone", "address", "dob"],
    "transaction_events": ["account", "device_id", "ip_address"],
    "data_lifecycle": ["data_deleted", "data_retained"],
    "governance_config": [],
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
    Supports both canonical pre-hashed CSVs and raw ID CSVs.
    """
    dfs = {}
    
    for table_name, filename in EXPECTED_FILES.items():
        file_path = csv_dir / filename
        
        # 1. Load CSV
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            raise ValueError(f"Failed to read {filename}: {str(e)}")
            
        # 2. Case-insensitive & whitespace-tolerant tenant_id matching
        clean_tenant_id = str(tenant_id).strip()
        if "tenant_id" not in df.columns:
            df["tenant_id"] = clean_tenant_id
        else:
            df["tenant_id"] = df["tenant_id"].astype(str).str.strip()
            filtered = df[df["tenant_id"].str.upper() == clean_tenant_id.upper()].copy()
            if len(filtered) == 0 and len(df) > 0:
                df["tenant_id"] = clean_tenant_id
            else:
                df = filtered
        
        # 3. Drop suppression columns (Technique 4)
        cols_to_drop = DROP_COLUMNS.get(table_name, [])
        for col in cols_to_drop:
            if col in df.columns:
                df = df.drop(columns=[col])
                
        # 4. Validate required column groups exist (at least one per group)
        missing_groups = []
        for group in REQUIRED_COLUMN_GROUPS.get(table_name, []):
            if not any(c in df.columns for c in group):
                missing_groups.append(" or ".join(group))
        if missing_groups:
            raise ValueError(f"File {filename} is missing required columns: {missing_groups}")
            
        # Preserve flexible JSONB extension field.
        # Older uploads may not contain it, so default to empty JSON.
        if "additional_attributes" not in df.columns:
            df["additional_attributes"] = "{}"
            
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
