import os
import json
import hashlib
import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.routes import get_db_connection, ensure_evaluation_results_table, compute_tenant_snapshot_hash, compute_kb_file_hash

# Set up test credentials in environment before client runs
admin_token = "secure_test_admin_token_2026"
other_token = "secure_test_other_token_2026"

def get_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

test_credentials = {
    get_hash(admin_token): {
        "username": "test_admin",
        "role": "admin",
        "authorized_tenants": ["tenant_a", "non_existent_tenant_XYZ"]
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
    # Make sure tables are created in the test DB
    with get_db_connection() as conn:
        ensure_evaluation_results_table(conn)
        with conn.cursor() as cur:
            cur.execute("INSERT INTO governance_config (tenant_id, tenant_name, audit_frequency_days, dpo_assigned, risk_level, dpo_contact_masked) VALUES ('tenant_a', 'Tenant A', 90, 'True', 'MEDIUM', 'dpo@tenant_a.com') ON CONFLICT DO NOTHING;")
            cur.execute("INSERT INTO governance_config (tenant_id, tenant_name, audit_frequency_days, dpo_assigned, risk_level, dpo_contact_masked) VALUES ('tenant_b', 'Tenant B', 90, 'True', 'MEDIUM', 'dpo@tenant_b.com') ON CONFLICT DO NOTHING;")
        conn.commit()

def test_immutable_audit_runs_and_lineage():
    # 1. First run for tenant_a
    res1 = client.post("/analyze", json={"tenant_id": "tenant_a"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res1.status_code == 200
    data1 = res1.json()
    run_id1 = data1["audit_run_id"]
    assert run_id1 is not None

    # 2. Second run for tenant_a
    res2 = client.post("/analyze", json={"tenant_id": "tenant_a"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res2.status_code == 200
    data2 = res2.json()
    run_id2 = data2["audit_run_id"]
    assert run_id2 is not None
    assert run_id1 != run_id2  # Different runs get different IDs

    # 3. Check lineage / parent run linkage
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT parent_audit_run_id, status FROM audit_runs WHERE audit_run_id = %s", (run_id2,))
            row = cur.fetchone()
            assert row is not None
            parent_id = row["parent_audit_run_id"] if isinstance(row, dict) else row[0]
            status = row["status"] if isinstance(row, dict) else row[1]
            assert parent_id == run_id1  # Links back to first run
            assert status == "completed"

            # Check that run 1 results and metadata remain unchanged
            cur.execute("SELECT status FROM audit_runs WHERE audit_run_id = %s", (run_id1,))
            row1 = cur.fetchone()
            status1 = row1["status"] if isinstance(row1, dict) else row1[0]
            assert status1 == "completed"

def test_wrong_tenant_run_id_rejection():
    # Run for tenant_a to get a valid run ID
    res1 = client.post("/analyze", json={"tenant_id": "tenant_a"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res1.status_code == 200
    run_id = res1.json()["audit_run_id"]

    # Query PDF endpoint using tenant_b but with tenant_a's run ID -> must return 403 (Tenant isolation check first)
    res_pdf = client.get(f"/report/pdf/tenant_b?audit_run_id={run_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_pdf.status_code == 403

    # Query dashboard endpoint using tenant_b but with tenant_a's run ID -> must return 403
    res_dash = client.get(f"/dashboard/tenant_b?audit_run_id={run_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_dash.status_code == 403

def test_not_assessable_run_persists_reason():
    # Attempt analyze for a non-existent tenant -> must create a not_assessable run
    fake_tenant = "non_existent_tenant_XYZ"
    res = client.post("/analyze", json={"tenant_id": fake_tenant}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 404

    # Assert that the run was created and stored as NOT_ASSESSABLE with reason
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT audit_run_id, status, validation_summary FROM audit_runs WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 1", (fake_tenant,))
            row = cur.fetchone()
            assert row is not None
            status = row["status"] if isinstance(row, dict) else row[1]
            val_summary = row["validation_summary"] if isinstance(row, dict) else row[2]
            assert status == "not_assessable"
            summary_dict = val_summary if isinstance(val_summary, dict) else json.loads(val_summary)
            assert "not found" in summary_dict["error"]

def test_hash_stability():
    # Hashes must be identical for same files, and change if missing or different
    hash1 = compute_kb_file_hash("data/dpdp_kb/dpdp_rules.json")
    hash2 = compute_kb_file_hash("data/dpdp_kb/dpdp_rules.json")
    assert hash1 == hash2

    hash_missing = compute_kb_file_hash("nonexistent_file.json")
    assert hash_missing == "missing"

def test_two_different_results_and_explicit_selection():
    # First run: dpo_assigned = True
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE governance_config SET is_significant_data_fiduciary = TRUE, dpo_assigned = TRUE, last_audit_date = CURRENT_DATE, audit_frequency_days = 90 WHERE tenant_id = 'tenant_a';")
        conn.commit()
    res1 = client.post("/analyze", json={"tenant_id": "tenant_a"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res1.status_code == 200
    run_id1 = res1.json()["audit_run_id"]
    risk_score1 = res1.json()["risk_score"]

    # Second run: dpo_assigned = False (different result)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE governance_config SET dpo_assigned = FALSE WHERE tenant_id = 'tenant_a';")
        conn.commit()
    res2 = client.post("/analyze", json={"tenant_id": "tenant_a"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res2.status_code == 200
    run_id2 = res2.json()["audit_run_id"]
    risk_score2 = res2.json()["risk_score"]
    
    assert run_id1 != run_id2
    assert risk_score1 != risk_score2

    # 1. Verify default GET selection retrieves latest (run 2)
    res_def = client.get("/dashboard/tenant_a", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_def.status_code == 200
    assert res_def.json()["audit_run_id"] == run_id2
    assert res_def.json()["risk_score"] == risk_score2

    # 2. Verify explicit earlier run selection retrieves run 1 through all components:
    # A. API analysis response (POST /analyze with audit_run_id)
    res_explicit_api = client.post("/analyze", json={"tenant_id": "tenant_a", "audit_run_id": run_id1}, headers={"Authorization": f"Bearer {admin_token}"})
    assert res_explicit_api.status_code == 200
    assert res_explicit_api.json()["audit_run_id"] == run_id1
    assert res_explicit_api.json()["risk_score"] == risk_score1

    # B. Dashboard data (GET /dashboard/{tenant_id}?audit_run_id={run_id})
    res_dash = client.get(f"/dashboard/tenant_a?audit_run_id={run_id1}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_dash.status_code == 200
    assert res_dash.json()["audit_run_id"] == run_id1
    assert res_dash.json()["risk_score"] == risk_score1

    # C. Report history (GET /report/history/{tenant_id})
    res_hist = client.get(f"/report/history/tenant_a", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_hist.status_code == 200
    hist_data = res_hist.json()["history"]
    run_ids = [h["audit_run_id"] for h in hist_data]
    assert run_id1 in run_ids
    assert run_id2 in run_ids

    # D. PDF generation (GET /report/pdf/{tenant_id}?audit_run_id={run_id})
    res_pdf = client.get(f"/report/pdf/tenant_a?audit_run_id={run_id1}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"
