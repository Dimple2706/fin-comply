import sys
import json
import math
from typing import List, Tuple, Dict
from .db_connection import get_connection
from .violation_record import ViolationRecord
from .regulation_agent import RegulationAgent
from .audit_agent import AuditAgent
from .risk_agent import RiskAgent
from .policy_agent import PolicyAgent
import logging
logger = logging.getLogger(__name__)

try:
    from src.modeling.ml_layer import run_ml_layer
    ML_AVAILABLE = True
except Exception as e:
    ML_AVAILABLE = False
    logger.warning(f"ML layer unavailable: {e}")

from .reporting_agent import ReportingAgent

# ── DPDP Act Risk Scoring Constants ──────────────────────────
# Max financial penalty under DPDP Act (₹250 Cr)
MAX_PENALTY_CRORE = 250.0

# Section 33 Recurrence Escalation
_RECURRENCE_STEP = 0.10
_RECURRENCE_MAX_BONUS = 0.50

SEVERITY_SCORE = {
    "CRITICAL": 1.00,
    "HIGH":     0.75,
    "MEDIUM":   0.50,
    "LOW":      0.25
}

# Accurate rule weight sum for normalization
# Weights match risk_weight field in data/dpdp_kb/dpdp_rules.json exactly
ALL_RULE_WEIGHTS = {
    "DPDP-001": 0.90,  # Invalid or Missing Consent Before Processing
    "DPDP-002": 0.85,  # Processing Beyond Stated Purpose
    "DPDP-003": 0.80,  # Retention Beyond Allowed Period
    "DPDP-004": 0.60,  # Missing Notice to Data Principal
    "DPDP-005": 1.00,  # Children's Data Without Guardian Consent
    "DPDP-006": 0.90,  # Unauthorised Third-Party Data Sharing
    "DPDP-007": 0.50,  # Data Minimisation Violation
    "DPDP-008": 0.95,  # Sensitive Data Stored Without Encryption
    "DPDP-009": 0.30,  # Missing Grievance Redressal Mechanism
    "DPDP-010": 0.85,  # Failure to Honour Data Erasure Request
    "DPDP-011": 0.60,  # Excess Data Retention After Purpose Completion
    "DPDP-012": 0.55,  # Missing or Overdue Audit Logs
    "DPDP-013": 0.90,  # Unauthorised Employee Access to PII
    "DPDP-014": 0.95,  # Delayed Breach Notification
    "DPDP-015": 0.85,  # Cross-Border Transfer Without Authorisation
    "DPDP-016": 0.85,  # Processor Accountability Failure
    # Policy agent rules (added after policy migration)
    "POLICY-001": 0.55,  # Retention Policy Compliance
    "POLICY-002": 0.80,  # Encryption Policy Compliance
    "POLICY-003": 0.75,  # Consent Mechanism Policy
}

RULE_SOURCE_TABLE = {
    "DPDP-001": "consent_records",
    "DPDP-002": "transaction_events",
    "DPDP-003": "data_lifecycle",
    "DPDP-004": "consent_records",
    "DPDP-005": "customer_master",
    "DPDP-006": "transaction_events",
    "DPDP-007": "access_logs",
    "DPDP-008": "security_events",
    "DPDP-009": "governance_config",
    "DPDP-010": "dsar_requests",
    "DPDP-011": "data_lifecycle",
    "DPDP-012": "governance_config",
    "DPDP-013": "access_logs",
    "DPDP-014": "security_events",
    "DPDP-015": "transaction_events",
    "DPDP-016": "system_inventory",
    "POLICY-001": "policies",
    "POLICY-002": "policies",
    "POLICY-003": "policies",
}

def compute_risk_score(violations: List[ViolationRecord], tenant_id: str) -> Tuple[float, str, Dict[str, float]]:
    """
    Computes an ISO 31000/NIST aligned 'Likelihood x Impact' risk score.
    Replaces legacy logarithmic-dampened scoring with linear prevalence ratios, 
    adding DPDP Act Section 33 recurrence escalation.
    """
    conn = get_connection()
    try:
        table_counts = {}
        for table in set(RULE_SOURCE_TABLE.values()):
            try:
                row = conn.execute(
                    f"SELECT COUNT(*) AS count FROM {table} WHERE tenant_id = %s",
                    [tenant_id]
                ).fetchone()
                table_counts[table] = max(row["count"] if row else 1, 1)
            except Exception:
                table_counts[table] = 1
    finally:
        conn.close()

    # ── Step 2: Group violations by rule_id ───────────────────
    rule_groups: Dict[str, List[ViolationRecord]] = {}
    for v in violations:
        rule_groups.setdefault(v.rule_id, []).append(v)

    # ── Step 3: Compute per-rule contribution ─────────────────
    contributions: Dict[str, float] = {}
    for rule_id, rule_vs in rule_groups.items():
        affected_rows = len(rule_vs)
        max_rule_score = max(v.rule_score for v in rule_vs)
        risk_weight = rule_vs[0].risk_weight
        severity = rule_vs[0].severity
        penalty_crore = rule_vs[0].penalty_exposure_crore

        # ── Likelihood ──
        source_table = RULE_SOURCE_TABLE.get(rule_id, "transaction_events")
        total_rows = table_counts.get(source_table, 1)
        prevalence_ratio = min(affected_rows / total_rows, 1.0)

        recurrence_factor = 1.0 + min(
            _RECURRENCE_STEP * (affected_rows - 1),
            _RECURRENCE_MAX_BONUS
        )
        L = prevalence_ratio * recurrence_factor

        # ── Impact ──
        sev_score = SEVERITY_SCORE.get(severity, 0.5)
        penalty_norm = penalty_crore / MAX_PENALTY_CRORE
        signal_strength = max_rule_score

        I = (
            0.4 * sev_score
            + 0.3 * penalty_norm
            + 0.3 * signal_strength
        )

        # ── Per-rule inherent risk ──
        contribution = L * I * float(risk_weight)
        contributions[rule_id] = round(contribution, 4)

    # ── Step 4: Aggregate and normalise ───────────────────────
    raw = sum(contributions.values())
    max_possible = sum(ALL_RULE_WEIGHTS.values())
    risk_score = round(min((raw / max_possible) * 100, 100.0), 1)

    # ── Step 5: Tier classification ───────────────
    if risk_score == 0:
        tier = "COMPLIANT"
    elif risk_score < 30:
        tier = "LOW"
    elif risk_score < 55:
        tier = "MEDIUM"
    elif risk_score < 75:
        tier = "HIGH"
    else:
        tier = "CRITICAL"

    return risk_score, tier, contributions

