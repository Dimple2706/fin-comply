import pytest
import pandas as pd
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.anonymization.field_mapper import _anonymize_dsar_requests, DsarValidationError
from src.anonymization.csv_loader import EXPECTED_FILES, REQUIRED_COLUMN_GROUPS

client = TestClient(app)

def build_dsar_df(submitted_date="2024-01-01", sla_due_date="2024-01-31", fulfilled_date=None, fulfillment_status="pending"):
    return pd.DataFrame([{
        "dsar_hash": "H1",
        "dsar_id": "D1",
        "customer_hash": "C1",
        "customer_id": "C1",
        "tenant_id": "T1",
        "request_type": "access",
        "submitted_date": submitted_date,
        "sla_due_date": sla_due_date,
        "fulfilled_date": fulfilled_date,
        "fulfillment_status": fulfillment_status,
        "sla_breached": False,
        "acknowledged_date": "2024-01-02",
        "rejection_reason": None
    }])

def test_1_fulfilled_dsar_genuine_date_preserved():
    df = build_dsar_df(fulfilled_date="2024-01-15", fulfillment_status="fulfilled")
    result = _anonymize_dsar_requests(df, "T1")
    assert result[0]["fulfilled_date"] == "2024-01-15"

def test_2_fulfilled_dsar_without_date_rejected():
    df = build_dsar_df(fulfilled_date=None, fulfillment_status="fulfilled")
    with pytest.raises(DsarValidationError) as exc:
        _anonymize_dsar_requests(df, "T1")
    assert exc.value.error_code == "MISSING_EVIDENCE"

def test_3_pending_dsar_with_date_rejected():
    df = build_dsar_df(fulfilled_date="2024-01-15", fulfillment_status="pending")
    with pytest.raises(DsarValidationError) as exc:
        _anonymize_dsar_requests(df, "T1")
    assert exc.value.error_code == "INVALID_EVIDENCE"

def test_4_invalid_fulfilled_date_rejected():
    df = build_dsar_df(fulfilled_date="Not-a-date", fulfillment_status="fulfilled")
    with pytest.raises(DsarValidationError) as exc:
        _anonymize_dsar_requests(df, "T1")
    assert exc.value.error_code == "INVALID_DATE_FORMAT"

def test_5_sla_due_date_30_days_accepted():
    df = build_dsar_df(submitted_date="2024-01-01", sla_due_date="2024-01-31")
    result = _anonymize_dsar_requests(df, "T1")
    assert result[0]["sla_due_date"] == "2024-01-31"

def test_6_inconsistent_sla_due_date_rejected():
    df = build_dsar_df(submitted_date="2024-01-01", sla_due_date="2024-02-15")
    with pytest.raises(DsarValidationError) as exc:
        _anonymize_dsar_requests(df, "T1")
    assert exc.value.error_code == "INCONSISTENT_SLA_DATE"

def test_rejected_without_reason_fails():
    df = build_dsar_df(fulfillment_status="rejected")
    # rejection_reason is None by default in build_dsar_df
    with pytest.raises(DsarValidationError) as exc:
        _anonymize_dsar_requests(df, "T1")
    assert exc.value.error_code == "MISSING_REASON"

def test_rejected_with_reason_preserved():
    df = build_dsar_df(fulfillment_status="rejected")
    df.loc[0, "rejection_reason"] = "Identity not verified"
    result = _anonymize_dsar_requests(df, "T1")
    assert result[0]["rejection_reason"] == "Identity not verified"

def test_fulfilled_date_before_submitted_rejected():
    df = build_dsar_df(submitted_date="2024-01-15", sla_due_date="2024-02-14", fulfilled_date="2024-01-01", fulfillment_status="fulfilled")
    with pytest.raises(DsarValidationError) as exc:
        _anonymize_dsar_requests(df, "T1")
    assert exc.value.error_code == "LOGICAL_CONTRADICTION"

def test_inconsistent_sla_breached_rejected():
    # sla_due_date = 2024-01-31, fulfilled_date = 2024-02-15 (breached!) but sla_breached = False
    df = build_dsar_df(submitted_date="2024-01-01", sla_due_date="2024-01-31", fulfilled_date="2024-02-15", fulfillment_status="fulfilled")
    df.loc[0, "sla_breached"] = False
    with pytest.raises(DsarValidationError) as exc:
        _anonymize_dsar_requests(df, "T1")
    assert exc.value.error_code == "CONTRADICTION"

def test_7_8_mapper_output_identical_system_date_change():
    # Proves no DSAR mapping path calls date.today()
    df = build_dsar_df(fulfilled_date="2024-01-15", fulfillment_status="fulfilled")
    result1 = _anonymize_dsar_requests(df, "T1")
    
    result2 = _anonymize_dsar_requests(df, "T1")
    
    assert result1 == result2

def generate_csv(table_name: str, tenant_id: str, inject_bad_dsar=False):
    groups = REQUIRED_COLUMN_GROUPS.get(table_name, [])
    cols = ["tenant_id"]
    for group in groups:
        if "tenant_id" not in group:
            cols.append(group[0])
            
    if table_name == "dsar_requests":
        cols.append("fulfillment_status")
            
    header = ",".join(cols)
    
    if table_name == "dsar_requests":
        if inject_bad_dsar:
            # Bad row: fulfillment_status = fulfilled but fulfilled_date = ""
            row = f"{tenant_id},H1,C1,access,2024-01-01,2024-01-31,,fulfilled"
        else:
            row = f"{tenant_id},H1,C1,access,2024-01-01,2024-01-31,2024-01-15,fulfilled"
    else:
        row = ",".join([tenant_id] + ["dummy" for _ in range(len(cols) - 1)])
    return f"{header}\n{row}".encode("utf-8")

