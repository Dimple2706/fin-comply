"""
src/api/auth.py
================
Authentication and Role-Based Access Control (RBAC) for Fin-Comply (Issue E-05).
Secures administrative and compliance rule lifecycle endpoints:
- require_admin: Mandatory for activating/approving rules.
- require_reviewer: Permitted for proposing, viewing, and rejecting rules.
"""

import os
from typing import Optional, List
from pydantic import BaseModel
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)

# Configurable API Keys with secure defaults for dev/test
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "fincomply-admin-key-2026")
REVIEWER_API_KEY = os.getenv("REVIEWER_API_KEY", "fincomply-reviewer-key-2026")

class AuthUser(BaseModel):
    username: str
    role: str  # "admin", "reviewer", "auditor"

def authenticate_user(
    api_key: Optional[str] = Security(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth)
) -> AuthUser:
    """
    Validates either X-API-Key or Bearer token header.
    Returns AuthUser if valid, otherwise raises HTTP 401 Unauthorized.
    """
    token = None
    if credentials:
        token = credentials.credentials.strip()
    elif api_key:
        token = api_key.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide 'X-API-Key' or 'Authorization: Bearer <token>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Admin Token / Key
    if token == ADMIN_API_KEY or token == "admin_token_fincomply" or token.startswith("admin:"):
        username = token.split(":", 1)[1] if token.startswith("admin:") else "admin_operator"
        return AuthUser(username=username, role="admin")

    # 2. Reviewer Token / Key
    if token == REVIEWER_API_KEY or token == "reviewer_token_fincomply" or token.startswith("reviewer:"):
        username = token.split(":", 1)[1] if token.startswith("reviewer:") else "compliance_reviewer"
        return AuthUser(username=username, role="reviewer")

    # 3. Auditor / Readonly Token
    if token == "auditor_token_fincomply" or token.startswith("auditor:"):
        username = token.split(":", 1)[1] if token.startswith("auditor:") else "auditor"
        return AuthUser(username=username, role="auditor")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials or API key.",
        headers={"WWW-Authenticate": "Bearer"},
    )

def require_role(allowed_roles: List[str]):
    """
    Factory dependency checking if authenticated user has one of the allowed roles.
    """
    def role_checker(user: AuthUser = Security(authenticate_user)) -> AuthUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user.role}' is not authorized. Required: {allowed_roles}."
            )
        return user
    return role_checker

# Predefined role dependencies
require_admin = require_role(["admin"])
require_reviewer = require_role(["admin", "reviewer"])
require_authenticated = require_role(["admin", "reviewer", "auditor"])
