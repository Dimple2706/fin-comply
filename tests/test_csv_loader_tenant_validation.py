import pytest
import pandas as pd
from pathlib import Path
import tempfile
from unittest.mock import patch

from src.anonymization.csv_loader import load_tenant_csvs, TenantValidationError, EXPECTED_FILES

@pytest.fixture
def temp_csv_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)

@pytest.fixture
def mock_expected_files():
    # Only require one file for these tests to simplify
    with patch("src.anonymization.csv_loader.EXPECTED_FILES", {"dummy_table": "dummy.csv"}):
        yield

def test_all_rows_correct_tenant(temp_csv_dir, mock_expected_files):
    df = pd.DataFrame({
        "tenant_id": ["TENANT-A", "TENANT-A"],
        "other_col": [1, 2]
    })
    df.to_csv(temp_csv_dir / "dummy.csv", index=False)
    
    result = load_tenant_csvs(temp_csv_dir, "TENANT-A")
    assert "dummy_table" in result
    assert len(result["dummy_table"]) == 2
    assert all(result["dummy_table"]["tenant_id"] == "TENANT-A")

def test_all_rows_another_tenant(temp_csv_dir, mock_expected_files):
    df = pd.DataFrame({
        "tenant_id": ["TENANT-B", "TENANT-B"],
        "other_col": [1, 2]
    })
    df.to_csv(temp_csv_dir / "dummy.csv", index=False)
    
    with pytest.raises(TenantValidationError) as exc:
        load_tenant_csvs(temp_csv_dir, "TENANT-A")
    assert exc.value.error_code == "TENANT_MISMATCH"
    assert exc.value.expected_tenant == "TENANT-A"
    assert exc.value.supplied_tenant == "TENANT-B"

def test_one_row_another_tenant(temp_csv_dir, mock_expected_files):
    df = pd.DataFrame({
        "tenant_id": ["TENANT-A", "TENANT-B", "TENANT-A"],
        "other_col": [1, 2, 3]
    })
    df.to_csv(temp_csv_dir / "dummy.csv", index=False)
    
    with pytest.raises(TenantValidationError) as exc:
        load_tenant_csvs(temp_csv_dir, "TENANT-A")
    assert exc.value.error_code == "TENANT_MISMATCH"
    assert exc.value.supplied_tenant == "TENANT-B"
    assert exc.value.row_number == 3  # Header is 1, data row 1 is 2, data row 2 is 3

def test_multiple_different_tenant_ids(temp_csv_dir, mock_expected_files):
    df = pd.DataFrame({
        "tenant_id": ["TENANT-B", "TENANT-C"],
        "other_col": [1, 2]
    })
    df.to_csv(temp_csv_dir / "dummy.csv", index=False)
    
    with pytest.raises(TenantValidationError) as exc:
        load_tenant_csvs(temp_csv_dir, "TENANT-A")
    assert exc.value.error_code == "TENANT_MISMATCH"
    assert exc.value.supplied_tenant == "TENANT-B"

def test_missing_tenant_id_column(temp_csv_dir, mock_expected_files):
    df = pd.DataFrame({
        "other_col": [1, 2]
    })
    df.to_csv(temp_csv_dir / "dummy.csv", index=False)
    
    with pytest.raises(TenantValidationError) as exc:
        load_tenant_csvs(temp_csv_dir, "TENANT-A")
    assert exc.value.error_code == "MISSING_TENANT_COLUMN"

def test_blank_tenant_id(temp_csv_dir, mock_expected_files):
    df = pd.DataFrame({
        "tenant_id": ["TENANT-A", "", "TENANT-A"],
        "other_col": [1, 2, 3]
    })
    df.to_csv(temp_csv_dir / "dummy.csv", index=False)
    
    with pytest.raises(TenantValidationError) as exc:
        load_tenant_csvs(temp_csv_dir, "TENANT-A")
    assert exc.value.error_code == "BLANK_TENANT_ID"
    
def test_null_tenant_id(temp_csv_dir, mock_expected_files):
    df = pd.DataFrame({
        "tenant_id": ["TENANT-A", None],
        "other_col": [1, 2]
    })
    df.to_csv(temp_csv_dir / "dummy.csv", index=False)
    
    with pytest.raises(TenantValidationError) as exc:
        load_tenant_csvs(temp_csv_dir, "TENANT-A")
    assert exc.value.error_code == "BLANK_TENANT_ID"

def test_surrounding_whitespace(temp_csv_dir, mock_expected_files):
    df = pd.DataFrame({
        "tenant_id": ["  TENANT-A  ", "TENANT-A"],
        "other_col": [1, 2]
    })
    df.to_csv(temp_csv_dir / "dummy.csv", index=False)
    
    result = load_tenant_csvs(temp_csv_dir, "TENANT-A")
    assert all(result["dummy_table"]["tenant_id"] == "TENANT-A")

def test_different_letter_case_rejected(temp_csv_dir, mock_expected_files):
    df = pd.DataFrame({
        "tenant_id": ["tenant-a", "TENANT-A"],
        "other_col": [1, 2]
    })
    df.to_csv(temp_csv_dir / "dummy.csv", index=False)
    
    with pytest.raises(TenantValidationError) as exc:
        load_tenant_csvs(temp_csv_dir, "TENANT-A")
    assert exc.value.error_code == "TENANT_MISMATCH"
    assert exc.value.supplied_tenant == "tenant-a"
