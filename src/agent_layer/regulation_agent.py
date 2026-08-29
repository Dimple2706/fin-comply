import psycopg
from typing import List
from .base_agent import BaseAgent
from .violation_record import ViolationRecord

class RegulationAgent(BaseAgent):
    name = "regulation_agent"
    assigned_rules = ["DPDP-001", "DPDP-002", "DPDP-004", "DPDP-005", "DPDP-007"]

    def _execute(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        return self._execute_rules(tenant_id, conn)