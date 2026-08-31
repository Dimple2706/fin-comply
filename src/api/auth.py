"""
src/api/auth.py
───────────────
Database-backed JWT authentication for Fin-Comply.

Flow:
  POST /auth/register  →  hash password, store in `users` table
  POST /auth/login     →  verify credentials, return signed JWT
  Protected routes     →  validate Bearer JWT, return AuthUser
"""

import os
import json
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

import bcrypt

# ── Password helpers (using bcrypt directly — passlib is incompatible with bcrypt 5.x) ──

def _hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt. Returns a UTF-8 string."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False
from jose import JWTError, jwt

from pydantic import BaseModel
from fastapi import Security, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────

_DEV_SECRET = "fin-comply-dev-secret-change-in-production"
SECRET_KEY = os.getenv("SECRET_KEY", _DEV_SECRET)
if os.getenv("ENVIRONMENT", "").strip().lower() != "test" and (
    SECRET_KEY == _DEV_SECRET or len(SECRET_KEY) < 32
):
    raise RuntimeError(
        "SECRET_KEY must be a non-default value of at least 32 characters."
    )
ALGORITHM     = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours
TOKEN_ISSUER = os.getenv("TOKEN_ISSUER", "fincomply-api")
TOKEN_AUDIENCE = os.getenv("TOKEN_AUDIENCE", "fincomply-web")

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "compliance_db")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# ── Password hashing ──────────────────────────────────────────────────────────

bearer_auth = HTTPBearer(auto_error=False)


# ── Models ────────────────────────────────────────────────────────────────────

class AuthUser(BaseModel):
    id: int
    username: str
    name: str
    email: str
    role: str                        # "admin" | "reviewer" | "auditor"
    authorized_tenants: List[str]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_db_connection():
    return psycopg.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        autocommit=False,
        row_factory=dict_row,
    )