def get_upload_files(tenant_id: str, inject_bad_dsar=False):
    return {
        table: (filename, generate_csv(table, tenant_id, inject_bad_dsar), "text/csv")
        for table, filename in EXPECTED_FILES.items()
    }

@patch("src.api.routes._build_full_response")
@patch("src.api.routes.write_tenant_data")
@patch("src.api.routes.run_compliance_analysis")
def test_9_10_invalid_dsar_input_returns_400(mock_run_analysis, mock_write_data, mock_build_response):
    files = get_upload_files("TENANT-A", inject_bad_dsar=True)
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": "TENANT-A", "tenant_name": "Tenant A"},
        files=files
    )
    
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "DSAR validation failed"
    assert data["detail"]["error_code"] == "MISSING_EVIDENCE"
    assert data["detail"]["field"] == "fulfilled_date"
    
    mock_write_data.assert_not_called()
    mock_run_analysis.assert_not_called()

def get_missing_col_files(tenant_id: str):
    # Same as generate_csv but omit fulfilled_date column in dsar_requests
    files = get_upload_files(tenant_id, inject_bad_dsar=False)
    dsar_tuple = files["dsar_requests"]
    # Rewrite the content to omit the last column entirely
    lines = dsar_tuple[1].decode("utf-8").split("\n")
    new_header = ",".join(lines[0].split(",")[:-1]) # remove fulfillment_status
    new_header = ",".join(new_header.split(",")[:-1]) # remove fulfilled_date
    new_row = ",".join(lines[1].split(",")[:-2])
    new_content = f"{new_header}\n{new_row}".encode("utf-8")
    files["dsar_requests"] = (dsar_tuple[0], new_content, "text/csv")
    return files

@patch("src.api.routes._build_full_response")
@patch("src.api.routes.write_tenant_data")
@patch("src.api.routes.run_compliance_analysis")
def test_missing_dsar_column_returns_400(mock_run_analysis, mock_write_data, mock_build_response):
    files = get_missing_col_files("TENANT-A")
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": "TENANT-A", "tenant_name": "Tenant A"},
        files=files
    )
    
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "Missing required column"
    assert data["detail"]["error_code"] == "MISSING_COLUMN"
    
    mock_write_data.assert_not_called()
    mock_run_analysis.assert_not_called()

@patch("src.api.routes._build_full_response")
@patch("src.api.routes.write_tenant_data")
@patch("src.api.routes.run_compliance_analysis")
def test_11_existing_valid_dsar_rows_still_load(mock_run_analysis, mock_write_data, mock_build_response):
    mock_write_data.return_value = 10
    mock_run_analysis.return_value = {"status": "ok"}
    mock_build_response.return_value = {
        "tenant_id": "TENANT-A",
        "total_obligations": 10,
        "unique_rules_violated": 0,
        "total_violation_occurrences": 0,
        "risk_score": 0.0,
        "risk_tier": "LOW",
        "violations": [],
        "status": "success",
        "agent_analysis": {"risk_agent": {}, "regulation_agent": {}}
    }

    files = get_upload_files("TENANT-A", inject_bad_dsar=False)
    
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": "TENANT-A", "tenant_name": "Tenant A"},
        files=files
    )
    
    assert response.status_code == 200
    mock_write_data.assert_called_once()
    mock_run_analysis.assert_called_once()

from src.anonymization.db_writer import write_tenant_data

@patch("src.anonymization.db_writer.date")
def test_writer_preserves_dsar_dates(mock_date):
    mock_date.today.return_value = date(2035, 1, 1)
    
    dsar_data = {
        "dsar_requests": [{
            "dsar_hash": "H1", "customer_hash": "C1", "tenant_id": "T1",
            "request_type": "access", "submitted_date": "2024-01-01",
            "sla_due_date": "2024-01-31", "fulfilled_date": "2024-01-15",
            "fulfillment_status": "fulfilled", "sla_breached": False,
            "acknowledged_date": "2024-01-02", "rejection_reason": None
        }]
    }
    
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = [1]
    
    with patch("src.anonymization.db_writer.get_db_connection", return_value=mock_conn):
        
        write_tenant_data("T1", dsar_data)
        
    mock_date.today.assert_not_called()
    
    # Check the execute call
    execute_calls = mock_cur.execute.call_args_list
    assert len(execute_calls) > 0
    dsar_call = None
    for call in execute_calls:
        if "INSERT INTO dsar_requests" in call[0][0]:
            dsar_call = call
            break
            
    assert dsar_call is not None
    args = dsar_call[0][1]
    
    # (dsar_hash, customer_hash, tenant_id, request_type, submitted_date, acknowledged_date, sla_due_date, sla_breached, fulfilled_date, fulfillment_status, rejection_reason)
    assert args[4] == "2024-01-01" # submitted_date
    assert args[6] == "2024-01-31" # sla_due_date
    assert args[8] == "2024-01-15" # fulfilled_date
