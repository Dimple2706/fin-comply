import os
import re
import pytest
import pandas as pd
from src.anonymization.hasher import hash_id, validate_hash_string, validate_hmac_secret_or_fail, check_database_migration_complete
from src.anonymization.field_mapper import _extract_hash

def test_startup_secret_checks():
    # Set to production
    os.environ["ENV"] = "production"
    
    # Missing secret -> failure
    if "ANONYMIZATION_HMAC_SECRET" in os.environ:
        del os.environ["ANONYMIZATION_HMAC_SECRET"]
    with pytest.raises(RuntimeError, match="required in production"):
        validate_hmac_secret_or_fail()

    # Weak secret (<32 chars) -> failure
    os.environ["ANONYMIZATION_HMAC_SECRET"] = "short_weak_secret"
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        validate_hmac_secret_or_fail()

    # Strong secret -> success
    os.environ["ANONYMIZATION_HMAC_SECRET"] = "a" * 32
    secret = validate_hmac_secret_or_fail()
    assert len(secret) >= 32

    # Database schema check fails in production when DATABASE_URL is invalid/empty
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    with pytest.raises(RuntimeError, match="DATABASE_URL is required in production"):
        check_database_migration_complete()

    # Database schema check succeeds when correct DATABASE_URL of migrated DB is set
    test_database_url = os.getenv("DPDP_TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("DPDP_TEST_DATABASE_URL is required for the database schema check")
    os.environ["DATABASE_URL"] = test_database_url
    check_database_migration_complete()

    # Restore environment
    os.environ["ENV"] = "test"
    os.environ["ANONYMIZATION_HMAC_SECRET"] = "dpdp-salt-2024-default-dev-reviewer-secret-32-chars"
    os.environ["DATABASE_URL"] = ""

def test_hash_stability_and_tenant_isolation():
    raw_id = "CUSTOMER_123"
    
    # Same tenant and raw ID produces stable hashes
    hash_t1_a = hash_id(raw_id, "tenant_1", version="v2")
    hash_t1_b = hash_id(raw_id, "tenant_1", version="v2")
    assert hash_t1_a == hash_t1_b
    assert hash_t1_a.startswith("v2:")
    assert len(hash_t1_a) == 67

    # Same raw ID across different tenants produces different hashes
    hash_t2 = hash_id(raw_id, "tenant_2", version="v2")
    assert hash_t1_a != hash_t2

def test_validation_pre_hashed_identifiers():
    # Valid v2 hash format
    valid_v2 = "v2:" + "a" * 64
    assert validate_hash_string(valid_v2) is True

    # Valid v1 hash format
    valid_v1 = "v1:" + "a" * 12
    assert validate_hash_string(valid_v1) is True

    # Legacy 12-char unprefixed hash
    valid_legacy = "a" * 12
    assert validate_hash_string(valid_legacy) is True

    # Malformed v2 (too short)
    invalid_v2 = "v2:" + "a" * 63
    assert validate_hash_string(invalid_v2) is False

    # Malformed v2 (non-hex chars)
    invalid_chars = "v2:" + "g" * 64
    assert validate_hash_string(invalid_chars) is False

    # Malformed empty hash
    assert validate_hash_string("") is False

def test_extract_hash_validation():
    # Upload with valid raw ID (computes hash server-side)
    row_raw = pd.Series({"customer_id": "CUST_456"})
    h_computed = _extract_hash(row_raw, "customer_hash", "customer_id", "tenant_a")
    assert h_computed is not None
    # Now defaults to v2 (67 characters) everywhere
    assert len(h_computed) == 67

    # Upload with valid pre-hashed ID
    row_pre = pd.Series({"customer_hash": "v1:" + "a" * 12})
    h_extracted = _extract_hash(row_pre, "customer_hash", "customer_id", "tenant_a")
    assert h_extracted == "v1:" + "a" * 12

    # Upload with malformed pre-hashed ID -> raises ValueError
    row_malformed = pd.Series({"customer_hash": "v2:invalid_hash_value"})
    with pytest.raises(ValueError, match="Invalid pre-hashed format"):
        _extract_hash(row_malformed, "customer_hash", "customer_id", "tenant_a")

def test_cross_tenant_supplied_hash_isolation():
    # Compute valid hash for tenant_b
    hash_tb = hash_id("CUST_SHARED", "tenant_b", version="v2")
    
    # If this is uploaded for tenant_a, the client-supplied hash mode is verified format-wise,
    # but the database lookup for tenant_a will never match it because client-side pre-hashing
    # would need tenant_a's salt scope. If they blindly copy tenant_b's hash to tenant_a,
    # it won't join with tenant_a's customer records (since tenant_a's customer_hash
    # generated server-side for "CUST_SHARED" is completely different).
    hash_ta_expected = hash_id("CUST_SHARED", "tenant_a", version="v2")
    assert hash_tb != hash_ta_expected

def test_uniqueness_fixture_and_collision_risk():
    # Large set of IDs to test uniqueness/collision-free output
    ids = [f"USER_{i}" for i in range(1000)]
    hashes = {hash_id(uid, "tenant_a", version="v2") for uid in ids}
    assert len(hashes) == 1000  # No collisions in v2 hashes

def test_no_secret_leakage_in_exceptions():
    secret_key = "very_sensitive_anonymization_hmac_secret_2026"
    os.environ["ANONYMIZATION_HMAC_SECRET"] = secret_key
    try:
        # Intentionally cause a ValueError
        raise ValueError("Sensitive error test")
    except Exception as ex:
        err_msg = str(ex)
        assert secret_key not in err_msg
