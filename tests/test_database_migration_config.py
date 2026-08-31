import pytest

from db.apply_schema_fresh import connection_env_from_url


def test_connection_env_uses_exact_database_from_url():
    env = connection_env_from_url(
        "postgresql://audit_user:encoded%20password@db.internal:5544/isolated_audit"
    )

    assert env["DB_HOST"] == "db.internal"
    assert env["DB_PORT"] == "5544"
    assert env["DB_NAME"] == "isolated_audit"
    assert env["DB_USER"] == "audit_user"
    assert env["DB_PASSWORD"] == "encoded password"
    assert env["DATABASE_URL"].endswith("/isolated_audit")
    assert env["DPDP_TEST_DATABASE_URL"].endswith("/isolated_audit")


@pytest.mark.parametrize(
    "url",
    [
        "mysql://user:password@localhost/db",
        "postgresql://user:password@localhost",
    ],
)
def test_connection_env_rejects_unsafe_or_incomplete_urls(url):
    with pytest.raises(ValueError):
        connection_env_from_url(url)
