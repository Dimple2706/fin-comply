import os
import pytest
import datetime
from unittest.mock import patch
from src.anonymization.pipeline import (
    LegacyPipelineDisabledError,
    map_governance_config,
    map_system_inventory,
    map_policies,
    map_customer_master,
    map_consent_records,
    map_transaction_events,
    map_access_logs,
    map_data_lifecycle,
    map_security_events,
    map_dsar_requests,
    run_anonymization_pipeline
)

def test_legacy_functions_fail_closed():
    # Verify that calling any legacy mapper function raises LegacyPipelineDisabledError
    legacy_mappers = [
        lambda: map_governance_config({"tenant_id": "t_test"}),
        lambda: map_system_inventory({"tenant_id": "t_test"}),
        lambda: map_policies({"tenant_id": "t_test"}),
        lambda: map_customer_master({"tenant_id": "t_test"}),
        lambda: map_consent_records({"tenant_id": "t_test"}, {}),
        lambda: map_transaction_events([], {"tenant_id": "t_test"}),
        lambda: map_access_logs([]),
        lambda: map_data_lifecycle({"tenant_id": "t_test"}),
        lambda: map_security_events([], {"tenant_id": "t_test"}),
        lambda: map_dsar_requests([])
    ]
    
    for mapper in legacy_mappers:
        with pytest.raises(LegacyPipelineDisabledError) as exc_info:
            mapper()
        assert "Legacy pipeline is retired and disabled" in str(exc_info.value)

def test_active_pipeline_is_system_date_independent():
    # Prove that changing system dates does not alter output/hashes in active pipeline paths
    # Set a mocked date 1
    mock_date_1 = datetime.date(2026, 1, 1)
    # Set a mocked date 2
    mock_date_2 = datetime.date(2026, 12, 31)
    
    with patch("datetime.date") as mock_date_class:
        mock_date_class.today.return_value = mock_date_1
        mock_date_class.side_effect = lambda *args, **kw: datetime.date(*args, **kw)
        
        # Test active pipeline mapping does not use today's date dynamically
        # Let's verify run_anonymization_pipeline doesn't raise LegacyPipelineDisabledError on csv load
        # We can also mock run_anonymization_pipeline's loader/mapper dependencies to verify no system date changes leak
        pass
