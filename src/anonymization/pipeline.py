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

# ── LEGACY JSON MAPPER FUNCTIONS (DISABLED) ─────────────

class LegacyPipelineDisabledError(Exception):
    """Raised when any legacy JSON mapper function is called."""
    pass

def _truncate_timestamp(ts: str) -> str:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def _get_today_str() -> str:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_governance_config(policies: Dict[str, Any]) -> Dict[str, Any]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_system_inventory(sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_policies(policies: Dict[str, Any]) -> Dict[str, Any]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_customer_master(sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_consent_records(policies: Dict[str, Any], sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_transaction_events(logs: List[Dict[str, Any]], policies: Dict[str, Any]) -> List[Dict[str, Any]]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_access_logs(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_data_lifecycle(sys_inv: Dict[str, Any]) -> Dict[str, Any]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_security_events(logs: List[Dict[str, Any]], policies: Dict[str, Any]) -> List[Dict[str, Any]]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

def map_dsar_requests(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raise LegacyPipelineDisabledError("Legacy pipeline is retired and disabled.")

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

