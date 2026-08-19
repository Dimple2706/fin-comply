import os
import psycopg
import dotenv
from pathlib import Path
import sys

dotenv.load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_layer.orchestrator import load_active_rule_metadata, compute_risk_score, run_compliance_analysis
from src.agent_layer.violation_record import ViolationRecord

def test_severity_floor():
    print("Testing Subtask 5.2 (E-01b) Severity Floor Policy...")
    rule_metadata = load_active_rule_metadata()

    # 1. Test synthetic single CRITICAL violation
    # Under standard weighting, a single rule might have raw score ~1.1 out of 19 max possible -> ~6.0% (LOW)
    # The floor must clamp it to at least 65.0 (HIGH)
    crit_violation = ViolationRecord(
        rule_id="DPDP-005",
        rule_name="Processing of Minor Personal Data Without Parental Consent",
        dpdp_section="Section 9(1)",
        agent_name="ConsentAuditorAgent",
        tenant_id="TEST-TENANT",
        record_id="cust_001",
        outcome="VIOLATION",
        rule_score=1.0,
        signals_fired=["S1", "S2"],
        signal_reasons=["Minor without verified guardian consent"],
        severity="CRITICAL",
        risk_weight=1.0,
        penalty_exposure_crore=200,
        violation_threshold=0.5,
        risk_threshold=0.25,
        fields_triggered=["is_minor", "guardian_consent_id"]
    )

    score, tier, contribs = compute_risk_score([crit_violation], "QUICKLOAN-001", rule_metadata)
    print(f"  [OK] Synthetic Single CRITICAL violation score = {score}, tier = {tier}")
    assert score >= 65.0, f"Expected CRITICAL violation score to be >= 65.0, got {score}"
    assert tier in ("HIGH", "CRITICAL"), f"Expected HIGH/CRITICAL tier, got {tier}"

    # 2. Test 3 HIGH violations
    high_violations = [
        ViolationRecord(
            rule_id=f"HIGH-RULE-{i}",
            rule_name="High Risk Check",
            dpdp_section="Section 8",
            agent_name="SecurityAgent",
            tenant_id="TEST-TENANT",
            record_id=f"rec_{i}",
            outcome="VIOLATION",
            rule_score=0.8,
            signals_fired=["S1"],
            signal_reasons=["High reason"],
            severity="HIGH",
            risk_weight=0.8,
            penalty_exposure_crore=50,
            violation_threshold=0.5,
            risk_threshold=0.25,
            fields_triggered=[]
        )
        for i in range(3)
    ]
    # Add dummy high rules to metadata for calculation
    dummy_meta = dict(rule_metadata)
    for i in range(3):
        dummy_meta[f"HIGH-RULE-{i}"] = {"risk_weight": 0.8, "primary_table": "transaction_events"}

    score_h, tier_h, _ = compute_risk_score(high_violations, "QUICKLOAN-001", dummy_meta)
    print(f"  [OK] Synthetic 3 HIGH violations score = {score_h}, tier = {tier_h}")
    assert score_h >= 45.0, f"Expected 3 HIGH violations score to be >= 45.0, got {score_h}"
    assert tier_h in ("MEDIUM", "HIGH", "CRITICAL"), f"Expected at least MEDIUM tier, got {tier_h}"

    # 3. Test empty violations (compliant)
    score_zero, tier_zero, _ = compute_risk_score([], "NEXUSNEOBANK-005", rule_metadata)
    print(f"  [OK] Zero violations score = {score_zero}, tier = {tier_zero}")
    assert score_zero == 0.0, f"Expected 0.0 for zero violations, got {score_zero}"
    assert tier_zero == "COMPLIANT", f"Expected COMPLIANT tier, got {tier_zero}"

    # 4. Test real QUICKLOAN-001 compliance orchestration
    print("\nRunning compliance orchestration on real QUICKLOAN-001...")
    result_ql = run_compliance_analysis("QUICKLOAN-001")
    ql_score = result_ql.get("risk_score")
    ql_tier = result_ql.get("risk_tier")
    print(f"  [OK] QUICKLOAN-001 Risk Score: {ql_score}, Tier: {ql_tier}")
    # QUICKLOAN-001 triggers DPDP-005 (CRITICAL) among others -> must be >= 65.0
    assert ql_score >= 65.0, f"Expected QUICKLOAN-001 score >= 65.0 due to CRITICAL findings, got {ql_score}"
    assert ql_tier in ("HIGH", "CRITICAL"), f"Expected HIGH or CRITICAL tier for QUICKLOAN-001, got {ql_tier}"

    print("\n==================================================")
    print("SUBTASK 5.2 (E-01b) VERIFICATION SUCCESSFUL!")
    print("==================================================")

if __name__ == "__main__":
    test_severity_floor()
