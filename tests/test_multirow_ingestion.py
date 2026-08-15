"""
Tests for multi-row backend ingestion fix.

Verifies that all multi-row datasets preserve every valid row through
the anonymization pipeline, and that governance_config remains single-row.
"""
import pandas as pd
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from src.anonymization.field_mapper import anonymize_dataframe
from src.anonymization.hasher import hash_id


# ═══════════════════════════════════════════════════════════════
# HELPER — build DataFrames from dicts
# ═══════════════════════════════════════════════════════════════

TENANT_ID = "TEST_TENANT_A"
TENANT_ID_B = "TEST_TENANT_B"


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════
# TEST A — Customer master rows preserved
# ═══════════════════════════════════════════════════════════════

class TestCustomerMasterMultiRow:
    def _build_customers(self, n: int) -> pd.DataFrame:
        rows = []
        for i in range(1, n + 1):
            rows.append({
                "customer_id": f"CUST-{i:03d}",
                "tenant_id": TENANT_ID,
                "is_minor": i == 2,  # second customer is minor
                "data_principal_type": "individual",
                "account_status": "active",
                "kyc_status": "verified",
                "country": "IN",
                "created_at": "2024-01-15",
                "dob": "1990-01-01",
            })
        return _make_df(rows)

    def test_three_rows_produce_three_records(self):
        df = self._build_customers(3)
        result = anonymize_dataframe(df, "customer_master", TENANT_ID)
        assert isinstance(result, list), "customer_master must return a list"
        assert len(result) == 3, f"Expected 3 records, got {len(result)}"

    def test_250_rows_produce_250_records(self):
        df = self._build_customers(250)
        result = anonymize_dataframe(df, "customer_master", TENANT_ID)
        assert len(result) == 250, f"Expected 250 records, got {len(result)}"

    def test_each_row_has_unique_hash(self):
        df = self._build_customers(5)
        result = anonymize_dataframe(df, "customer_master", TENANT_ID)
        hashes = [r["customer_hash"] for r in result]
        assert len(set(hashes)) == 5, "Each customer should have a unique hash"

    def test_minor_flag_preserved(self):
        df = self._build_customers(3)
        result = anonymize_dataframe(df, "customer_master", TENANT_ID)
        assert result[1]["is_minor"] is True
        assert result[1]["data_principal_type"] == "minor"


# ═══════════════════════════════════════════════════════════════
# TEST B — Consent records rows preserved
# ═══════════════════════════════════════════════════════════════

class TestConsentRecordsMultiRow:
    def _build_consents(self, n: int) -> pd.DataFrame:
        rows = []
        for i in range(1, n + 1):
            rows.append({
                "consent_id": f"CON-{i:03d}",
                "customer_id": f"CUST-{i:03d}",
                "tenant_id": TENANT_ID,
                "consent_status": "active",
                "consent_timestamp": "2024-01-10",
                "expiry_timestamp": "2025-01-10",
                "consented_purpose": "loan_processing",
                "consent_version": "v2.0",
                "notice_provided": True,
                "is_bundled": False,
                "consent_channel": "app",
                "withdrawal_timestamp": None,
            })
        return _make_df(rows)

    def test_four_rows_produce_four_records(self):
        df = self._build_consents(4)
        result = anonymize_dataframe(df, "consent_records", TENANT_ID)
        assert isinstance(result, list), "consent_records must return a list"
        assert len(result) == 4, f"Expected 4 records, got {len(result)}"

    def test_320_rows_produce_320_records(self):
        df = self._build_consents(320)
        result = anonymize_dataframe(df, "consent_records", TENANT_ID)
        assert len(result) == 320, f"Expected 320 records, got {len(result)}"


# ═══════════════════════════════════════════════════════════════
# TEST C — Data lifecycle rows preserved
# ═══════════════════════════════════════════════════════════════

