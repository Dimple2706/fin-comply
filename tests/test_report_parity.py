import os
import io
import json
import pytest
import hashlib
import tempfile
import fitz  # PyMuPDF
from pathlib import Path
from fastapi.testclient import TestClient
from pypdf import PdfReader
from src.api.main import app

client = TestClient(app)

# Security Credentials for testing parity
admin_token = "secure_test_admin_token_2026"
unauthorized_token = "unauthorized_test_token_2026"

test_credentials = {
    hashlib.sha256(admin_token.encode("utf-8")).hexdigest(): {
        "username": "test_admin",
        "role": "admin",
        "authorized_tenants": ["t_clean", "t_dpdp001"]
    },
    hashlib.sha256(unauthorized_token.encode("utf-8")).hexdigest(): {
        "username": "test_limited",
        "role": "reviewer",
        "authorized_tenants": ["t_clean"]  # NO access to t_dpdp001
    }
}

@pytest.fixture
def run_auth_mock():
    old_creds = os.environ.get("FINCOMPLY_TEST_CREDENTIALS")
    os.environ["FINCOMPLY_TEST_CREDENTIALS"] = json.dumps(test_credentials)
    yield
    if old_creds is not None:
        os.environ["FINCOMPLY_TEST_CREDENTIALS"] = old_creds
    else:
        os.environ.pop("FINCOMPLY_TEST_CREDENTIALS", None)

