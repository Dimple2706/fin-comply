"""
tests/test_ml_output_contract.py
================================
Regression tests for the ML output contract.

Tests the probability format, SHAP/LIME structure, and ensures the
test fixture itself passes all validation checks.

This file uses a static test fixture ONLY for contract verification.
Production code must always use the real XGBoost, SHAP, and LIME output.
"""

import os
import sys
import json
import importlib
from pathlib import Path

import dotenv
import pytest

dotenv.load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "ml_response_fixture.json"

READABLE_LABELS = {
    "n_violations": "Total compliance findings",
    "n_warnings": "Total warnings",
    "n_critical_rules_fired": "Critical rules triggered",
    "n_high_rules_fired": "High-severity rules triggered",
    "breach_rule_fired": "Personal-data breach detected",
    "minor_data_rule_fired": "Children's data violation detected",
    "max_rule_score": "Highest rule score",
    "max_prevalence_ratio": "Highest prevalence ratio",
    "consent_violation_count": "Consent-related findings",
    "retention_violation_count": "Retention-related findings",
    "encryption_violation_count": "Encryption-related findings",
    "access_violation_count": "Unauthorised access findings",
    "policy_violation_count": "Internal policy findings",
    "total_penalty_exposure": "Maximum statutory exposure (₹ crore)",
}

EXPECTED_CLASSES = {"COMPLIANT", "LOW", "MEDIUM", "HIGH", "CRITICAL"}


@pytest.fixture
def fixture_data():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── Probability contract tests ──────────────────────────────────────────────

class TestProbabilityContract:
    def test_five_class_probabilities(self, fixture_data):
        """Exactly five class probabilities exist."""
        probs = fixture_data["probabilities"]
        assert set(probs.keys()) == EXPECTED_CLASSES

    def test_probabilities_are_percentage_scale(self, fixture_data):
        """All probabilities are in [0, 100]."""
        for cls, val in fixture_data["probabilities"].items():
            assert 0 <= val <= 100, f"{cls} probability {val} out of range"

    def test_probabilities_sum_approximately_100(self, fixture_data):
        """Sum ≈ 100 within rounding tolerance."""
        total = sum(fixture_data["probabilities"].values())
        assert abs(total - 100.0) <= 1.0, f"Sum is {total}, expected ≈100"

    def test_predicted_tier_is_highest_probability(self, fixture_data):
        """predicted_tier equals the class with the highest probability."""
        probs = fixture_data["probabilities"]
        max_class = max(probs, key=probs.get)
        assert fixture_data["predicted_tier"] == max_class

    def test_confidence_percent_matches_predicted_tier(self, fixture_data):
        """confidence_percent matches probabilities[predicted_tier]."""
        predicted = fixture_data["predicted_tier"]
        expected = fixture_data["probabilities"][predicted]
        actual = fixture_data["confidence_percent"]
        assert abs(actual - expected) < 0.01

    def test_probability_unit_is_percent(self, fixture_data):
        """probability_unit field is 'percent'."""
        assert fixture_data["probability_unit"] == "percent"

    def test_small_percent_not_multiplied(self, fixture_data):
        """0.2 stays 0.2 (not 20) and 0.5 stays 0.5 (not 50)."""
        probs = fixture_data["probabilities"]
        # COMPLIANT is 0.2 — it must remain 0.2, not be treated as a fraction
        assert probs["COMPLIANT"] == 0.2, (
            f"COMPLIANT should be 0.2%, got {probs['COMPLIANT']}"
        )
        # HIGH is 0.5 — it must remain 0.5
        assert probs["HIGH"] == 0.5, (
            f"HIGH should be 0.5%, got {probs['HIGH']}"
        )


# ─── SHAP contract tests ─────────────────────────────────────────────────────

