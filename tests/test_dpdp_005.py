import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.anonymization.field_mapper import _anonymize_consent_records, hash_id
from src.anonymization.csv_loader import MissingColumnError
from src.agent_layer.signal_evaluator import _eval_dpdp_005
from tests.test_dsar_validation import get_upload_files

client = TestClient(app)

def build_consent_df(guardian_consent_id="GC-123", consent_status="active"):
    return pd.DataFrame([{
        "consent_id": "CON-1",
        "customer_id": "C1",
        "tenant_id": "T1",
        "consent_status": consent_status,
        "consented_purpose": "loan_processing",
        "guardian_consent_id": guardian_consent_id
    }])

def test_1_raw_guardian_id_is_hashed_and_preserved():
    df = build_consent_df(guardian_consent_id="GC-123")
    result = _anonymize_consent_records(df, "T1")
    assert result[0]["guardian_consent_hash"] == hash_id("GC-123", "T1")
    assert "guardian_consent_id" not in result[0]

def test_2_pre_hashed_guardian_hash_is_preserved():
    from src.anonymization.hasher import hash_id
    con_hash = hash_id("CON-1", "T1", version="v2")
    cust_hash = hash_id("C-1", "T1", version="v2")
    gc_hash = hash_id("GC-1", "T1", version="v2")
    df = pd.DataFrame([{
        "consent_hash": con_hash,
        "customer_hash": cust_hash,
        "tenant_id": "T1",
        "consent_status": "active",
        "consented_purpose": "loan_processing",
        "guardian_consent_hash": gc_hash
    }])
    result = _anonymize_consent_records(df, "T1")
    assert result[0]["guardian_consent_hash"] == gc_hash

def get_missing_guardian_col_files(tenant_id: str):
    files = get_upload_files(tenant_id, inject_bad_dsar=False)
    consent_tuple = files["consent_records"]
    # Drop guardian_consent_id column
    df = pd.DataFrame({
        "tenant_id": [tenant_id],
        "consent_hash": ["CH1"],
        "customer_hash": ["C1"],
        "consent_status": ["active"],
        "consented_purpose": ["loan_processing"]
    })
    new_content = df.to_csv(index=False).encode("utf-8")
    files["consent_records"] = (consent_tuple[0], new_content, "text/csv")
    return files

@patch("src.api.routes._build_full_response")
@patch("src.api.routes.write_tenant_data")
@patch("src.api.routes.run_compliance_analysis")
def test_3_missing_guardian_column_returns_400(mock_run_analysis, mock_write_data, mock_build_response, authorized_client):
    files = get_missing_guardian_col_files("TENANT-A")
    client = authorized_client("TENANT-A")
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": "TENANT-A", "tenant_name": "Tenant A"},
        files=files
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "Missing required column"
    assert data["detail"]["error_code"] == "MISSING_COLUMN"
    assert data["detail"]["field"] == "guardian_consent_hash"
    mock_write_data.assert_not_called()

def test_4_blank_guardian_value_is_accepted():
    df = build_consent_df(guardian_consent_id="")
    result = _anonymize_consent_records(df, "T1")
    assert result[0]["guardian_consent_hash"] is None

import os
import psycopg
from psycopg.rows import dict_row

def _get_test_conn():
    return psycopg.connect(
        dbname=os.environ.get("DB_NAME", "dpdp_test_isolated"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "postgres"),
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        row_factory=dict_row
    )

