import os
import pytest
import psycopg
import pandas as pd
from io import BytesIO
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from urllib.parse import urlparse
from psycopg.rows import dict_row

def validate_db_url(db_url):
    if not db_url:
        raise ValueError("DPDP_TEST_DATABASE_URL environment variable is not set!")
    parsed = urlparse(db_url)
    db_name = parsed.path.lstrip('/')
    if not db_name or "_test" not in db_name:
        raise ValueError(f"Database name '{db_name}' is unsafe! It must contain '_test'.")

# Ensure test DB URL is set and valid at load time, or skip the module if absent
db_url_env = os.environ.get("DPDP_TEST_DATABASE_URL")
if not db_url_env:
    pytest.skip("DPDP_TEST_DATABASE_URL environment variable is not set; skipping database-backed tests.", allow_module_level=True)
else:
    validate_db_url(db_url_env)

_test_conn_instance = None

def mock_get_db_connection():
    global _test_conn_instance
    if _test_conn_instance is not None:
        return _test_conn_instance
    db_url_local = os.environ.get("DPDP_TEST_DATABASE_URL")
    validate_db_url(db_url_local)
    return psycopg.connect(conninfo=db_url_local, row_factory=dict_row)

import src.api.routes
import src.anonymization.db_writer

@pytest.fixture(autouse=True)
def db_transaction(monkeypatch):
    global _test_conn_instance
    conn = psycopg.connect(conninfo=os.environ.get("DPDP_TEST_DATABASE_URL"), row_factory=dict_row)
    conn.autocommit = False
    
    # Mock commit to be a no-op during the test
    original_commit = conn.commit
    conn.commit = lambda: None
    
    # Mock close to be a no-op during the test
    original_close = conn.close
    conn.close = lambda: None
    
    _test_conn_instance = conn
    
    # Monkeypatch the DB connections in routes and db_writer to use this transaction connection
    monkeypatch.setattr(src.api.routes, "get_db_connection", mock_get_db_connection)
    monkeypatch.setattr(src.anonymization.db_writer, "get_db_connection", mock_get_db_connection)
    
    try:
        yield conn
    finally:
        # Restore original commit and close
        conn.commit = original_commit
        conn.close = original_close
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
        _test_conn_instance = None

from src.api.main import app
from src.anonymization.field_mapper import hash_id

client = TestClient(app)

# Helper to build valid CSV content
def get_valid_csvs(tenant_id="T1"):
    return {
        "governance_config": (
            "governance_config.csv",
            f"tenant_id,tenant_name,grievance_endpoint_available,dpo_assigned,dpo_contact_masked,audit_frequency_days,last_audit_date,risk_level\n"
            f"{tenant_id},Test Tenant,True,True,dpo@test.local,365,2024-01-01,MEDIUM".encode("utf-8"),
            "text/csv"
        ),
        "customer_master": (
            "customer_master.csv",
            f"customer_id,tenant_id,is_minor,data_principal_type,account_status,kyc_status,country,created_at\n"
            f"C1,{tenant_id},False,individual,active,verified,IN,2024-01-01".encode("utf-8"),
            "text/csv"
        ),
        "consent_records": (
            "consent_records.csv",
            f"consent_id,customer_id,tenant_id,consent_status,consented_purpose,notice_provided,is_bundled,consent_channel,guardian_consent_id,consent_date,expiry_date\n"
            f"CON1,C1,{tenant_id},active,marketing,True,False,web,,2024-01-01,2025-01-01".encode("utf-8"),
            "text/csv"
        ),
        "system_inventory": (
            "system_inventory.csv",
            f"system_id,tenant_id,system_name,system_type,pii_stored,encryption_enabled,access_control_enabled,data_processor_type,retention_policy_applied,dpa_signed,dpa_expiry_date\n"
            f"SYS1,{tenant_id},System 1,crm,True,True,True,internal,True,True,".encode("utf-8"),
            "text/csv"
        ),
        "transaction_events": (
            "transaction_events.csv",
            f"event_id,customer_id,tenant_id,consent_id,event_type,processing_purpose,event_date,shared_with_third_party,third_party_id,is_cross_border,transfer_country\n"
            f"TX1,C1,{tenant_id},CON1,marketing_push,marketing,2024-01-15,True,SYS1,False,".encode("utf-8"),
            "text/csv"
        ),
        "access_logs": (
            "access_logs.csv",
            f"access_id,customer_id,tenant_id,employee_id,employee_role,accessed_pii,pii_fields_accessed,access_reason,access_outcome,data_volume_accessed,access_date\n"
            f"ACC1,C1,{tenant_id},E1,underwriter,True,name,loan_review,granted,low,2024-01-02".encode("utf-8"),
            "text/csv"
        ),
        "data_lifecycle": (
            "data_lifecycle.csv",
            f"lifecycle_id,customer_id,tenant_id,data_category,retention_expiry_date,retention_status,purpose_completed,erasure_requested,erasure_date,legal_hold_flag,erasure_request_source\n"
            f"L1,C1,{tenant_id},kyc_documents,2025-01-01,active,False,False,,False,".encode("utf-8"),
            "text/csv"
        ),
        "security_events": (
            "security_events.csv",
            f"security_id,customer_id,tenant_id,pii_encrypted,encryption_type,breach_detected,breach_confirmed_date,notification_delay_hours,affected_user_count,data_categories_breached,security_audit_flag\n"
            f"SEC1,C1,{tenant_id},True,AES-256,False,,,0,,False".encode("utf-8"),
            "text/csv"
        ),
        "dsar_requests": (
            "dsar_requests.csv",
            f"dsar_id,customer_id,tenant_id,request_type,submitted_date,acknowledged_date,sla_due_date,sla_breached,fulfilled_date,fulfillment_status,rejection_reason\n"
            f"DS1,C1,{tenant_id},access,2024-01-01,2024-01-02,2024-01-31,False,,pending,".encode("utf-8"),
            "text/csv"
        ),
        "policies": (
            "policies.csv",
            f"policy_id,tenant_id,policy_type,policy_name,policy_value_numeric,policy_value_unit,effective_date,last_updated,is_active\n"
            f"P1,{tenant_id},retention,Retention Policy,365,days,2024-01-01,2024-01-01,True".encode("utf-8"),
            "text/csv"
        ),
    }

