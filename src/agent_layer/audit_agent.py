import psycopg
from typing import List
from .base_agent import BaseAgent
from .violation_record import ViolationRecord

class AuditAgent(BaseAgent):
    name = "audit_agent"
    assigned_rules = ["DPDP-003", "DPDP-009", "DPDP-011", "DPDP-013"]

    def _execute(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        from .rule_loader import load_rules
        records = []
        rules = load_rules(self.name, conn)
        for rule in rules:
            records.extend(self._run_rule_dynamic(rule, tenant_id, conn))
        return records