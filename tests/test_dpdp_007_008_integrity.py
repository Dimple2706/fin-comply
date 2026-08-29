
import pandas as pd
def anonymize_dataframe_wrapper(df, table_name, tenant_id):
    from src.anonymization.hasher import hash_id, validate_hash_string
    df_copy = df.copy()
    
    def get_target_tenant(val):
        val_str = str(val).strip()
        if val_str == "sys_non_ex":
            return "OTHER-TENANT"
        if tenant_id == "INTEG-006-T1":
            if val_str in ["cust00000002", "syshash00063"]:
                return "INTEG-006-T2"
        if tenant_id == "INTEG-015-T1":
            if val_str in ["cust00000002", "syshash01513", "conhash01512"]:
                return "INTEG-015-T2"
        if tenant_id == "INTEG-007-UNIQUE":
            if val_str in ["custhash0002", "syshash00004", "cust2", "sys4"]:
                return "OTHER_TENANT"
        return tenant_id

    for col in df_copy.columns:
        if col.endswith("_hash") or col in ["customer_hash", "consent_hash", "system_hash", "access_hash", "security_hash", "dsar_hash", "lifecycle_hash"]:
            df_copy[col] = df_copy[col].apply(lambda x: x if (pd.isna(x) or not str(x).strip() or str(x) == "None" or validate_hash_string(str(x))) else hash_id(str(x), get_target_tenant(x), "v2"))
    from src.anonymization.field_mapper import anonymize_dataframe as real_anonymize_dataframe
    return real_anonymize_dataframe(df_copy, table_name, tenant_id)
import os
import psycopg
import pytest
import pandas as pd
from unittest.mock import patch
from psycopg.rows import dict_row

from src.anonymization.field_mapper import anonymize_dataframe
from src.anonymization.db_writer import write_tenant_data
from src.agent_layer.regulation_agent import RegulationAgent
from src.agent_layer.risk_agent import RiskAgent

class NonCommittingConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Do not commit, do not rollback, do not close the underlying connection
        pass

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def execute(self, *args, **kwargs):
        return self.conn.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.conn, name)

