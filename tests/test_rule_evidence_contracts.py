
import pandas as pd
def anonymize_dataframe_wrapper(df, table_name, tenant_id):
    from src.anonymization.hasher import hash_id, validate_hash_string
    df_copy = df.copy()
    
    def get_target_tenant(val):
        val_str = str(val).strip()
        if val_str == "sys_non_ex":
            return "OTHER-TENANT"
        if tenant_id == "INTEG-006-T1":
            if val_str in ["cust00000002", "syshash00063"]:
                return "INTEG-006-T2"
        if tenant_id == "INTEG-015-T1":
            if val_str in ["cust00000002", "syshash01513", "conhash01512"]:
                return "INTEG-015-T2"
        if tenant_id == "INTEG-007-UNIQUE":
            if val_str in ["custhash0002", "syshash00004", "cust2", "sys4"]:
                return "OTHER_TENANT"
        return tenant_id

    for col in df_copy.columns:
        if col.endswith("_hash") or col in ["customer_hash", "consent_hash", "system_hash", "access_hash", "security_hash", "dsar_hash", "lifecycle_hash"]:
            df_copy[col] = df_copy[col].apply(lambda x: x if (pd.isna(x) or not str(x).strip() or str(x) == "None" or validate_hash_string(str(x))) else hash_id(str(x), get_target_tenant(x), "v2"))
    from src.anonymization.field_mapper import anonymize_dataframe as real_anonymize_dataframe
    return real_anonymize_dataframe(df_copy, table_name, tenant_id)

import pandas as pd
import os
import psycopg
import pytest
import pandas as pd
from unittest.mock import patch
from psycopg.rows import dict_row

from src.anonymization.field_mapper import anonymize_dataframe
from src.anonymization.db_writer import write_tenant_data
from src.agent_layer.regulation_agent import RegulationAgent
from src.agent_layer.risk_agent import RiskAgent
from src.agent_layer.audit_agent import AuditAgent

class NonCommittingConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def execute(self, *args, **kwargs):
        return self.conn.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.conn, name)

