import os

# Tests must never inherit the application's real DB_NAME from .env.  Set the
# isolated database before importing the FastAPI app because its connection
# settings are captured at module-import time.
TEST_DB_NAME = os.getenv("FINCOMPLY_TEST_DB_NAME", "dpdp_test_isolated").strip()
if "test" not in TEST_DB_NAME.lower():
    raise RuntimeError(
        "Refusing to run tests against a non-test database. "
        "FINCOMPLY_TEST_DB_NAME must contain the word 'test'."
    )
os.environ["DB_NAME"] = TEST_DB_NAME
os.environ["ENVIRONMENT"] = "test"

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.auth import AuthUser, authenticate_user


@pytest.fixture(autouse=True, scope="session")
def test_runtime_environment():
    """Assert that test-only credentials and DB isolation remain active."""
    assert os.environ.get("ENVIRONMENT") == "test"
    assert os.environ.get("DB_NAME") == TEST_DB_NAME
    yield

@pytest.fixture
def authorized_client():
    """
    Factory fixture returning a function to create an authenticated client
    bound to a specific tenant and role using official authentication mechanisms.
    """
    def _create_client(tenant_id: str, role: str = "admin"):
        user = AuthUser(
            id=1,
            username=f"user-{tenant_id}",
            name="Test User",
            email="test@example.invalid",
            role=role,
            authorized_tenants=[tenant_id],
        )
        app.dependency_overrides[authenticate_user] = lambda: user
        return TestClient(app)

    yield _create_client
    app.dependency_overrides.pop(authenticate_user, None)