def run_compliance_analysis(tenant_id: str) -> dict:
    import datetime as _dt
    max_possible = sum(ALL_RULE_WEIGHTS.values())
    print(f"[orchestrator] max_possible_score = {round(max_possible, 4)} (19 rules)")

    # ── Step 1: Run all four agents ───────────────────────────
    conn = get_connection()
    all_violations = (
        RegulationAgent().run(tenant_id, conn) +
        AuditAgent().run(tenant_id, conn) +
        RiskAgent().run(tenant_id, conn) +
        PolicyAgent().run(tenant_id, conn)
    )
    conn.close()

    violations_only = [v for v in all_violations if v.outcome == "VIOLATION"]
    warnings_only   = [v for v in all_violations if v.outcome == "WARNING"]

    # ── Step 2: Risk scoring ──────────────────────────────────
    risk_score, tier, contributions = compute_risk_score(violations_only, tenant_id)

    # ── Step 3: Compliance score ──────────────────────────────
    total_obligations = 19
    violated_rules = len({v.rule_id for v in violations_only})
    compliance_score = round(
        max((total_obligations - violated_rules) / total_obligations * 100, 0.0), 1
    )

    # ── Step 4: Agent breakdown ───────────────────────────────
    agent_breakdown = {}
    for agent in ["regulation_agent", "audit_agent", "risk_agent", "policy_agent"]:
        agent_breakdown[agent] = {
            "violations": sum(1 for v in violations_only if v.agent_name == agent),
            "warnings":   sum(1 for v in warnings_only   if v.agent_name == agent),
        }

    # ── Step 5: Assemble five-section report ──────────────────
    report_conn = get_connection()
    try:
        report = ReportingAgent().assemble_report(
            tenant_id=tenant_id,
            all_violations=all_violations,
            risk_score=risk_score,
            risk_tier=tier,
            compliance_score=compliance_score,
            conn=report_conn,
        )
    finally:
        report_conn.close()

    if ML_AVAILABLE:
        try:
            ml_result = run_ml_layer(report)
            report['ml_layer'] = ml_result
        except Exception as e:
            logger.error(f"ML layer failed: {e}")
            report['ml_layer'] = {'ml_available': False, 'reason': str(e)}
    else:
        report['ml_layer'] = {'ml_available': False, 'reason': 'Model not loaded'}

    final_report = {
        "tenant_id":       tenant_id,
        "run_timestamp":   _dt.datetime.utcnow().isoformat() + "Z",
        "status":          "success",
        # legacy summary fields (kept for backward compatibility)
        "total_violations": len(violations_only),
        "total_warnings":   len(warnings_only),
        "risk_score":       risk_score,
        "risk_tier":        tier,
        "risk_contributions": contributions,
        "agent_breakdown":  agent_breakdown,
        # five-section structured report
        "violation_report":     report.get("violation_report", []),
        "risk_insights":        report.get("risk_insights", {}),
        "compliance_score":     report.get("compliance_score", {}),
        "mapped_regulations":   report.get("mapped_regulations", []),
        "explainable_insights": report.get("explainable_insights", []),
        "ml_layer":             report.get("ml_layer")
    }

    from src.governance.audit_logger import log_event, ANALYSIS_RUN
    log_event(
      ANALYSIS_RUN,
      details={
        'risk_score': final_report.get('risk_score'),
        'risk_tier': final_report.get('risk_tier'),
        'n_violations': final_report.get('total_violations'),
        'n_rules_evaluated': 19,
        'ml_predicted_tier': final_report.get('ml_layer', {}).get('predicted_tier')
      },
      tenant_id=tenant_id
    )

    return final_report

if __name__ == "__main__":
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else "tenant_a"
    result = run_compliance_analysis(tenant_id)
    print(json.dumps(result, indent=2, default=str))