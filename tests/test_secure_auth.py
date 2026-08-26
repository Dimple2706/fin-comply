import os
import json
import hashlib
import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.routes import get_db_connection, ensure_evaluation_results_table

# Set up test credentials in environment before client import/run
admin_token = "secure_test_admin_token_2026"
reviewer_token = "secure_test_reviewer_token_2026"
other_token = "secure_test_other_token_2026"

def get_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

test_credentials = {
    get_hash(admin_token): {
        "username": "test_admin",
        "role": "admin",
        "authorized_tenants": ["tenant_a"]
    },
    get_hash(reviewer_token): {
        "username": "test_reviewer",
        "role": "reviewer",
        "authorized_tenants": ["tenant_a"]
    },
    get_hash(other_token): {
        "username": "test_other",
        "role": "auditor",
        "authorized_tenants": ["tenant_b"]
    }
}

# Re-initialize client
client = TestClient(app)

@pytest.fixture(autouse=True)
def run_schema_ensure():
    os.environ["FINCOMPLY_TEST_CREDENTIALS"] = json.dumps(test_credentials)
    with get_db_connection() as conn:
        ensure_evaluation_results_table(conn)
        with conn.cursor() as cur:
            cur.execute("INSERT INTO governance_config (tenant_id, tenant_name, audit_frequency_days, dpo_assigned, risk_level, dpo_contact_masked) VALUES ('tenant_a', 'Tenant A', 90, 'True', 'MEDIUM', 'dpo@tenant_a.com') ON CONFLICT DO NOTHING;")
            cur.execute("INSERT INTO governance_config (tenant_id, tenant_name, audit_frequency_days, dpo_assigned, risk_level, dpo_contact_masked) VALUES ('tenant_b', 'Tenant B', 90, 'True', 'MEDIUM', 'dpo@tenant_b.com') ON CONFLICT DO NOTHING;")
        conn.commit()

def test_unauthenticated_requests():
    # No credentials -> 401
    res = client.post("/analyze", json={"tenant_id": "tenant_a"})
    assert res.status_code == 401

    res = client.get("/dashboard/tenant_a")
    assert res.status_code == 401

    res = client.get("/report/history/tenant_a")
    assert res.status_code == 401

    res = client.get("/report/pdf/tenant_a")
    assert res.status_code == 401

def test_invalid_and_prefix_tokens():
    # Prefix format token -> 401
    res = client.post("/analyze", json={"tenant_id": "tenant_a"}, headers={"Authorization": "Bearer admin:test_admin"})
    assert res.status_code == 401

    # Malformed token -> 401
    res = client.post("/analyze", json={"tenant_id": "tenant_a"}, headers={"Authorization": "Bearer invalid_secret_token"})
    assert res.status_code == 401

def test_tenant_authorization():
    # Valid token, authorized tenant -> 200
    res = client.post("/analyze", json={"tenant_id": "tenant_a"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    run_id = res.json()["audit_run_id"]

    # Valid token, unauthorized tenant -> 403
    res_unauth = client.post("/analyze", json={"tenant_id": "tenant_b"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res_unauth.status_code == 403

    res_dash = client.get("/dashboard/tenant_b", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_dash.status_code == 403

    res_pdf = client.get(f"/report/pdf/tenant_b?audit_run_id={run_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_pdf.status_code == 403

def test_invalid_tenant_id_inputs():
    # Oversized tenant ID (> 64 chars) -> 400
    oversized_id = "a" * 65
    res = client.post("/analyze", json={"tenant_id": oversized_id}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 400

    # Malformed tenant ID characters -> 400
    res = client.post("/analyze", json={"tenant_id": "tenant_a; DROP TABLE customer_master;"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 400

def test_oversized_upload():
    # Test file upload size limits rejection (> 5MB)
    large_content = b"x" * (5 * 1024 * 1024 + 10)
    files = {
        "governance_config": ("governance_config.csv", large_content),
        "customer_master": ("customer_master.csv", b"dummy"),
        "consent_records": ("consent_records.csv", b"dummy"),
        "transaction_events": ("transaction_events.csv", b"dummy"),
        "access_logs": ("access_logs.csv", b"dummy"),
        "data_lifecycle": ("data_lifecycle.csv", b"dummy"),
        "security_events": ("security_events.csv", b"dummy"),
        "dsar_requests": ("dsar_requests.csv", b"dummy"),
        "system_inventory": ("system_inventory.csv", b"dummy"),
        "policies": ("policies.csv", b"dummy"),
    }
    data = {
        "tenant_id": "tenant_a",
        "tenant_name": "Tenant A"
    }
    res = client.post(
        "/analyze/upload",
        data=data,
        files=files,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 400
    assert "exceeds maximum allowed size" in res.json()["detail"]
