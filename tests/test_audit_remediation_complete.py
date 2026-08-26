"""
tests/test_audit_remediation_complete.py
=========================================
Final End-to-End Verification of Audit Fixes:
1. PDF generation across all 5 benchmark tenants (validates dictionary row access and report formatting).
2. Phase 7 Master Verification (XAI separation, ml_layer passthrough, multi-class probabilities).
3. Phase 8 Master Verification (SQL Identifier safety, run_metadata versioning, RBAC authentication).
"""

import sys
from pathlib import Path
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app
from tests.test_phase7_master_verification import test_phase7_complete
from tests.test_phase8_master_verification import test_phase8_master

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

TENANTS = [
    "QUICKLOAN-001",
    "PAYFLEX-002",
    "WEALTHNEST-003",
    "RURALCRED-004",
    "NEXUSNEOBANK-005"
]

def test_audit_remediation():
    print("=" * 70)
    print("RUNNING FINAL SYSTEM-WIDE AUDIT REMEDIATION VERIFICATION")
    print("=" * 70)

    client = TestClient(app)

    # ── 1. Test PDF Export for all 5 Tenants ──
    print("\n[VERIFICATION 1] Testing PDF Export Generation...")
    for tenant_id in TENANTS:
        admin_headers = {"Authorization": "Bearer admin:bob_admin"}
        resp = client.get(f"/report/pdf/{tenant_id}", headers=admin_headers)
        assert resp.status_code == 200, f"PDF generation failed for {tenant_id}: {resp.status_code} - {resp.text}"
        assert resp.headers["content-type"] == "application/pdf", f"Invalid content type: {resp.headers.get('content-type')}"
        assert resp.content.startswith(b"%PDF-"), "Generated file does not have valid PDF header"
        print(f"  [OK PDF] Tenant {tenant_id}: Generated valid PDF ({len(resp.content)} bytes)")

    # ── 2. Run Phase 7 Master Test Suite ──
    print("\n[VERIFICATION 2] Running Phase 7 Master Test Suite...")
    test_phase7_complete()

    # ── 3. Run Phase 8 Master Test Suite ──
    print("\n[VERIFICATION 3] Running Phase 8 Master Test Suite...")
    test_phase8_master()

    print("\n" + "=" * 70)
    print("[SUCCESS] ALL AUDIT REMEDIATIONS & MASTER SUITES 100% PASSED!")
    print("=" * 70)

if __name__ == "__main__":
    test_audit_remediation()
