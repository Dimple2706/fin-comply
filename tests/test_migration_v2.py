import os
import json
import pytest
import psycopg
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.routes import get_db_connection
from src.anonymization.hasher import hash_id, validate_hash_string, check_database_migration_complete
from db.migrate_hash_v2 import run_ddl_migration, COLUMNS_TO_MIGRATE

client = TestClient(app)

# Helper token hash for testing auth integration
import hashlib
admin_token = "secure_test_admin_token_2026"
test_credentials = {
    hashlib.sha256(admin_token.encode("utf-8")).hexdigest(): {
        "username": "test_admin",
        "role": "admin",
        "authorized_tenants": ["tenant_a", "tenant_b", "non_existent_tenant_XYZ"]
    }
}

@pytest.fixture(autouse=True)
def run_schema_ensure():
    # Dynamically inject credentials into test environment to prevent cross-test pollution
    old_creds = os.environ.get("FINCOMPLY_TEST_CREDENTIALS")
    os.environ["FINCOMPLY_TEST_CREDENTIALS"] = json.dumps(test_credentials)
    
    with get_db_connection() as conn:
        ensure_evaluation_results_table_mock(conn)
        with conn.cursor() as cur:
            cur.execute("INSERT INTO governance_config (tenant_id, tenant_name, audit_frequency_days, dpo_assigned, risk_level, dpo_contact_masked) VALUES ('tenant_a', 'Tenant A', 90, 'True', 'MEDIUM', 'dpo@tenant_a.com') ON CONFLICT DO NOTHING;")
        conn.commit()
        
    yield
    
    # Restore credentials to prevent pollution
    if old_creds is not None:
        os.environ["FINCOMPLY_TEST_CREDENTIALS"] = old_creds
    else:
        os.environ.pop("FINCOMPLY_TEST_CREDENTIALS", None)

