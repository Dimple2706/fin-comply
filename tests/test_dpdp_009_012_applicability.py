from src.agent_layer.outcome_evaluator import determine_row_outcome
from src.agent_layer.result_state import RuleOutcome


def _outcome(rule_id: str, row: dict):
    return determine_row_outcome(rule_id, row, [], [], 0.5, 0.25)[0]


def test_dpdp009_does_not_require_a_universal_dpo():
    assert _outcome("DPDP-009", {
        "grievance_endpoint_available": True,
        "dpo_assigned": False,
    }) == RuleOutcome.PASS


def test_dpdp009_rejects_missing_grievance_mechanism():
    assert _outcome("DPDP-009", {
        "grievance_endpoint_available": False,
        "dpo_assigned": True,
    }) == RuleOutcome.VIOLATION


def test_dpdp012_is_not_applicable_to_non_sdf_tenant():
    assert _outcome("DPDP-012", {
        "is_significant_data_fiduciary": False,
    }) == RuleOutcome.NOT_APPLICABLE


def test_dpdp012_requires_explicit_sdf_designation():
    assert _outcome("DPDP-012", {
        "is_significant_data_fiduciary": None,
    }) == RuleOutcome.NOT_ASSESSABLE


def test_dpdp012_sdf_without_dpo_is_violation():
    assert _outcome("DPDP-012", {
        "is_significant_data_fiduciary": True,
        "last_audit_date": "2026-08-01",
        "audit_frequency_days": 90,
        "dpo_assigned": False,
    }) == RuleOutcome.VIOLATION