class TestDataLifecycleMultiRow:
    def _build_lifecycle(self, n: int) -> pd.DataFrame:
        rows = []
        categories = ["kyc_documents", "transaction_history", "credit_score", "contact_info", "device_info"]
        for i in range(1, n + 1):
            rows.append({
                "lifecycle_id": f"LC-{i:03d}",
                "customer_id": f"CUST-{i:03d}",
                "tenant_id": TENANT_ID,
                "data_category": categories[i % len(categories)],
                "retention_expiry_date": "2023-06-01",
                "retention_status": "active",
                "purpose_completed": False,
                "erasure_requested": False,
                "erasure_timestamp": None,
                "legal_hold_flag": False,
                "erasure_request_source": None,
            })
        return _make_df(rows)

    def test_five_rows_produce_five_records(self):
        df = self._build_lifecycle(5)
        result = anonymize_dataframe(df, "data_lifecycle", TENANT_ID)
        assert isinstance(result, list), "data_lifecycle must return a list"
        assert len(result) == 5, f"Expected 5 records, got {len(result)}"

    def test_legal_hold_flag_preserved(self):
        df = self._build_lifecycle(2)
        df.at[0, "legal_hold_flag"] = True
        result = anonymize_dataframe(df, "data_lifecycle", TENANT_ID)
        assert result[0]["legal_hold_flag"] is True
        assert result[1]["legal_hold_flag"] is False

    def test_erasure_request_source_preserved(self):
        df = self._build_lifecycle(2)
        df.at[0, "erasure_requested"] = True
        df.at[0, "erasure_request_source"] = "system"
        result = anonymize_dataframe(df, "data_lifecycle", TENANT_ID)
        assert result[0]["erasure_request_source"] == "system"
        assert result[0]["erasure_requested"] is True


# ═══════════════════════════════════════════════════════════════
# TEST D — System inventory rows preserved
# ═══════════════════════════════════════════════════════════════

class TestSystemInventoryMultiRow:
    def _build_systems(self, n: int) -> pd.DataFrame:
        rows = []
        for i in range(1, n + 1):
            rows.append({
                "system_id": f"SYS-{i:03d}",
                "tenant_id": TENANT_ID,
                "system_name": f"System {i}",
                "system_type": "crm",
                "data_types_stored": "pii",
                "pii_stored": True,
                "encryption_enabled": True,
                "access_control_enabled": True,
                "retention_policy_applied": True,
                "third_party_integrations": "none",
                "data_processor_type": "internal",
                "dpa_signed": False,
                "dpa_expiry_date": None,
            })
        return _make_df(rows)

    def test_three_rows_produce_three_records(self):
        df = self._build_systems(3)
        result = anonymize_dataframe(df, "system_inventory", TENANT_ID)
        assert isinstance(result, list), "system_inventory must return a list"
        assert len(result) == 3, f"Expected 3 records, got {len(result)}"

    def test_pii_stored_field_present(self):
        df = self._build_systems(2)
        result = anonymize_dataframe(df, "system_inventory", TENANT_ID)
        assert "pii_stored" in result[0], "pii_stored field must be present"
        assert result[0]["pii_stored"] is True

    def test_encryption_and_access_control_preserved(self):
        df = self._build_systems(1)
        result = anonymize_dataframe(df, "system_inventory", TENANT_ID)
        assert result[0]["encryption_enabled"] is True
        assert result[0]["access_control_enabled"] is True
        assert result[0]["retention_policy_applied"] is True


# ═══════════════════════════════════════════════════════════════
# TEST E — Policy rows preserved
# ═══════════════════════════════════════════════════════════════

class TestPoliciesMultiRow:
    def _build_policies(self, n: int) -> pd.DataFrame:
        rows = []
        types = ["retention", "consent", "encryption", "access_control", "breach_notification"]
        for i in range(1, n + 1):
            rows.append({
                "policy_id": f"POL-{i:03d}",
                "tenant_id": TENANT_ID,
                "policy_type": types[i % len(types)],
                "policy_name": f"Policy {i}",
                "policy_value_numeric": 365,
                "policy_value_unit": "days",
                "effective_date": "2024-01-01",
                "last_updated": "2024-06-01",
                "is_active": True,
            })
        return _make_df(rows)

    def test_four_rows_produce_four_records(self):
        df = self._build_policies(4)
        result = anonymize_dataframe(df, "policies", TENANT_ID)
        assert isinstance(result, list), "policies must return a list"
        assert len(result) == 4, f"Expected 4 records, got {len(result)}"


