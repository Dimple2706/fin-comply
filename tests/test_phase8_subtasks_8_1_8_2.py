"""
tests/test_phase8_subtasks_8_1_8_2.py
======================================
Verifies Subtasks 8.1 & 8.2:
- Subtask 8.1: SQL Identifier safety & table whitelist enforcement (Issue E-12).
- Subtask 8.2: Run-level audit metadata & model SHA-256 fingerprinting (Issue E-13).
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
from src.agent_layer.orchestrator import ALLOWED_TABLES, _get_model_sha256, run_compliance_analysis
from src.api.schemas import AnalyzeResponse

def test_subtasks_8_1_and_8_2():
    print("=" * 70)
    print("TESTING PHASE 8 SUBTASKS 8.1 & 8.2 (E-12 & E-13)")
    print("=" * 70)

    # ── 1. Check Subtask 8.1: SQL Safety & ALLOWED_TABLES ──
    print("\n[SUBTASK 8.1] Verifying SQL Identifier Safety (E-12)...")
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
    print("  [OK] E-12 verified: Dynamic table queries use safe SQL Identifiers and table whitelist.")

    # ── 2. Check Subtask 8.2: Model SHA-256 Fingerprint ──
    print("\n[SUBTASK 8.2] Verifying Model SHA-256 Fingerprinting & RunMetadata (E-13)...")
    model_sha = _get_model_sha256()
    assert len(model_sha) == 64, f"Invalid SHA-256 hash length: {model_sha}"
    assert re.match(r"^[0-9a-f]{64}$", model_sha), f"SHA-256 is not a valid hex string: {model_sha}"
    print(f"  [OK] Model fingerprint: {model_sha}")

    # ── 3. Test API Endpoint Response ──
    client = TestClient(app)
    tenant_id = "QUICKLOAN-001"
    response = client.post("/analyze", json={"tenant_id": tenant_id})
    assert response.status_code == 200, f"Analysis failed: {response.text}"
    
    data = response.json()
    parsed = AnalyzeResponse(**data)
    assert parsed.run_metadata is not None, "run_metadata is missing from AnalyzeResponse"
    meta = parsed.run_metadata
    assert meta.engine_version == "1.0.0", f"Unexpected engine_version: {meta.engine_version}"
    assert meta.schema_version == "2026.1", f"Unexpected schema_version: {meta.schema_version}"
    assert meta.active_rule_count >= 19, f"Unexpected active_rule_count: {meta.active_rule_count}"
    assert meta.model_sha256 == model_sha, f"Model SHA mismatch: {meta.model_sha256} vs {model_sha}"
    assert meta.evaluated_at is not None, "evaluated_at is None"
    print(f"  [OK] API response returned run_metadata: Engine v{meta.engine_version}, Schema {meta.schema_version}, Rules: {meta.active_rule_count}, Time: {meta.evaluated_at}")

    # ── 4. Test Database Audit Persistence ──
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
            print(f"  [OK] Verified PostgreSQL audit persistence of run_metadata in evaluation_results table.")

    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED FOR SUBTASKS 8.1 & 8.2!")
    print("=" * 70)

if __name__ == "__main__":
    test_subtasks_8_1_and_8_2()
