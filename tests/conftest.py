import pytest
import os
import json
import hashlib
from fastapi.testclient import TestClient
from src.api.main import app

@pytest.fixture
def authorized_client():
    """
    Factory fixture returning a function to create an authenticated client
    bound to a specific tenant and role using official authentication mechanisms.
    """
    def _create_client(tenant_id: str, role: str = "admin"):
        token = f"token-{tenant_id}-{role}"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        
        # Load existing or initialize
        creds = {}
        env_creds = os.getenv("FINCOMPLY_TEST_CREDENTIALS")
        if env_creds:
            try:
                creds = json.loads(env_creds)
            except Exception:
                pass
        
        # Add test token
        creds[token_hash] = {
            "username": f"user-{tenant_id}",
            "role": role,
            "authorized_tenants": [tenant_id]
        }
        
        os.environ["FINCOMPLY_TEST_CREDENTIALS"] = json.dumps(creds)
        
        # Return client with auth header
        client = TestClient(app)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client
        
    return _create_client