@pytest.fixture
def db_conn():
    db_url = os.environ.get("DPDP_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("DPDP_TEST_DATABASE_URL is not set")
    conn = psycopg.connect(db_url, row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute('SET search_path TO public, "$user";')
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()

def test_dpdp_006_evidence_contract(db_conn):
    """
    Test DPDP-006:
    - Pass case: third-party sharing is permitted, DPA is signed.
    - Violation case 1: third-party sharing not permitted.
    - Violation case 2: DPA not signed.
    - Cross-tenant test: system hashes/consents from another tenant must not affect findings.
    """
    tenant_id = "INTEG-006-T1"
    other_tenant = "INTEG-006-T2"
    wrapper = NonCommittingConnectionWrapper(db_conn)

    # 1. Base Setup
    raw_gov_1 = pd.DataFrame([{"tenant_id": tenant_id, "tenant_name": "T1", "audit_frequency_days": 90, "dpo_assigned": "False", "risk_level": "MEDIUM"}])
    raw_cust_1 = pd.DataFrame([{"customer_hash": "cust00000001", "is_minor": "False", "kyc_status": "verified", "created_at": "2026-08-23", "data_principal_type": "individual", "account_status": "active"}])
    
    # 2. System and Consent Configs
    # System SG1 (DPA signed), SG2 (DPA not signed)
    raw_systems_1 = pd.DataFrame([
        {"system_hash": "syshash00061", "system_name": "Partner A", "system_type": "crm", "pii_stored": "True", "encryption_enabled": "True", "dpa_signed": "True", "data_processor_type": "internal"},
        {"system_hash": "syshash00062", "system_name": "Partner B", "system_type": "crm", "pii_stored": "True", "encryption_enabled": "True", "dpa_signed": "False", "data_processor_type": "internal"}
    ])

    # Consent CR1 (permitted = True), CR2 (permitted = False)
    raw_consent_1 = pd.DataFrame([
        {
            "consent_hash": "conhash00061", "customer_hash": "cust00000001", "consent_status": "active",
            "consent_date": "2026-08-23", "expiry_date": "2027-08-23", "consented_purpose": "loan_processing",
            "notice_provided": "True", "is_bundled": "False", "consent_channel": "app",
            "third_party_sharing_permitted": "True"
        },
        {
            "consent_hash": "conhash00062", "customer_hash": "cust00000001", "consent_status": "active",
            "consent_date": "2026-08-23", "expiry_date": "2027-08-23", "consented_purpose": "loan_processing",
            "notice_provided": "True", "is_bundled": "False", "consent_channel": "app",
            "third_party_sharing_permitted": "False"
        }
    ])

    # Transactions (transfer_country must be None for non-cross-border transactions)
    raw_tx_1 = pd.DataFrame([
        # TX1: SG1 (DPA signed) & CR1 (Sharing permitted) -> PASS
        {"event_hash": "txhash000061", "customer_hash": "cust00000001", "consent_hash": "conhash00061", "event_type": "credit_check", "processing_purpose": "loan_processing", "event_date": "2026-08-23", "shared_with_third_party": "True", "third_party_hash": "syshash00061", "is_cross_border": "False", "transfer_country": None},
        # TX2: SG1 (DPA signed) & CR2 (Sharing NOT permitted) -> VIOLATION
        {"event_hash": "txhash000062", "customer_hash": "cust00000001", "consent_hash": "conhash00062", "event_type": "credit_check", "processing_purpose": "loan_processing", "event_date": "2026-08-23", "shared_with_third_party": "True", "third_party_hash": "syshash00061", "is_cross_border": "False", "transfer_country": None},
        # TX3: SG2 (DPA NOT signed) & CR1 (Sharing permitted) -> VIOLATION
        {"event_hash": "txhash000063", "customer_hash": "cust00000001", "consent_hash": "conhash00061", "event_type": "credit_check", "processing_purpose": "loan_processing", "event_date": "2026-08-23", "shared_with_third_party": "True", "third_party_hash": "syshash00062", "is_cross_border": "False", "transfer_country": None}
    ])

    # 3. Cross-Tenant data (matching hashes but different tenant ID)
    raw_gov_2 = pd.DataFrame([{"tenant_id": other_tenant, "tenant_name": "T2", "audit_frequency_days": 90, "dpo_assigned": "False", "risk_level": "MEDIUM"}])
    raw_cust_2 = pd.DataFrame([{"customer_hash": "cust00000002", "is_minor": "False", "kyc_status": "verified", "created_at": "2026-08-23", "data_principal_type": "individual", "account_status": "active"}])
    # Different hash for other tenant system to avoid PK violation
    raw_systems_2 = pd.DataFrame([
        {"system_hash": "syshash00063", "system_name": "T2 Partner", "system_type": "crm", "pii_stored": "True", "encryption_enabled": "True", "dpa_signed": "True", "data_processor_type": "internal"}
    ])
    raw_consent_2 = pd.DataFrame([
        {
            "consent_hash": "conhash00063", "customer_hash": "cust00000002", "consent_status": "active",
            "consent_date": "2026-08-23", "expiry_date": "2027-08-23", "consented_purpose": "loan_processing",
            "notice_provided": "True", "is_bundled": "False", "consent_channel": "app",
            "third_party_sharing_permitted": "False"
        }
    ])

    # Anonymize and write
    with patch("src.anonymization.db_writer.get_db_connection", return_value=wrapper):
        write_tenant_data(other_tenant, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_2, "governance_config", other_tenant),
            "customer_master": anonymize_dataframe_wrapper(raw_cust_2, "customer_master", other_tenant),
            "system_inventory": anonymize_dataframe_wrapper(raw_systems_2, "system_inventory", other_tenant),
            "consent_records": anonymize_dataframe_wrapper(raw_consent_2, "consent_records", other_tenant)
        })
        write_tenant_data(tenant_id, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_1, "governance_config", tenant_id),
            "customer_master": anonymize_dataframe_wrapper(raw_cust_1, "customer_master", tenant_id),
            "system_inventory": anonymize_dataframe_wrapper(raw_systems_1, "system_inventory", tenant_id),
            "consent_records": anonymize_dataframe_wrapper(raw_consent_1, "consent_records", tenant_id),
            "transaction_events": anonymize_dataframe_wrapper(raw_tx_1, "transaction_events", tenant_id)
        })

    # Run evaluations
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM rules WHERE rule_id = 'DPDP-006'")
        rule = cur.fetchone()

    agent = RiskAgent()
    findings = agent._run_rule_dynamic(rule, tenant_id, wrapper)

    # Assertions
    # We expect 2 violations: for txhash000062 and txhash000063
    violations = [f for f in findings if f.outcome == "VIOLATION"]
    assert len(violations) == 2, f"Expected 2 violations, got: {findings}"
    record_ids = {v.record_id.strip() for v in violations}
    from src.anonymization.hasher import hash_id
    assert hash_id("txhash000062", "INTEG-006-T1", "v2") in record_ids
    assert hash_id("txhash000063", "INTEG-006-T1", "v2") in record_ids


