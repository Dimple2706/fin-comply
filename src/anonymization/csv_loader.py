import pandas as pd
from pathlib import Path
from typing import Dict, List, Set, Any

class MissingColumnError(ValueError):
    def __init__(self, filename: str, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"Missing column {field} in {filename}: {explanation}")

class TenantValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, expected_tenant: str, supplied_tenant: str, error_code: str):
        self.filename = filename
        self.row_number = row_number
        self.expected_tenant = expected_tenant
        self.supplied_tenant = supplied_tenant
        self.error_code = error_code
        super().__init__(
            f"Validation error in {filename} at row {row_number}: {error_code} "
            f"(Expected '{expected_tenant}', got '{supplied_tenant}')"
        )

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
        ["consented_purpose"],
        ["guardian_consent_hash", "guardian_consent_id"]
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
        ["request_type"],
        ["submitted_date", "submitted_at"],
        ["sla_due_date"],
        ["fulfilled_date", "fulfilled_at"]
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
            
        # 2. Strict tenant_id matching
        clean_tenant_id = str(tenant_id).strip()
        if "tenant_id" not in df.columns:
            raise TenantValidationError(
                filename=filename,
                row_number=1,
                expected_tenant=clean_tenant_id,
                supplied_tenant="",
                error_code="MISSING_TENANT_COLUMN"
            )
            
        for i, val in enumerate(df["tenant_id"]):
            row_num = i + 2 # Header is line 1
            if pd.isna(val):
                raise TenantValidationError(
                    filename=filename,
                    row_number=row_num,
                    expected_tenant=clean_tenant_id,
                    supplied_tenant="",
                    error_code="BLANK_TENANT_ID"
                )
            
            supplied = str(val).strip()
            if not supplied:
                raise TenantValidationError(
                    filename=filename,
                    row_number=row_num,
                    expected_tenant=clean_tenant_id,
                    supplied_tenant="",
                    error_code="BLANK_TENANT_ID"
                )
                
            if supplied != clean_tenant_id:
                raise TenantValidationError(
                    filename=filename,
                    row_number=row_num,
                    expected_tenant=clean_tenant_id,
                    supplied_tenant=supplied,
                    error_code="TENANT_MISMATCH"
                )
        
        df["tenant_id"] = clean_tenant_id
        
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
            missing_col = missing_groups[0].split(" or ")[0]
            raise MissingColumnError(
                filename=filename, 
                field=missing_col, 
                error_code="MISSING_COLUMN", 
                explanation=f"File {filename} is missing required columns: {missing_groups}"
            )
            
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
