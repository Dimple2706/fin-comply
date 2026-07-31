import json
import psycopg
from src.agent_layer.db_connection import get_connection

def check_profiles():
    target_tenants = ['GEN-251', 'GEN-266', 'GEN-267']
    with get_connection() as conn:
        with conn.cursor() as cur:
            for t in target_tenants:
                cur.execute("SELECT risk_score, result_json FROM evaluation_results WHERE tenant_id = %s", (t,))
                row = cur.fetchone()
                if row:
                    data = json.loads(row[1])
                    exposure = data.get("total_penalty_exposure", 0)
                    tier = data.get("risk_tier", "UNKNOWN")
                    rules = list(data.get("risk_contributions", {}).keys())
                    print(f"{t} | Exposure: {exposure} | Label: {tier} | Rules: {','.join(rules)}")

if __name__ == "__main__":
    check_profiles()