def clear_test_db(conn, tenant_id="T1"):
    with conn.cursor() as cur:
        for table in [
            "dsar_requests", "security_events", "data_lifecycle", "access_logs",
            "transaction_events", "consent_records", "customer_master", "policies",
            "system_inventory", "governance_config"
        ]:
            cur.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,))

def test_database_url_safety_rules():
    # 1. Reject missing url
    with pytest.raises(ValueError, match="is not set"):
        validate_db_url(None)
        
    # 2. Reject unsafe name where _test is not in the db name
    with pytest.raises(ValueError, match="is unsafe"):
        validate_db_url("postgresql://postgres:pwd@localhost:5432/production_db")
        
    # 3. Reject unsafe name even if _test is in username or parameters
    with pytest.raises(ValueError, match="is unsafe"):
        validate_db_url("postgresql://postgres_test:pwd@localhost:5432/prod_db?param=_test")
        
    # 4. Accept safe name
    validate_db_url("postgresql://postgres:pwd@localhost:5432/dpdp_test_isolated")

def test_1_invalid_consent_missing_customer(db_transaction, authorized_client):
    tenant_id = "T_VAL1"
    client = authorized_client("T_VAL1")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["consent_records"] = (
        "consent_records.csv",
        f"consent_id,customer_id,tenant_id,consent_status,consented_purpose,notice_provided,is_bundled,consent_channel,guardian_consent_id,consent_date,expiry_date\n"
        f"CON1,C_MISSING,{tenant_id},active,marketing,True,False,web,,2024-01-01,2025-01-01".encode("utf-8"),
        "text/csv"
    )
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "Cross-file validation failed"
    details = data["detail"]["details"]
    assert len(details) == 1
    err = details[0]
    assert err["source_file"] == "consent_records.csv"
    assert err["row_number"] == 2
    assert err["field_name"] == "customer_id"
    assert err["invalid_reference"] == hash_id("C_MISSING", tenant_id)

def test_2_invalid_transaction_missing_consent(db_transaction, authorized_client):
    tenant_id = "T_VAL2"
    client = authorized_client("T_VAL2")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["transaction_events"] = (
        "transaction_events.csv",
        f"event_id,customer_id,tenant_id,consent_id,event_type,processing_purpose,event_date,shared_with_third_party,third_party_id,is_cross_border,transfer_country\n"
        f"TX1,C1,{tenant_id},CON_MISSING,marketing_push,marketing,2024-01-15,True,SYS1,False,".encode("utf-8"),
        "text/csv"
    )
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "Cross-file validation failed"
    details = data["detail"]["details"]
    assert any(err["field_name"] == "consent_id" and err["invalid_reference"] == hash_id("CON_MISSING", tenant_id) for err in details)

