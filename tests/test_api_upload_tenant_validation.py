import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.api.main import app
from src.anonymization.csv_loader import EXPECTED_FILES, REQUIRED_COLUMN_GROUPS

client = TestClient(app)

def generate_csv(table_name: str, tenant_id: str):
    # Get required columns
    groups = REQUIRED_COLUMN_GROUPS.get(table_name, [])
    cols = ["tenant_id"]
    for group in groups:
        if "tenant_id" not in group:
            cols.append(group[0])
            
    header = ",".join(cols)
    row = ",".join([tenant_id] + ["dummy" for _ in range(len(cols) - 1)])
    return f"{header}\n{row}".encode("utf-8")

def get_upload_files(tenant_id: str):
    return {
        table: (filename, generate_csv(table, tenant_id), "text/csv")
        for table, filename in EXPECTED_FILES.items()
    }

@patch("src.api.routes.write_tenant_data")
@patch("src.api.routes.run_compliance_analysis")
def test_api_invalid_tenant_returns_400(mock_run_analysis, mock_write_data, authorized_client):
    files = get_upload_files("WRONG-TENANT")
    
    # Authorized client for TENANT-A. Note that WRONG-TENANT is uploaded.
    client = authorized_client("TENANT-A")
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": "TENANT-A", "tenant_name": "Tenant A"},
        files=files
    )
    
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error_code"] == "TENANT_MISMATCH"
    assert "filename" in data["detail"]
    assert "row_number" in data["detail"]
    assert data["detail"]["expected_tenant"] == "TENANT-A"
    assert data["detail"]["supplied_tenant"] == "WRONG-TENANT"
    
    mock_write_data.assert_not_called()
    mock_run_analysis.assert_not_called()

@patch("src.api.routes._build_full_response")
@patch("src.api.routes.anonymize_dataframe")
@patch("src.api.routes.write_tenant_data")
@patch("src.api.routes.run_compliance_analysis")
def test_api_valid_tenant_proceeds(mock_run_analysis, mock_write_data, mock_anonymize, mock_build_response, authorized_client):
    mock_write_data.return_value = 10
    mock_run_analysis.return_value = {"status": "ok"}
    mock_anonymize.return_value = [{"dummy": "data"}]
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
    
    files = get_upload_files("TENANT-A")
    
    client = authorized_client("TENANT-A")
    response = client.post(
        "/analyze/upload",
        data={"tenant_id": "TENANT-A", "tenant_name": "Tenant A"},
        files=files
    )
    
    if response.status_code != 200:
        print("FAILED:", response.json())
        
    assert response.status_code == 200
    mock_write_data.assert_called_once()
    mock_run_analysis.assert_called_once()
