import abc
import psycopg
from typing import List, Dict
from .violation_record import ViolationRecord

class BaseAgent(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """
        Agent name (e.g. regulation_agent).
        """
        pass

    @property
    @abc.abstractmethod
    def assigned_rules(self) -> List[str]:
        """
        Assigned DPDP rules.
        """
        pass

    @abc.abstractmethod
    def _execute(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        Implementation-specific logic.
        """
        pass

    def run(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        try:
            return self._execute(tenant_id, conn)
        except Exception as e:
            print(f"Error in {self.name} for tenant {tenant_id}: {e}")
            return []

    def _compute_rule_score(self, signals_fired: List[str], signal_weights: Dict[str, float]) -> float:
        total = sum(signal_weights[s] for s in signals_fired)
        return round(total, 4)

    def _classify_outcome(self, score: float, v_threshold: float, r_threshold: float) -> str:
        if score >= v_threshold:
            return "VIOLATION"
        if score >= r_threshold:
            return "WARNING"
        return "PASS"

    def _make_record(
        self, rule_id: str, rule_name: str, dpdp_section: str,
        tenant_id: str, record_id: str, outcome: str,
        rule_score: float, signals_fired: List[str], signal_reasons: List[str],
        severity: str, risk_weight: float,
        penalty_crore: int, v_thresh: float, r_thresh: float
    ) -> ViolationRecord:
        return ViolationRecord(
            rule_id=rule_id,
            rule_name=rule_name,
            dpdp_section=dpdp_section,
            agent_name=self.name,
            tenant_id=tenant_id,
            record_id=record_id,
            outcome=outcome,
            rule_score=rule_score,
            signals_fired=signals_fired,
            signal_reasons=signal_reasons,
            severity=severity,
            risk_weight=risk_weight,
            penalty_exposure_crore=penalty_crore,
            violation_threshold=v_thresh,
            risk_threshold=r_thresh
        )