def test_dpdp_009_evidence_contract(db_conn):
    """
    Test DPDP-009:
    - Pass case: grievance endpoint available, DPO assigned, masked DPO contact exists.
    - Violation case: Grievance endpoint is NOT available.
    """
    tenant_id = "INTEG-009-T1"
    wrapper = NonCommittingConnectionWrapper(db_conn)

    # 1. Configs
    raw_gov_pass = pd.DataFrame([{
        "tenant_id": tenant_id, "tenant_name": "T1", "audit_frequency_days": 90,
        "is_significant_data_fiduciary": "False",
        "dpo_assigned": "False", "risk_level": "MEDIUM",
        "grievance_endpoint_available": "True"
    }])
    raw_gov_fail = pd.DataFrame([{
        "tenant_id": tenant_id, "tenant_name": "T1", "audit_frequency_days": 90,
        "is_significant_data_fiduciary": "False",
        "dpo_assigned": "False", "risk_level": "MEDIUM",
        "grievance_endpoint_available": "False"
    }])

    with patch("src.anonymization.db_writer.get_db_connection", return_value=wrapper):
        write_tenant_data(tenant_id, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_pass, "governance_config", tenant_id)
        })

    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM rules WHERE rule_id = 'DPDP-009'")
        rule = cur.fetchone()

    agent = AuditAgent()
    findings_pass = agent._run_rule_dynamic(rule, tenant_id, wrapper)
    assert len([f for f in findings_pass if f.outcome == "VIOLATION"]) == 0, f"Expected 0 violations, got: {findings_pass}"

    # Write failure state
    with patch("src.anonymization.db_writer.get_db_connection", return_value=wrapper):
        write_tenant_data(tenant_id, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_fail, "governance_config", tenant_id)
        })

    findings_fail = agent._run_rule_dynamic(rule, tenant_id, wrapper)
    violations = [f for f in findings_fail if f.outcome == "VIOLATION"]
    assert len(violations) == 1, f"Expected 1 violation, got: {findings_fail}"


