import sys
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Dict
from psycopg.sql import SQL, Identifier

from .db_connection import get_connection
from .violation_record import ViolationRecord
from .regulation_agent import RegulationAgent
from .audit_agent import AuditAgent
from .risk_agent import RiskAgent
from .policy_agent import PolicyAgent

import logging

logger = logging.getLogger(__name__)

ALLOWED_TABLES = {
    "governance_config",
    "system_inventory",
    "policies",
    "customer_master",
    "consent_records",
    "transaction_events",
    "access_logs",
    "data_lifecycle",
    "security_events",
    "dsar_requests",
}

def _get_model_sha256() -> str:
    model_path = Path("src/modeling/risk_model.pkl")
    if model_path.exists():
        return hashlib.sha256(model_path.read_bytes()).hexdigest()
    return "model_file_not_found"


try:
    from src.modeling.ml_layer import run_ml_layer
    ML_AVAILABLE = True
except Exception as e:
    ML_AVAILABLE = False
    logger.warning(f"ML layer unavailable: {e}")


from .reporting_agent import ReportingAgent


# ─────────────────────────────────────────────────────────────
# Risk scoring constants
# ─────────────────────────────────────────────────────────────

MAX_PENALTY_CRORE = 250.0

_RECURRENCE_STEP = 0.10
_RECURRENCE_MAX_BONUS = 0.50


SEVERITY_SCORE = {
    "CRITICAL": 1.00,
    "HIGH": 0.75,
    "MEDIUM": 0.50,
    "LOW": 0.25
}


# ─────────────────────────────────────────────────────────────
# Load active rule metadata dynamically from PostgreSQL
# ─────────────────────────────────────────────────────────────

