import psycopg
from typing import List
from .base_agent import BaseAgent
from .violation_record import ViolationRecord

class RiskAgent(BaseAgent):
    name = "risk_agent"
    assigned_rules = ["DPDP-006", "DPDP-008", "DPDP-010", "DPDP-012", "DPDP-014", "DPDP-015", "DPDP-016"]

    def _execute(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        return self._execute_rules(tenant_id, conn)