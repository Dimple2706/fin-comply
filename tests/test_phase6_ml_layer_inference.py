import os
import sys
import dotenv
from pathlib import Path

dotenv.load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.ml_layer import run_ml_layer, extract_features
from src.agent_layer.orchestrator import run_compliance_analysis

def test_ml_layer_inference():
    print("Testing ML Layer runtime inference with new model artifacts...")

    # 1. Test low-risk report (4 violations)
    low_report = {
        "tenant_id": "LOW-TEST-001",
        "violation_report": [
            {"rule_id": "DPDP-001", "outcome": "VIOLATION", "severity": "LOW", "score": 0.35},
            {"rule_id": "DPDP-004", "outcome": "VIOLATION", "severity": "LOW", "score": 0.30},
        ],
        "risk_insights": {
            "per_rule_contributions": [
                {"rule_id": "DPDP-001", "contribution_percentage": 5.0},
            ],
            "total_penalty_exposure_crore": 250.0,
        }
    }

    low_features = extract_features(low_report)
    assert low_features.shape == (1, 14)
    assert low_features[0, -1] == 250.0

    counted_report = {
        **low_report,
        "total_violations": 25,
        "total_warnings": 7,
    }
    counted_features = extract_features(counted_report)
    assert counted_features[0, 0] == 25.0
    assert counted_features[0, 1] == 7.0

    res_low = run_ml_layer(low_report)
    print(f"  [OK] Low Report ML Prediction: {res_low.get('predicted_tier')}")
    print(f"  [OK] Low Report Probabilities: {res_low.get('probabilities')}")
    assert res_low.get("predicted_tier") in ["COMPLIANT", "LOW"], f"Expected LOW risk, got {res_low.get('predicted_tier')}"

    # 2. Test real QUICKLOAN-001 report (202 violations)
    print("\nRunning ML layer on real QUICKLOAN-001 report...")
    ql_report = run_compliance_analysis("QUICKLOAN-001")
    res_ql = run_ml_layer(ql_report)
    print(f"  [OK] QUICKLOAN-001 ML Prediction: {res_ql.get('predicted_tier')}")
    print(f"  [OK] QUICKLOAN-001 Probabilities: {res_ql.get('probabilities')}")
    print(f"  [OK] QUICKLOAN-001 SHAP Top Drivers: {res_ql.get('shap_explanation', {}).get('top_positive_features')}")
    assert res_ql.get("predicted_tier") in ["MEDIUM", "HIGH", "CRITICAL"], f"Expected MEDIUM/HIGH/CRITICAL for QUICKLOAN-001, got {res_ql.get('predicted_tier')}"
    assert len(res_ql["shap_explanation"]["feature_contributions"]) == 14
    assert len(res_ql["lime_explanation"]["feature_contributions"]) == 10

    # Verify new probability contract fields
    assert res_ql.get("probability_unit") == "percent", "Missing or wrong probability_unit"
    assert res_ql.get("confidence_percent") is not None, "Missing confidence_percent"

    # Verify probability sum ≈ 100
    prob_sum = sum(res_ql["probabilities"].values())
    assert abs(prob_sum - 100.0) <= 1.0, f"Probabilities sum to {prob_sum}, expected ≈100"

    # Verify predicted_tier matches highest probability
    probs = res_ql["probabilities"]
    max_class = max(probs, key=probs.get)
    assert res_ql["predicted_tier"] == max_class, (
        f"predicted_tier={res_ql['predicted_tier']} but highest is {max_class}"
    )

    # Verify confidence_percent matches predicted_tier probability
    assert abs(res_ql["confidence_percent"] - probs[res_ql["predicted_tier"]]) < 0.01

    print(f"  [OK] probability_unit: {res_ql['probability_unit']}")
    print(f"  [OK] confidence_percent: {res_ql['confidence_percent']}")
    print(f"  [OK] Probability sum: {prob_sum:.1f}%")

    print("\n==================================================")
    print("PHASE 6 ML LAYER RUNTIME INFERENCE FULLY VERIFIED!")
    print("==================================================")

if __name__ == "__main__":
    test_ml_layer_inference()
