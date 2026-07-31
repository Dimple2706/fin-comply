"""
Revert DB to 25-tenant state by removing GEN-026 through GEN-030
from all tables that hold tenant-scoped data.
"""
import psycopg

TENANTS_TO_DELETE = [f"GEN-{i:03d}" for i in range(26, 31)]

TABLES = [
    "evaluation_results",
    "transaction_events",
    "access_logs",
    "data_lifecycle",
    "security_events",
    "dsar_requests",
    "consent_records",
    "customer_master",
    "policies",
    "system_inventory",
    "governance_config",
]

def main():
    with psycopg.connect("dbname=compliance_db user=postgres password=mysql@1703") as conn:
        with conn.cursor() as cur:
            for tenant in TENANTS_TO_DELETE:
                print(f"\n[Deleting] {tenant}")
                for table in TABLES:
                    cur.execute(
                        f"DELETE FROM {table} WHERE tenant_id = %s",
                        (tenant,)
                    )
                    print(f"  {table}: {cur.rowcount} rows deleted")
            conn.commit()

        # Verify final state
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM evaluation_results")
            count = cur.fetchone()[0]
            print(f"\n[VERIFY] evaluation_results row count: {count}")

            cur.execute(
                "SELECT tenant_id FROM evaluation_results ORDER BY tenant_id"
            )
            tenants = [r[0] for r in cur.fetchall()]
            print(f"[VERIFY] Tenants present: {tenants}")

            if count == 25 and all(t.startswith("GEN-") and int(t.split("-")[1]) <= 25 for t in tenants):
                print("\n✅ Database successfully reverted to 25-tenant state.")
            else:
                print(f"\n⚠️  Unexpected state — expected 25 GEN-001..GEN-025 rows.")

if __name__ == "__main__":
    main()
