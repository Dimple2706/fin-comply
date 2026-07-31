import sys
import json
import psycopg
from src.agent_layer.db_connection import get_connection
from src.agent_layer.orchestrator import run_compliance_analysis

def reset_and_evaluate():
    print("[1] Clearing existing evaluation_results...")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE evaluation_results RESTART IDENTITY")
        conn.commit()

    print("[2] Re-evaluating 250 profiles with fixed rule thresholds...")
    with get_connection() as conn:
        for i in range(1, 251):
            tenant_id = f"GEN-{i:03d}"
            print(f"  -> Evaluating {tenant_id}")
            result = run_compliance_analysis(tenant_id)
            risk_score = result.get("risk_score", 0)
            
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evaluation_results
                        (tenant_id, result_json, risk_score, created_at)
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (
                        tenant_id,
                        json.dumps(result, default=str),
                        risk_score,
                    ),
                )
            conn.commit()
        
    print("[3] Done.")
        
    print("[3] Done.")

if __name__ == "__main__":
    reset_and_evaluate()
