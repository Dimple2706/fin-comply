"""
tests/test_phase7_subtasks_7_1_7_2.py
======================================
Verifies Subtasks 7.1 and 7.2:
- E-03: ml_layer is exposed in API schema and response builder.
- E-06: signal_contribution and total_signal_weight are explicitly labeled.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_layer.orchestrator import run_compliance_analysis
from src.api.routes import _build_full_response
from src.api.schemas import AnalyzeResponse, SignalDetail, FullExplanation

def test_phase7_subtasks():
    print("Testing Phase 7 Subtasks 7.1 and 7.2...")

    # 1. Run compliance analysis
    tenant_id = "QUICKLOAN-001"
    analysis_result = run_compliance_analysis(tenant_id)
    assert "ml_layer" in analysis_result, "ml_layer missing from orchestrator analysis_result"

    # 2. Build full response
    response_dict = _build_full_response(analysis_result, tenant_name="QuickLoan Test")
    
    # 3. Verify ml_layer is present in response dict (E-03)
    assert "ml_layer" in response_dict, "ml_layer missing from _build_full_response dictionary"
    ml_layer = response_dict["ml_layer"]
    assert ml_layer is not None, "ml_layer is None"
    assert ml_layer.get("ml_available") is True, f"ml_available should be True, got {ml_layer.get('ml_available')}"
    assert "predicted_tier" in ml_layer, "predicted_tier missing from ml_layer"
    assert "probabilities" in ml_layer, "probabilities missing from ml_layer"
    assert "shap_explanation" in ml_layer, "shap_explanation missing from ml_layer"
    print("  [OK] E-03 verified: ml_layer passed through _build_full_response with predictions and SHAP.")

    # 4. Verify Pydantic schema validation (AnalyzeResponse)
    parsed_response = AnalyzeResponse(**response_dict)
    assert parsed_response.ml_layer is not None, "parsed_response.ml_layer is None"
    print("  [OK] E-03 verified: AnalyzeResponse Pydantic model successfully parsed ml_layer.")

    # 5. Verify E-06: signal_contribution and total_signal_weight
    violations = parsed_response.violations
    assert len(violations) > 0, "No violations in parsed response"
    for v in violations:
        exp = v.explanation
        assert hasattr(exp, "total_signal_weight"), "total_signal_weight missing from FullExplanation"
        assert hasattr(exp, "total_shap"), "total_shap alias missing from FullExplanation"
        assert exp.total_signal_weight == exp.total_shap, "total_signal_weight and total_shap mismatch"
        
        for sig in exp.signals_analysis:
            assert hasattr(sig, "signal_contribution"), "signal_contribution missing from SignalDetail"
            assert hasattr(sig, "phi"), "phi alias missing from SignalDetail"
            assert sig.signal_contribution == sig.phi, "signal_contribution and phi mismatch"

    print("  [OK] E-06 verified: Violations explicitly expose signal_contribution and total_signal_weight.")
    print("\nALL CHECKS PASSED FOR SUBTASKS 7.1 & 7.2!")

if __name__ == "__main__":
    test_phase7_subtasks()
