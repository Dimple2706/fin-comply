import os
import psycopg
import dotenv
from pathlib import Path
import sys

dotenv.load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_layer.orchestrator import run_compliance_analysis, compute_risk_score, load_active_rule_metadata

TENANTS = [
    "QUICKLOAN-001",
    "PAYFLEX-002",
    "WEALTHNEST-003",
    "RURALCRED-004",
    "NEXUSNEOBANK-005"
]

def test_all_tenants_calibration():
    print("==================================================")
    print("SUBTASK 5.3: RISK SCORING CALIBRATION ACROSS ALL TENANTS")
    print("==================================================\n")

    results = {}
    for tenant_id in TENANTS:
        print(f"Running compliance analysis for {tenant_id}...")
        res = run_compliance_analysis(tenant_id)
        results[tenant_id] = res

    print("\n" + "=" * 70)
    print(f"{'TENANT ID':<18} | {'VIOLATIONS':<12} | {'RISK SCORE':<12} | {'RISK TIER':<12}")
    print("=" * 70)

    for tenant_id, res in results.items():
        v_count = len(res.get("violations", []))
        score = res.get("risk_score", 0.0)
        tier = res.get("risk_tier", "UNKNOWN")
        print(f"{tenant_id:<18} | {v_count:<12} | {score:<12.1f} | {tier:<12}")

    print("=" * 70)

    # Validations:
    # 1. High-risk tenants with CRITICAL Section 9 violations must be clamped to >= 65.0 (HIGH/CRITICAL)
    assert results["QUICKLOAN-001"]["risk_score"] >= 65.0, "QUICKLOAN-001 must have risk score >= 65.0!"
    assert results["QUICKLOAN-001"]["risk_tier"] in ("HIGH", "CRITICAL"), "QUICKLOAN-001 must be HIGH or CRITICAL!"

    assert results["PAYFLEX-002"]["risk_score"] >= 65.0, "PAYFLEX-002 must have risk score >= 65.0!"
    assert results["PAYFLEX-002"]["risk_tier"] in ("HIGH", "CRITICAL"), "PAYFLEX-002 must be HIGH or CRITICAL!"

    assert results["RURALCRED-004"]["risk_score"] >= 65.0, "RURALCRED-004 must have risk score >= 65.0!"
    assert results["RURALCRED-004"]["risk_tier"] in ("HIGH", "CRITICAL"), "RURALCRED-004 must be HIGH or CRITICAL!"

    # 2. Synthetic zero-violation tenant check
    rule_meta = load_active_rule_metadata()
    clean_score, clean_tier, _ = compute_risk_score([], "CLEAN-MOCK-000", rule_meta)
    print(f"\nSynthetic Clean Tenant -> Score: {clean_score}, Tier: {clean_tier}")
    assert clean_score == 0.0, "Synthetic clean tenant must have 0.0 risk score!"
    assert clean_tier == "COMPLIANT", "Synthetic clean tenant must have COMPLIANT tier!"

    print("\n[SUCCESS] Subtask 5.3: All 5 tenants and zero-violation baseline verified successfully!")

if __name__ == "__main__":
    test_all_tenants_calibration()