def _ensure_users_table():
    """Create the users table if it does not exist yet."""
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.users (
                    id                  SERIAL          PRIMARY KEY,
                    name                VARCHAR(128)    NOT NULL,
                    email               VARCHAR(256)    NOT NULL UNIQUE,
                    username            VARCHAR(64)     NOT NULL UNIQUE,
                    password_hash       TEXT            NOT NULL,
                    role                VARCHAR(32)     NOT NULL DEFAULT 'admin',
                    authorized_tenants  TEXT[]          NOT NULL DEFAULT '{}',
                    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
                    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                    CONSTRAINT users_name_valid CHECK (
                        name = BTRIM(name) AND CHAR_LENGTH(name) BETWEEN 2 AND 128
                    ),
                    CONSTRAINT users_email_valid CHECK (
                        email = LOWER(BTRIM(email))
                        AND CHAR_LENGTH(email) BETWEEN 3 AND 254
                        AND email ~ '^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$'
                    ),
                    CONSTRAINT users_username_valid CHECK (
                        username = BTRIM(username)
                        AND username ~ '^[A-Za-z0-9_-]{3,64}$'
                    ),
                    CONSTRAINT users_password_hash_valid CHECK (
                        password_hash ~ '^\\$2[aby]\\$'
                    ),
                    CONSTRAINT users_role_valid CHECK (
                        role IN ('admin', 'reviewer', 'auditor')
                    ),
                    CONSTRAINT users_have_tenant CHECK (
                        CARDINALITY(authorized_tenants) > 0
                    )
                )
            """)
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS users_username_ci_key "
                "ON public.users (LOWER(username));"
            )
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS users_email_ci_key "
                "ON public.users (LOWER(email));"
            )
        conn.commit()


def get_user_by_username(username: str) -> Optional[dict]:
    """Return the user row dict for the given username, or None."""
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.users "
                    "WHERE LOWER(username) = LOWER(%s) AND is_active = TRUE",
                    (username.strip(),),
                )
                return cur.fetchone()
    except Exception as e:
        logging.error(f"[auth] DB lookup failed for '{username}': {e}")
        return None


def get_user_by_email(email: str) -> Optional[dict]:
    """Return the user row dict for the given email, or None."""
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.users WHERE email = %s",
                    (email.strip().lower(),),
                )
                return cur.fetchone()
    except Exception as e:
        logging.error(f"[auth] DB email lookup failed for '{email}': {e}")
        return None


def create_user_in_db(name: str, email: str, username: str,
                      password: str, role: str = "admin",
                      tenant_id: str = "", tenant_name: str = "") -> dict:
    """
    Hash the password and insert a new user row.
    The user is immediately authorized for their company's tenant_id.
    Returns the created user dict.
    Raises HTTPException on duplicate username/email or invalid tenant_id.
    """
    _ensure_users_table()

    # Validate tenant_id format (same rules as verify_tenant_access)
    clean_tid = tenant_id.strip().upper()
    if not clean_tid or len(clean_tid) > 64 or not all(
        c.isalnum() or c in "-_" for c in clean_tid
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Tenant ID format. Use only letters, numbers, hyphens (-) and underscores (_), max 64 characters. Example: HDFC-001",
        )

    hashed = _hash_password(password)
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                # Serialize registrations for the same tenant and prevent a
                # new account from self-assigning an existing company's data.
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (clean_tid,))
                cur.execute(
                    """
                    SELECT (EXISTS (
                        SELECT 1 FROM public.governance_config WHERE tenant_id = %s
                    ) OR EXISTS (
                        SELECT 1 FROM public.users WHERE %s = ANY(authorized_tenants)
                    )) AS tenant_taken
                    """,
                    (clean_tid, clean_tid),
                )
                if cur.fetchone()["tenant_taken"]:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Tenant '{clean_tid}' already exists or is assigned. "
                            "Ask the tenant administrator to grant access."
                        ),
                    )
                cur.execute(
                    """
                    INSERT INTO public.users
                        (name, email, username, password_hash, role, authorized_tenants)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, name, email, username, role, authorized_tenants, created_at
                    """,
                    (name.strip(), email.strip().lower(),
                     username.strip(), hashed, role, [clean_tid]),
                )
                row = cur.fetchone()
            conn.commit()
        return row
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as e:
        constraint_name = (getattr(e.diag, "constraint_name", "") or "").lower()
        if "username" in constraint_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{username}' is already taken. Please choose another.",
            )
        if "email" in constraint_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An account with email '{email}' already exists.",
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate entry.")
    except Exception as e:
        logging.error(f"[auth] create_user_in_db failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user. Please try again.",
        )


# ── Password & token helpers ──────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return _verify_password(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "nbf": now,
            "jti": str(uuid.uuid4()),
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ── FastAPI dependency — validates Bearer JWT ─────────────────────────────────

def authenticate_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth),
) -> AuthUser:
    """
    Validates a Bearer JWT from the Authorization header.
    Returns AuthUser if valid, raises HTTP 401 otherwise.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise credentials_exception

    token = credentials.credentials.strip()

    # Backward-compatible test credentials are deliberately unavailable in
    # every non-test environment.  This keeps integration tests independent
    # from the users table without creating a production authentication bypass.
    if os.getenv("ENVIRONMENT", "").strip().lower() == "test":
        raw_test_credentials = os.getenv("FINCOMPLY_TEST_CREDENTIALS", "")
        if raw_test_credentials:
            try:
                test_credentials = json.loads(raw_test_credentials)
                test_user = test_credentials.get(
                    hashlib.sha256(token.encode("utf-8")).hexdigest()
                )
            except (json.JSONDecodeError, TypeError, AttributeError):
                test_user = None
            if test_user:
                return AuthUser(
                    id=int(test_user.get("id", 0)),
                    username=str(test_user.get("username", "test-user")),
                    name=str(test_user.get("name", "Test User")),
                    email=str(test_user.get("email", "test@example.invalid")),
                    role=str(test_user.get("role", "auditor")),
                    authorized_tenants=list(test_user.get("authorized_tenants") or []),
                )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=TOKEN_AUDIENCE,
            issuer=TOKEN_ISSUER,
        )
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_row = get_user_by_username(username)
    if not user_row:
        raise credentials_exception

    return AuthUser(
        id=user_row["id"],
        username=user_row["username"],
        name=user_row["name"],
        email=user_row["email"],
        role=user_row["role"],
        authorized_tenants=list(user_row.get("authorized_tenants") or []),
    )


# ── Role-based access control ─────────────────────────────────────────────────

def require_role(allowed_roles: List[str]):
    """Factory dependency: checks that the authenticated user has one of allowed_roles."""
    def role_checker(user: AuthUser = Depends(authenticate_user)) -> AuthUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user.role}' is not authorized. Required: {allowed_roles}.",
            )
        return user
    return role_checker


def verify_tenant_access(tenant_id: str, user: AuthUser) -> AuthUser:
    """
    Validates the authenticated user is authorized for the requested tenant_id.
    Every role, including admin, is restricted to its explicitly authorized
    tenant list.  The admin role controls operations, not tenant scope.
    """
    clean_tenant_id = tenant_id.strip()
    if not clean_tenant_id or len(clean_tenant_id) > 64 or not all(
        c.isalnum() or c in "-_" for c in clean_tenant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format or length.",
        )

    if clean_tenant_id not in user.authorized_tenants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: You are not authorized for tenant '{clean_tenant_id}'.",
        )
    return user


# ── Predefined role shortcuts ─────────────────────────────────────────────────

require_admin         = require_role(["admin"])
require_reviewer      = require_role(["admin", "reviewer"])
require_authenticated = require_role(["admin", "reviewer", "auditor"])
