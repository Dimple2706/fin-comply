from src.agent_layer.outcome_evaluator import determine_row_outcome
from src.agent_layer.result_state import RuleOutcome


def evaluate(row):
    return determine_row_outcome(
        "DPDP-008",
        row,
        [],
        [],
        v_threshold=0.5,
        r_threshold=0.3,
    )


def test_unencrypted_data_violates_even_without_breach():
    outcome, _ = evaluate(
        {"pii_encrypted": False, "encryption_type": "none", "breach_detected": False}
    )
    assert outcome == RuleOutcome.VIOLATION


def test_encrypted_data_passes_without_breach():
    outcome, _ = evaluate(
        {"pii_encrypted": True, "encryption_type": "AES-256", "breach_detected": False}
    )
    assert outcome == RuleOutcome.PASS


def test_missing_encryption_evidence_is_not_assessable():
    outcome, _ = evaluate({"pii_encrypted": None, "encryption_type": None})
    assert outcome == RuleOutcome.NOT_ASSESSABLE


def test_weak_algorithm_is_a_violation():
    outcome, _ = evaluate({"pii_encrypted": True, "encryption_type": "sha1"})
    assert outcome == RuleOutcome.VIOLATION
