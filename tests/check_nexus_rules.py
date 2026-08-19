import os
import psycopg
import dotenv
from pathlib import Path
import sys

dotenv.load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_layer.orchestrator import load_active_rule_metadata, get_connection
from src.agent_layer.audit_agent import AuditAgent
from src.agent_layer.policy_agent import PolicyAgent
from src.agent_layer.regulation_agent import RegulationAgent
from src.agent_layer.risk_agent import RiskAgent

def check_rules():
    tenant_id = "NEXUSNEOBANK-005"
    conn = get_connection()
    agents = [
        AuditAgent(),
        PolicyAgent(),
        RegulationAgent(),
        RiskAgent(),
    ]
    try:
        for agent in agents:
            res = agent.run(tenant_id, conn)
            violations = [v for v in res if getattr(v, "outcome", "") == "VIOLATION"]
            print(f"Agent {agent.name}: {len(violations)} violations")
            by_r = {}
            for v in violations:
                by_r.setdefault(v.rule_id, []).append(v)
            for r, vs in by_r.items():
                print(f"  - {r}: {len(vs)} violations. Signals: {vs[0].signals_fired}, reasons: {vs[0].signal_reasons}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_rules()