def test_3_unknown_third_party_reference_never_nullified(db_transaction, authorized_client):
    tenant_id = "T_VAL3"
    client = authorized_client("T_VAL3")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["transaction_events"] = (
        "transaction_events.csv",
        f"event_id,customer_id,tenant_id,consent_id,event_type,processing_purpose,event_date,shared_with_third_party,third_party_id,is_cross_border,transfer_country\n"
        f"TX1,C1,{tenant_id},CON1,marketing_push,marketing,2024-01-15,True,SYS_MISSING,False,".encode("utf-8"),
        "text/csv"
    )
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "Cross-file validation failed"
    details = data["detail"]["details"]
    assert any(err["field_name"] == "third_party_id" and err["invalid_reference"] == hash_id("SYS_MISSING", tenant_id) for err in details)
    
    # Assert nothing was saved to DB (including as NULL)
    with db_transaction.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM transaction_events WHERE tenant_id = %s", (tenant_id,))
        assert cur.fetchone()["count"] == 0

def test_4_multiple_invalid_references_collected(db_transaction, authorized_client):
    tenant_id = "T_VAL4"
    client = authorized_client("T_VAL4")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    
    # Consent references missing customer C_BAD
    files["consent_records"] = (
        "consent_records.csv",
        f"consent_id,customer_id,tenant_id,consent_status,consented_purpose,notice_provided,is_bundled,consent_channel,guardian_consent_id,consent_date,expiry_date\n"
        f"CON1,C_BAD,{tenant_id},active,marketing,True,False,web,,2024-01-01,2025-01-01".encode("utf-8"),
        "text/csv"
    )
    # Transaction references missing consent CON_BAD
    files["transaction_events"] = (
        "transaction_events.csv",
        f"event_id,customer_id,tenant_id,consent_id,event_type,processing_purpose,event_date,shared_with_third_party,third_party_id,is_cross_border,transfer_country\n"
        f"TX1,C1,{tenant_id},CON_BAD,marketing_push,marketing,2024-01-15,True,SYS1,False,".encode("utf-8"),
        "text/csv"
    )
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    data = response.json()
    details = data["detail"]["details"]
    assert len(details) >= 2
    fields = [d["field_name"] for d in details]
    assert "customer_id" in fields
    assert "consent_id" in fields

# Downstream analysis is mocked for these ingestion-safety tests.
# These tests focus strictly on ingestion integrity and cross-file validation.
# End-to-end analysis belongs in a separately isolated integration suite.
@patch("src.api.routes.run_compliance_analysis")
@patch("src.api.routes._build_full_response")
def test_5_invalid_upload_leaves_existing_data_unchanged(mock_build_response, mock_run_analysis, db_transaction, authorized_client):
    mock_run_analysis.return_value = {"status": "ok"}
    mock_build_response.return_value = {
        "tenant_id": "T_VAL5",
        "total_obligations": 10,
        "unique_rules_violated": 0,
        "total_violation_occurrences": 0,
        "risk_score": 0.0,
        "risk_tier": "LOW",
        "violations": [],
        "status": "success",
        "agent_analysis": {"risk_agent": {}, "regulation_agent": {}}
    }

    tenant_id = "T_VAL5"
    client = authorized_client("T_VAL5")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    
    # First write a valid dataset to DB
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 200
    assert mock_run_analysis.call_count == 1
    
    # Now attempt a bad upload
    bad_files = get_valid_csvs(tenant_id)
    bad_files["consent_records"] = (
        "consent_records.csv",
        f"consent_id,customer_id,tenant_id,consent_status,consented_purpose,notice_provided,is_bundled,consent_channel,guardian_consent_id,consent_date,expiry_date\n"
        f"CON1,C_MISSING,{tenant_id},active,marketing,True,False,web,,2024-01-01,2025-01-01".encode("utf-8"),
        "text/csv"
    )
    
    response2 = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=bad_files
    )
    assert response2.status_code == 400
    # Still only 1 call from the first successful upload
    assert mock_run_analysis.call_count == 1
    
    # Verify that the original valid C1 customer still exists (i.e. not deleted)
    with db_transaction.cursor() as cur:
        cur.execute("SELECT customer_hash FROM customer_master WHERE tenant_id = %s", (tenant_id,))
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["customer_hash"].strip() == hash_id("C1", tenant_id)

@patch("src.api.routes.run_compliance_analysis")
def test_6_analysis_is_not_called_on_failure(mock_run_analysis, db_transaction, authorized_client):
    tenant_id = "T_VAL6"
    client = authorized_client("T_VAL6")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["consent_records"] = (
        "consent_records.csv",
        f"consent_id,customer_id,tenant_id,consent_status,consented_purpose,notice_provided,is_bundled,consent_channel,guardian_consent_id,consent_date,expiry_date\n"
        f"CON1,C_MISSING,{tenant_id},active,marketing,True,False,web,,2024-01-01,2025-01-01".encode("utf-8"),
        "text/csv"
    )
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    mock_run_analysis.assert_not_called()

