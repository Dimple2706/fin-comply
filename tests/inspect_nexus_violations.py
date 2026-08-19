import os
import psycopg
import dotenv
from pathlib import Path
import sys

dotenv.load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_layer.orchestrator import run_compliance_analysis

def inspect_nexus():
    res = run_compliance_analysis("NEXUSNEOBANK-005")
    violations = res.get("violations", [])
    print(f"Total violations for NEXUSNEOBANK-005: {len(violations)}")
    by_rule = {}
    for v in violations:
        by_rule.setdefault(v.get("rule_id"), []).append(v)

    for rid, vs in by_rule.items():
        print(f"  - {rid:10s} ({len(vs)} occurrences): sample reason = {vs[0].get('signal_reasons')}")

if __name__ == "__main__":
    inspect_nexus()
