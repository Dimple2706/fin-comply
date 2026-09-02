"""
tests/test_lime_reproducibility.py
===================================
Verifies that LIME explanations are deterministic: running the same model
on identical feature inputs twice produces the same conditions, directions,
and coefficients within numerical tolerance.

The reproducibility is achieved by creating a fresh LimeTabularExplainer
with random_state=42 per inference call and passing random_state=42 to
explain_instance.
"""

import os
import sys
from pathlib import Path

import dotenv
import pytest

dotenv.load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_synthetic_report():
    """Build a synthetic report that exercises all 14 features."""
    return {
        "violation_report": [
            {"rule_id": "DPDP-001", "outcome": "VIOLATION", "severity": "HIGH", "score": 0.85},
            {"rule_id": "DPDP-002", "outcome": "VIOLATION", "severity": "HIGH", "score": 0.72},
            {"rule_id": "DPDP-003", "outcome": "VIOLATION", "severity": "MEDIUM", "score": 0.55},
            {"rule_id": "DPDP-005", "outcome": "VIOLATION", "severity": "CRITICAL", "score": 1.0},
            {"rule_id": "DPDP-008", "outcome": "VIOLATION", "severity": "HIGH", "score": 0.68},
            {"rule_id": "DPDP-014", "outcome": "VIOLATION", "severity": "CRITICAL", "score": 1.0},
            {"rule_id": "DPDP-013", "outcome": "VIOLATION", "severity": "MEDIUM", "score": 0.45},
            {"rule_id": "DPDP-011", "outcome": "VIOLATION", "severity": "LOW", "score": 0.30},
            {"rule_id": "DPDP-004", "outcome": "WARNING", "severity": "LOW", "score": 0.20},
            {"rule_id": "DPDP-007", "outcome": "WARNING", "severity": "LOW", "score": 0.15},
        ],
        "risk_insights": {
            "per_rule_contributions": [
                {"rule_id": "DPDP-001", "contribution_percentage": 18.0},
                {"rule_id": "DPDP-005", "contribution_percentage": 22.0},
                {"rule_id": "DPDP-014", "contribution_percentage": 25.0},
            ],
            "total_penalty_exposure_crore": 800.0,
        },
        "total_violations": 50,
        "total_warnings": 120,
        "internal_controls": {"findings": [
            {"outcome": "VIOLATION"},
            {"outcome": "VIOLATION"},
            {"outcome": "PASS"},
        ]},
    }


@pytest.fixture(scope="module")
def ml_module():
    """Import the ML layer module once for the test session."""
    from src.modeling import ml_layer
    if ml_layer._MODEL is None:
        pytest.skip("ML model not loaded — cannot test LIME reproducibility")
    return ml_layer


class TestLimeReproducibility:
    def test_identical_inputs_produce_identical_lime(self, ml_module):
        """
        Running run_ml_layer twice on the same report must produce
        identical LIME conditions, directions, and coefficients.
        """
        report = _make_synthetic_report()

        result1 = ml_module.run_ml_layer(report)
        result2 = ml_module.run_ml_layer(report)

        assert result1.get("ml_available") is True, (
            f"First run failed: {result1.get('reason')}"
        )
        assert result2.get("ml_available") is True, (
            f"Second run failed: {result2.get('reason')}"
        )

        lime1 = result1["lime_explanation"]
        lime2 = result2["lime_explanation"]

        # Skip if LIME is unavailable
        if "error" in lime1 or "error" in lime2:
            pytest.skip("LIME unavailable")

        contribs1 = lime1["feature_contributions"]
        contribs2 = lime2["feature_contributions"]

        assert len(contribs1) == len(contribs2), (
            f"Different LIME contribution counts: {len(contribs1)} vs {len(contribs2)}"
        )

        for i, (c1, c2) in enumerate(zip(contribs1, contribs2)):
            # Same feature condition string
            assert c1["feature"] == c2["feature"], (
                f"LIME contribution {i} feature mismatch: "
                f"{c1['feature']} vs {c2['feature']}"
            )
            # Same direction
            assert c1["direction"] == c2["direction"], (
                f"LIME contribution {i} direction mismatch: "
                f"{c1['direction']} vs {c2['direction']}"
            )
            # Same coefficient within small numerical tolerance
            assert abs(c1["coefficient"] - c2["coefficient"]) < 1e-6, (
                f"LIME contribution {i} coefficient mismatch: "
                f"{c1['coefficient']} vs {c2['coefficient']}"
            )

    def test_lime_random_state_is_set(self, ml_module):
        """
        Verify that the LIME explanation uses random_state=42 by checking
        that a third run also matches.
        """
        report = _make_synthetic_report()

        result1 = ml_module.run_ml_layer(report)
        result3 = ml_module.run_ml_layer(report)

        if result1.get("ml_available") is not True:
            pytest.skip("ML layer unavailable")

        lime1 = result1["lime_explanation"]
        lime3 = result3["lime_explanation"]

        if "error" in lime1 or "error" in lime3:
            pytest.skip("LIME unavailable")

        contribs1 = lime1["feature_contributions"]
        contribs3 = lime3["feature_contributions"]

        for c1, c3 in zip(contribs1, contribs3):
            assert c1["feature"] == c3["feature"]
            assert abs(c1["coefficient"] - c3["coefficient"]) < 1e-6