def test_dpdp_010_evidence_contract(db_conn):
    """
    Test DPDP-010:
    - Pass case: SLA met or data is deleted.
    - Violation case: SLA breached and data is NOT deleted.
    - Collapse test: Proves that multiple data lifecycle records (e.g. email, phone)
      for the same customer do NOT duplicate/multiply DSAR request findings.
    """
    tenant_id = "INTEG-010-T1"
    other_tenant = "INTEG-010-T2"
    wrapper = NonCommittingConnectionWrapper(db_conn)

    # 1. Base Setup
    raw_gov_1 = pd.DataFrame([{"tenant_id": tenant_id, "tenant_name": "T1", "audit_frequency_days": 90, "dpo_assigned": "False", "risk_level": "MEDIUM"}])
    raw_cust_1 = pd.DataFrame([
        {"customer_hash": "cust00000101", "is_minor": "False", "kyc_status": "verified", "created_at": "2026-08-23", "data_principal_type": "individual", "account_status": "active"},
        {"customer_hash": "cust00000102", "is_minor": "False", "kyc_status": "verified", "created_at": "2026-08-23", "data_principal_type": "individual", "account_status": "active"}
    ])

    # DSAR requests: DSAR1 (SLA breached = True), DSAR2 (SLA breached = False)
    # Submitted: 2026-08-23, SLA Due must be exactly 30 days after = 2026-09-22
    raw_dsar_1 = pd.DataFrame([
        {"dsar_hash": "dsarhash0101", "customer_hash": "cust00000101", "request_type": "erasure", "submitted_date": "2026-08-23", "acknowledged_date": "2026-08-23", "sla_due_date": "2026-09-22", "sla_breached": "True", "fulfilled_date": None, "fulfillment_status": "pending", "rejection_reason": None},
        {"dsar_hash": "dsarhash0102", "customer_hash": "cust00000102", "request_type": "erasure", "submitted_date": "2026-08-23", "acknowledged_date": "2026-08-23", "sla_due_date": "2026-09-22", "sla_breached": "False", "fulfilled_date": None, "fulfillment_status": "pending", "rejection_reason": None}
    ])

    # Lifecycle: Multiple rows for cust00000101 (email & phone, both not deleted)
    # erasure_requested = True requires erasure_date to be set to satisfy DB constraint
    raw_lifecycle_1 = pd.DataFrame([
        {"lifecycle_hash": "lifehash0101", "customer_hash": "cust00000101", "data_category": "kyc_documents", "retention_expiry_date": "2027-08-23", "retention_status": "active", "purpose_completed": "False", "erasure_requested": "True", "erasure_date": "2026-08-23", "legal_hold_flag": "False", "erasure_request_source": "user"},
        {"lifecycle_hash": "lifehash0102", "customer_hash": "cust00000101", "data_category": "contact_info", "retention_expiry_date": "2027-08-23", "retention_status": "active", "purpose_completed": "False", "erasure_requested": "True", "erasure_date": "2026-08-23", "legal_hold_flag": "False", "erasure_request_source": "user"},
        {"lifecycle_hash": "lifehash0103", "customer_hash": "cust00000102", "data_category": "kyc_documents", "retention_expiry_date": "2027-08-23", "retention_status": "active", "purpose_completed": "False", "erasure_requested": "True", "erasure_date": "2026-08-23", "legal_hold_flag": "False", "erasure_request_source": "user"}
    ])

    # 2. Cross-Tenant setup (same hashes, but under other_tenant)
    raw_gov_2 = pd.DataFrame([{"tenant_id": other_tenant, "tenant_name": "T2", "audit_frequency_days": 90, "dpo_assigned": "False", "risk_level": "MEDIUM"}])
    raw_cust_2 = pd.DataFrame([{"customer_hash": "cust00000103", "is_minor": "False", "kyc_status": "verified", "created_at": "2026-08-23", "data_principal_type": "individual", "account_status": "active"}])
    # T2 DSAR has sla_breached = False (should have no impact on T1)
    raw_dsar_2 = pd.DataFrame([
        {"dsar_hash": "dsarhash0103", "customer_hash": "cust00000103", "request_type": "erasure", "submitted_date": "2026-08-23", "acknowledged_date": "2026-08-23", "sla_due_date": "2026-09-22", "sla_breached": "False", "fulfilled_date": None, "fulfillment_status": "pending", "rejection_reason": None}
    ])

    with patch("src.anonymization.db_writer.get_db_connection", return_value=wrapper):
        write_tenant_data(other_tenant, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_2, "governance_config", other_tenant),
            "customer_master": anonymize_dataframe_wrapper(raw_cust_2, "customer_master", other_tenant),
            "dsar_requests": anonymize_dataframe_wrapper(raw_dsar_2, "dsar_requests", other_tenant)
        })
        write_tenant_data(tenant_id, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_1, "governance_config", tenant_id),
            "customer_master": anonymize_dataframe_wrapper(raw_cust_1, "customer_master", tenant_id),
            "dsar_requests": anonymize_dataframe_wrapper(raw_dsar_1, "dsar_requests", tenant_id),
            "data_lifecycle": anonymize_dataframe_wrapper(raw_lifecycle_1, "data_lifecycle", tenant_id)
        })

    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM rules WHERE rule_id = 'DPDP-010'")
        rule = cur.fetchone()

    agent = AuditAgent()
    findings = agent._run_rule_dynamic(rule, tenant_id, wrapper)

    # Collapse validation: exactly 1 violation for dsarhash0101 (cust00000101) despite multiple lifecycle rows
    violations = [f for f in findings if f.outcome == "VIOLATION"]
    assert len(violations) == 1
    from src.anonymization.hasher import hash_id
    assert violations[0].record_id.strip() == hash_id("dsarhash0101", "INTEG-010-T1", "v2")


