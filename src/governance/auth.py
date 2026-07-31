"""
src/governance/auth.py
======================
JWT-based authentication and role-based access control for Fin-Comply.

Uses python-jose for JWT encoding/decoding and passlib CryptContext
for password hashing and verification.

Public API:
  verify_password(plain, hashed)           -> bool
  create_access_token(data)                -> str
  get_current_user(token)                  -> dict  [FastAPI dependency]
  require_admin(current_user)              -> dict  [FastAPI dependency]
  require_reviewer_or_admin(current_user)  -> dict  [FastAPI dependency]
  require_any_role(current_user)           -> dict  [FastAPI dependency]
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext  # pyrefly: ignore [missing-import]
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from src.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

load_dotenv()

log = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_db_conn() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "compliance_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )


# ── OAuth2 scheme ─────────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


# ── PART A — Password and token utilities ─────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a hashed password using passlib CryptContext.
    """
    try:
        return pwd_context.verify(plain, hashed)
    except Exception as exc:
        log.warning("[auth] verify_password error: %s", exc)
        return False



def create_access_token(data: dict) -> str:
    """
    Encode a JWT with a UTC expiry. 'data' should contain at least {"sub": username}.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ── PART B — FastAPI dependency: get current user ─────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> dict:
    """
    Decode the Bearer token, look up the user in the database, and return
    a dict with username, role, full_name, is_active.

    Raises HTTP 401 on any failure (invalid token, unknown user, inactive).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        with _get_db_conn() as conn:
            row = conn.execute(
                "SELECT username, role, full_name, is_active "
                "FROM users WHERE username = %s",
                [username],
            ).fetchone()
    except Exception as exc:
        log.error("[auth] DB error during token validation: %s", exc)
        raise credentials_exception

    if row is None or not row["is_active"]:
        raise credentials_exception

    return dict(row)


# ── PART C — Role requirement dependencies ────────────────────────────────────

def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Allows only users with role == 'admin'. Raises HTTP 403 otherwise."""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


def require_reviewer_or_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Allows users with role in ('admin', 'reviewer'). Raises HTTP 403 otherwise."""
    if current_user["role"] not in ("admin", "reviewer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer or Admin role required",
        )
    return current_user


def require_any_role(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Allows any authenticated user regardless of role."""
    return current_user