# Downstream analysis is mocked for these ingestion-safety tests.
# These tests focus strictly on ingestion integrity and cross-file validation.
# End-to-end analysis belongs in a separately isolated integration suite.
@patch("src.api.routes.run_compliance_analysis")
@patch("src.api.routes._build_full_response")
def test_7_fully_valid_linked_dataset_uploads_successfully(mock_build_response, mock_run_analysis, db_transaction, authorized_client):
    mock_run_analysis.return_value = {"status": "ok"}
    mock_build_response.return_value = {
        "tenant_id": "T_VAL7",
        "total_obligations": 10,
        "unique_rules_violated": 0,
        "total_violation_occurrences": 0,
        "risk_score": 0.0,
        "risk_tier": "LOW",
        "violations": [],
        "status": "success",
        "agent_analysis": {"risk_agent": {}, "regulation_agent": {}}
    }

    tenant_id = "T_VAL7"
    client = authorized_client("T_VAL7")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == tenant_id
    assert data["status"] == "success"
    assert mock_run_analysis.call_count == 1

def test_8_blank_required_reference(db_transaction, authorized_client):
    # Customer_id is blank in consent_records.csv
    tenant_id = "T_VAL8"
    client = authorized_client("T_VAL8")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["consent_records"] = (
        "consent_records.csv",
        f"consent_id,customer_id,tenant_id,consent_status,consented_purpose,notice_provided,is_bundled,consent_channel,guardian_consent_id,consent_date,expiry_date\n"
        f"CON1,,{tenant_id},active,marketing,True,False,web,,2024-01-01,2025-01-01".encode("utf-8"),
        "text/csv"
    )
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "Cross-file validation failed"
    details = data["detail"]["details"]
    assert any(err["field_name"] == "customer_id" and err["invalid_reference"] is None for err in details)

