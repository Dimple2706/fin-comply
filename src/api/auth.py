import os
import json
import hashlib
import hmac
import logging
from typing import Optional, List
from pydantic import BaseModel
from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)

class AuthUser(BaseModel):
    username: str
    role: str  # "admin", "reviewer", "auditor"
    authorized_tenants: List[str]

# Global cache or dictionary for loaded credentials
_CREDENTIALS_DB = {}

def load_credentials():
    global _CREDENTIALS_DB
        
    creds_json = os.getenv("FINCOMPLY_CREDENTIALS")
    if creds_json:
        try:
            _CREDENTIALS_DB = json.loads(creds_json)
        except Exception as e:
            logging.error(f"Failed to parse FINCOMPLY_CREDENTIALS: {e}")
            _CREDENTIALS_DB = {}
    else:
        test_creds_json = os.getenv("FINCOMPLY_TEST_CREDENTIALS")
        if test_creds_json:
            try:
                _CREDENTIALS_DB = json.loads(test_creds_json)
            except Exception as e:
                logging.error(f"Failed to parse FINCOMPLY_TEST_CREDENTIALS: {e}")
                _CREDENTIALS_DB = {}
        else:
            logging.warning("No authentication configuration found. Access will fail closed.")
            _CREDENTIALS_DB = {}

def get_hash(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()

def authenticate_user(
    api_key: Optional[str] = Security(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth)
) -> AuthUser:
    """
    Validates either X-API-Key or Bearer token header.
    Checks the SHA-256 hash of the token against credentials config using constant-time comparison.
    Returns AuthUser if valid, otherwise raises HTTP 401 Unauthorized.
    """
    load_credentials()
    
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

    token_hash = get_hash(token)
    
    for stored_hash, user_info in _CREDENTIALS_DB.items():
        if hmac.compare_digest(stored_hash.encode("utf-8"), token_hash.encode("utf-8")):
            return AuthUser(
                username=user_info.get("username", "unknown"),
                role=user_info.get("role", "auditor"),
                authorized_tenants=user_info.get("authorized_tenants", [])
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials or API key.",
        headers={"WWW-Authenticate": "Bearer"},
    )

def require_role(allowed_roles: List[str]):
    """
    Factory dependency checking if authenticated user has one of the allowed roles.
    """
    def role_checker(user: AuthUser = Depends(authenticate_user)) -> AuthUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user.role}' is not authorized. Required: {allowed_roles}."
            )
        return user
    return role_checker

def verify_tenant_access(tenant_id: str, user: AuthUser = Depends(authenticate_user)) -> AuthUser:
    """
    Validates that the authenticated user is explicitly authorized for the requested tenant_id.
    Also validates tenant ID format and maximum length.
    """
    clean_tenant_id = tenant_id.strip()
    if not clean_tenant_id or len(clean_tenant_id) > 64 or not all(c.isalnum() or c in "-_" for c in clean_tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format or length."
        )
        
    if clean_tenant_id not in user.authorized_tenants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: You are not authorized for tenant '{clean_tenant_id}'."
        )
        
    return user

# Predefined role dependencies
require_admin = require_role(["admin"])
require_reviewer = require_role(["admin", "reviewer"])
require_authenticated = require_role(["admin", "reviewer", "auditor"])