def test_report_and_dashboard_parity(run_auth_mock):
    from src.api.routes import get_db_connection
    tenant_id = "t_dpdp001"
    
    # Clean database of any previous test runs for t_dpdp001 to ensure isolation
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM evaluation_results WHERE tenant_id = %s", (tenant_id,))
            cur.execute("DELETE FROM audit_runs WHERE tenant_id = %s", (tenant_id,))
        conn.commit()

    fixture_root = Path("tests/fixtures/deterministic_compliance_package")
    
    # 1. Prepare files for run 1 (Violation - DPDP-001)
    dir_1 = fixture_root / tenant_id
    files_1 = {}
    for fname in sorted(os.listdir(dir_1)):
        if fname.endswith(".csv"):
            field_name = fname.replace(".csv", "")
            with open(dir_1 / fname, "rb") as f_in:
                files_1[field_name] = (fname, f_in.read(), "text/csv")
                
    # Upload run 1 dataset (this automatically runs analysis and registers it)
    up_res_1 = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "VIOLATION TENANT"},
        files=files_1,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert up_res_1.status_code == 200, up_res_1.text
    run_1_full = up_res_1.json()
    run_id_1 = run_1_full["audit_run_id"]
    
    # 2. Prepare files for run 2 (Clean)
    dir_2 = fixture_root / "t_clean"
    files_2 = {}
    for fname in sorted(os.listdir(dir_2)):
        if fname.endswith(".csv"):
            field_name = fname.replace(".csv", "")
            with open(dir_2 / fname, "rb") as f_in:
                content = f_in.read().replace(b"t_clean", b"t_dpdp001")
                files_2[field_name] = (fname, content, "text/csv")
                
    # Upload run 2 dataset to the same tenant t_dpdp001 (automatically runs analysis and registers it)
    up_res_2 = client.post(
        "/analyze/upload",
        data={"tenant_id": tenant_id, "tenant_name": "CLEANED TENANT"},
        files=files_2,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert up_res_2.status_code == 200, up_res_2.text
    run_2_full = up_res_2.json()
    run_id_2 = run_2_full["audit_run_id"]
    
    # Assert run IDs are distinct
    assert run_id_1 != run_id_2
    
    # 3. Request the older run (run_id_1) from dashboard
    dash_res = client.get(
        f"/dashboard/{tenant_id}?audit_run_id={run_id_1}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    
    # Request the older run (run_id_1) from PDF
    pdf_res = client.get(
        f"/report/pdf/{tenant_id}?audit_run_id={run_id_1}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    
    # 4. Assert exact parity between API (run_1_full) and Dashboard (dash_data)
    assert run_1_full["audit_run_id"] == run_id_1
    assert dash_data["audit_run_id"] == run_id_1
    
    assert run_1_full["run_status"] == dash_data["run_status"]
    assert run_1_full["risk_score"] == dash_data["risk_score"]
    assert run_1_full["risk_tier"] == dash_data["risk_tier"]
    assert run_1_full["unique_rules_violated"] == dash_data["unique_rules_violated"]
    assert run_1_full["total_violation_occurrences"] == dash_data["total_violation_occurrences"]
    assert run_1_full["failed_rules_count"] == dash_data["failed_rules_count"]
    assert run_1_full["not_assessable_rules_count"] == dash_data["not_assessable_rules_count"]
    assert run_1_full["total_penalty_exposure_crore"] == dash_data["total_penalty_exposure_crore"]
    assert run_1_full["disclaimer"] == dash_data["disclaimer"]
    
    assert run_1_full["compliance_score"]["score_percentage"] == dash_data["compliance_score"]["score_percentage"]
    assert run_1_full["compliance_score"]["satisfied_obligations"] == dash_data["compliance_score"]["satisfied_obligations"]
    assert run_1_full["compliance_score"]["violated_obligations"] == dash_data["compliance_score"]["violated_obligations"]
    assert run_1_full["compliance_score"]["failed_obligations"] == dash_data["compliance_score"]["failed_obligations"]
    
    assert run_1_full["outcome_count_by_state"] == dash_data["outcome_count_by_state"]
    
    # Assert rule/finding identities match
    run_1_rules = sorted([v["rule_id"] for v in run_1_full["violations"]])
    dash_rules = sorted([v["rule_id"] for v in dash_data["violations"]])
    assert run_1_rules == dash_rules
    
    # 5. Visual PDF verification using pymupdf & text extraction
    pdf_bytes = pdf_res.content
    with tempfile.TemporaryDirectory() as tmpdir:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert len(doc) > 0, "PDF must render at least one page successfully."
        
        # Render page 1 to image and save to temporary test directory
        page = doc[0]
        pix = page.get_pixmap()
        image_path = os.path.join(tmpdir, "page_1.png")
        pix.save(image_path)
        
        assert os.path.exists(image_path)
        assert os.path.getsize(image_path) > 0
        
        # Assert page 1 contains readable labels
        page_text = page.get_text()
        assert run_id_1 in page_text, "Audit Run ID must be readable on page 1."
        assert "COMPLETED" in page_text.upper(), "Run status must be visible on page 1."
        assert str(run_1_full["risk_score"]) in page_text, "Risk score must be visible on page 1."
        assert "Compliance Score Percentage" in page_text, "Compliance score label must be visible on page 1."
        assert f"{run_1_full['compliance_score']['score_percentage']:.1f}%" in page_text, "Compliance score value must be visible on page 1."
        assert "Disclaimer:" in page_text, "Disclaimer label must be visible on page 1."
        assert " ".join(run_1_full["disclaimer"].split()) in " ".join(page_text.split()), "Disclaimer text must be visible on page 1."
        
    # 6. Explicit negative assertion (verify no newer run values leak into older run outputs)
    assert run_id_2 not in run_1_full["audit_run_id"]
    assert run_id_2 not in dash_data["audit_run_id"]
    assert run_id_2 not in page_text
    
    assert run_2_full["risk_score"] == 0.0
    assert run_1_full["risk_score"] > 0.0
    assert dash_data["risk_score"] == run_1_full["risk_score"]
    
    assert run_2_full["unique_rules_violated"] == 0
    assert run_1_full["unique_rules_violated"] > 0
    assert dash_data["unique_rules_violated"] == run_1_full["unique_rules_violated"]
    
    # 7. Authorization Test for cross-tenant access
    # Unauthorized token has access to t_clean but NOT t_dpdp001
    dash_unauth = client.get(
        f"/dashboard/{tenant_id}?audit_run_id={run_id_1}",
        headers={"Authorization": f"Bearer {unauthorized_token}"}
    )
    assert dash_unauth.status_code == 403
    
    pdf_unauth = client.get(
        f"/report/pdf/{tenant_id}?audit_run_id={run_id_1}",
        headers={"Authorization": f"Bearer {unauthorized_token}"}
    )
    assert pdf_unauth.status_code == 403
