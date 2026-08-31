import hashlib
import hmac
import os
import re
from typing import Optional

def validate_hmac_secret_or_fail() -> str:
    secret = os.getenv("ANONYMIZATION_HMAC_SECRET")
    is_prod = os.getenv("ENV") == "production"
    
    if is_prod:
        if not secret:
            raise RuntimeError("Fatal: ANONYMIZATION_HMAC_SECRET environment variable is required in production.")
        if len(secret) < 32:
            raise RuntimeError("Fatal: ANONYMIZATION_HMAC_SECRET must be at least 32 characters long in production.")
    else:
        # Development/Test fallback
        if not secret:
            secret = "dpdp-salt-2024-default-dev-reviewer-secret-32-chars"
            os.environ["ANONYMIZATION_HMAC_SECRET"] = secret
            
    return secret

# Validate and load secret
HMAC_SECRET = validate_hmac_secret_or_fail()

def hash_id(value: str, tenant_id: str, version: Optional[str] = None) -> str:
    """
    Computes tenant-scoped HMAC-SHA-256 for a raw identifier.
    Supports version 'v2' (default: v2:<64 hex>) and 'v1' (legacy: v1:<12 hex>).
    """
    if version is None:
        version = os.getenv("HASH_VERSION", "v2")
    # Force secret reload in case environment was modified during test run
    secret = os.getenv("ANONYMIZATION_HMAC_SECRET", HMAC_SECRET)
    key = f"{secret}:{tenant_id}".encode()
    msg = str(value).encode()
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    if version == "v2":
        return f"v2:{digest}"
    elif version == "v1":
        return f"v1:{digest[:12]}"
    raise ValueError(f"Unknown hashing version: {version}")

def validate_hash_string(h: str) -> bool:
    """
    Strictly validates format, length, and hex characters for a pre-hashed string.
    """
    h_str = str(h).strip()
    if h_str.startswith("v2:"):
        digest = h_str[3:]
        return len(digest) == 64 and bool(re.match(r"^[0-9a-fA-F]+$", digest))
    elif h_str.startswith("v1:"):
        digest = h_str[3:]
        return len(digest) == 12 and bool(re.match(r"^[0-9a-fA-F]+$", digest))
    # Legacy unprefixed 12 hex characters
    return len(h_str) == 12 and bool(re.match(r"^[0-9a-fA-F]+$", h_str))

def check_database_migration_complete():
    # If ENV = "production", query DB schema directly to verify customer_hash has varchar(67)+ width
    if os.getenv("ENV") == "production":
        import psycopg
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise RuntimeError("Fatal: DATABASE_URL is required in production.")
        try:
            conn = psycopg.connect(db_url)
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT character_maximum_length 
                        FROM information_schema.columns 
                        WHERE table_name = 'customer_master' AND column_name = 'customer_hash';
                    """)
                    row = cur.fetchone()
                    if not row or row[0] is None or row[0] < 67:
                        raise RuntimeError("Fatal: Hashing implementation is upgraded to secure v2 (HMAC-SHA-256 with 67 characters), but database schema columns are still character(12). Production use is blocked until schema migration is complete.")
            finally:
                conn.close()
        except Exception as e:
            if "Production use is blocked" in str(e):
                raise
            raise RuntimeError(f"Fatal: Database validation check failed at startup: {e}")

