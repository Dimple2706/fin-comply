import os
import psycopg
import dotenv
from pathlib import Path
import sys

dotenv.load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_layer.orchestrator import run_compliance_analysis
from src.api.routes import _build_full_response

def test_phase4():
    tenant_id = "QUICKLOAN-001"
    print(f"Running compliance orchestration for {tenant_id}...")

    result = run_compliance_analysis(tenant_id)
    violations = result.get("violations", [])
    print(f"  [OK] Total violations returned: {len(violations)}")

    # Check ViolationRecord dicts have fields_triggered populated
    rules_with_fields = 0
    sample_fields = {}
    for v in violations:
        ft = v.get("fields_triggered", [])
        if ft:
            rules_with_fields += 1
            sample_fields[v["rule_id"]] = ft

    print(f"  [OK] Violations with populated fields_triggered: {rules_with_fields}/{len(violations)}")
    print("  Sample fields triggered per rule:")
    for rid, fields in list(sample_fields.items())[:5]:
        print(f"    - {rid}: {fields}")

    assert rules_with_fields > 0, "Expected fields_triggered to be populated dynamically!"

    # Check API response builder
    print("\nTesting API response builder (_build_full_response)...")
    full_resp = _build_full_response(result, "QuickLoan Instant Credits")
    violation_items = full_resp.get("violations", [])
    print(f"  [OK] Full response violation items count: {len(violation_items)}")

    populated_api_items = 0
    for item in violation_items:
        ft = item.fields_triggered if hasattr(item, "fields_triggered") else item.get("fields_triggered", [])
        rid = item.rule_id if hasattr(item, "rule_id") else item.get("rule_id")
        if ft:
            populated_api_items += 1
            print(f"    - ViolationItem {rid} fields_triggered: {ft}")

    print(f"  [OK] Violation items with populated fields_triggered: {populated_api_items}/{len(violation_items)}")
    assert populated_api_items > 0, "Expected ViolationItem.fields_triggered to be non-empty!"

    print("\n==================================================")
    print("PHASE 4 (E-11) VERIFICATION SUCCESSFUL!")
    print("==================================================")

if __name__ == "__main__":
    test_phase4()
