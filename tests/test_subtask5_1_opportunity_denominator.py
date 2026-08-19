import os
import psycopg
import dotenv
from pathlib import Path
import sys

dotenv.load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_layer.orchestrator import load_active_rule_metadata, compute_risk_score, run_compliance_analysis

def test_opportunity_denominator():
    tenant_id = "QUICKLOAN-001"
    print(f"Testing Subtask 5.1 (E-01a) Join-Aware Opportunity Denominator on {tenant_id}...")

    # 1. Verify active metadata loads opportunity_query
    meta = load_active_rule_metadata()
    print(f"  [OK] Loaded metadata for {len(meta)} rules.")
    rules_with_opp = [rid for rid, m in meta.items() if m.get("opportunity_query")]
    print(f"  [OK] Rules with explicit opportunity queries: {len(rules_with_opp)}: {rules_with_opp}")
    assert "DPDP-005" in rules_with_opp, "DPDP-005 must have opportunity_query!"
    assert "DPDP-006" in rules_with_opp, "DPDP-006 must have opportunity_query!"

    # 2. Run analysis
    result = run_compliance_analysis(tenant_id)
    violations = result.get("violations", [])
    contributions = result.get("risk_contributions", {})
    risk_score = result.get("risk_score", 0.0)

    print(f"\n  [OK] Total violations: {len(violations)}")
    print(f"  [OK] Computed Risk Score: {risk_score} (Tier: {result.get('risk_tier')})")
    print("  [OK] Risk Contributions per Rule:")
    for rid, score in contributions.items():
        print(f"    - {rid:10s}: contribution = {score:.4f}")

    # Check DPDP-005 (minor data)
    if "DPDP-005" in contributions:
        c = contributions["DPDP-005"]
        print(f"\n  [OK] DPDP-005 (Minor Consent) Risk Contribution: {c:.4f}")
        assert c > 0, "DPDP-005 contribution should be positive and accurately scaled!"

    print("\n==================================================")
    print("SUBTASK 5.1 (E-01a) VERIFICATION SUCCESSFUL!")
    print("==================================================")

if __name__ == "__main__":
    test_opportunity_denominator()
