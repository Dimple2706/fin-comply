"""
src/api/auth_routes.py
======================
FastAPI router providing authentication endpoints for Fin-Comply.

Routes:
  POST /auth/token  — OAuth2 password flow; returns JWT access token
  GET  /auth/me     — Returns the currently authenticated user's profile
"""

from __future__ import annotations

import os
import logging
import psycopg
from psycopg.rows import dict_row

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from src.governance.auth import (
    verify_password,
    create_access_token,
    get_current_user,
)
from src.governance.audit_logger import log_event

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# ── DB connection ─────────────────────────────────────────────────────────────

def _get_db_conn() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "compliance_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_router.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    OAuth2 password flow login endpoint.

    Accepts form fields: username, password.
    Returns an access_token (Bearer JWT) on success.
    Logs both successful and failed login attempts to the audit log.
    """
    # Query user from DB
    try:
        with _get_db_conn() as conn:
            row = conn.execute(
                "SELECT username, password_hash, role, full_name, is_active "
                "FROM users WHERE username = %s",
                [form_data.username],
            ).fetchone()
    except Exception as exc:
        log.error("[auth_routes] DB error during login for '%s': %s", form_data.username, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    # Validate credentials
    if not row or not verify_password(form_data.password, row["password_hash"]):
        log_event(
            "login_failed",
            details={
                "username": form_data.username,
                "reason": "invalid credentials",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not row["is_active"]:
        log_event(
            "login_failed",
            details={
                "username": form_data.username,
                "reason": "account disabled",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Issue token
    token = create_access_token(
        data={"sub": row["username"], "role": row["role"]}
    )

    log_event(
        "login_success",
        details={
            "username": row["username"],
            "role": row["role"],
        },
        user=row["username"],
    )

    log.info("[auth_routes] Login success: %s (%s)", row["username"], row["role"])

    return {
        "access_token": token,
        "token_type":   "bearer",
        "username":     row["username"],
        "role":         row["role"],
        "full_name":    row["full_name"],
    }


@auth_router.get("/me")
async def get_me(
    current_user: dict = Depends(get_current_user),
):
    """Returns the currently authenticated user's profile."""
    return current_user
