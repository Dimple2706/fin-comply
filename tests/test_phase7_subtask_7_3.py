"""
tests/test_phase7_subtask_7_3.py
=================================
Verifies Subtask 7.3:
- FastAPI endpoint POST /analyze returns 200 with ml_layer
- PostgreSQL evaluation_results table receives and persists the full ml_layer payload
"""

import sys
import json
from pathlib import Path
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app
from src.api.routes import get_db_connection

def test_api_routes_ml_layer():
    print("Testing Subtask 7.3: API Routes & Response Builder Integration...")
    client = TestClient(app)

    # 1. Test POST /analyze endpoint with existing tenant
    tenant_id = "QUICKLOAN-001"
    response = client.post("/analyze", json={"tenant_id": tenant_id})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    data = response.json()
    assert "ml_layer" in data, "ml_layer missing from API response"
    ml_layer = data["ml_layer"]
    assert ml_layer is not None, "ml_layer is null in API response"
    assert ml_layer["ml_available"] is True, "ml_available is False"
    assert "predicted_tier" in ml_layer, "predicted_tier missing from ml_layer in API response"
    assert "probabilities" in ml_layer, "probabilities missing from ml_layer in API response"
    assert "shap_explanation" in ml_layer, "shap_explanation missing from ml_layer in API response"
    print(f"  [OK] POST /analyze returned 200 with ml_layer (predicted_tier={ml_layer['predicted_tier']}).")

    # 2. Test PostgreSQL evaluation_results persistence
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
            assert row is not None, f"No evaluation_results found for {tenant_id}"
            
            stored_payload = row["result_json"]
            if isinstance(stored_payload, str):
                stored_payload = json.loads(stored_payload)
                
            assert "ml_layer" in stored_payload, "ml_layer missing from stored result_json in DB"
            assert stored_payload["ml_layer"] is not None, "stored ml_layer is null"
            assert "predicted_tier" in stored_payload["ml_layer"], "predicted_tier missing from stored ml_layer"
            assert "shap_explanation" in stored_payload["ml_layer"], "shap_explanation missing from stored ml_layer"
            print("  [OK] Stored evaluation_results in PostgreSQL contains verified ml_layer payload.")

    print("\nALL CHECKS PASSED FOR SUBTASK 7.3!")

if __name__ == "__main__":
    test_api_routes_ml_layer()
