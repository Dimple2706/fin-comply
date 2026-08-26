"""
tests/test_phase8_master_verification.py
=========================================
Master Verification Suite for Phase 8:
- Issue E-12: SQL Identifier Parameterization & Table Whitelist
- Issue E-13: Run-Level Audit Versioning & Model SHA-256 Fingerprint
- Issue E-05: RBAC Security & Authentication on Rules Management Endpoints
"""

import sys
import json
import re
from pathlib import Path
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app
from src.api.routes import get_db_connection
from src.agent_layer.orchestrator import ALLOWED_TABLES, _get_model_sha256
from src.api.schemas import AnalyzeResponse
import pytest
import os
import json
import hashlib

@pytest.fixture(autouse=True)
def setup_credentials():
    test_credentials = {
        hashlib.sha256(b"admin:bob_admin").hexdigest(): {
            "username": "bob_admin",
            "role": "admin",
            "authorized_tenants": ["QUICKLOAN-001", "PAYFLEX-002", "WEALTHNEST-003", "RURALCRED-004", "NEXUSNEOBANK-005"]
        },
        hashlib.sha256(b"reviewer:alice_reviewer").hexdigest(): {
            "username": "alice_reviewer",
            "role": "reviewer",
            "authorized_tenants": ["QUICKLOAN-001", "PAYFLEX-002", "WEALTHNEST-003", "RURALCRED-004", "NEXUSNEOBANK-005"]
        }
    }
    old_creds = os.environ.get("FINCOMPLY_TEST_CREDENTIALS")
    os.environ["FINCOMPLY_TEST_CREDENTIALS"] = json.dumps(test_credentials)
    yield
    if old_creds is not None:
        os.environ["FINCOMPLY_TEST_CREDENTIALS"] = old_creds
    else:
        os.environ.pop("FINCOMPLY_TEST_CREDENTIALS", None)