# ═══════════════════════════════════════════════════════════════
# TEST F — Stable hashing across datasets
# ═══════════════════════════════════════════════════════════════

class TestStableHashing:
    def test_same_customer_id_produces_same_hash_across_tables(self):
        customer_id = "CUST-001"

        # customer_master
        cm_df = _make_df([{
            "customer_id": customer_id, "tenant_id": TENANT_ID,
            "is_minor": False, "data_principal_type": "individual",
            "account_status": "active", "kyc_status": "verified",
            "country": "IN", "created_at": "2024-01-15", "dob": "1990-01-01",
        }])
        cm_result = anonymize_dataframe(cm_df, "customer_master", TENANT_ID)
        cm_hash = cm_result[0]["customer_hash"]

        # consent_records
        cr_df = _make_df([{
            "consent_id": "CON-001", "customer_id": customer_id,
            "tenant_id": TENANT_ID, "consent_status": "active",
            "consent_timestamp": "2024-01-10", "expiry_timestamp": "2025-01-10",
            "consented_purpose": "loan_processing", "consent_version": "v1.0",
            "notice_provided": True, "is_bundled": False,
            "consent_channel": "app", "withdrawal_timestamp": None,
        }])
        cr_result = anonymize_dataframe(cr_df, "consent_records", TENANT_ID)
        cr_hash = cr_result[0]["customer_hash"]

        # transaction_events
        tx_df = _make_df([{
            "event_id": "EVT-001", "customer_id": customer_id,
            "tenant_id": TENANT_ID, "consent_id": "CON-001",
            "event_type": "credit_check", "processing_purpose": "loan_processing",
            "timestamp": "2024-03-01", "shared_with_third_party": False,
            "third_party_id": None, "is_cross_border": False,
            "transfer_country": None,
        }])
        tx_result = anonymize_dataframe(tx_df, "transaction_events", TENANT_ID)
        tx_hash = tx_result[0]["customer_hash"]

        assert cm_hash == cr_hash == tx_hash, (
            f"Same customer_id must produce same hash: "
            f"cm={cm_hash}, cr={cr_hash}, tx={tx_hash}"
        )

    def test_consent_hash_consistent_across_tables(self):
        consent_id = "CON-042"

        cr_df = _make_df([{
            "consent_id": consent_id, "customer_id": "CUST-001",
            "tenant_id": TENANT_ID, "consent_status": "active",
            "consent_timestamp": "2024-01-10", "expiry_timestamp": "2025-01-10",
            "consented_purpose": "loan_processing", "consent_version": "v1.0",
            "notice_provided": True, "is_bundled": False,
            "consent_channel": "app", "withdrawal_timestamp": None,
        }])
        cr_result = anonymize_dataframe(cr_df, "consent_records", TENANT_ID)

        tx_df = _make_df([{
            "event_id": "EVT-099", "customer_id": "CUST-001",
            "tenant_id": TENANT_ID, "consent_id": consent_id,
            "event_type": "credit_check", "processing_purpose": "loan_processing",
            "timestamp": "2024-03-01", "shared_with_third_party": False,
            "third_party_id": None, "is_cross_border": False,
            "transfer_country": None,
        }])
        tx_result = anonymize_dataframe(tx_df, "transaction_events", TENANT_ID)

        assert cr_result[0]["consent_hash"] == tx_result[0]["consent_hash"]


# ═══════════════════════════════════════════════════════════════
# TEST G — Different tenants produce different hashes
# ═══════════════════════════════════════════════════════════════

class TestTenantIsolation:
    def test_same_id_different_tenants_different_hashes(self):
        hash_a = hash_id("CUST-001", TENANT_ID)
        hash_b = hash_id("CUST-001", TENANT_ID_B)
        assert hash_a != hash_b, "Same ID under different tenants must produce different hashes"


# ═══════════════════════════════════════════════════════════════
# TEST H — Empty optional IDs remain None
# ═══════════════════════════════════════════════════════════════

