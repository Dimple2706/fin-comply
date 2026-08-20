import os
import psycopg
import dotenv

dotenv.load_dotenv()

def get_db_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "tenant_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres")
    )

def verify_tenant_data(tenant_id: str) -> dict:
    """
    Verifies that the pipelined tenant data respects DPDP rules in the PostgreSQL schema.
    
    Checks per prompt:
    - 10 tables hold data for tenant.
    - Exactly 1 row mapped into governance_config for the tenant.
    - No raw PII exists (no @ symbol exists in any text/varchar column query response for the tenant isolation).
      Fixed for psycopg3 compliance by using POSITION() rather than literal LIKE '%@%'.
    - Foreign key integrity checks (e.g. customer_hash correctly links across customer_master and consent mappings).
    """
    results = {"passed": True, "checks": {}}
    
    tables = [
        "governance_config", "system_inventory", "policies",
        "customer_master", "consent_records", "transaction_events",
        "access_logs", "data_lifecycle", "security_events", "dsar_requests"
    ]
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                
                # Check 1: All 10 tables have rows for tenant
                missing_tables = []
                for t in tables:
                    cur.execute(f"SELECT COUNT(*) FROM {t} WHERE tenant_id = %s", (tenant_id,))
                    if cur.fetchone()[0] == 0:
                        missing_tables.append(t)
                        
                check_name_1 = "All 10 tables populated"
                if missing_tables:
                    print(f"FAIL: {check_name_1} (Missing rows in: {', '.join(missing_tables)})")
                    results["checks"][check_name_1] = False
                    results["passed"] = False
                else:
                    print(f"PASS: {check_name_1}")
                    results["checks"][check_name_1] = True
                    
                # Check 2: Exactly 1 row for governance_config
                cur.execute("SELECT COUNT(*) FROM governance_config WHERE tenant_id = %s", (tenant_id,))
                gc_count = cur.fetchone()[0]
                check_name_2 = "Exactly 1 row in governance_config"
                if gc_count == 1:
                    print(f"PASS: {check_name_2}")
                    results["checks"][check_name_2] = True
                else:
                    print(f"FAIL: {check_name_2} (Found {gc_count})")
                    results["checks"][check_name_2] = False
                    results["passed"] = False

                # Check 3: No @ present (email PII) in string fields
                check_name_3 = "No raw PII (@ signs) visible"
                pii_leaked = False
                
                for t in tables:
                    # Fetching string type columns to search for @ character 
                    cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t}' AND data_type IN ('text', 'character varying', 'character')")
                    str_cols = [r[0] for r in cur.fetchall()]
                    
                    if not str_cols:
                        continue
                        
                    # Fix for psycopg v3: Replacing LIKE '%@%' with POSITION('@' IN ...) to avoid escaping issues
                    query_parts = [f"POSITION('@' IN {col}) > 0" for col in str_cols]
                    where_clause = " OR ".join(query_parts)
                    
                    cur.execute(f"SELECT COUNT(*) FROM {t} WHERE tenant_id = %s AND ({where_clause})", (tenant_id,))
                    if cur.fetchone()[0] > 0:
                        pii_leaked = True
                        break
                        
                if pii_leaked:
                    print(f"FAIL: {check_name_3}")
                    results["checks"][check_name_3] = False
                    results["passed"] = False
                else:
                    print(f"PASS: {check_name_3}")
                    results["checks"][check_name_3] = True

                # Check 4: FK Integrity holds (Customer hash cross-check example)
                check_name_4 = "FK integrity holds (Customer Hash)"
                cur.execute("SELECT customer_hash FROM customer_master WHERE tenant_id = %s", (tenant_id,))
                c_hash = cur.fetchone()[0]
                cur.execute("SELECT customer_hash FROM consent_records WHERE tenant_id = %s AND customer_hash = %s", (tenant_id, c_hash))
                
                cr_hash = cur.fetchone()
                if cr_hash and cr_hash[0] == c_hash:
                    print(f"PASS: {check_name_4}")
                    results["checks"][check_name_4] = True
                else:
                    print(f"FAIL: {check_name_4}")
                    results["checks"][check_name_4] = False
                    results["passed"] = False
                    
    except Exception as e:
        print(f"FAIL: Pre-mature failure applying DB checks - {e}")
        results["passed"] = False
        
    return results

if __name__ == "__main__":
    import sys
    import json
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else "tenant_a"
    result = verify_tenant_data(tenant_id)
    print(json.dumps(result, indent=2))