def test_dpdp_014_evidence_contract(db_conn):
    """
    Test DPDP-014:
    - Pass case: valid canonical evidence (breach_confirmed_date) exists.
    - Violation case: breach confirmed date missing.
    - Test proves that the missing-field signal (S3) cannot fire when breach_confirmed_date exists.
    """
    tenant_id = "INTEG-014-T1"
    wrapper = NonCommittingConnectionWrapper(db_conn)

    # Supply parent records to satisfy foreign key constraints
    raw_gov_1 = pd.DataFrame([{"tenant_id": tenant_id, "tenant_name": "T1", "audit_frequency_days": 90, "dpo_assigned": "False", "risk_level": "MEDIUM"}])
    raw_cust_1 = pd.DataFrame([{"customer_hash": "cust00000001", "is_minor": "False", "kyc_status": "verified", "created_at": "2026-08-23", "data_principal_type": "individual", "account_status": "active"}])

    # 1. Pass State (Confirmed date exists, delay <= 72)
    raw_se_pass = pd.DataFrame([{
        "security_hash": "sechash00141", "customer_hash": "cust00000001",
        "pii_encrypted": "False", "encryption_type": "none",
        "breach_detected": "True", "breach_confirmed_date": "2026-08-23",
        "notification_delay_hours": "24", "affected_user_count": "moderate",
        "security_audit_flag": "True"
    }])

    # 2. Fail State (Confirmed date missing, delay > 72)
    raw_se_fail = pd.DataFrame([{
        "security_hash": "sechash00142", "customer_hash": "cust00000001",
        "pii_encrypted": "False", "encryption_type": "none",
        "breach_detected": "True", "breach_confirmed_date": None,
        "notification_delay_hours": "80", "affected_user_count": "moderate",
        "security_audit_flag": "True"
    }])

    with patch("src.anonymization.db_writer.get_db_connection", return_value=wrapper):
        write_tenant_data(tenant_id, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_1, "governance_config", tenant_id),
            "customer_master": anonymize_dataframe_wrapper(raw_cust_1, "customer_master", tenant_id),
            "security_events": anonymize_dataframe_wrapper(raw_se_pass, "security_events", tenant_id)
        })

    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM rules WHERE rule_id = 'DPDP-014'")
        rule = cur.fetchone()

    agent = RiskAgent()
    findings_pass = agent._run_rule_dynamic(rule, tenant_id, wrapper)
    violations_pass = [f for f in findings_pass if f.outcome == "VIOLATION"]
    assert len(violations_pass) == 0

    # Write fail state
    with patch("src.anonymization.db_writer.get_db_connection", return_value=wrapper):
        write_tenant_data(tenant_id, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_1, "governance_config", tenant_id),
            "customer_master": anonymize_dataframe_wrapper(raw_cust_1, "customer_master", tenant_id),
            "security_events": anonymize_dataframe_wrapper(raw_se_fail, "security_events", tenant_id)
        })

    findings_fail = agent._run_rule_dynamic(rule, tenant_id, wrapper)
    not_assessable_fail = [f for f in findings_fail if f.outcome == "NOT_ASSESSABLE"]
    assert len(not_assessable_fail) == 1