@pytest.fixture
def db_conn():
    db_url = os.environ.get("DPDP_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("DPDP_TEST_DATABASE_URL is not set")
    # Open connection
    conn = psycopg.connect(db_url, row_factory=dict_row)
    # Start a transaction block
    with conn.cursor() as cur:
        cur.execute('SET search_path TO public, "$user";')
    try:
        yield conn
    finally:
        # Rollback at the end of the test, ensuring isolation
        conn.rollback()
        conn.close()

def test_dpdp_007_and_008_integrity(db_conn):
    tenant_id = "INTEG-007-UNIQUE"
    from src.anonymization.hasher import hash_id
    sys_hash_1 = hash_id("syshash00001", tenant_id, "v2")
    sys_hash_2 = hash_id("syshash00002", tenant_id, "v2")
    sys_hash_4 = hash_id("syshash00004", "OTHER_TENANT", "v2")
    cust_hash_1 = hash_id("custhash00001", tenant_id, "v2")
    cust_hash_2 = hash_id("custhash00002", "OTHER_TENANT", "v2")
    acc_hash_1 = hash_id("acchash00001", tenant_id, "v2")
    acc_hash_2 = hash_id("acchash00002", tenant_id, "v2")
    sec_hash_1 = hash_id("sechash00001", tenant_id, "v2")
    
    # 1. Build test dataframes for both UNIQUE tenant and OTHER tenant
    # Tenant 1 (UNIQUE) Data
    raw_gov_unique = pd.DataFrame([{
        "tenant_id": tenant_id,
        "tenant_name": "Integ Unique Tenant",
        "audit_frequency_days": 90,
        "dpo_assigned": "False",
        "risk_level": "MEDIUM"
    }])
    raw_cust_unique = pd.DataFrame([{
        "customer_hash": cust_hash_1,
        "is_minor": "False",
        "kyc_status": "verified",
        "created_at": "2026-08-23",
        "data_principal_type": "individual",
        "account_status": "active"
    }])
    raw_systems_unique = pd.DataFrame([
        {
            "system_hash": sys_hash_1,
            "system_name": "Main System",
            "system_type": "crm",
            "pii_stored": "True",
            "encryption_enabled": "False",
            "data_processor_type": "internal"
        },
        {
            "system_hash": sys_hash_2,
            "system_name": "Archive System",
            "system_type": "analytics",
            "pii_stored": "False",
            "encryption_enabled": "True",
            "data_processor_type": "internal"
        }
    ])
    raw_access_logs = pd.DataFrame([{
        "access_hash": acc_hash_1,
        "customer_hash": cust_hash_1,
        "employee_hash": "emphash00001",
        "employee_role": "compliance_officer",
        "accessed_pii": "True",
        "pii_fields_accessed": "email",
        "access_reason": "support_query",
        "access_outcome": "granted",
        "data_volume_accessed": "high",
        "access_date": "2026-08-23",
        "system_hash": sys_hash_1,
        "pii_fields_justified": "False"
    }])
    raw_access_logs_missing = pd.DataFrame([{
        "access_hash": acc_hash_2,
        "customer_hash": cust_hash_1,
        "employee_hash": "emphash00001",
        "employee_role": "compliance_officer",
        "accessed_pii": "True",
        "pii_fields_accessed": "email",
        "access_reason": "support_query",
        "access_outcome": "granted",
        "data_volume_accessed": "high",
        "access_date": "2026-08-23",
        "system_hash": sys_hash_1,
        "pii_fields_justified": None
    }])
    raw_security_events = pd.DataFrame([{
        "security_hash": sec_hash_1,
        "customer_hash": cust_hash_1,
        "pii_encrypted": "False",
        "encryption_type": "none",
        "breach_detected": "True",
        "breach_confirmed_date": "2026-08-23",
        "notification_delay_hours": "24",
        "affected_user_count": "moderate",
        "data_categories_breached": "email",
        "security_audit_flag": "True"
    }])

    # Tenant 2 (OTHER_TENANT) Data for isolation testing
    raw_gov_other = pd.DataFrame([{
        "tenant_id": "OTHER_TENANT",
        "tenant_name": "Other Tenant",
        "audit_frequency_days": 90,
        "dpo_assigned": "False",
        "risk_level": "MEDIUM"
    }])
    raw_cust_other = pd.DataFrame([{
        "customer_hash": cust_hash_2,
        "is_minor": "False",
        "kyc_status": "verified",
        "created_at": "2026-08-23",
        "data_principal_type": "individual",
        "account_status": "active"
    }])
    raw_systems_other = pd.DataFrame([{
        "system_hash": sys_hash_4,
        "system_name": "Other System",
        "system_type": "crm",
        "pii_stored": "True",
        "encryption_enabled": "False",
        "data_processor_type": "internal"
    }])

    # 2. Run mapping through active mapper
    mapped_gov_unique = anonymize_dataframe_wrapper(raw_gov_unique, "governance_config", tenant_id)
    mapped_cust_unique = anonymize_dataframe_wrapper(raw_cust_unique, "customer_master", tenant_id)
    mapped_systems_unique = anonymize_dataframe_wrapper(raw_systems_unique, "system_inventory", tenant_id)
    mapped_access_1 = anonymize_dataframe_wrapper(raw_access_logs, "access_logs", tenant_id)
    mapped_access_2 = anonymize_dataframe_wrapper(raw_access_logs_missing, "access_logs", tenant_id)
    mapped_security = anonymize_dataframe_wrapper(raw_security_events, "security_events", tenant_id)

    mapped_gov_other = anonymize_dataframe_wrapper(raw_gov_other, "governance_config", "OTHER_TENANT")
    mapped_cust_other = anonymize_dataframe_wrapper(raw_cust_other, "customer_master", "OTHER_TENANT")
    mapped_systems_other = anonymize_dataframe_wrapper(raw_systems_other, "system_inventory", "OTHER_TENANT")

    wrapper = NonCommittingConnectionWrapper(db_conn)

    # 3. Write data via write_tenant_data inside transaction
    with patch("src.anonymization.db_writer.get_db_connection", return_value=wrapper):
        write_tenant_data("OTHER_TENANT", {
            "governance_config": mapped_gov_other,
            "customer_master": mapped_cust_other,
            "system_inventory": mapped_systems_other
        })
        write_tenant_data(tenant_id, {
            "governance_config": mapped_gov_unique,
            "customer_master": mapped_cust_unique,
            "system_inventory": mapped_systems_unique,
            "access_logs": mapped_access_1 + mapped_access_2,
            "security_events": mapped_security
        })

    # 4. Assert database storage of mapped values (evidence check)
    with db_conn.cursor() as cur:
        # Record 1: pii_fields_justified is False, system_hash is syshash00001
        cur.execute("SELECT system_hash, pii_fields_justified FROM access_logs WHERE access_hash = %s", (acc_hash_1,))
        row1 = cur.fetchone()
        assert row1 is not None
        assert row1["system_hash"].strip() == sys_hash_1
        assert row1["pii_fields_justified"] is False

        # Record 2: pii_fields_justified remains NULL/None
        cur.execute("SELECT system_hash, pii_fields_justified FROM access_logs WHERE access_hash = %s", (acc_hash_2,))
        row2 = cur.fetchone()
        assert row2 is not None
        assert row2["system_hash"].strip() == sys_hash_1
        assert row2["pii_fields_justified"] is None

    # 5. Duplicate-proof assertions
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM rules WHERE rule_id IN ('DPDP-007', 'DPDP-008')")
        rules = {r["rule_id"]: r for r in cur.fetchall()}

    reg_agent = RegulationAgent()
    risk_agent = RiskAgent()

    findings_007 = reg_agent._run_rule_dynamic(rules["DPDP-007"], tenant_id, wrapper)
    findings_008 = risk_agent._run_rule_dynamic(rules["DPDP-008"], tenant_id, wrapper)

    # Assert exactly 2 findings for DPDP-007, and 1 for DPDP-008
    assert len(findings_007) == 2, f"Expected 2 findings for DPDP-007, got {len(findings_007)}"
    assert len(findings_008) == 1, f"Expected 1 finding for DPDP-008, got {len(findings_008)}"
    
    # Store rule score & identities
    original_scores_007 = sorted([f.rule_score for f in findings_007])
    original_score_008 = findings_008[0].rule_score
    original_rec_ids_007 = sorted([f.record_id for f in findings_007])
    original_rec_id_008 = findings_008[0].record_id

    # Add unrelated systems inside transaction using write_tenant_data end-to-end path
    raw_systems_expanded = pd.DataFrame([
        {
            "system_hash": "syshash00001",
            "system_name": "Main System",
            "system_type": "crm",
            "pii_stored": "True",
            "encryption_enabled": "False",
            "data_processor_type": "internal"
        },
        {
            "system_hash": "syshash00002",
            "system_name": "Archive System",
            "system_type": "analytics",
            "pii_stored": "False",
            "encryption_enabled": "True",
            "data_processor_type": "internal"
        },
        {
            "system_hash": "syshash00005",
            "system_name": "Extra System 1",
            "system_type": "analytics",
            "pii_stored": "False",
            "encryption_enabled": "True",
            "data_processor_type": "internal"
        },
        {
            "system_hash": "syshash00006",
            "system_name": "Extra System 2",
            "system_type": "data_warehouse",
            "pii_stored": "False",
            "encryption_enabled": "False",
            "data_processor_type": "internal"
        }
    ])
    mapped_systems_expanded = anonymize_dataframe_wrapper(raw_systems_expanded, "system_inventory", tenant_id)

    with patch("src.anonymization.db_writer.get_db_connection", return_value=wrapper):
        write_tenant_data(tenant_id, {
            "governance_config": mapped_gov_unique,
            "customer_master": mapped_cust_unique,
            "system_inventory": mapped_systems_expanded,
            "access_logs": mapped_access_1 + mapped_access_2,
            "security_events": mapped_security
        })

    findings_007_after = reg_agent._run_rule_dynamic(rules["DPDP-007"], tenant_id, wrapper)
    findings_008_after = risk_agent._run_rule_dynamic(rules["DPDP-008"], tenant_id, wrapper)

    # Assert counts, scores, and identities are unchanged
    assert len(findings_007_after) == 2
    assert len(findings_008_after) == 1
    assert sorted([f.rule_score for f in findings_007_after]) == original_scores_007
    assert findings_008_after[0].rule_score == original_score_008
    assert sorted([f.record_id for f in findings_007_after]) == original_rec_ids_007
    assert findings_008_after[0].record_id == original_rec_id_008

    # Assert cross-tenant systems do not affect rule result
    # OTHER_TENANT syshash00004 should have no effect on INTEG-007-UNIQUE findings
    assert len(findings_007_after) == 2
