import os
import sys
from pathlib import Path
import dotenv

dotenv.load_dotenv()

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.anonymization.csv_loader import load_tenant_csvs
from src.anonymization.field_mapper import anonymize_dataframe
from src.anonymization.db_writer import write_tenant_data

TEST_TENANTS = [
    "QUICKLOAN-001",
    "PAYFLEX-002",
    "WEALTHNEST-003",
    "RURALCRED-004",
    "NEXUSNEOBANK-005"
]

def ingest_all():
    base_dir = PROJECT_ROOT / "data" / "test_tenants"
    results = {}

    for tenant_id in TEST_TENANTS:
        tenant_dir = base_dir / tenant_id
        print(f"\n==================================================")
        print(f"Ingesting Tenant: {tenant_id}")
        print(f"Directory: {tenant_dir}")
        print(f"==================================================")

        if not tenant_dir.exists():
            print(f"[ERROR] Directory not found for {tenant_id}")
            continue

        try:
            # 1. Load CSVs
            dfs = load_tenant_csvs(tenant_dir, tenant_id)
            print(f"  [OK] Loaded {len(dfs)} CSV dataframes")

            # 2. Anonymize & Map
            mapped_data = {}
            for table_name, df in dfs.items():
                mapped_data[table_name] = anonymize_dataframe(df, table_name, tenant_id)
            print(f"  [OK] Anonymized and mapped {len(mapped_data)} tables")

            # 3. Write to Database (FK-safe atomic transaction)
            rows_written = write_tenant_data(tenant_id, mapped_data)
            results[tenant_id] = rows_written
            print(f"  [SUCCESS] Written rows summary for {tenant_id}:")
            for tbl, count in rows_written.items():
                print(f"    - {tbl:20s}: {count} inserted")

        except Exception as e:
            print(f"  [FAILED] Error ingesting {tenant_id}: {e}")
            import traceback
            traceback.print_exc()

    print("\n==================================================")
    print("ALL TEST TENANTS INGESTION SUMMARY")
    print("==================================================")
    for tid, res in results.items():
        total = sum(res.values())
        print(f"Tenant: {tid:20s} | Total Rows Inserted: {total}")

if __name__ == "__main__":
    ingest_all()
