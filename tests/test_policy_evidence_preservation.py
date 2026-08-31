from unittest.mock import MagicMock, patch

import pandas as pd

from src.anonymization.csv_loader import load_tenant_csvs
from src.anonymization.db_writer import write_tenant_data
from src.anonymization.field_mapper import _anonymize_policies


def test_loader_preserves_policy_value_text(tmp_path):
    policy_csv = tmp_path / "policies.csv"
    pd.DataFrame(
        [{
            "policy_id": "P1",
            "tenant_id": "TENANT-A",
            "policy_type": "encryption",
            "policy_value_text": "AES-256",
        }]
    ).to_csv(policy_csv, index=False)

    with (
        patch("src.anonymization.csv_loader.EXPECTED_FILES", {"policies": "policies.csv"}),
        patch(
            "src.anonymization.csv_loader.REQUIRED_COLUMN_GROUPS",
            {"policies": [["policy_id"], ["tenant_id"], ["policy_type"]]},
        ),
    ):
        loaded = load_tenant_csvs(tmp_path, "TENANT-A")

    assert loaded["policies"].loc[0, "policy_value_text"] == "AES-256"


def test_mapper_preserves_policy_value_text():
    mapped = _anonymize_policies(
        pd.DataFrame(
            [{
                "policy_id": "P1",
                "tenant_id": "TENANT-A",
                "policy_type": "encryption",
                "policy_name": "Encryption Policy",
                "policy_value_text": " AES-256 ",
                "is_active": True,
            }]
        ),
        "TENANT-A",
    )

    assert mapped[0]["policy_value_text"] == "AES-256"


def test_writer_inserts_policy_value_text():
    policy_data = {
        "policies": [{
            "policy_hash": "v2:" + "a" * 64,
            "tenant_id": "TENANT-A",
            "policy_type": "encryption",
            "policy_name": "Encryption Policy",
            "policy_value_numeric": None,
            "policy_value_unit": None,
            "policy_value_text": "AES-256",
            "effective_date": "2026-01-01",
            "last_updated": "2026-01-01",
            "is_active": True,
        }]
    }
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = [1]

    with patch("src.anonymization.db_writer.get_db_connection", return_value=mock_conn):
        write_tenant_data("TENANT-A", policy_data)

    insert_call = next(
        call
        for call in mock_cur.execute.call_args_list
        if "INSERT INTO policies" in call.args[0]
    )
    assert "policy_value_text" in insert_call.args[0]
    assert insert_call.args[1][6] == "AES-256"