def test_dpdp_005_e2e_scenarios():
    from src.agent_layer.regulation_agent import RegulationAgent
    from src.agent_layer.rule_loader import load_rules
    
    import uuid
    uid = uuid.uuid4().hex[:8]
    tenant = f"TENANT_TEST_005_{uid}"
    other_tenant = f"OTHER_TENANT_{uid}"
    with _get_test_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM consent_records WHERE tenant_id IN ('{tenant}', '{other_tenant}')")
            cur.execute(f"DELETE FROM customer_master WHERE tenant_id IN ('{tenant}', '{other_tenant}')")
            cur.execute(f"DELETE FROM governance_config WHERE tenant_id IN ('{tenant}', '{other_tenant}')")
            
            # Tenant configuration
            cur.execute(f"INSERT INTO governance_config (tenant_id, tenant_name, audit_frequency_days) VALUES ('{tenant}', 'Test Tenant', 365) ON CONFLICT DO NOTHING")
            cur.execute(f"INSERT INTO governance_config (tenant_id, tenant_name, audit_frequency_days) VALUES ('{other_tenant}', 'Other', 365) ON CONFLICT DO NOTHING")
            
            # Define dynamic hashes
            c_adult = f"c_adult_{uid}"
            c_minor_no_consent = f"c_minor_nocons_{uid}"
            c_minor_orphan = f"c_minor_orphan_{uid}"
            c_minor_inactive = f"c_minor_inactive_{uid}"
            c_minor_valid = f"c_minor_valid_{uid}"
            c_minor_multi = f"c_minor_multi_{uid}"
            c_minor_cross = f"c_minor_cross_{uid}"
            
            cons_orphan = f"cons_orphan_{uid}"
            cons_inactive_g = f"cons_inactive_g_{uid}"
            cons_inactive_m = f"cons_inactive_m_{uid}"
            cons_valid_g = f"cons_valid_g_{uid}"
            cons_valid_m = f"cons_valid_m_{uid}"
            cons_multi_1 = f"cons_multi_1_{uid}"
            cons_multi_2 = f"cons_multi_2_{uid}"
            cons_cross = f"cons_cross_{uid}"
            
            # Adult
            cur.execute(f"INSERT INTO customer_master (customer_hash, tenant_id, is_minor, data_principal_type, account_status, kyc_status, country, created_at) VALUES ('{c_adult}', '{tenant}', false, 'individual', 'active', 'verified', 'IN', '2020-01-01')")
            
            # Minor with no consent
            cur.execute(f"INSERT INTO customer_master (customer_hash, tenant_id, is_minor, data_principal_type, account_status, kyc_status, country, created_at) VALUES ('{c_minor_no_consent}', '{tenant}', true, 'minor', 'active', 'verified', 'IN', '2020-01-01')")
            
            # Minor with orphan guardian hash
            cur.execute(f"INSERT INTO customer_master (customer_hash, tenant_id, is_minor, data_principal_type, account_status, kyc_status, country, created_at) VALUES ('{c_minor_orphan}', '{tenant}', true, 'minor', 'active', 'verified', 'IN', '2020-01-01')")
            cur.execute(f"INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consented_purpose, notice_provided, is_bundled, consent_channel, guardian_consent_hash, consent_version, consent_date, expiry_date) VALUES ('{cons_orphan}', '{c_minor_orphan}', '{tenant}', 'active', 'marketing', true, false, 'web', 'ghost_hash', '1.0', '2020-01-01', '2025-01-01')")
            
            # Minor with inactive guardian
            cur.execute(f"INSERT INTO customer_master (customer_hash, tenant_id, is_minor, data_principal_type, account_status, kyc_status, country, created_at) VALUES ('{c_minor_inactive}', '{tenant}', true, 'minor', 'active', 'verified', 'IN', '2020-01-01')")
            cur.execute(f"INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consented_purpose, notice_provided, is_bundled, consent_channel, guardian_consent_hash, consent_version, consent_date, expiry_date) VALUES ('{cons_inactive_g}', '{c_adult}', '{tenant}', 'expired', 'marketing', true, false, 'web', NULL, '1.0', '2020-01-01', '2025-01-01')")
            cur.execute(f"INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consented_purpose, notice_provided, is_bundled, consent_channel, guardian_consent_hash, consent_version, consent_date, expiry_date) VALUES ('{cons_inactive_m}', '{c_minor_inactive}', '{tenant}', 'active', 'marketing', true, false, 'web', '{cons_inactive_g}', '1.0', '2020-01-01', '2025-01-01')")
            
            # Minor with valid guardian
            cur.execute(f"INSERT INTO customer_master (customer_hash, tenant_id, is_minor, data_principal_type, account_status, kyc_status, country, created_at) VALUES ('{c_minor_valid}', '{tenant}', true, 'minor', 'active', 'verified', 'IN', '2020-01-01')")
            cur.execute(f"INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consented_purpose, notice_provided, is_bundled, consent_channel, guardian_consent_hash, consent_version, consent_date, expiry_date) VALUES ('{cons_valid_g}', '{c_adult}', '{tenant}', 'active', 'marketing', true, false, 'web', NULL, '1.0', '2020-01-01', '2025-01-01')")
            cur.execute(f"INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consented_purpose, notice_provided, is_bundled, consent_channel, guardian_consent_hash, consent_version, consent_date, expiry_date) VALUES ('{cons_valid_m}', '{c_minor_valid}', '{tenant}', 'active', 'marketing', true, false, 'web', '{cons_valid_g}', '1.0', '2020-01-01', '2025-01-01')")
            
            # Multiple consents (one valid, one orphan) for same minor
            cur.execute(f"INSERT INTO customer_master (customer_hash, tenant_id, is_minor, data_principal_type, account_status, kyc_status, country, created_at) VALUES ('{c_minor_multi}', '{tenant}', true, 'minor', 'active', 'verified', 'IN', '2020-01-01')")
            cur.execute(f"INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consented_purpose, notice_provided, is_bundled, consent_channel, guardian_consent_hash, consent_version, consent_date, expiry_date) VALUES ('{cons_multi_1}', '{c_minor_multi}', '{tenant}', 'active', 'marketing', true, false, 'web', '{cons_valid_g}', '1.0', '2020-01-01', '2025-01-01')")
            cur.execute(f"INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consented_purpose, notice_provided, is_bundled, consent_channel, guardian_consent_hash, consent_version, consent_date, expiry_date) VALUES ('{cons_multi_2}', '{c_minor_multi}', '{tenant}', 'active', 'loan_processing', true, false, 'web', 'ghost_hash', '1.0', '2020-01-01', '2025-01-01')")
            
            # Cross-tenant record
            cur.execute(f"INSERT INTO customer_master (customer_hash, tenant_id, is_minor, data_principal_type, account_status, kyc_status, country, created_at) VALUES ('{c_minor_cross}', '{other_tenant}', true, 'minor', 'active', 'verified', 'IN', '2020-01-01')")
            cur.execute(f"INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consented_purpose, notice_provided, is_bundled, consent_channel, guardian_consent_hash, consent_version, consent_date, expiry_date) VALUES ('{cons_cross}', '{c_minor_cross}', '{other_tenant}', 'active', 'loan_processing', true, false, 'web', NULL, '1.0', '2020-01-01', '2025-01-01')")
            
            conn.commit()
            
            rules = load_rules('regulation_agent', conn)
            dpdp_005 = next(r for r in rules if r['rule_id'] == 'DPDP-005')
            
            agent = RegulationAgent()
            results = agent._run_rule_dynamic(dpdp_005, tenant, conn)
            findings = set(r.record_id for r in results if r.outcome == 'VIOLATION')
            # Minor with no consent SHOULD produce finding (fallback to customer hash)
            assert c_minor_no_consent in findings
            
            # Minor with orphan guardian hash SHOULD produce finding (consent_hash used as primary_hash)
            assert cons_orphan in findings
            
            # Minor with inactive guardian SHOULD produce finding
            assert cons_inactive_m in findings
            
            # Minor with valid guardian SHOULD NOT produce finding
            assert cons_valid_m not in findings
            assert c_minor_valid not in findings
            
            # Multiple consents: one valid ('cons_multi_1'), one orphan ('cons_multi_2')
            assert cons_multi_1 not in findings
            assert cons_multi_2 in findings
            
            # Cross-tenant record should NOT be in findings for this tenant
            assert cons_cross not in findings
            assert c_minor_cross not in findings

    