class TestEmptyOptionalIds:
    def test_blank_consent_id_not_hashed(self):
        tx_df = _make_df([{
            "event_id": "EVT-001", "customer_id": "CUST-001",
            "tenant_id": TENANT_ID, "consent_id": None,
            "event_type": "credit_check", "processing_purpose": "loan_processing",
            "timestamp": "2024-03-01", "shared_with_third_party": False,
            "third_party_id": None, "is_cross_border": False,
            "transfer_country": None,
        }])
        result = anonymize_dataframe(tx_df, "transaction_events", TENANT_ID)
        assert result[0]["consent_hash"] is None, "Blank consent_id must remain None"

    def test_blank_third_party_with_no_sharing(self):
        tx_df = _make_df([{
            "event_id": "EVT-002", "customer_id": "CUST-001",
            "tenant_id": TENANT_ID, "consent_id": "CON-001",
            "event_type": "credit_check", "processing_purpose": "loan_processing",
            "timestamp": "2024-03-01", "shared_with_third_party": False,
            "third_party_id": None, "is_cross_border": False,
            "transfer_country": None,
        }])
        result = anonymize_dataframe(tx_df, "transaction_events", TENANT_ID)
        assert result[0]["third_party_hash"] is None

    def test_blank_guardian_consent(self):
        cr_df = _make_df([{
            "consent_id": "CON-001", "customer_id": "CUST-001",
            "tenant_id": TENANT_ID, "consent_status": "active",
            "consent_timestamp": "2024-01-10", "expiry_timestamp": "2025-01-10",
            "consented_purpose": "loan_processing", "consent_version": "v1.0",
            "notice_provided": True, "is_bundled": False,
            "consent_channel": "app", "withdrawal_timestamp": None,
        }])
        result = anonymize_dataframe(cr_df, "consent_records", TENANT_ID)
        assert result[0]["guardian_consent_hash"] is None

    def test_blank_erasure_no_date(self):
        dl_df = _make_df([{
            "lifecycle_id": "LC-001", "customer_id": "CUST-001",
            "tenant_id": TENANT_ID, "data_category": "kyc_documents",
            "retention_expiry_date": "2023-06-01", "retention_status": "active",
            "purpose_completed": False, "erasure_requested": False,
            "erasure_timestamp": None, "legal_hold_flag": False,
            "erasure_request_source": None,
        }])
        result = anonymize_dataframe(dl_df, "data_lifecycle", TENANT_ID)
        assert result[0]["erasure_date"] is None
        assert result[0]["erasure_request_source"] is None


# ═══════════════════════════════════════════════════════════════
# TEST I — Writer accepts multi-row lists (mock DB)
# ═══════════════════════════════════════════════════════════════