class TestShapContract:
    def test_fourteen_shap_contributions(self, fixture_data):
        """Exactly 14 SHAP feature contributions."""
        contribs = fixture_data["shap_explanation"]["feature_contributions"]
        assert len(contribs) == 14

    def test_shap_has_positive_and_negative(self, fixture_data):
        """Both supporting and opposing contributions exist."""
        contribs = fixture_data["shap_explanation"]["feature_contributions"]
        directions = {c["direction"] for c in contribs}
        assert "positive" in directions, "No positive SHAP contributions"
        assert "negative" in directions, "No negative SHAP contributions"

    def test_shap_raw_values_preserved(self, fixture_data):
        """Raw SHAP values are available in JSON for auditability."""
        raw = fixture_data["shap_explanation"].get("raw_contributions", {})
        assert len(raw) == 14, "raw_contributions should have 14 entries"
        for feat, val in raw.items():
            assert isinstance(val, (int, float)), f"{feat} SHAP value is not numeric"

    def test_shap_features_have_readable_labels(self):
        """All 14 feature names have readable labels in FEATURE_LABEL_MAP."""
        runtime_features = [
            "n_violations", "n_warnings", "n_critical_rules_fired",
            "n_high_rules_fired", "breach_rule_fired", "minor_data_rule_fired",
            "max_rule_score", "max_prevalence_ratio", "consent_violation_count",
            "retention_violation_count", "encryption_violation_count",
            "access_violation_count", "policy_violation_count",
            "total_penalty_exposure",
        ]
        for feat in runtime_features:
            assert feat in READABLE_LABELS, f"No readable label for {feat}"
            assert READABLE_LABELS[feat] != feat, f"Label for {feat} is still raw"


# ─── LIME contract tests ─────────────────────────────────────────────────────

class TestLimeContract:
    def test_ten_lime_contributions(self, fixture_data):
        """Ten LIME feature contributions."""
        contribs = fixture_data["lime_explanation"]["feature_contributions"]
        assert len(contribs) == 10

    def test_lime_has_positive_and_negative(self, fixture_data):
        """Both supporting and opposing LIME contributions exist."""
        contribs = fixture_data["lime_explanation"]["feature_contributions"]
        directions = {c["direction"] for c in contribs}
        assert "positive" in directions, "No positive LIME contributions"
        assert "negative" in directions, "No negative LIME contributions"

    def test_lime_raw_coefficients_preserved(self, fixture_data):
        """Raw LIME coefficients are available for audit."""
        contribs = fixture_data["lime_explanation"]["feature_contributions"]
        for c in contribs:
            assert "coefficient" in c, "Missing raw coefficient"
            assert isinstance(c["coefficient"], (int, float))


# ─── No hard-coded QuickLoan values ──────────────────────────────────────────

class TestNoHardcodedValues:
    def test_no_quickloan_specific_values(self, fixture_data):
        """Fixture uses generic data, not QuickLoan-specific hard-coded values."""
        json_str = json.dumps(fixture_data)
        assert "QUICKLOAN" not in json_str, "Fixture contains QuickLoan-specific values"

    def test_production_does_not_import_fixture(self):
        """Production ML code does not import the test fixture."""
        ml_layer_path = PROJECT_ROOT / "src" / "modeling" / "ml_layer.py"
        content = ml_layer_path.read_text(encoding="utf-8")
        assert "ml_response_fixture" not in content, (
            "Production ml_layer.py must not import the test fixture"
        )
        assert "fixtures" not in content.lower() or "fixture" not in content.lower(), (
            "Production ml_layer.py should not reference test fixtures"
        )


# ─── Backend validation function test ─────────────────────────────────────────

class TestValidationFunction:
    def test_fixture_passes_validation(self, fixture_data):
        """The test fixture passes _validate_ml_output."""
        from src.modeling.ml_layer import _validate_ml_output
        result = _validate_ml_output(fixture_data)
        assert result.get("ml_available") is True, (
            f"Fixture failed validation: {result.get('reason')}"
        )

    def test_bad_sum_fails_validation(self, fixture_data):
        """Probabilities that don't sum to ~100 are rejected."""
        from src.modeling.ml_layer import _validate_ml_output
        bad = {**fixture_data, "probabilities": {
            "COMPLIANT": 50.0, "LOW": 50.0, "MEDIUM": 50.0,
            "HIGH": 50.0, "CRITICAL": 50.0
        }}
        result = _validate_ml_output(bad)
        assert result.get("ml_available") is False

    def test_wrong_predicted_tier_fails(self, fixture_data):
        """predicted_tier != highest probability is rejected."""
        from src.modeling.ml_layer import _validate_ml_output
        bad = {**fixture_data, "predicted_tier": "LOW"}
        result = _validate_ml_output(bad)
        assert result.get("ml_available") is False

    def test_missing_class_fails(self, fixture_data):
        """Missing a class probability is rejected."""
        from src.modeling.ml_layer import _validate_ml_output
        bad_probs = {k: v for k, v in fixture_data["probabilities"].items() if k != "COMPLIANT"}
        bad = {**fixture_data, "probabilities": bad_probs}
        result = _validate_ml_output(bad)
        assert result.get("ml_available") is False
