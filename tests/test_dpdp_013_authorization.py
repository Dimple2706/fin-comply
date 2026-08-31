from src.agent_layer.outcome_evaluator import determine_row_outcome
from src.agent_layer.result_state import RuleOutcome


def _outcome(row: dict):
    return determine_row_outcome("DPDP-013", row, [], [], 0.5, 0.25)[0]


def test_role_name_does_not_decide_authorization():
    assert _outcome({
        "employee_role": "collections_agent",
        "accessed_pii": True,
        "access_authorized": True,
        "access_outcome": "granted",
    }) == RuleOutcome.PASS


def test_explicit_unauthorized_pii_access_is_violation():
    assert _outcome({
        "employee_role": "manager",
        "accessed_pii": True,
        "access_authorized": False,
        "access_outcome": "granted",
    }) == RuleOutcome.VIOLATION


def test_missing_authorization_evidence_is_not_assessable():
    assert _outcome({
        "accessed_pii": True,
        "access_authorized": None,
    }) == RuleOutcome.NOT_ASSESSABLE
