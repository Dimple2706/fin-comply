from dataclasses import dataclass
from typing import List

@dataclass
class ViolationRecord:
    rule_id: str
    rule_name: str
    dpdp_section: str
    agent_name: str        
    tenant_id: str
    record_id: str
    outcome: str           
    rule_score: float
    signals_fired: List[str]   
    signal_reasons: List[str]  
    severity: str          
    risk_weight: float
    penalty_exposure_crore: int
    violation_threshold: float
    risk_threshold: float

    def to_dict(self) -> dict:
        """
        Returns all fields as JSON-serializable dict.
        Converts all floats to round(v, 4) for clean output.
        """
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "dpdp_section": self.dpdp_section,
            "agent_name": self.agent_name,
            "tenant_id": self.tenant_id,
            "record_id": self.record_id,
            "outcome": self.outcome,
            "rule_score": round(self.rule_score, 4),
            "signals_fired": self.signals_fired,
            "signal_reasons": self.signal_reasons,
            "severity": self.severity,
            "risk_weight": round(self.risk_weight, 4),
            "penalty_exposure_crore": self.penalty_exposure_crore,
            "violation_threshold": round(self.violation_threshold, 4),
            "risk_threshold": round(self.risk_threshold, 4),
        }
