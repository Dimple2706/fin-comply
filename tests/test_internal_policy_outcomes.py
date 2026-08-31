from src.agent_layer.outcome_evaluator import determine_row_outcome
from src.agent_layer.query_builder import build_query
from src.agent_layer.result_state import RuleOutcome


def evaluate(rule_id, row):
    return determine_row_outcome(rule_id, row, [], [], 0.5, 0.3)[0]


def test_retention_policy_has_no_invented_730_day_limit():
    row = {
        "policy_type": "retention",
        "is_active": True,
        "policy_value_numeric": 1095,
    }
    assert evaluate("POLICY-001", row) == RuleOutcome.PASS


def test_policy_rules_require_their_own_policy_type():
    sql, params = build_query({"rule_id": "POLICY-002"}, "TENANT-A")
    assert "policy_type = 'encryption'" in sql
    assert params == ["TENANT-A"]


def test_missing_policy_text_is_not_assessable():
    row = {"policy_type": "encryption", "is_active": True, "policy_value_text": None}
    assert evaluate("POLICY-002", row) == RuleOutcome.NOT_ASSESSABLE


def test_weak_encryption_policy_is_internal_violation():
    row = {"policy_type": "encryption", "is_active": True, "policy_value_text": "sha1"}
    assert evaluate("POLICY-002", row) == RuleOutcome.VIOLATION


def test_affirmative_consent_policy_passes():
    row = {"policy_type": "consent", "is_active": True, "policy_value_text": "explicit"}
    assert evaluate("POLICY-003", row) == RuleOutcome.PASS