def load_active_rule_metadata() -> Dict[str, dict]:
    """
    Loads all enabled rules from PostgreSQL including opportunity_query.
    """
    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                rule_id,
                risk_weight,
                primary_table,
                opportunity_query
            FROM rules
            WHERE enabled = TRUE
            ORDER BY rule_id
            """
        ).fetchall()

        metadata = {}

        for row in rows:
            metadata[row["rule_id"]] = {
                "risk_weight": float(row["risk_weight"]),
                "primary_table": row["primary_table"],
                "opportunity_query": row.get("opportunity_query")
            }

        return metadata

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Risk Score
# ─────────────────────────────────────────────────────────────

def compute_risk_score(
    all_violations: List[ViolationRecord],
    tenant_id: str,
    rule_metadata: Dict[str, dict]
) -> Tuple[float, str, Dict[str, float]]:

    """
    Computes risk score using rule metadata and join-aware opportunity
    counts loaded dynamically from PostgreSQL (E-01a fix).
    """

    violations = [v for v in all_violations if v.outcome == "VIOLATION"]
    conn = get_connection()


    try:
        table_counts = {}

        # Get all source tables dynamically from rules table
        source_tables = {
            metadata["primary_table"]
            for metadata in rule_metadata.values()
            if metadata.get("primary_table")
        }

        for table in source_tables:
            if table not in ALLOWED_TABLES:
                logger.warning(
                    f"Skipping row count for unauthorized or unknown table '{table}'"
                )
                table_counts[table] = 1
                continue

            try:
                query = SQL(
                    "SELECT COUNT(*) AS count FROM {} WHERE tenant_id = %s"
                ).format(Identifier(table))

                row = conn.execute(query, [tenant_id]).fetchone()

                table_counts[table] = max(
                    row["count"] if row else 1,
                    1
                )
            except Exception as e:
                logger.warning(
                    f"Could not count rows in {table}: {e}"
                )
                table_counts[table] = 1

        # [E-01a FIX] Calculate join-aware opportunity counts for targeted subsets
        opportunity_counts = {}
        for rule_id, meta in rule_metadata.items():
            opp_q = meta.get("opportunity_query")
            if opp_q:
                try:
                    row = conn.execute(opp_q, [tenant_id]).fetchone()
                    if row is not None:
                        count_val = row[0] if not isinstance(row, dict) else row.get("count", 1)
                        opportunity_counts[rule_id] = max(int(count_val) if count_val else 1, 1)
                    else:
                        opportunity_counts[rule_id] = table_counts.get(meta.get("primary_table"), 1)
                except Exception as e:
                    logger.warning(f"Could not execute opportunity query for {rule_id}: {e}")
                    opportunity_counts[rule_id] = table_counts.get(meta.get("primary_table"), 1)
            else:
                opportunity_counts[rule_id] = table_counts.get(meta.get("primary_table"), 1)

    finally:
        conn.close()


    # ── Group violations by rule ─────────────────────────────

    rule_groups: Dict[str, List[ViolationRecord]] = {}

    for violation in violations:
        rule_groups.setdefault(
            violation.rule_id,
            []
        ).append(violation)


    # ── Calculate contribution of each violated rule ─────────

    contributions: Dict[str, float] = {}

    for rule_id, rule_violations in rule_groups.items():
        metadata = rule_metadata.get(rule_id)

        # Rule should exist in PostgreSQL.
        if not metadata:
            logger.warning(
                f"Rule {rule_id} produced a violation "
                f"but is not present as an enabled DB rule."
            )
            continue

        # Deduplicate violations by record_id
        unique_violations = {}
        for rv in rule_violations:
            if rv.record_id not in unique_violations:
                unique_violations[rv.record_id] = rv
        rule_violations = list(unique_violations.values())
        affected_rows = len(rule_violations)

        max_rule_score = max(
            violation.rule_score
            for violation in rule_violations
        )

        risk_weight = metadata["risk_weight"]
        severity = rule_violations[0].severity
        penalty_crore = rule_violations[0].penalty_exposure_crore

        # ─────────────────────────────────────────────────────
        # Likelihood (Join-Aware Denominator E-01a)
        # ─────────────────────────────────────────────────────
        source_table = metadata["primary_table"]
        total_opportunity = opportunity_counts.get(
            rule_id,
            table_counts.get(source_table, 1)
        )

        prevalence_ratio = min(
            affected_rows / max(total_opportunity, 1),
            1.0
        )

        recurrence_factor = (
            1.0
            +
            min(
                _RECURRENCE_STEP
                * (affected_rows - 1),
                _RECURRENCE_MAX_BONUS
            )
        )


        likelihood = (
            prevalence_ratio
            * recurrence_factor
        )


        # ─────────────────────────────────────────────────────
        # Impact
        # ─────────────────────────────────────────────────────

        severity_score = (
            SEVERITY_SCORE.get(
                severity,
                0.5
            )
        )


        penalty_norm = (
            penalty_crore
            / MAX_PENALTY_CRORE
        )


        signal_strength = (
            max_rule_score
        )


        impact = (

            0.4 * severity_score

            + 0.3 * penalty_norm

            + 0.3 * signal_strength
        )


        # ─────────────────────────────────────────────────────
        # Per-rule risk contribution
        # ─────────────────────────────────────────────────────

        contribution = (

            likelihood
            * impact
            * risk_weight
        )


        contributions[rule_id] = round(
            contribution,
            4
        )


    # ─────────────────────────────────────────────────────────
    # Dynamic normalization
    # ─────────────────────────────────────────────────────────

    raw_score = sum(
        contributions.values()
    )


    # IMPORTANT:
    # No more hardcoded ALL_RULE_WEIGHTS.
    # Maximum possible weight is calculated from ACTIVE DB rules.
    # Exclude NOT_APPLICABLE rules from the max possible denominator
    not_applicable_rules = set()
    for r_id in rule_metadata.keys():
        records = [v for v in all_violations if v.rule_id == r_id]
        if records and all(r.outcome == "NOT_APPLICABLE" for r in records):
            not_applicable_rules.add(r_id)

    max_possible = sum(
        meta["risk_weight"]
        for r_id, meta in rule_metadata.items()
        if r_id not in not_applicable_rules
    )


    if max_possible > 0:
        risk_score = round(
            min(
                (raw_score / max_possible) * 100,
                100.0
            ),
            1
        )
    else:
        risk_score = 0.0

    # ─────────────────────────────────────────────────────────
    # Severity Floor Policy (E-01b Fix)
    # ─────────────────────────────────────────────────────────
    # DPDP Statutory Policy:
    # 1. Any CRITICAL violation (e.g. minor data without consent under Sec 9)
    #    must never score below 65.0 (guarantees HIGH tier minimum).
    # 2. Accumulation of 3+ HIGH severity violations must never score below 45.0 (guarantees MEDIUM tier minimum).
    has_critical = any(
        v.severity == "CRITICAL"
        for v in violations
        if getattr(v, "outcome", "VIOLATION") == "VIOLATION"
    )
    high_count = sum(
        1
        for v in violations
        if v.severity == "HIGH" and getattr(v, "outcome", "VIOLATION") == "VIOLATION"
    )

    if has_critical:
        risk_score = max(risk_score, 65.0)
    elif high_count >= 3:
        risk_score = max(risk_score, 45.0)

    # ─────────────────────────────────────────────────────────
    # Risk tier
    # ─────────────────────────────────────────────────────────

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

    return (
        risk_score,
        tier,
        contributions
    )


# ─────────────────────────────────────────────────────────────
# Main compliance analysis
# ─────────────────────────────────────────────────────────────

def run_compliance_analysis(
    tenant_id: str
) -> dict:

    import datetime as _dt


    # ── Load rules dynamically ───────────────────────────────

    all_rule_metadata = load_active_rule_metadata()
    rule_metadata = {
        k: v for k, v in all_rule_metadata.items()
        if not k.startswith("POLICY-")
    }
    internal_control_metadata = {
        k: v for k, v in all_rule_metadata.items()
        if k.startswith("POLICY-")
    }
    total_obligations = len(rule_metadata)

    print(
        f"[orchestrator] active rules from DB = "
        f"{len(all_rule_metadata)} "
        f"({total_obligations} statutory, "
        f"{len(internal_control_metadata)} internal)"
    )


    # ── Step 1: Run agents ───────────────────────────────────

    conn = get_connection()

    try:

        all_violations = (

            RegulationAgent().run(
                tenant_id,
                conn
            )

            +

            AuditAgent().run(
                tenant_id,
                conn
            )

            +

            RiskAgent().run(
                tenant_id,
                conn
            )

            +

            PolicyAgent().run(
                tenant_id,
                conn
            )
        )

    finally:

        conn.close()


    # ── Separate outcomes ────────────────────────────────────

    statutory_findings = [
        finding for finding in all_violations
        if not finding.rule_id.startswith("POLICY-")
    ]
    internal_control_findings = [
        finding for finding in all_violations
        if finding.rule_id.startswith("POLICY-")
    ]

    violations_only = [

        violation

        for violation in statutory_findings

        if violation.outcome == "VIOLATION"
    ]


    warnings_only = [

        violation

        for violation in statutory_findings

        if violation.outcome == "WARNING"
    ]


    # ── Step 2: Dynamic risk scoring ─────────────────────────
    risk_score, tier, contributions = (
        compute_risk_score(
            statutory_findings,
            tenant_id,
            rule_metadata
        )
    )

    # ── Step 3: Compliance score ─────────────────────────────
    # Group all_violations by rule_id to determine rule-level states
    rule_states = {}
    for r_id in rule_metadata.keys():
        records = [v for v in statutory_findings if v.rule_id == r_id]
        if any(r.outcome == "FAILED" for r in records):
            rule_states[r_id] = "FAILED"
        elif any(r.outcome == "VIOLATION" for r in records):
            rule_states[r_id] = "VIOLATION"
        elif any(r.outcome == "NOT_ASSESSABLE" for r in records):
            rule_states[r_id] = "NOT_ASSESSABLE"
        elif any(r.outcome == "PASS" for r in records):
            rule_states[r_id] = "PASS"
        else:
            rule_states[r_id] = "NOT_APPLICABLE"

    violated_rules_count = sum(1 for s in rule_states.values() if s == "VIOLATION")
    pass_rules_count = sum(1 for s in rule_states.values() if s == "PASS")
    not_assessable_rules_count = sum(1 for s in rule_states.values() if s == "NOT_ASSESSABLE")
    failed_rules_count = sum(1 for s in rule_states.values() if s == "FAILED")
    not_applicable_rules_count = sum(1 for s in rule_states.values() if s == "NOT_APPLICABLE")

    denom = pass_rules_count + violated_rules_count + not_assessable_rules_count + failed_rules_count
    if denom > 0:
        compliance_score = round((pass_rules_count / denom) * 100.0, 1)
    else:
        compliance_score = 100.0



    # ── Step 4: Agent breakdown ──────────────────────────────

    agent_breakdown = {}


    for agent in [

        "regulation_agent",
        "audit_agent",
        "risk_agent",
        "policy_agent"

    ]:

        agent_breakdown[agent] = {

            "violations": sum(

                1

                for violation
                in violations_only

                if violation.agent_name
                == agent
            ),

            "warnings": sum(

                1

                for violation
                in warnings_only

                if violation.agent_name
                == agent
            )
        }


    # ── Step 5: Reporting Agent ──────────────────────────────

    report_conn = get_connection()

    try:

        report = (

            ReportingAgent()
            .assemble_report(

                tenant_id=tenant_id,

                all_violations=statutory_findings,

                risk_score=risk_score,

                risk_tier=tier,

                compliance_score=compliance_score,

                conn=report_conn
            )
        )

    finally:

        report_conn.close()


    internal_control_states = {}
    for rule_id in internal_control_metadata:
        records = [
            finding for finding in internal_control_findings
            if finding.rule_id == rule_id
        ]
        if any(record.outcome == "FAILED" for record in records):
            internal_control_states[rule_id] = "FAILED"
        elif any(record.outcome == "VIOLATION" for record in records):
            internal_control_states[rule_id] = "VIOLATION"
        elif any(record.outcome == "NOT_ASSESSABLE" for record in records):
            internal_control_states[rule_id] = "NOT_ASSESSABLE"
        elif any(record.outcome == "PASS" for record in records):
            internal_control_states[rule_id] = "PASS"
        else:
            internal_control_states[rule_id] = "NOT_APPLICABLE"

    report["internal_controls"] = {
        "classification": "INTERNAL_CONTROL",
        "statutory_penalty_exposure_crore": 0.0,
        "summary_by_rule": internal_control_states,
        "findings": [finding.to_dict() for finding in internal_control_findings],
    }

    # ── Step 6: ML layer ─────────────────────────────────────

    if ML_AVAILABLE:

        try:

            ml_result = (
                run_ml_layer(report)
            )

            report["ml_layer"] = (
                ml_result
            )

        except Exception as e:

            logger.error(
                f"ML layer failed: {e}"
            )

            report["ml_layer"] = {

                "ml_available": False,

                "reason": str(e)
            }

    else:

        report["ml_layer"] = {

            "ml_available": False,

            "reason": "Model not loaded"
        }


    # ── Step 7: Final API response ───────────────────────────

    final_report = {

        "tenant_id":
            tenant_id,


        "run_timestamp":
            _dt.datetime.now(_dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),


        "status":
            "success",


        # Dynamic active rule count
        "total_obligations":
            total_obligations,

        "internal_control_count":
            len(internal_control_metadata),

        "internal_controls":
            report.get("internal_controls"),


        # Summary
        "total_violations":
            len(violations_only),


        "total_warnings":
            len(warnings_only),


        # Actual violation records required by routes.py
        "violations": [

            violation.to_dict()

            for violation
            in violations_only
        ],


        "warnings": [

            warning.to_dict()

            for warning
            in warnings_only
        ],


        # Risk
        "risk_score":
            risk_score,


        "risk_tier":
            tier,


        "risk_contributions":
            contributions,


        # Agents
        "agent_breakdown":
            agent_breakdown,


        # Five-section structured report
        "violation_report":
            report.get(
                "violation_report",
                []
            ),


        "risk_insights":
            report.get(
                "risk_insights",
                {}
            ),


        "compliance_score":
            report.get(
                "compliance_score",
                {}
            ),


        "mapped_regulations":
            report.get(
                "mapped_regulations",
                []
            ),


        "explainable_insights":
            report.get(
                "explainable_insights",
                []
            ),


        "ml_layer":
            report.get(
                "ml_layer"
            ),

        "run_metadata": {
            "engine_version": "1.0.0",
            "schema_version": "2026.1",
            "active_rule_count": len(all_rule_metadata),
            "statutory_rule_count": total_obligations,
            "internal_control_count": len(internal_control_metadata),
            "model_version": "1.0",
            "model_sha256": _get_model_sha256(),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        },
        "findings": [
            {
                "rule_id": f.rule_id,
                "record_id": f.record_id,
                "outcome": f.outcome,
                "reason": f.signal_reasons[0] if f.signal_reasons else None
            }
            for f in all_violations
        ],
        "rule_execution_statuses": [
            {
                "rule_id": rule_id,
                "status": (
                    "FAILED" if any(f.rule_id == rule_id and f.outcome == "FAILED" for f in all_violations)
                    else "NOT_ASSESSABLE" if any(f.rule_id == rule_id and f.outcome == "NOT_ASSESSABLE" for f in all_violations)
                    else "COMPLETED"
                ),
                "error_message": next(
                    (f.signal_reasons[0] for f in all_violations if f.rule_id == rule_id and f.outcome in ("FAILED", "NOT_ASSESSABLE") and f.signal_reasons),
                    None
                ),
                "partial_results_discarded": any(f.rule_id == rule_id and f.outcome == "FAILED" for f in all_violations)
            }
            for rule_id in rule_metadata.keys()
        ]
    }


    # ── Step 8: Governance logging ───────────────────────────

    from src.governance.audit_logger import (
        log_event,
        ANALYSIS_RUN
    )


    log_event(

        ANALYSIS_RUN,

        details={

            "risk_score":
                final_report.get(
                    "risk_score"
                ),


            "risk_tier":
                final_report.get(
                    "risk_tier"
                ),


            "n_violations":
                final_report.get(
                    "total_violations"
                ),


            # Dynamic
            "n_rules_evaluated":
                total_obligations,


            "ml_predicted_tier":

                final_report
                .get(
                    "ml_layer",
                    {}
                )
                .get(
                    "predicted_tier"
                )
        },

        tenant_id=tenant_id
    )


    return final_report


# ─────────────────────────────────────────────────────────────
# CLI test
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    tenant_id = (

        sys.argv[1]

        if len(sys.argv) > 1

        else "tenant_a"
    )


    result = (
        run_compliance_analysis(
            tenant_id
        )
    )


    print(

        json.dumps(

            result,

            indent=2,

            default=str
        )
    )
