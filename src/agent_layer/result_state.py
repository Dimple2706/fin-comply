from enum import Enum

class RuleOutcome(str, Enum):
    PASS = "PASS"
    VIOLATION = "VIOLATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"
