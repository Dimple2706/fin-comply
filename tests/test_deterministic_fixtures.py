import os
import json
import pytest
import hashlib
from pathlib import Path
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

# Credentials configuration
admin_token = "secure_test_admin_token_2026"
test_credentials = {
    hashlib.sha256(admin_token.encode("utf-8")).hexdigest(): {
        "username": "test_admin",
        "role": "admin",
        "authorized_tenants": ["t_clean"] + [f"t_dpdp{i:03d}" for i in range(1, 17)]
    }
}

@pytest.fixture(autouse=True)
def run_schema_ensure():
    old_creds = os.environ.get("FINCOMPLY_TEST_CREDENTIALS")
    os.environ["FINCOMPLY_TEST_CREDENTIALS"] = json.dumps(test_credentials)
    yield
    if old_creds is not None:
        os.environ["FINCOMPLY_TEST_CREDENTIALS"] = old_creds
    else:
        os.environ.pop("FINCOMPLY_TEST_CREDENTIALS", None)

def test_deterministic_compliance_fixtures():
    fixture_root = Path("tests/fixtures/deterministic_compliance_package")
    manifest_path = fixture_root / "expected_results.json"
    
    assert manifest_path.exists(), "Fixtures expected_results.json manifest must exist."
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    for tenant_id, expected in manifest.items():
        tenant_dir = fixture_root / tenant_id
        assert tenant_dir.exists(), f"Tenant directory for {tenant_id} must exist."
        
        # 1. Verify input file hashes against static expected values
        files = {}
        expected_hashes = expected["input_file_hashes"]
        for fname in sorted(os.listdir(tenant_dir)):
            if fname.endswith(".csv"):
                field_name = fname.replace(".csv", "")
                with open(tenant_dir / fname, "rb") as f_in:
                    content = f_in.read()
                    actual_hash = hashlib.sha256(content).hexdigest()
                    assert actual_hash == expected_hashes[fname], (
                        f"Hash mismatch for input file {fname} in tenant {tenant_id}. "
                        f"Expected {expected_hashes[fname]}, got {actual_hash}"
                    )
                    files[field_name] = (fname, content, "text/csv")
                    
        # 2. Upload dataset
        upload_res = client.post(
            "/analyze/upload",
            data={"tenant_id": tenant_id, "tenant_name": tenant_id.upper()},
            files=files,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert upload_res.status_code == 200, f"Upload failed for {tenant_id}: {upload_res.text}"
        
        # 3. First run analysis
        analyze_res_1 = client.post(
            "/analyze",
            json={"tenant_id": tenant_id},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert analyze_res_1.status_code == 200, f"Analysis first run failed for {tenant_id}: {analyze_res_1.text}"
        res_data_1 = analyze_res_1.json()
        
        # 4. Assert ground truth metrics for the first run
        # A. Outcome count by state
        outcome_by_state = expected["outcome_count_by_state"]
        findings_1 = res_data_1.get("findings") or []
        
        # Compute outcome counts per rule
        computed_rule_outcomes = {}
        for r_i in range(1, 17):
            computed_rule_outcomes[f"DPDP-{r_i:03d}"] = "NOT_APPLICABLE"
        for f in findings_1:
            r_id = f.get("rule_id")
            if r_id and r_id.startswith("POLICY-"):
                continue
            outcome = f.get("outcome")
            current = computed_rule_outcomes.get(r_id, "NOT_APPLICABLE")
            order = ["NOT_APPLICABLE", "PASS", "NOT_ASSESSABLE", "WARNING", "VIOLATION", "FAILED"]
            if outcome in order:
                if order.index(outcome) > order.index(current):
                    computed_rule_outcomes[r_id] = outcome
                    
        computed_state_counts = {k: 0 for k in outcome_by_state.keys()}
        for state in computed_rule_outcomes.values():
            if state in computed_state_counts:
                computed_state_counts[state] += 1
                
        for state, exp_count in outcome_by_state.items():
            assert computed_state_counts.get(state, 0) == exp_count, (
                f"Outcome count mismatch for state {state} in tenant {tenant_id}. "
                f"Expected {exp_count}, got {computed_state_counts.get(state, 0)}"
            )
            
        # B. Outcome count by rule
        outcome_by_rule = expected["outcome_count_by_rule"]
        for rule_id, exp_status in outcome_by_rule.items():
            assert computed_rule_outcomes.get(rule_id) == exp_status, (
                f"Outcome mismatch for rule {rule_id} in tenant {tenant_id}. "
                f"Expected {exp_status}, got {computed_rule_outcomes.get(rule_id)}"
            )
            
        # C. Record hashes / identities
        exp_record_hashes = expected["expected_record_hashes_identities"]
        actual_record_hashes = [f["record_id"] for f in findings_1 if f["outcome"] == "VIOLATION" and f.get("record_id")]
        assert sorted(actual_record_hashes) == sorted(exp_record_hashes), (
            f"Record hashes mismatch for tenant {tenant_id}. "
            f"Expected {exp_record_hashes}, got {actual_record_hashes}"
        )
        
        # D. Failed rule count, compliance score, risk score, maximum statutory exposure estimate
        assert res_data_1.get("risk_score") == expected["risk_score"], (
            f"Risk score mismatch for {tenant_id}. "
            f"Expected {expected['risk_score']}, got {res_data_1.get('risk_score')}"
        )
        assert res_data_1.get("total_penalty_exposure_crore") == expected["maximum_statutory_exposure_crore"], (
            f"Statutory exposure mismatch for {tenant_id}. "
            f"Expected {expected['maximum_statutory_exposure_crore']}, got {res_data_1.get('total_penalty_exposure_crore')}"
        )
        
        comp_score_1 = res_data_1.get("compliance_score") or {}
        exp_comp_score = expected["compliance_score"] or {}
        assert comp_score_1.get("score_percentage") == exp_comp_score.get("score_percentage"), (
            f"Compliance score mismatch for {tenant_id}. "
            f"Expected {exp_comp_score.get('score_percentage')}, got {comp_score_1.get('score_percentage')}"
        )
        
        # E. Coverage guard specific to target scenarios vs clean
        violation_rules = {v["rule_id"] for v in res_data_1.get("violations", [])}
        expected_violations = {
            r_id for r_id, state in expected["outcome_count_by_rule"].items()
            if state in ("VIOLATION", "FAILED")
        }
        assert violation_rules == expected_violations, (
            f"Tenant {tenant_id} violated unexpected rules. "
            f"Expected exactly {expected_violations}, but triggered {violation_rules}."
        )
        if tenant_id == "t_clean":
            assert len(res_data_1.get("violations", [])) == 0
            assert expected["failed_rules_count"] == 0
            
        # 5. Repeat-run lineage semantics & stability
        # A. Second run analysis
        analyze_res_2 = client.post(
            "/analyze",
            json={"tenant_id": tenant_id},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert analyze_res_2.status_code == 200
        res_data_2 = analyze_res_2.json()
        
        # B. Assert run IDs are distinct
        run_id_1 = res_data_1.get("audit_run_id")
        run_id_2 = res_data_2.get("audit_run_id")
        assert run_id_1 != run_id_2
        assert run_id_1 is not None and run_id_2 is not None
        
        # C. Assert the second run has the first run as its parent when it is a re-analysis
        # We query the audit run database details for the second run
        from src.api.routes import get_db_connection
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT parent_audit_run_id, status, rule_set_hash, clause_set_hash, input_snapshot_hash "
                    "FROM audit_runs WHERE audit_run_id = %s",
                    (run_id_2,)
                )
                row_2 = cur.fetchone()
                assert row_2 is not None
                db_parent = row_2.get("parent_audit_run_id") if isinstance(row_2, dict) else row_2[0]
                db_status = row_2.get("status") if isinstance(row_2, dict) else row_2[1]
                db_rule_hash = row_2.get("rule_set_hash") if isinstance(row_2, dict) else row_2[2]
                db_clause_hash = row_2.get("clause_set_hash") if isinstance(row_2, dict) else row_2[3]
                db_input_hash = row_2.get("input_snapshot_hash") if isinstance(row_2, dict) else row_2[4]
                
                # Assert status matches completed
                assert db_status == expected["expected_audit_run_status"]
                
                # Assert lineage parent matches the first run id
                assert db_parent == run_id_1
                
                # Fetch first run details to check hash stability
                cur.execute(
                    "SELECT rule_set_hash, clause_set_hash, input_snapshot_hash "
                    "FROM audit_runs WHERE audit_run_id = %s",
                    (run_id_1,)
                )
                row_1 = cur.fetchone()
                assert row_1 is not None
                db_rule_hash_1 = row_1.get("rule_set_hash") if isinstance(row_1, dict) else row_1[0]
                db_clause_hash_1 = row_1.get("clause_set_hash") if isinstance(row_1, dict) else row_1[1]
                db_input_hash_1 = row_1.get("input_snapshot_hash") if isinstance(row_1, dict) else row_1[2]
                
                # Assert input/rule/clause hashes remain stable across both runs
                assert db_rule_hash == db_rule_hash_1
                assert db_clause_hash == db_clause_hash_1
                assert db_input_hash == db_input_hash_1
                
        # D. Assert deterministic result content is identical after excluding run-specific fields
        def clean_payload(d):
            if not isinstance(d, dict):
                return d
            cleaned = dict(d)
            cleaned.pop("audit_run_id", None)
            cleaned.pop("evaluated_at", None)
            cleaned.pop("run_timestamp", None)
            cleaned.pop("parent_audit_run_id", None)
            cleaned.pop("ml_layer", None)
            if "run_metadata" in cleaned:
                cleaned["run_metadata"] = dict(cleaned["run_metadata"])
                cleaned["run_metadata"].pop("evaluated_at", None)
            return cleaned
            
        c1 = clean_payload(res_data_1)
        c2 = clean_payload(res_data_2)
        assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True), (
            f"Non-deterministic result content between run 1 and run 2 for {tenant_id}."
        )