def test_fabrication_preservation_dpo_masked(db_transaction, authorized_client):
    # Valid supplied DPO email is masked and stored correctly, not fabricated.
    tenant_id = "T_FAB1"
    client = authorized_client("T_FAB1")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["governance_config"] = (
        "governance_config.csv",
        f"tenant_id,tenant_name,grievance_endpoint_available,dpo_assigned,dpo_contact_masked,audit_frequency_days,last_audit_date,risk_level\n"
        f"{tenant_id},Test Tenant,True,True,security-dpo@example.com,365,2024-01-01,MEDIUM".encode("utf-8"),
        "text/csv"
    )
    # Mock analysis to isolate DB write check
    with patch("src.api.routes.run_compliance_analysis") as mock_run, \
         patch("src.api.routes._build_full_response") as mock_build:
        mock_run.return_value = {"status": "ok"}
        mock_build.return_value = {
            "tenant_id": tenant_id, "total_obligations": 0, "unique_rules_violated": 0,
            "total_violation_occurrences": 0, "risk_score": 0.0, "risk_tier": "LOW",
            "violations": [], "status": "success", "agent_analysis": {}
        }
        response = client.post(
            "/analyze/upload",
            data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
            files=files
        )
        assert response.status_code == 200
        
    with db_transaction.cursor() as cur:
        cur.execute("SELECT dpo_contact_masked FROM governance_config WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
        assert row["dpo_contact_masked"] == "s***@example.com"

def test_fabrication_missing_dpo_assigned_rejected(db_transaction, authorized_client):
    # DPO assigned is True, but contact is empty -> rejected with HTTP 400.
    tenant_id = "T_FAB2"
    client = authorized_client("T_FAB2")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["governance_config"] = (
        "governance_config.csv",
        f"tenant_id,tenant_name,grievance_endpoint_available,dpo_assigned,dpo_contact_masked,audit_frequency_days,last_audit_date,risk_level\n"
        f"{tenant_id},Test Tenant,True,True,,365,2024-01-01,MEDIUM".encode("utf-8"),
        "text/csv"
    )
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "Governance validation failed"
    assert data["detail"]["field"] == "dpo_contact_masked"
    assert data["detail"]["error_code"] == "MISSING_DPO_CONTACT"

def test_fabrication_cross_border_missing_country_rejected(db_transaction, authorized_client):
    # is_cross_border is True, but country is missing -> rejected with HTTP 400.
    tenant_id = "T_FAB3"
    client = authorized_client("T_FAB3")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["transaction_events"] = (
        "transaction_events.csv",
        f"event_id,customer_id,tenant_id,consent_id,event_type,processing_purpose,event_date,shared_with_third_party,third_party_id,is_cross_border,transfer_country\n"
        f"TX1,C1,{tenant_id},CON1,marketing_push,marketing,2024-01-15,False,,True,".encode("utf-8"),
        "text/csv"
    )
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "Transaction validation failed"
    assert data["detail"]["field"] == "transfer_country"
    assert data["detail"]["error_code"] == "MISSING_TRANSFER_COUNTRY"

def test_fabrication_no_invented_third_party(db_transaction, authorized_client):
    # If shared_with_third_party is False, third_party_hash stays None (missing evidence, not fabricated).
    tenant_id = "T_FAB4"
    client = authorized_client("T_FAB4")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["transaction_events"] = (
        "transaction_events.csv",
        f"event_id,customer_id,tenant_id,consent_id,event_type,processing_purpose,event_date,shared_with_third_party,third_party_id,is_cross_border,transfer_country\n"
        f"TX1,C1,{tenant_id},CON1,marketing_push,marketing,2024-01-15,False,,,None".encode("utf-8"),
        "text/csv"
    )
    with patch("src.api.routes.run_compliance_analysis") as mock_run, \
         patch("src.api.routes._build_full_response") as mock_build:
        mock_run.return_value = {"status": "ok"}
        mock_build.return_value = {
            "tenant_id": tenant_id, "total_obligations": 0, "unique_rules_violated": 0,
            "total_violation_occurrences": 0, "risk_score": 0.0, "risk_tier": "LOW",
            "violations": [], "status": "success", "agent_analysis": {}
        }
        response = client.post(
            "/analyze/upload",
            data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
            files=files
        )
        assert response.status_code == 200
        
    with db_transaction.cursor() as cur:
        cur.execute("SELECT third_party_hash FROM transaction_events WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
        assert row["third_party_hash"] is None

def test_missing_breach_evidence_accepted_as_none(db_transaction, authorized_client):
    # When breach_detected is True, missing breach_confirmed_date, notification_delay_hours, and affected_user_count must be accepted and stored as None.
    tenant_id = "T_FAB5"
    client = authorized_client("T_FAB5")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["security_events"] = (
        "security_events.csv",
        f"security_id,customer_id,tenant_id,pii_encrypted,encryption_type,breach_detected,breach_confirmed_date,notification_delay_hours,affected_user_count,data_categories_breached,security_audit_flag\n"
        f"SEC1,C1,{tenant_id},True,AES-256,True,,,,,\n".encode("utf-8"),
        "text/csv"
    )
    with patch("src.api.routes.run_compliance_analysis") as mock_run, \
         patch("src.api.routes._build_full_response") as mock_build:
        mock_run.return_value = {"status": "ok"}
        mock_build.return_value = {
            "tenant_id": tenant_id, "total_obligations": 0, "unique_rules_violated": 0,
            "total_violation_occurrences": 0, "risk_score": 0.0, "risk_tier": "LOW",
            "violations": [], "status": "success", "agent_analysis": {}
        }
        response = client.post(
            "/analyze/upload",
            data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
            files=files
        )
        assert response.status_code == 200

    with db_transaction.cursor() as cur:
        cur.execute("SELECT breach_confirmed_date, notification_delay_hours, affected_user_count, data_categories_breached FROM security_events WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
        assert row["breach_confirmed_date"] is None
        assert row["notification_delay_hours"] is None
        assert row["affected_user_count"] is None
        assert row["data_categories_breached"] is None

def test_invalid_supplied_breach_evidence_rejected(db_transaction, authorized_client):
    # Supplied malformed date should return HTTP 400.
    tenant_id = "T_FAB6"
    client = authorized_client("T_FAB6")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["security_events"] = (
        "security_events.csv",
        f"security_id,customer_id,tenant_id,pii_encrypted,encryption_type,breach_detected,breach_confirmed_date,notification_delay_hours,affected_user_count,data_categories_breached,security_audit_flag\n"
        f"SEC1,C1,{tenant_id},True,AES-256,True,invalid-date,24,minimal,kyc_documents,False".encode("utf-8"),
        "text/csv"
    )
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    assert "INVALID_DATE_FORMAT" in response.json()["detail"]["error_code"]

    # Supplied negative delay should return HTTP 400.
    files["security_events"] = (
        "security_events.csv",
        f"security_id,customer_id,tenant_id,pii_encrypted,encryption_type,breach_detected,breach_confirmed_date,notification_delay_hours,affected_user_count,data_categories_breached,security_audit_flag\n"
        f"SEC1,C1,{tenant_id},True,AES-256,True,2024-01-01,-5,minimal,kyc_documents,False".encode("utf-8"),
        "text/csv"
    )
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    assert "INVALID_DELAY_VALUE" in response.json()["detail"]["error_code"]

def test_fabrication_invalid_enum_rejected(db_transaction, authorized_client):
    # kyc_status as unknown_status is invalid -> rejected with HTTP 400.
    tenant_id = "T_FAB7"
    client = authorized_client("T_FAB7")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    files["customer_master"] = (
        "customer_master.csv",
        f"customer_id,tenant_id,is_minor,data_principal_type,account_status,kyc_status,country,created_at\n"
        f"C1,{tenant_id},False,individual,active,unknown_status,IN,2024-01-01".encode("utf-8"),
        "text/csv"
    )
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "Enum validation failed"
    assert data["detail"]["field"] == "kyc_status"
    assert data["detail"]["error_code"] == "INVALID_ENUM_VALUE"

def test_fabrication_missing_optional_enum_preserved(db_transaction, authorized_client):
    # erasure_request_source is optional (missing) and preserved as None (not defaulted).
    tenant_id = "T_FAB8"
    client = authorized_client("T_FAB8")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    # Set erasure_requested to False and leave erasure_request_source empty
    files["data_lifecycle"] = (
        "data_lifecycle.csv",
        f"lifecycle_id,customer_id,tenant_id,data_category,retention_expiry_date,retention_status,purpose_completed,erasure_requested,erasure_date,legal_hold_flag,erasure_request_source\n"
        f"L1,C1,{tenant_id},kyc_documents,2025-01-01,active,False,False,2024-01-01,False,".encode("utf-8"),
        "text/csv"
    )
    with patch("src.api.routes.run_compliance_analysis") as mock_run, \
         patch("src.api.routes._build_full_response") as mock_build:
        mock_run.return_value = {"status": "ok"}
        mock_build.return_value = {
            "tenant_id": tenant_id, "total_obligations": 0, "unique_rules_violated": 0,
            "total_violation_occurrences": 0, "risk_score": 0.0, "risk_tier": "LOW",
            "violations": [], "status": "success", "agent_analysis": {}
        }
        response = client.post(
            "/analyze/upload",
            data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
            files=files
        )
        assert response.status_code == 200
        
    with db_transaction.cursor() as cur:
        cur.execute("SELECT erasure_request_source FROM data_lifecycle WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
        assert row["erasure_request_source"] is None

def test_missing_system_policy_category_preserved_as_none(db_transaction, authorized_client):
    # Proves blank categories, missing system names, and missing policy names are never replaced by placeholder strings.
    tenant_id = "T_FAB9"
    client = authorized_client("T_FAB9")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    
    # 1. Blank category breached in security_events
    files["security_events"] = (
        "security_events.csv",
        f"security_id,customer_id,tenant_id,pii_encrypted,encryption_type,breach_detected,breach_confirmed_date,notification_delay_hours,affected_user_count,data_categories_breached,security_audit_flag\n"
        f"SEC1,C1,{tenant_id},True,AES-256,True,2024-01-01,24,minimal,,False".encode("utf-8"),
        "text/csv"
    )
    # 2. Blank system_name in system_inventory
    files["system_inventory"] = (
        "system_inventory.csv",
        f"system_id,tenant_id,system_name,system_type,pii_stored,encryption_enabled,access_control_enabled,retention_policy_applied,data_processor_type,dpa_signed,dpa_expiry_date\n"
        f"SYS1,{tenant_id},,crm,True,True,True,True,internal,True,".encode("utf-8"),
        "text/csv"
    )
    # 3. Blank policy_name in policies
    files["policies"] = (
        "policies.csv",
        f"policy_id,tenant_id,policy_type,policy_name,policy_value_numeric,policy_value_unit,effective_date,last_updated,is_active,additional_attributes\n"
        f"P1,{tenant_id},retention,,30,days,2024-01-01,2024-01-01,True,".encode("utf-8"),
        "text/csv"
    )

    with patch("src.api.routes.run_compliance_analysis") as mock_run, \
         patch("src.api.routes._build_full_response") as mock_build:
        mock_run.return_value = {"status": "ok"}
        mock_build.return_value = {
            "tenant_id": tenant_id, "total_obligations": 0, "unique_rules_violated": 0,
            "total_violation_occurrences": 0, "risk_score": 0.0, "risk_tier": "LOW",
            "violations": [], "status": "success", "agent_analysis": {}
        }
        response = client.post(
            "/analyze/upload",
            data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
            files=files
        )
        assert response.status_code == 200

    with db_transaction.cursor() as cur:
        cur.execute("SELECT data_categories_breached FROM security_events WHERE tenant_id = %s", (tenant_id,))
        assert cur.fetchone()["data_categories_breached"] is None

        cur.execute("SELECT system_name FROM system_inventory WHERE tenant_id = %s", (tenant_id,))
        assert cur.fetchone()["system_name"] is None

        cur.execute("SELECT policy_name FROM policies WHERE tenant_id = %s", (tenant_id,))
        assert cur.fetchone()["policy_name"] is None

def test_omitted_system_policy_category_preserved_as_none(db_transaction, authorized_client):
    # Proves that omitted columns for system names, policy names, and data categories breached are also accepted and stored as None.
    tenant_id = "T_FAB9_OMIT"
    client = authorized_client("T_FAB9_OMIT")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)

    # 1. Omitted data_categories_breached column in security_events
    files["security_events"] = (
        "security_events.csv",
        f"security_id,customer_id,tenant_id,pii_encrypted,encryption_type,breach_detected,breach_confirmed_date,notification_delay_hours,affected_user_count,security_audit_flag\n"
        f"SEC1,C1,{tenant_id},True,AES-256,True,2024-01-01,24,minimal,False".encode("utf-8"),
        "text/csv"
    )
    # 2. Omitted system_name column in system_inventory
    files["system_inventory"] = (
        "system_inventory.csv",
        f"system_id,tenant_id,system_type,pii_stored,encryption_enabled,access_control_enabled,retention_policy_applied,data_processor_type,dpa_signed,dpa_expiry_date\n"
        f"SYS1,{tenant_id},crm,True,True,True,True,internal,True,".encode("utf-8"),
        "text/csv"
    )
    # 3. Omitted policy_name column in policies
    files["policies"] = (
        "policies.csv",
        f"policy_id,tenant_id,policy_type,policy_value_numeric,policy_value_unit,effective_date,last_updated,is_active,additional_attributes\n"
        f"P1,{tenant_id},retention,30,days,2024-01-01,2024-01-01,True,".encode("utf-8"),
        "text/csv"
    )

    with patch("src.api.routes.run_compliance_analysis") as mock_run, \
         patch("src.api.routes._build_full_response") as mock_build:
        mock_run.return_value = {"status": "ok"}
        mock_build.return_value = {
            "tenant_id": tenant_id, "total_obligations": 0, "unique_rules_violated": 0,
            "total_violation_occurrences": 0, "risk_score": 0.0, "risk_tier": "LOW",
            "violations": [], "status": "success", "agent_analysis": {}
        }
        response = client.post(
            "/analyze/upload",
            data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
            files=files
        )
        assert response.status_code == 200

    with db_transaction.cursor() as cur:
        cur.execute("SELECT data_categories_breached FROM security_events WHERE tenant_id = %s", (tenant_id,))
        assert cur.fetchone()["data_categories_breached"] is None

        cur.execute("SELECT system_name FROM system_inventory WHERE tenant_id = %s", (tenant_id,))
        assert cur.fetchone()["system_name"] is None

        cur.execute("SELECT policy_name FROM policies WHERE tenant_id = %s", (tenant_id,))
        assert cur.fetchone()["policy_name"] is None

def test_missing_tenant_name_rejected(db_transaction, authorized_client):
    tenant_id = "T_FAB10"
    client = authorized_client("T_FAB10")
    clear_test_db(db_transaction, tenant_id)
    files = get_valid_csvs(tenant_id)
    
    # 1. Blank tenant_name in CSV should be rejected
    files["governance_config"] = (
        "governance_config.csv",
        f"tenant_id,tenant_name,grievance_endpoint_available,dpo_assigned,dpo_contact_masked,audit_frequency_days,last_audit_date,risk_level\n"
        f"{tenant_id},,True,True,dpo@test.com,365,2024-01-01,LOW\n".encode("utf-8"),
        "text/csv"
    )
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "MISSING_TENANT_NAME"

    # 2. Omitted tenant_name column should be rejected
    files["governance_config"] = (
        "governance_config.csv",
        f"tenant_id,grievance_endpoint_available,dpo_assigned,dpo_contact_masked,audit_frequency_days,last_audit_date,risk_level\n"
        f"{tenant_id},True,True,dpo@test.com,365,2024-01-01,LOW\n".encode("utf-8"),
        "text/csv"
    )
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "Test Tenant"},
        files=files
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] in ("MISSING_TENANT_NAME", "MISSING_COLUMN")

def test_schema_migration_reproducibility():
    # Test that initializes or migrates an isolated empty test database and proves the required nullable fields/constraint state.
    db_url = os.environ.get("DPDP_TEST_DATABASE_URL")
    assert db_url, "DPDP_TEST_DATABASE_URL must be configured"
    
    # Connect to postgres default DB to recreate a temporary DB
    from urllib.parse import urlparse
    parsed = urlparse(db_url)
    dbname_orig = parsed.path.lstrip("/")
    
    # We can connect to 'postgres' DB using same credentials
    postgres_url = db_url.replace(f"/{dbname_orig}", "/postgres")
    temp_db_url = db_url.replace(f"/{dbname_orig}", "/dpdp_test_isolated_temp")
    
    conn = psycopg.connect(postgres_url, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = 'dpdp_test_isolated_temp'
              AND pid <> pg_backend_pid();
        """)
        cur.execute("DROP DATABASE IF EXISTS dpdp_test_isolated_temp")
        cur.execute("CREATE DATABASE dpdp_test_isolated_temp")
    conn.close()
    
    conn_temp = psycopg.connect(temp_db_url, autocommit=True)
    
    try:
        # 0. Run create_tables (1).sql
        with open("db/create_tables (1).sql", "r") as f:
            create_sql = f.read()
        with conn_temp.cursor() as cur:
            cur.execute(create_sql)

        # 1. Run schema.sql
        with open("db/schema.sql", "r") as f:
            schema_sql = f.read()
        clean_sql = "\n".join([l for l in schema_sql.splitlines() if not l.strip().startswith("\\")])
        with conn_temp.cursor() as cur:
            cur.execute(clean_sql)
            
            # Reset search path since schema.sql clears it
            cur.execute('SET search_path TO public, "$user";')
            
        # Run migrate_rules_to_db.py --reset to populate rules/clauses
        import subprocess
        env = os.environ.copy()
        env["DB_NAME"] = "dpdp_test_isolated_temp"
        subprocess.run(["python", "db/migrate_rules_to_db.py", "--reset"], env=env, capture_output=True, check=True)
            
        # Verify initial state has constraints and NOT NULLs
        with conn_temp.cursor() as cur:
            # Check constraints on security_events
            cur.execute("SELECT conname FROM pg_constraint WHERE conrelid = 'public.security_events'::regclass AND conname = 'chk_breach_fields'")
            assert cur.fetchone() is not None
            
            # Check NOT NULL on system_inventory.system_name
            cur.execute("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'system_inventory' AND column_name = 'system_name'")
            assert cur.fetchone()[0] == "NO"
            
            # Check NOT NULL on policies.policy_name
            cur.execute("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'policies' AND column_name = 'policy_name'")
            assert cur.fetchone()[0] == "NO"
            
        # 2. Run migrations
        for mig_file in [
            "db/issue_3_guardian_consent_migration.sql",
            "db/issue_4_evidence_preservation_migration.sql",
            "db/issue_5_access_logs_system_relation.sql",
            "db/issue_8_audit_run_migration.sql"
        ]:
            with open(mig_file, "r") as f:
                mig_sql = f.read()
            clean_mig_sql = "\n".join([l for l in mig_sql.splitlines() if not l.strip().startswith("\\")])
            with conn_temp.cursor() as cur:
                # Set search path for migrations too
                cur.execute('SET search_path TO public, "$user";')
                cur.execute(clean_mig_sql)
                
        # 3. Assert nullable fields / constraint state
        with conn_temp.cursor() as cur:
            # chk_breach_fields constraint must be gone
            cur.execute("SELECT conname FROM pg_constraint WHERE conrelid = 'public.security_events'::regclass AND conname = 'chk_breach_fields'")
            assert cur.fetchone() is None
            
            # system_name must be nullable (YES)
            cur.execute("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'system_inventory' AND column_name = 'system_name'")
            assert cur.fetchone()[0] == "YES"
            
            # policy_name must be nullable (YES)
            cur.execute("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'policies' AND column_name = 'policy_name'")
            assert cur.fetchone()[0] == "YES"
            
    finally:
        conn_temp.close()
        # Drop temp database
        conn = psycopg.connect(postgres_url, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = 'dpdp_test_isolated_temp'
                  AND pid <> pg_backend_pid();
            """)
            cur.execute("DROP DATABASE IF EXISTS dpdp_test_isolated_temp")
        conn.close()