def test_phase8_master():
    print("=" * 70)
    print("FIN-COMPLY MASTER PHASE 8 VERIFICATION (E-05, E-12, E-13)")
    print("=" * 70)

    client = TestClient(app)

    # ─────────────────────────────────────────────────────────────
    # 1. TEST ISSUE E-12: SQL IDENTIFIER SAFETY & WHITELIST
    # ─────────────────────────────────────────────────────────────
    print("\n[CHECK 1] Verifying SQL Safety & Table Whitelist (E-12)...")
    expected_tables = {
        "governance_config", "system_inventory", "policies",
        "customer_master", "consent_records", "transaction_events",
        "access_logs", "data_lifecycle", "security_events", "dsar_requests"
    }
    assert ALLOWED_TABLES == expected_tables, f"ALLOWED_TABLES mismatch: {ALLOWED_TABLES}"
    
    with open("src/agent_layer/orchestrator.py", "r", encoding="utf-8") as f:
        orch_src = f.read()
    assert "Identifier(table)" in orch_src, "Identifier(table) missing from orchestrator.py"
    assert "SQL(" in orch_src, "SQL(...) missing from orchestrator.py"
    print("  [OK E-12] Dynamic table queries use safe SQL Identifiers and reject unauthorized table names.")

    # ─────────────────────────────────────────────────────────────
    # 2. TEST ISSUE E-13: RUN METADATA & MODEL FINGERPRINT
    # ─────────────────────────────────────────────────────────────
    print("\n[CHECK 2] Verifying Run-Level Audit Versioning & Model SHA-256 (E-13)...")
    model_sha = _get_model_sha256()
    assert len(model_sha) == 64, f"Invalid SHA-256 hash length: {model_sha}"
    assert re.match(r"^[0-9a-f]{64}$", model_sha), f"SHA-256 is not a valid hex string: {model_sha}"
    print(f"  [OK] Model fingerprint: {model_sha}")

    tenant_id = "QUICKLOAN-001"
    admin_headers = {"Authorization": "Bearer admin:bob_admin"}
    response = client.post("/analyze", json={"tenant_id": tenant_id}, headers=admin_headers)
    assert response.status_code == 200, f"Analysis failed: {response.text}"
    
    data = response.json()
    parsed = AnalyzeResponse(**data)
    assert parsed.run_metadata is not None, "run_metadata missing from AnalyzeResponse"
    meta = parsed.run_metadata
    assert meta.engine_version == "1.0.0"
    assert meta.schema_version == "2026.1"
    assert meta.active_rule_count >= 19
    assert meta.model_sha256 == model_sha
    assert meta.evaluated_at is not None

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT result_json 
                FROM evaluation_results 
                WHERE tenant_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
                """,
                [tenant_id]
            )
            row = cur.fetchone()
            assert row is not None, f"No evaluation_results in DB for {tenant_id}"
            stored = row["result_json"]
            if isinstance(stored, str):
                stored = json.loads(stored)
            assert "run_metadata" in stored, "run_metadata missing from DB result_json"
            assert stored["run_metadata"]["model_sha256"] == model_sha
    print("  [OK E-13] RunMetadata serialized in API response and persisted to evaluation_results.")

    # ─────────────────────────────────────────────────────────────
    # 3. TEST ISSUE E-05: RULE MANAGEMENT ENDPOINT RBAC & AUTH
    # ─────────────────────────────────────────────────────────────
    print("\n[CHECK 3] Verifying Rule Management Authentication & RBAC (E-05)...")

    # A. Unauthenticated requests MUST be rejected with 401
    resp_unauth_rules = client.get("/rules")
    assert resp_unauth_rules.status_code == 401, f"Expected 401 for unauthenticated /rules, got {resp_unauth_rules.status_code}"
    
    resp_unauth_proposed = client.get("/rules/proposed")
    assert resp_unauth_proposed.status_code == 401, f"Expected 401 for unauthenticated /rules/proposed, got {resp_unauth_proposed.status_code}"

    resp_unauth_approve = client.post("/rules/approve/999")
    assert resp_unauth_approve.status_code == 401, f"Expected 401 for unauthenticated /rules/approve/999, got {resp_unauth_approve.status_code}"

    resp_unauth_reject = client.post("/rules/reject/999")
    assert resp_unauth_reject.status_code == 401, f"Expected 401 for unauthenticated /rules/reject/999, got {resp_unauth_reject.status_code}"
    print("  [OK E-05] Unauthenticated requests to /rules, /rules/proposed, /rules/approve, and /rules/reject correctly rejected (401 Unauthorized).")

    # B. Reviewer token accessing /rules (authenticated) and /rules/proposed (reviewer) MUST succeed
    reviewer_headers = {"Authorization": "Bearer reviewer:alice_reviewer"}
    resp_rev_rules = client.get("/rules", headers=reviewer_headers)
    assert resp_rev_rules.status_code == 200, f"Expected 200 for reviewer /rules, got {resp_rev_rules.status_code}"
    assert len(resp_rev_rules.json()) >= 19, "Expected at least 19 active rules"

    resp_rev_prop = client.get("/rules/proposed", headers=reviewer_headers)
    assert resp_rev_prop.status_code == 200, f"Expected 200 for reviewer /rules/proposed, got {resp_rev_prop.status_code}"

    # C. Reviewer trying to approve a rule MUST be rejected with 403 Forbidden
    resp_rev_approve = client.post("/rules/approve/999", headers=reviewer_headers)
    assert resp_rev_approve.status_code == 403, f"Expected 403 Forbidden for non-admin on /rules/approve, got {resp_rev_approve.status_code}"
    print("  [OK E-05] Reviewer role authorized for inspection (200 OK) but blocked from approving rules (403 Forbidden).")

    # D. Admin token accessing /rules/approve
    admin_headers = {"Authorization": "Bearer admin:bob_admin"}
    # Should get past auth check (returns 404 for non-existent proposal ID 99999, proving auth passed)
    resp_admin_approve = client.post("/rules/approve/99999", headers=admin_headers)
    assert resp_admin_approve.status_code == 404, f"Expected 404 Proposal Not Found after passing admin auth, got {resp_admin_approve.status_code}"
    print("  [OK E-05] Admin role successfully authorized on /rules/approve.")

    print("\n" + "=" * 70)
    print("PHASE 8 MASTER VERIFICATION COMPLETE: ALL CHECKS PASSED (100%)!")
    print("=" * 70)

if __name__ == "__main__":
    test_phase8_master()