def ensure_evaluation_results_table_mock(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_runs (
                audit_run_id varchar(64) PRIMARY KEY,
                tenant_id varchar(32) NOT NULL,
                status varchar(20) NOT NULL,
                hash_version varchar(10) NOT NULL DEFAULT 'v1',
                created_at timestamp DEFAULT NOW()
            );
        """)

def test_fresh_migrated_db_joins_v2():
    hash_c = hash_id("CUST_MIGRATED", "tenant_a", version="v2")
    hash_cons = hash_id("CONSENT_MIGRATED", "tenant_a", version="v2")
    
    assert len(hash_c) == 67
    assert len(hash_cons) == 67

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM consent_records WHERE customer_hash = %s", (hash_c,))
            cur.execute("DELETE FROM customer_master WHERE customer_hash = %s", (hash_c,))
            
            cur.execute(
                "INSERT INTO customer_master (customer_hash, tenant_id, data_principal_type, kyc_status, country, created_at) "
                "VALUES (%s, %s, 'individual', 'verified', 'IN', '2026-08-24')",
                (hash_c, "tenant_a")
            )
            
            cur.execute(
                "INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consent_date, expiry_date, consented_purpose, consent_version, consent_channel, notice_provided) "
                "VALUES (%s, %s, %s, 'granted', '2026-08-24', '2027-08-24', 'marketing', '1.0', 'web', true)",
                (hash_cons, hash_c, "tenant_a")
            )
            
            cur.execute("""
                SELECT c.customer_hash, r.consent_hash 
                FROM customer_master c 
                JOIN consent_records r ON c.customer_hash = r.customer_hash 
                WHERE c.customer_hash = %s AND c.tenant_id = %s
            """, (hash_c, "tenant_a"))
            
            row = cur.fetchone()
            assert row is not None
            c_hash = row["customer_hash"] if isinstance(row, dict) else row[0]
            cons_hash = row["consent_hash"] if isinstance(row, dict) else row[1]
            assert c_hash.strip() == hash_c
            assert cons_hash.strip() == hash_cons
            
            cur.execute("DELETE FROM consent_records WHERE customer_hash = %s", (hash_c,))
            cur.execute("DELETE FROM customer_master WHERE customer_hash = %s", (hash_c,))
        conn.commit()

def test_production_startup_validation_check():
    os.environ["ENV"] = "production"
    os.environ["DATABASE_URL"] = os.getenv("DPDP_TEST_DATABASE_URL") or "postgresql://postgres:rasika23@localhost:5432/dpdp_test_isolated"
    
    try:
        check_database_migration_complete()
    except Exception as e:
        pytest.fail(f"Production startup check should succeed on migrated DB: {e}")
        
    os.environ["DATABASE_URL"] = "postgresql://postgres:rasika23@localhost:5432/non_existent_db_fake"
    with pytest.raises(RuntimeError, match="Database validation check failed at startup"):
        check_database_migration_complete()

    os.environ["ENV"] = "test"
    os.environ["DATABASE_URL"] = ""

def test_rollback_consistency():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS cnt FROM customer_master")
            row = cur.fetchone()
            orig_count = row["cnt"] if isinstance(row, dict) else row[0]
            
            try:
                cur.execute(
                    "INSERT INTO customer_master (customer_hash, tenant_id, data_principal_type, kyc_status, country, created_at) "
                    "VALUES ('fake', 'tenant_a', 'individual', 'verified', 'IN', '2026-08-24')"
                )
                cur.execute("SELECT some_invalid_column_force_failure FROM customer_master")
            except Exception:
                conn.rollback()
                
            cur.execute("SELECT count(*) AS cnt FROM customer_master")
            row2 = cur.fetchone()
            post_count = row2["cnt"] if isinstance(row2, dict) else row2[0]
            assert orig_count == post_count
    finally:
        conn.close()

def test_mixed_hash_version_upload_rejection():
    tenant_id = "tenant_a"
    files = {
        "governance_config": (
            "governance_config.csv",
            f"tenant_id,tenant_name,grievance_endpoint_available,dpo_assigned,dpo_contact_masked,audit_frequency_days,last_audit_date,risk_level\n"
            f"{tenant_id},Test Tenant,True,True,dpo@test.local,365,2024-01-01,MEDIUM".encode("utf-8")
        ),
        "customer_master": (
            "customer_master.csv",
            f"customer_id,tenant_id,is_minor,data_principal_type,account_status,kyc_status,country,created_at\n"
            f"C1,{tenant_id},False,individual,active,verified,IN,2024-01-01".encode("utf-8")
        ),
        "consent_records": (
            "consent_records.csv",
            f"consent_id,customer_id,tenant_id,consent_status,consented_purpose,notice_provided,is_bundled,consent_channel,guardian_consent_id,consent_date,expiry_date,customer_hash\n"
            f"CON1,C1,{tenant_id},active,marketing,True,False,web,,2024-01-01,2025-01-01,v1:123456789012\n"
            f"CON2,C1,{tenant_id},active,marketing,True,False,web,,2024-01-01,2025-01-01,v2:2234567890123456789012345678901234567890123456789012345678901234\n".encode("utf-8")
        ),
        "system_inventory": (
            "system_inventory.csv",
            f"system_id,tenant_id,system_name,system_type,pii_stored,encryption_enabled,access_control_enabled,data_processor_type,retention_policy_applied,dpa_signed,dpa_expiry_date\n"
            f"SYS1,{tenant_id},System 1,crm,True,True,True,internal,True,True,".encode("utf-8")
        ),
        "transaction_events": (
            "transaction_events.csv",
            f"event_id,customer_id,tenant_id,consent_id,event_type,processing_purpose,event_date,shared_with_third_party,third_party_id,is_cross_border,transfer_country\n"
            f"TX1,C1,{tenant_id},CON1,marketing_push,marketing,2024-01-15,True,SYS1,False,".encode("utf-8")
        ),
        "access_logs": (
            "access_logs.csv",
            f"access_id,customer_id,tenant_id,employee_id,employee_role,accessed_pii,pii_fields_accessed,access_reason,access_outcome,data_volume_accessed,access_date\n"
            f"ACC1,C1,{tenant_id},E1,underwriter,True,name,loan_review,granted,low,2024-01-02".encode("utf-8")
        ),
        "data_lifecycle": (
            "data_lifecycle.csv",
            f"lifecycle_id,customer_id,tenant_id,data_category,retention_expiry_date,retention_status,purpose_completed,erasure_requested,erasure_date,legal_hold_flag,erasure_request_source\n"
            f"L1,C1,{tenant_id},kyc_documents,2025-01-01,active,False,False,,False,".encode("utf-8")
        ),
        "security_events": (
            "security_events.csv",
            f"security_id,customer_id,tenant_id,pii_encrypted,encryption_type,breach_detected,breach_confirmed_date,notification_delay_hours,affected_user_count,data_categories_breached,security_audit_flag\n"
            f"SEC1,C1,{tenant_id},True,AES-256,False,,,0,,False".encode("utf-8")
        ),
        "dsar_requests": (
            "dsar_requests.csv",
            f"dsar_id,customer_id,tenant_id,request_type,submitted_date,acknowledged_date,sla_due_date,sla_breached,fulfilled_date,fulfillment_status,rejection_reason\n"
            f"DS1,C1,{tenant_id},access,2024-01-01,2024-01-02,2024-01-31,False,,pending,".encode("utf-8")
        ),
        "policies": (
            "policies.csv",
            f"policy_id,tenant_id,policy_type,policy_name,policy_value_numeric,policy_value_unit,effective_date,last_updated,is_active\n"
            f"P1,{tenant_id},retention,Retention Policy,365,days,2024-01-01,2024-01-01,True".encode("utf-8")
        ),
    }
    
    data = {
        "tenant_id": "tenant_a",
        "tenant_name": "Tenant A"
    }
    res = client.post(
        "/analyze/upload",
        data=data,
        files=files,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    print("Response JSON:", res.json())
    assert res.status_code == 400
    assert "mix v1 and v2 identifiers" in res.json()["detail"]

def test_parent_hash_version_mismatch_rejection(authorized_client):
    # Setup parent run v1 in DB
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit_runs WHERE tenant_id = 'tenant_b';")
            cur.execute(
                "INSERT INTO audit_runs (audit_run_id, tenant_id, input_snapshot_hash, rule_set_hash, "
                "clause_set_hash, engine_version, model_hash, source_data_row_counts, validation_summary, status, hash_version) "
                "VALUES ('run_parent_v1', 'tenant_b', 'dummy_hash', 'dummy_hash', 'dummy_hash', '2.0.0', 'xgb', '{}', '{}', 'completed', 'v1')"
            )
        conn.commit()

    os.environ["HASH_VERSION"] = "v2"
    client_b = authorized_client("tenant_b")
    res = client_b.post(
        "/analyze",
        json={"tenant_id": "tenant_b"}
    )
    assert res.status_code == 400
    assert "Mismatched hash version" in res.json()["detail"]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit_runs WHERE tenant_id = 'tenant_b';")
        conn.commit()

def test_schema_integrity_column_widths():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for table, cols in COLUMNS_TO_MIGRATE:
                for col in cols:
                    cur.execute(f"""
                        SELECT character_maximum_length 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}' AND column_name = '{col}';
                    """)
                    row = cur.fetchone()
                    assert row is not None
                    width = row["character_maximum_length"] if isinstance(row, dict) else row[0]
                    assert width >= 67

def test_legacy_v1_rows_survive_schema_migration():
    # Insert legacy linked v1 rows
    hash_c_v1 = "123456789012"
    hash_cons_v1 = "523456789012"
    
    # 1. Insert v1 rows and commit transaction to release locks
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM consent_records WHERE customer_hash = %s", (hash_c_v1,))
            cur.execute("DELETE FROM customer_master WHERE customer_hash = %s", (hash_c_v1,))
            
            cur.execute(
                "INSERT INTO customer_master (customer_hash, tenant_id, data_principal_type, kyc_status, country, created_at) "
                "VALUES (%s, %s, 'individual', 'verified', 'IN', '2026-08-24')",
                (hash_c_v1, "tenant_a")
            )
            
            cur.execute(
                "INSERT INTO consent_records (consent_hash, customer_hash, tenant_id, consent_status, consent_date, expiry_date, consented_purpose, consent_version, consent_channel, notice_provided) "
                "VALUES (%s, %s, %s, 'granted', '2026-08-24', '2027-08-24', 'marketing', '1.0', 'web', true)",
                (hash_cons_v1, hash_c_v1, "tenant_a")
            )
        conn.commit()
            
    # 2. Apply migration (re-run is idempotent) without holding open locks
    run_ddl_migration()
    
    # 3. Query & Assert readability and joins are valid
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.customer_hash, r.consent_hash 
                FROM customer_master c 
                JOIN consent_records r ON c.customer_hash = r.customer_hash 
                WHERE c.customer_hash = %s AND c.tenant_id = %s
            """, (hash_c_v1, "tenant_a"))
            
            row = cur.fetchone()
            assert row is not None
            c_hash = row["customer_hash"] if isinstance(row, dict) else row[0]
            cons_hash = row["consent_hash"] if isinstance(row, dict) else row[1]
            # Prove original values remain unmodified/untruncated/unconverted
            assert c_hash.strip() == hash_c_v1
            assert cons_hash.strip() == hash_cons_v1
            
            cur.execute("DELETE FROM consent_records WHERE customer_hash = %s", (hash_c_v1,))
            cur.execute("DELETE FROM customer_master WHERE customer_hash = %s", (hash_c_v1,))
        conn.commit()

def test_migration_idempotency():
    try:
        run_ddl_migration()
        run_ddl_migration()
    except Exception as e:
        pytest.fail(f"Idempotency run failed with exception: {e}")