def test_12_raw_guardian_identifiers_never_reach_db(caplog, monkeypatch):
    import logging
    from src.anonymization.db_writer import write_tenant_data
    caplog.set_level(logging.INFO)
    
    class MockCursor:
        def __init__(self):
            self.execute_calls = []
            self.rowcount = 1
        def execute(self, query, params=None):
            assert "GC-RAW-SECRET" not in str(query)
            assert "GC-RAW-SECRET" not in str(params)
            self.execute_calls.append((query, params))
        def copy(self, *args, **kwargs):
            class MockCopy:
                def __enter__(self): return self
                def __exit__(self, *a): pass
                def write_row(self, row):
                    assert "GC-RAW-SECRET" not in str(row)
            return MockCopy()
        def fetchone(self): return (1,)
        def fetchall(self): return []
    class MockConn:
        def cursor(self, *args, **kwargs):
            class CursorContext:
                def __enter__(self): return MockCursor()
                def __exit__(self, *a): pass
            return CursorContext()
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
    
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda **k: MockConn())
    
    tenant_data = {
        "consent_records": [
            {
                "consent_hash": "ch1",
                "customer_hash": "custh1", 
                "tenant_id": "T1", 
                "consent_status": "active",
                "consent_date": "2026-01-01",
                "expiry_date": "2027-01-01",
                "withdrawal_date": None,
                "consented_purpose": "marketing",
                "consent_version": "1.0",
                "notice_provided": True,
                "is_bundled": False,
                "consent_channel": "web",
                "guardian_consent_id": "GC-RAW-SECRET", 
                "guardian_consent_hash": None
            }
        ]
    }
    write_tenant_data("T1", tenant_data)
    
    # Ensure it's not in logs
    assert "GC-RAW-SECRET" not in caplog.text

def test_14_runtime_loads_rule_from_postgresql():
    from src.agent_layer.rule_loader import load_rules
    with _get_test_conn() as conn:
        rules = load_rules('regulation_agent', conn)
        dpdp_005 = next(r for r in rules if r['rule_id'] == 'DPDP-005')
        assert dpdp_005['violation_threshold'] == 1.0
        assert dpdp_005['evidence_signals'][0]['signal_id'] == 'guardian_consent_missing_or_invalid'

def test_pre_hashed_guardian_hash_malformed_rejected():
    from src.anonymization.field_mapper import _anonymize_consent_records
    df = pd.DataFrame([{
        "consent_hash": "CON-HASH-MALFORMED",
        "customer_hash": "C-HASH-MALFORMED",
        "tenant_id": "T1",
        "consent_status": "active",
        "consented_purpose": "loan_processing",
        "guardian_consent_hash": "GC-HASH-MALFORMED"
    }])
    with pytest.raises(ValueError, match="Invalid pre-hashed format"):
        _anonymize_consent_records(df, "T1")
