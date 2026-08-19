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
    violations: List[ViolationRecord],
    tenant_id: str,
    rule_metadata: Dict[str, dict]
) -> Tuple[float, str, Dict[str, float]]:

    """
    Computes risk score using rule metadata and join-aware opportunity
    counts loaded dynamically from PostgreSQL (E-01a fix).
    """

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
    max_possible = sum(

        metadata["risk_weight"]

        for metadata
        in rule_metadata.values()
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

    rule_metadata = (
        load_active_rule_metadata()
    )


    total_obligations = len(
        rule_metadata
    )


    print(
        f"[orchestrator] active rules from DB = "
        f"{total_obligations}"
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

    violations_only = [

        violation

        for violation in all_violations

        if violation.outcome == "VIOLATION"
    ]


    warnings_only = [

        violation

        for violation in all_violations

        if violation.outcome == "WARNING"
    ]


    # ── Step 2: Dynamic risk scoring ─────────────────────────

    risk_score, tier, contributions = (

        compute_risk_score(

            violations_only,

            tenant_id,

            rule_metadata
        )
    )


    # ── Step 3: Compliance score ─────────────────────────────

    violated_rules = len({

        violation.rule_id

        for violation
        in violations_only

        if violation.rule_id
        in rule_metadata
    })


    if total_obligations > 0:

        compliance_score = round(

            max(

                (
                    total_obligations
                    - violated_rules
                )

                / total_obligations

                * 100,

                0.0
            ),

            1
        )

    else:

        compliance_score = 0.0


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

                all_violations=all_violations,

                risk_score=risk_score,

                risk_tier=tier,

                compliance_score=compliance_score,

                conn=report_conn
            )
        )

    finally:

        report_conn.close()


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
            _dt.datetime.utcnow()
            .isoformat()
            + "Z",


        "status":
            "success",


        # Dynamic active rule count
        "total_obligations":
            total_obligations,


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
            "active_rule_count": total_obligations,
            "model_version": "1.0",
            "model_sha256": _get_model_sha256(),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
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