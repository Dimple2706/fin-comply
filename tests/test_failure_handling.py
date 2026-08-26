import os
import psycopg
import pytest
from unittest.mock import patch, MagicMock
from psycopg.rows import dict_row

from src.agent_layer.base_agent import BaseAgent
from src.agent_layer.regulation_agent import RegulationAgent
from src.agent_layer.orchestrator import run_compliance_analysis
from src.agent_layer.rule_loader import load_rules as original_load_rules
from src.agent_layer.query_builder import build_query as original_build_query

class NonCommittingConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def execute(self, *args, **kwargs):
        return self.conn.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.conn, name)

@pytest.fixture
def db_conn():
    db_url = os.environ.get("DPDP_TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("DPDP_TEST_DATABASE_URL is not set")
    conn = psycopg.connect(db_url, row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute('SET search_path TO public, "$user";')
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()

def test_single_rule_query_failure(db_conn):
    """
    Test that if a single rule query fails, the rule is marked FAILED,
    a safe error reason is recorded, and other unaffected rules still complete.
    """
    tenant_id = "tenant_a"
    wrapper = NonCommittingConnectionWrapper(db_conn)
    
    # Mock build_query to fail ONLY for DPDP-001
    def mock_build_query(rule, t_id):
        if rule["rule_id"] == "DPDP-001":
            raise ValueError("SECRET_DB_PASSWORD=12345 SQL syntax error near SELECT")
        return original_build_query(rule, t_id)

    with patch("src.agent_layer.query_builder.build_query", side_effect=mock_build_query), \
         patch("src.agent_layer.orchestrator.get_connection", return_value=wrapper):
        
        response = run_compliance_analysis(tenant_id)
        
        # Verify DPDP-001 failed
        statuses = response["rule_execution_statuses"]
        dpdp_001_status = next(s for s in statuses if s["rule_id"] == "DPDP-001")
        assert dpdp_001_status["status"] == "FAILED"
        assert dpdp_001_status["partial_results_discarded"] is True
        
        # Verify safe error message (no leaked secrets/sql)
        assert "Rule execution failed due to an internal query or evaluation error." in dpdp_001_status["error_message"]
        assert "SECRET_DB_PASSWORD" not in dpdp_001_status["error_message"]
        assert "SELECT" not in dpdp_001_status["error_message"]
        
        # Verify unaffected rules (e.g. DPDP-002) still completed
        dpdp_002_status = next(s for s in statuses if s["rule_id"] == "DPDP-002")
        assert dpdp_002_status["status"] == "COMPLETED"

def test_single_rule_evaluator_failure(db_conn):
    """
    Test that if a single rule signal evaluator fails, the rule is marked FAILED,
    and safe explanation is returned.
    """
    tenant_id = "tenant_a"
    wrapper = NonCommittingConnectionWrapper(db_conn)

    # Mock evaluate_all_signals to fail ONLY for DPDP-002
    def mock_evaluate(rule_id, signals, row):
        if rule_id == "DPDP-002":
            raise ValueError("INTERNAL_STACK_TRACE_DETAILS")
        return {}, []

    # Mock build_query for DPDP-002 to return a dummy query that yields one row, so evaluator gets called
    def mock_build_query(rule, t_id):
        if rule["rule_id"] == "DPDP-002":
            return "SELECT 1 AS dummy", []
        return original_build_query(rule, t_id)

    with patch("src.agent_layer.signal_evaluator.evaluate_all_signals", side_effect=mock_evaluate), \
         patch("src.agent_layer.query_builder.build_query", side_effect=mock_build_query), \
         patch("src.agent_layer.orchestrator.get_connection", return_value=wrapper):
        
        response = run_compliance_analysis(tenant_id)
        
        statuses = response["rule_execution_statuses"]
        dpdp_002_status = next(s for s in statuses if s["rule_id"] == "DPDP-002")
        assert dpdp_002_status["status"] == "FAILED"
        assert "INTERNAL_STACK_TRACE_DETAILS" not in dpdp_002_status["error_message"]
        assert dpdp_002_status["partial_results_discarded"] is True

def test_agent_rule_loading_failure(db_conn):
    """
    Test that if rule loading fails completely for an agent,
    all rules assigned to that agent are marked FAILED.
    """
    tenant_id = "tenant_a"
    wrapper = NonCommittingConnectionWrapper(db_conn)

    # Mock load_rules to fail for RegulationAgent
    def mock_load_rules(agent_name, conn):
        if agent_name == "regulation_agent":
            raise psycopg.Error("Connection aborted abruptly (leaked_db_url=postgresql://admin:secret@host/db)")
        return original_load_rules(agent_name, conn)

    with patch("src.agent_layer.rule_loader.load_rules", side_effect=mock_load_rules), \
         patch("src.agent_layer.orchestrator.get_connection", return_value=wrapper):
        
        response = run_compliance_analysis(tenant_id)
        
        statuses = response["rule_execution_statuses"]
        # RegulationAgent assigned rules: DPDP-001, DPDP-002, DPDP-004, DPDP-005, DPDP-007
        for r_id in ["DPDP-001", "DPDP-002", "DPDP-004", "DPDP-005", "DPDP-007"]:
            r_status = next(s for s in statuses if s["rule_id"] == r_id)
            assert r_status["status"] == "FAILED"
            assert "leaked_db_url" not in r_status["error_message"]
            assert "secret" not in r_status["error_message"]
            assert "Agent execution failed" in r_status["error_message"]
            
        # Verify AuditAgent rules (e.g. DPDP-003) still complete successfully
        dpdp_003_status = next(s for s in statuses if s["rule_id"] == "DPDP-003")
        assert dpdp_003_status["status"] == "COMPLETED"