class TestWriterMultiRow:
    @patch("src.anonymization.db_writer.get_db_connection")
    def test_writer_inserts_all_rows(self, mock_get_conn):
        """Verify write_tenant_data iterates over lists, not just single dicts."""
        from src.anonymization.db_writer import write_tenant_data

        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value = mock_conn

        data = {
            "governance_config": {
                "tenant_id": TENANT_ID, "tenant_name": "Test",
                "grievance_endpoint_available": True, "dpo_assigned": False,
                "dpo_contact_masked": None, "audit_frequency_days": 90,
                "last_audit_date": "2024-01-01", "risk_level": "MEDIUM",
            },
            "customer_master": [
                {"customer_hash": f"hash_{i}", "tenant_id": TENANT_ID,
                 "is_minor": False, "data_principal_type": "individual",
                 "account_status": "active", "kyc_status": "verified",
                 "country": "IN", "created_at": "2024-01-01"}
                for i in range(250)
            ],
            "consent_records": [
                {"consent_hash": f"ch_{i}", "customer_hash": f"hash_{i}",
                 "tenant_id": TENANT_ID, "consent_status": "active",
                 "consent_date": "2024-01-01", "expiry_date": "2025-01-01",
                 "withdrawal_date": None, "consented_purpose": "loan_processing",
                 "consent_version": "v1.0", "notice_provided": True,
                 "is_bundled": False, "consent_channel": "app",
                 "guardian_consent_hash": None}
                for i in range(320)
            ],
            "transaction_events": [],
            "access_logs": [],
            "data_lifecycle": [
                {"lifecycle_hash": f"lh_{i}", "customer_hash": f"hash_{i}",
                 "tenant_id": TENANT_ID, "data_category": "kyc_documents",
                 "retention_expiry_date": "2023-06-01", "retention_status": "active",
                 "purpose_completed": False, "erasure_requested": False,
                 "erasure_date": None, "legal_hold_flag": False,
                 "erasure_request_source": None}
                for i in range(5)
            ],
            "security_events": [],
            "dsar_requests": [],
            "system_inventory": [
                {"system_hash": f"sh_{i}", "tenant_id": TENANT_ID,
                 "system_name": f"Sys {i}", "system_type": "crm",
                 "pii_stored": True, "encryption_enabled": True,
                 "access_control_enabled": True, "data_processor_type": "internal",
                 "retention_policy_applied": True, "dpa_signed": False,
                 "dpa_expiry_date": None}
                for i in range(12)
            ],
            "policies": [
                {"policy_hash": f"ph_{i}", "tenant_id": TENANT_ID,
                 "policy_type": "retention", "policy_name": f"Pol {i}",
                 "policy_value_numeric": 365, "policy_value_unit": "days",
                 "effective_date": "2024-01-01", "last_updated": "2024-06-01",
                 "is_active": True}
                for i in range(6)
            ],
        }

        result = write_tenant_data(TENANT_ID, data)

        # Verify row counts match input
        assert result["governance_config"] == 1
        assert result["customer_master"] == 250, f"Expected 250, got {result['customer_master']}"
        assert result["consent_records"] == 320, f"Expected 320, got {result['consent_records']}"
        assert result["data_lifecycle"] == 5, f"Expected 5, got {result['data_lifecycle']}"
        assert result["system_inventory"] == 12, f"Expected 12, got {result['system_inventory']}"
        assert result["policies"] == 6, f"Expected 6, got {result['policies']}"


# ═══════════════════════════════════════════════════════════════
# TEST — Governance config remains single-row dict
# ═══════════════════════════════════════════════════════════════

class TestGovernanceConfigSingleRow:
    def test_governance_returns_dict(self):
        df = _make_df([{
            "tenant_id": TENANT_ID, "tenant_name": "Test Corp",
            "grievance_endpoint_available": True, "dpo_assigned": True,
            "audit_frequency_days": 90, "last_audit_date": "2024-01-01",
            "risk_level": "MEDIUM",
        }])
        result = anonymize_dataframe(df, "governance_config", TENANT_ID)
        assert isinstance(result, dict), "governance_config must return a dict, not a list"

    def test_empty_governance_returns_dict(self):
        df = pd.DataFrame()
        result = anonymize_dataframe(df, "governance_config", TENANT_ID)
        assert isinstance(result, dict)

    def test_empty_multirow_table_returns_list(self):
        df = pd.DataFrame()
        for table in ["customer_master", "consent_records", "transaction_events",
                       "access_logs", "data_lifecycle", "security_events",
                       "dsar_requests", "system_inventory", "policies"]:
            result = anonymize_dataframe(df, table, TENANT_ID)
            assert isinstance(result, list), f"Empty {table} must return [], got {type(result)}"


# ═══════════════════════════════════════════════════════════════
# TEST — Boolean parsing
# ═══════════════════════════════════════════════════════════════

class TestBooleanParsing:
    def test_false_string_not_truthy(self):
        df = _make_df([{
            "customer_id": "CUST-001", "tenant_id": TENANT_ID,
            "is_minor": "false", "data_principal_type": "individual",
            "account_status": "active", "kyc_status": "verified",
            "country": "IN", "created_at": "2024-01-15", "dob": "1990-01-01",
        }])
        result = anonymize_dataframe(df, "customer_master", TENANT_ID)
        assert result[0]["is_minor"] is False, "'false' string must parse to False"

    def test_true_string_is_truthy(self):
        df = _make_df([{
            "customer_id": "CUST-002", "tenant_id": TENANT_ID,
            "is_minor": "true", "data_principal_type": "individual",
            "account_status": "active", "kyc_status": "verified",
            "country": "IN", "created_at": "2024-01-15", "dob": "1990-01-01",
        }])
        result = anonymize_dataframe(df, "customer_master", TENANT_ID)
        assert result[0]["is_minor"] is True
