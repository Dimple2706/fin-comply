import bcrypt
import psycopg
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from src.api.auth import ALGORITHM, SECRET_KEY, TOKEN_AUDIENCE, TOKEN_ISSUER
from src.api.main import app
from src.api.routes import get_db_connection


client = TestClient(app)
TEST_USER_PREFIX = "authsafe_"
TEST_TENANTS = ("AUTHSAFE-900", "AUTHSAFE-901", "AUTHSAFE-902", "AUTHSAFE-EXISTING")


def valid_registration(**overrides):
    body = {
        "name": "Authentication Test",
        "email": "authsafe@example.test",
        "username": "authsafe_owner",
        "password": "Secure1!Password",
        "tenant_id": "AUTHSAFE-900",
        "tenant_name": "Authentication Test Ltd",
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def clean_auth_test_rows():
    def cleanup():
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.users WHERE LOWER(username) LIKE %s",
                    (TEST_USER_PREFIX + "%",),
                )
                cur.execute(
                    "DELETE FROM public.governance_config WHERE tenant_id = ANY(%s)",
                    (list(TEST_TENANTS),),
                )
            conn.commit()

    cleanup()
    yield
    cleanup()


def test_register_login_me_and_password_hash():
    registration = client.post("/auth/register", json=valid_registration())
    assert registration.status_code == 201, registration.text
    public_user = registration.json()
    assert public_user["username"] == "authsafe_owner"
    assert public_user["tenant_id"] == "AUTHSAFE-900"
    assert "password" not in public_user
    assert "password_hash" not in public_user

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM public.users WHERE username = %s",
                ("authsafe_owner",),
            )
            stored_hash = cur.fetchone()["password_hash"]
    assert stored_hash != "Secure1!Password"
    assert bcrypt.checkpw(b"Secure1!Password", stored_hash.encode("utf-8"))

    login = client.post(
        "/auth/login",
        json={"username": "AUTHSAFE_OWNER", "password": "Secure1!Password"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    claims = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=TOKEN_AUDIENCE,
        issuer=TOKEN_ISSUER,
    )
    assert claims["sub"] == "authsafe_owner"
    assert claims.get("exp") and claims.get("iat") and claims.get("jti")

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["tenant_id"] == "AUTHSAFE-900"


def test_duplicate_username_email_and_tenant_are_rejected():
    assert client.post("/auth/register", json=valid_registration()).status_code == 201

    duplicate_username = client.post(
        "/auth/register",
        json=valid_registration(
            username="AUTHSAFE_OWNER",
            email="different@example.test",
            tenant_id="AUTHSAFE-901",
        ),
    )
    assert duplicate_username.status_code == 409

    duplicate_email = client.post(
        "/auth/register",
        json=valid_registration(
            username="authsafe_second",
            email="AUTHSAFE@EXAMPLE.TEST",
            tenant_id="AUTHSAFE-902",
        ),
    )
    assert duplicate_email.status_code == 409

    duplicate_tenant = client.post(
        "/auth/register",
        json=valid_registration(
            username="authsafe_third",
            email="third@example.test",
        ),
    )
    assert duplicate_tenant.status_code == 409
    assert "already exists or is assigned" in duplicate_tenant.json()["detail"]


def test_existing_company_tenant_cannot_be_self_claimed():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.governance_config
                    (tenant_id, tenant_name, audit_frequency_days)
                VALUES (%s, %s, %s)
                """,
                ("AUTHSAFE-EXISTING", "Existing Company", 90),
            )
        conn.commit()

    response = client.post(
        "/auth/register",
        json=valid_registration(tenant_id="AUTHSAFE-EXISTING"),
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", " "),
        ("email", "not-an-email"),
        ("username", "bad username"),
        ("password", "weakpass"),
        ("password", "A1!" + "x" * 70),
        ("tenant_id", "BAD TENANT"),
        ("tenant_name", " "),
    ],
)
def test_registration_input_validation(field, value):
    response = client.post(
        "/auth/register",
        json=valid_registration(**{field: value}),
    )
    assert response.status_code == 422


def test_wrong_password_inactive_user_and_database_constraints():
    assert client.post("/auth/register", json=valid_registration()).status_code == 201

    wrong_password = client.post(
        "/auth/login",
        json={"username": "authsafe_owner", "password": "Wrong1!Password"},
    )
    missing_user = client.post(
        "/auth/login",
        json={"username": "authsafe_missing", "password": "Wrong1!Password"},
    )
    assert wrong_password.status_code == missing_user.status_code == 401
    assert wrong_password.json()["detail"] == missing_user.json()["detail"]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.users SET is_active = FALSE WHERE username = %s",
                ("authsafe_owner",),
            )
        conn.commit()
    inactive = client.post(
        "/auth/login",
        json={"username": "authsafe_owner", "password": "Secure1!Password"},
    )
    assert inactive.status_code == 401

    with pytest.raises(psycopg.errors.CheckViolation):
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.users
                        (name, email, username, password_hash, role, authorized_tenants)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        "Invalid Role",
                        "invalid-role@example.test",
                        "authsafe_invalid",
                        bcrypt.hashpw(b"Secure1!Password", bcrypt.gensalt()).decode(),
                        "superadmin",
                        ["AUTHSAFE-901"],
                    ),
                )
