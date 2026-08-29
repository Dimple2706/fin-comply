import psycopg
from typing import List
from .base_agent import BaseAgent
from .violation_record import ViolationRecord


class PolicyAgent(BaseAgent):
    name = "policy_agent"
    assigned_rules = ["POLICY-001", "POLICY-002", "POLICY-003"]

    def _execute(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        return self._execute_rules(tenant_id, conn)