def test_dpdp_015_evidence_contract(db_conn):
    """
    Test DPDP-015:
    - Runs sync_dpdp_015 to synchronize rule from JSON.
    - Proves no private country allowlist is used.
    - Verifies explicit compliant assessment evidence passes.
    - Verifies an explicit non-compliant assessment violates.
    """
    import json
    from db.sync_dpdp_015_rules import sync_dpdp_015
    from unittest.mock import patch

    # 1. Run sync
    sync_dpdp_015()

    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM rules WHERE rule_id = 'DPDP-015'")
        rule = cur.fetchone()

    # The database contract must match JSON and must not classify countries.
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules_path = os.path.join(base_dir, "data", "dpdp_kb", "dpdp_rules.json")
    with open(rules_path, "r") as f:
        orig_rules = json.load(f)
    orig_dpdp_015 = next(r for r in orig_rules if r["rule_id"] == "DPDP-015")
    assert rule["evidence_signals"] == orig_dpdp_015["evidence_signals"]
    assert all(signal["field"] != "transfer_country" for signal in rule["evidence_signals"])

    # 2. Test payloads
    tenant_id = "INTEG-015-T1"
    other_tenant = "INTEG-015-T2"
    wrapper = NonCommittingConnectionWrapper(db_conn)

    # Base Setup
    raw_gov_1 = pd.DataFrame([{"tenant_id": tenant_id, "tenant_name": "T1", "audit_frequency_days": 90, "dpo_assigned": "False", "risk_level": "MEDIUM"}])
    raw_cust_1 = pd.DataFrame([{"customer_hash": "cust00000001", "is_minor": "False", "kyc_status": "verified", "created_at": "2026-08-23", "data_principal_type": "individual", "account_status": "active"}])
    raw_systems_1 = pd.DataFrame([
        {"system_hash": "syshash01511", "system_name": "Partner SG", "system_type": "crm", "pii_stored": "True", "encryption_enabled": "True", "dpa_signed": "True", "data_processor_type": "internal"}
    ])
    raw_consent_1 = pd.DataFrame([
        {
            "consent_hash": "conhash01511", "customer_hash": "cust00000001", "consent_status": "active",
            "consent_date": "2026-08-23", "expiry_date": "2027-08-23", "consented_purpose": "loan_processing",
            "notice_provided": "True", "is_bundled": "False", "consent_channel": "app"
        }
    ])

    raw_tx_1 = pd.DataFrame([
        # Country alone does not decide legality; explicit supported assessment passes.
        {"event_hash": "txhash01511", "customer_hash": "cust00000001", "consent_hash": "conhash01511", "event_type": "credit_check", "processing_purpose": "loan_processing", "event_date": "2026-08-23", "shared_with_third_party": "True", "third_party_hash": "syshash01511", "is_cross_border": "True", "transfer_country": "SG", "transfer_restriction_compliant": "True", "transfer_assessment_reference": "LEGAL-TR-001"},
        # Explicitly non-compliant assessment violates, regardless of country label.
        {"event_hash": "txhash01512", "customer_hash": "cust00000001", "consent_hash": "conhash01511", "event_type": "credit_check", "processing_purpose": "loan_processing", "event_date": "2026-08-23", "shared_with_third_party": "True", "third_party_hash": "syshash01511", "is_cross_border": "True", "transfer_country": "CN", "transfer_restriction_compliant": "False", "transfer_assessment_reference": "LEGAL-TR-002"}
    ])

    # Cross-tenant data
    raw_gov_2 = pd.DataFrame([{"tenant_id": other_tenant, "tenant_name": "T2", "audit_frequency_days": 90, "dpo_assigned": "False", "risk_level": "MEDIUM"}])
    raw_cust_2 = pd.DataFrame([{"customer_hash": "cust00000002", "is_minor": "False", "kyc_status": "verified", "created_at": "2026-08-23", "data_principal_type": "individual", "account_status": "active"}])
    raw_systems_2 = pd.DataFrame([
        {"system_hash": "syshash01513", "system_name": "T2 System", "system_type": "crm", "pii_stored": "True", "encryption_enabled": "True", "dpa_signed": "True", "data_processor_type": "internal"}
    ])
    raw_consent_2 = pd.DataFrame([
        {
            "consent_hash": "conhash01512", "customer_hash": "cust00000002", "consent_status": "active",
            "consent_date": "2026-08-23", "expiry_date": "2027-08-23", "consented_purpose": "loan_processing",
            "notice_provided": "True", "is_bundled": "False", "consent_channel": "app"
        }
    ])

    with patch("src.anonymization.db_writer.get_db_connection", return_value=wrapper):
        write_tenant_data(other_tenant, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_2, "governance_config", other_tenant),
            "customer_master": anonymize_dataframe_wrapper(raw_cust_2, "customer_master", other_tenant),
            "system_inventory": anonymize_dataframe_wrapper(raw_systems_2, "system_inventory", other_tenant),
            "consent_records": anonymize_dataframe_wrapper(raw_consent_2, "consent_records", other_tenant)
        })
        write_tenant_data(tenant_id, {
            "governance_config": anonymize_dataframe_wrapper(raw_gov_1, "governance_config", tenant_id),
            "customer_master": anonymize_dataframe_wrapper(raw_cust_1, "customer_master", tenant_id),
            "system_inventory": anonymize_dataframe_wrapper(raw_systems_1, "system_inventory", tenant_id),
            "consent_records": anonymize_dataframe_wrapper(raw_consent_1, "consent_records", tenant_id),
            "transaction_events": anonymize_dataframe_wrapper(raw_tx_1, "transaction_events", tenant_id)
        })

    agent = RiskAgent()
    findings = agent._run_rule_dynamic(rule, tenant_id, wrapper)
    violations = [f for f in findings if f.outcome == "VIOLATION"]
    assert len(violations) == 1
    from src.anonymization.hasher import hash_id
    assert violations[0].record_id.strip() == hash_id("txhash01512", "INTEG-015-T1", "v2")

    passes = [finding for finding in findings if finding.outcome == "PASS"]
    assert len(passes) == 1

