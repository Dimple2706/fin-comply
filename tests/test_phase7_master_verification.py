"""
tests/test_phase7_master_verification.py
=========================================
Master Verification Suite for Phase 7:
- Issue E-03: Full API payload passthrough of ml_layer and PostgreSQL persistence.
- Issue E-06: Deterministic rule signal weights labeled as signal_contribution & total_signal_weight.
- Multi-Tenant Verification across all 5 benchmark tenant profiles.
"""

import sys
import json
from pathlib import Path
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app
from src.api.routes import get_db_connection
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

def test_phase7_complete():
    print("=" * 70)
    print("FIN-COMPLY MASTER PHASE 7 VERIFICATION (E-03 & E-06)")
    print("=" * 70)

    client = TestClient(app)

    for tenant_id in TENANTS:
        print(f"\nEvaluating Tenant: {tenant_id}...")
        admin_headers = {"Authorization": "Bearer admin:bob_admin"}
        response = client.post("/analyze", json={"tenant_id": tenant_id}, headers=admin_headers)
        assert response.status_code == 200, f"Failed for {tenant_id}: {response.status_code} - {response.text}"
        
        data = response.json()
        parsed = AnalyzeResponse(**data)

        # ── 1. Check E-03: ml_layer in API response ──
        assert parsed.ml_layer is not None, f"ml_layer is None for {tenant_id}"
        ml = parsed.ml_layer
        assert ml.get("ml_available") is True, f"ml_available is False for {tenant_id}"
        assert "predicted_tier" in ml, f"predicted_tier missing for {tenant_id}"
        assert "probabilities" in ml, f"probabilities missing for {tenant_id}"
        assert "shap_explanation" in ml, f"shap_explanation missing for {tenant_id}"
        
        prob_sum = sum(ml["probabilities"].values())
        assert abs(prob_sum - 100.0) < 1.0 or abs(prob_sum - 1.0) < 0.05, f"Probabilities invalid sum: {prob_sum}"
        
        print(f"  [OK E-03] API response: Deterministic Tier={parsed.risk_tier} (Score={parsed.risk_score}), ML Predicted Tier={ml['predicted_tier']}")

        # ── 2. Check E-06: signal_contribution vs TreeSHAP ──
        for v in parsed.violations:
            exp = v.explanation
            assert hasattr(exp, "total_signal_weight"), "total_signal_weight missing"
            assert exp.total_signal_weight is not None, "total_signal_weight is None"
            for s in exp.signals_analysis:
                assert hasattr(s, "signal_contribution"), "signal_contribution missing"
                assert s.signal_contribution is not None, "signal_contribution is None"
                if s.fired:
                    assert s.signal_contribution > 0, "Fired signal must have positive contribution"

        # ── 3. Check Database Persistence ──
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT result_json, risk_score 
                    FROM evaluation_results 
                    WHERE tenant_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1
                    """,
                    [tenant_id]
                )
                row = cur.fetchone()
                assert row is not None, f"No evaluation_results in DB for {tenant_id}"
                payload = row["result_json"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                assert "ml_layer" in payload, f"ml_layer missing from stored DB payload for {tenant_id}"
                assert payload["ml_layer"]["predicted_tier"] == ml["predicted_tier"]
                print(f"  [OK DB Persistence] Verified database record in evaluation_results with complete ml_layer.")

    print("\n" + "=" * 70)
    print("PHASE 7 VERIFICATION COMPLETE: ALL 5 TENANTS 100% PASSED!")
    print("=" * 70)

if __name__ == "__main__":
    test_phase7_complete()
