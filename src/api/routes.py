import json
import os
import logging
import psycopg
from psycopg.rows import dict_row
import tempfile
import shutil
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Any
import hashlib
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response

from src.governance.audit_logger import log_event, RULE_APPROVED, RULE_REJECTED
from src.api.auth import (
    require_admin, require_reviewer, require_authenticated,
    AuthUser, verify_tenant_access, authenticate_user,
    create_user_in_db, get_user_by_username, verify_password, create_access_token,
)

from src.api.schemas import (
    AnalyzeRequest, AnalyzeResponse, ViolationItem,
    FullExplanation, SignalDetail, AgentBreakdown, RemediationItem,
    UserRegisterRequest, UserLoginRequest, TokenResponse, UserPublic,
)
from src.legal_context import build_regulatory_context
from src.anonymization.csv_loader import load_tenant_csvs, TenantValidationError, MissingColumnError
from src.anonymization.field_mapper import (
    anonymize_dataframe,
    DsarValidationError,
    EnumValidationError,
    GovernanceValidationError,
    TransactionValidationError,
    ConsentValidationError,
    SecurityEventValidationError,
    SystemInventoryValidationError,
    LifecycleValidationError
)
from src.anonymization.db_writer import write_tenant_data, CrossFileValidationError
from src.agent_layer.orchestrator import run_compliance_analysis
from src.explainability.service import enrich_violations, generate_executive_summary, RULE_EXPLANATIONS
from src.explainability.report_builder import URGENCY_ORDER, SEVERITY_TO_URGENCY

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'tenant_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD')   # Must be set in .env - no hardcoded fallback

router = APIRouter()

def get_db_connection():
    return psycopg.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        autocommit=False,
        row_factory=dict_row,
    )


def ensure_evaluation_results_table(conn: psycopg.Connection) -> None:
    """
    Create evaluation_results and audit_runs if missing, so inserts never fail silently.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.audit_runs (
                audit_run_id character varying(64) PRIMARY KEY,
                tenant_id character varying(32) NOT NULL,
                input_snapshot_hash character varying(64) NOT NULL,
                rule_set_hash character varying(64) NOT NULL,
                clause_set_hash character varying(64) NOT NULL,
                engine_version character varying(32) NOT NULL,
                model_hash character varying(64),
                source_data_row_counts jsonb,
                validation_summary jsonb,
                status character varying(32) NOT NULL,
                parent_audit_run_id character varying(64),
                hash_version character varying(10) NOT NULL DEFAULT 'v2',
                created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.evaluation_results (
                id BIGSERIAL PRIMARY KEY,
                tenant_id character varying(32) NOT NULL,
                result_json jsonb NOT NULL,
                risk_score numeric(5,2) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            "ALTER TABLE public.evaluation_results ADD COLUMN IF NOT EXISTS audit_run_id character varying(64);"
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evaluation_results_tenant_id
            ON public.evaluation_results (tenant_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evaluation_results_created_at
            ON public.evaluation_results (created_at DESC)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evaluation_results_audit_run_id
            ON public.evaluation_results (audit_run_id)
            """
        )

def compute_tenant_snapshot_hash(tenant_id: str, conn) -> str:
    tables = [
        "customer_master",
        "consent_records",
        "transaction_events",
        "access_logs",
        "data_lifecycle",
        "security_events",
        "dsar_requests",
        "system_inventory",
        "policies",
        "governance_config"
    ]
    h = hashlib.sha256()
    for table in tables:
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {table} WHERE tenant_id = %s", (tenant_id,))
                rows = cur.fetchall()
            serialized_rows = []
            for row in rows:
                if isinstance(row, dict):
                    item = sorted((k, str(v)) for k, v in row.items())
                else:
                    item = str(row)
                serialized_rows.append(item)
            serialized_rows.sort()
            h.update(json.dumps(serialized_rows, default=str).encode("utf-8"))
        except Exception:
            h.update(b"")
    return h.hexdigest()

def get_tenant_row_counts(tenant_id: str, conn) -> dict:
    tables = [
        "customer_master",
        "consent_records",
        "transaction_events",
        "access_logs",
        "data_lifecycle",
        "security_events",
        "dsar_requests",
        "system_inventory",
        "policies",
        "governance_config"
    ]
    counts = {}
    for table in tables:
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) as cnt FROM {table} WHERE tenant_id = %s", (tenant_id,))
                row = cur.fetchone()
            counts[table] = row["cnt"] if isinstance(row, dict) else row[0]
        except Exception:
            counts[table] = 0
    return counts

def compute_kb_file_hash(file_path: str) -> str:
    if not os.path.exists(file_path):
        return "missing"
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

def get_latest_audit_run_id(tenant_id: str, conn) -> Optional[str]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT audit_run_id FROM audit_runs WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 1",
                (tenant_id,)
            )
            row = cur.fetchone()
            if row:
                return row["audit_run_id"] if isinstance(row, dict) else row[0]
    except Exception:
        pass
    return None

def resolve_audit_run_id(tenant_id: str, audit_run_id: Optional[str], conn) -> str:
    if audit_run_id:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM audit_runs WHERE audit_run_id = %s", (audit_run_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Audit run '{audit_run_id}' not found.")
            run_tenant = row["tenant_id"] if isinstance(row, dict) else row[0]
            if run_tenant != tenant_id:
                raise HTTPException(status_code=404, detail="Requested run ID does not belong to the tenant.")
            return audit_run_id
    else:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT audit_run_id FROM audit_runs WHERE tenant_id = %s AND status = 'completed' ORDER BY created_at DESC LIMIT 1",
                (tenant_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"No completed compliance data found for tenant {tenant_id}")
            resolved_id = row["audit_run_id"] if isinstance(row, dict) else row[0]
            return resolved_id


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# SHARED HELPERS ΓÇö used by both /analyze and /analyze/upload
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ


def _build_full_response(analysis_result: dict, tenant_name: str = "", audit_run_id: str = None, run_status: str = "completed") -> dict:
    tenant_id = analysis_result["tenant_id"]
    contributions = analysis_result.get("risk_contributions", {})

    all_records = (
        analysis_result.get("violations", [])
        + analysis_result.get("warnings", [])
    )
    enriched = enrich_violations(all_records, contributions)

    display_name = tenant_name or tenant_id

    # ΓöÇΓöÇ Executive Summary (fail-safe) ΓöÇΓöÇ
    try:
        executive_summary = generate_executive_summary(
            tenant_id=tenant_id,
            tenant_name=display_name,
            explanations=enriched,
            risk_score=analysis_result["risk_score"],
            tier=analysis_result["risk_tier"],
        )
    except Exception as e:
        logging.warning(f"Executive summary generation failed: {e}")
        executive_summary = (
            f"{display_name} compliance analysis completed with risk score "
            f"{analysis_result.get('risk_score', 0)}/100 "
            f"({analysis_result.get('risk_tier', 'UNKNOWN')})."
        )

    violation_enriched = [
        e for e in enriched if e.outcome == "VIOLATION"
    ]

    # ΓöÇΓöÇ Group violations by rule_id ΓöÇΓöÇ
    raw_violations = analysis_result.get("violations", [])
    # Build a lookup: rule_id -> list of raw violation dicts
    raw_by_rule: dict[str, list] = {}
    for v in raw_violations:
        rid = v.get("rule_id")
        if rid:
            raw_by_rule.setdefault(rid, []).append(v)

    grouped: dict[str, dict] = {}
    for exp in violation_enriched:
        rid = exp.rule_id
        raw_list = raw_by_rule.get(rid, [])
        raw_risk_weight = raw_list[0].get("risk_weight", 0.0) if raw_list else 0.0

        if rid not in grouped:
            grouped[rid] = {
                "rule_id": rid,
                "rule_name": exp.rule_name,
                "dpdp_section": exp.dpdp_section,
                "severity": exp.severity,
                "risk_weight": raw_risk_weight,
                "occurrence_count": 0,
                "reasons": [],
                "matched_record_ids": set(),
                "fields_triggered": set(),
                "best_exp": exp,
                "max_score": exp.top_signal_weight,
                "penalty_exposure_crore": exp.penalty_exposure_crore,
                "root_cause": exp.root_cause,
            }
        else:
            if exp.top_signal_weight > grouped[rid]["max_score"]:
                grouped[rid]["max_score"] = exp.top_signal_weight
                grouped[rid]["best_exp"] = exp

        grouped[rid]["occurrence_count"] += 1
        # record_id and fields_triggered live on the raw violation dict
        for rv in raw_list:
            rec_id = rv.get("record_id")
            if rec_id:
                grouped[rid]["matched_record_ids"].add(str(rec_id))
            for f in rv.get("fields_triggered", []):
                if f:
                    grouped[rid]["fields_triggered"].add(str(f))

    # Collect signal_reasons from raw violation dicts
    for rid, raw_list in raw_by_rule.items():
        if rid in grouped:
            for v in raw_list:
                for reason in v.get("signal_reasons", []):
                    if reason and reason not in grouped[rid]["reasons"]:
                        grouped[rid]["reasons"].append(reason)

    violation_items: list[ViolationItem] = []
    for rid, entry in grouped.items():
        best = entry["best_exp"]
        matched = sorted(entry["matched_record_ids"])
        reason_text = (
            "; ".join(entry["reasons"])
            if entry["reasons"]
            else f"{entry['rule_name']} triggered"
        )

        signals = []
        for s in best.signals_analysis:
            sig_def = RULE_EXPLANATIONS.get(rid, {}).get("signal_definitions", {}).get(s.get("signal", ""), {})
            contrib = s.get("weight", 0.0) if s.get("fired", False) else 0.0
            signals.append(SignalDetail(
                signal=s.get("signal", ""),
                description=sig_def.get("description", s.get("description", "")),
                weight=s.get("weight", 0.0),
                fired=s.get("fired", False),
                reason=s.get("reason", "ΓÇö"),
                signal_contribution=round(contrib, 4),
                phi=round(contrib, 4),
            ))

        total_weight = sum(sig.signal_contribution for sig in signals)

        explanation = FullExplanation(
            why_detected=best.what_happened,
            evidence=best.what_happened or "",
            risk_reason=best.why_violation,
            mitigation=best.remediation_steps if isinstance(best.remediation_steps, list) else [],
            signals_analysis=signals,
            top_contributing_signal=best.top_contributing_signal,
            total_signal_weight=round(total_weight, 4),
            total_shap=round(total_weight, 4),
            root_cause=best.root_cause,
            penalty_exposure_crore=best.penalty_exposure_crore,
        )

        violation_items.append(
            ViolationItem(
                rule_id=rid,
                rule_name=entry["rule_name"],
                dpdp_section=entry["dpdp_section"],
                severity=entry["severity"],
                risk_weight=entry["risk_weight"],
                occurrence_count=entry["occurrence_count"],
                contribution_to_score=float(contributions.get(rid, 0.0)),
                reason=reason_text,
                explanation=explanation,
                penalty_exposure_crore=entry["penalty_exposure_crore"],
                root_cause=entry["root_cause"],
                matched_record_ids=matched,
                fields_triggered=sorted(list(entry["fields_triggered"])),
                matched_logs_count=len(matched),
            )
        )

    violation_items.sort(key=lambda x: x.rule_id)

    seen_remediation: set = set()
    remediation_raw = []
    for exp in violation_enriched:
        if exp.rule_id not in seen_remediation:
            urgency = SEVERITY_TO_URGENCY.get(exp.severity, "LOW")
            remediation_raw.append({
                "rule_id": exp.rule_id,
                "rule_name": exp.rule_name,
                "action": (
                    exp.remediation_steps[0]
                    if exp.remediation_steps else ""
                ),
                "urgency": urgency,
                "penalty_exposure_crore": exp.penalty_exposure_crore,
                "risk_contribution": exp.risk_contribution,
            })
            seen_remediation.add(exp.rule_id)

    remediation_sorted = sorted(
        remediation_raw,
        key=lambda x: (
            URGENCY_ORDER.get(x["urgency"], 3),
            -x["risk_contribution"],
            -x["penalty_exposure_crore"],
        ),
    )
    remediation_priority = [
        RemediationItem(
            priority=i + 1,
            rule_id=r["rule_id"],
            rule_name=r["rule_name"],
            action=r["action"],
            urgency=r["urgency"],
            penalty_exposure_crore=r["penalty_exposure_crore"],
        )
        for i, r in enumerate(remediation_sorted)
    ]

    seen_penalty: set = set()
    total_penalty = 0
    for exp in violation_enriched:
        if exp.rule_id not in seen_penalty:
            total_penalty += exp.penalty_exposure_crore
            seen_penalty.add(exp.rule_id)

    raw_breakdown = analysis_result.get("agent_breakdown", {})
    agent_breakdown = {
        name: AgentBreakdown(
            violations=info.get("violations", 0),
            warnings=info.get("warnings", 0),
        )
        for name, info in raw_breakdown.items()
    }

    comp_score = analysis_result.get("compliance_score") or {}
    violated = comp_score.get("violated_obligations", 0)
    failed = comp_score.get("failed_obligations", 0)
    # Execution failures are not compliance violations. Keep them separate so
    # callers can distinguish a proven violation from a rule that did not run.
    failed_rules_count = failed
    not_assessable = comp_score.get("not_assessable_obligations", 0)
    
    outcome_count_by_state = {
        "PASS": comp_score.get("satisfied_obligations", 0),
        "VIOLATION": violated,
        "WARNING": comp_score.get("warning_obligations", 0),
        "NOT_ASSESSABLE": not_assessable,
        "FAILED": failed,
        "NOT_APPLICABLE": comp_score.get("not_applicable_obligations", 0),
    }

    return {
        "tenant_id": tenant_id,
        "total_obligations": int(analysis_result.get("total_obligations", 0)),
        "internal_control_count": int(analysis_result.get("internal_control_count", 0)),
        "internal_controls": analysis_result.get("internal_controls"),
        "unique_rules_violated": len(violation_items),
        "total_violation_occurrences": sum(
            v.occurrence_count for v in violation_items
        ),
        "risk_score": float(analysis_result.get("risk_score", 0.0)),
        "risk_tier": analysis_result.get("risk_tier", "COMPLIANT"),
        "violations": violation_items,
        "status": "success",
        "executive_summary": executive_summary,
        "agent_breakdown": agent_breakdown,
        "risk_contributions": contributions,
        "remediation_priority": remediation_priority,
        "total_penalty_exposure_crore": total_penalty,
        "compliance_score": comp_score,
        "rule_execution_statuses": analysis_result.get("rule_execution_statuses"),
        "findings": analysis_result.get("findings"),
        "ml_layer": analysis_result.get("ml_layer"),
        "run_metadata": analysis_result.get("run_metadata"),
        "audit_run_id": audit_run_id,
        "run_status": run_status,
        "failed_rules_count": failed_rules_count,
        "not_assessable_rules_count": not_assessable,
        "outcome_count_by_state": outcome_count_by_state,
        "regulatory_context": build_regulatory_context(),
        "disclaimer": (
            "Maximum statutory exposure estimate, not an actual or certain fine. "
            "Automated evidence-based decision support only; not legal advice, "
            "regulatory certification, or a Board determination."
        ),
    }

def validate_dataset_hash_version(mapped_data: dict):
    seen = set()
    for table_name, rows in mapped_data.items():
        if isinstance(rows, dict):
            rows = [rows]
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    for col, val in row.items():
                        if col.endswith("_hash") and val is not None:
                            val_str = str(val).strip()
                            if val_str.startswith("v2:"):
                                seen.add("v2")
                            else:
                                seen.add("v1")
    if len(seen) > 1:
        raise HTTPException(
            status_code=400,
            detail="Upload rejected: Cannot mix v1 and v2 identifiers in the same tenant dataset. The entire dataset must be migrated to v2 consistently."
        )


# ├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼
# ENDPOINTS
# ├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼├—┬ó├óΓé¼┬¥├óΓÇÜ┬¼

@router.get("/health")
def health_check():
    return {
        "status": "running",
        "service": "Fin-Comply ├—┬ó├óΓÇÜ┬¼├óΓé¼┬¥ DPDP Compliance Engine"
    }



# -- Auth Endpoints -----------------------------------------------------------

@router.post("/auth/register", response_model=UserPublic, status_code=201)
def register_user(body: UserRegisterRequest):
    """
    Register a new user account linked to their company's tenant.
    Returns the created user's public profile (no password hash).
    """
    row = create_user_in_db(
        name=body.name,
        email=body.email,
        username=body.username,
        password=body.password,
        tenant_id=body.tenant_id,
        tenant_name=body.tenant_name,
    )
    tenants = list(row.get("authorized_tenants") or [])
    return UserPublic(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        username=row["username"],
        role=row["role"],
        tenant_id=tenants[0] if tenants else None,
        created_at=str(row.get("created_at", "")),
    )


@router.post("/auth/login", response_model=TokenResponse)
def login_user(body: UserLoginRequest):
    """
    Authenticate with username + password, receive a signed JWT.
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="Incorrect username or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_row = get_user_by_username(body.username)
    if not user_row:
        raise credentials_exception
    if not verify_password(body.password, user_row["password_hash"]):
        raise credentials_exception

    token = create_access_token(data={"sub": user_row["username"]})
    tenants = list(user_row.get("authorized_tenants") or [])
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user_row["username"],
        name=user_row["name"],
        role=user_row["role"],
        tenant_id=tenants[0] if tenants else None,
    )


@router.get("/auth/me", response_model=UserPublic)
def get_current_user(current_user: AuthUser = Depends(authenticate_user)):
    """
    Returns the authenticated user's public profile.
    """
    tenants = list(current_user.authorized_tenants or [])
    return UserPublic(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        username=current_user.username,
        role=current_user.role,
        tenant_id=tenants[0] if tenants else None,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_tenant(
    request: AnalyzeRequest,
    current_user: AuthUser = Depends(authenticate_user),
):
    try:
        clean_tenant_id = request.tenant_id.strip()
        verify_tenant_access(clean_tenant_id, current_user)
            
        if request.audit_run_id:
            with get_db_connection() as conn:
                ensure_evaluation_results_table(conn)
                resolved_run_id = resolve_audit_run_id(clean_tenant_id, request.audit_run_id, conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT result_json FROM evaluation_results WHERE tenant_id = %s AND audit_run_id = %s",
                        (clean_tenant_id, resolved_run_id)
                    )
                    row = cur.fetchone()
                    if not row:
                        raise HTTPException(status_code=404, detail=f"No evaluation results found for run '{resolved_run_id}'.")
                    res_json = row["result_json"] if isinstance(row, dict) else row[0]
                    res_data = res_json if isinstance(res_json, dict) else json.loads(res_json)
                    return AnalyzeResponse(**res_data)

        audit_run_id = f"run_{uuid.uuid4().hex}"
        rule_set_hash = compute_kb_file_hash("data/dpdp_kb/dpdp_rules.json")
        clause_set_hash = compute_kb_file_hash("data/dpdp_kb/clauses.json")
        engine_version = "2.0.0"
        model_hash = "xgboost_v1"
        
        with get_db_connection() as conn:
            ensure_evaluation_results_table(conn)
            parent_audit_run_id = get_latest_audit_run_id(clean_tenant_id, conn)

        tenant_name = ""
        # Verify tenant existence in database
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tenant_name FROM governance_config WHERE tenant_id = %s LIMIT 1",
                    (clean_tenant_id,)
                )
                row = cur.fetchone()
                if row:
                    tenant_name = row.get("tenant_name", clean_tenant_id)
                else:
                    cur.execute(
                        "SELECT 1 FROM customer_master WHERE tenant_id = %s LIMIT 1",
                        (clean_tenant_id,)
                    )
                    if not cur.fetchone():
                        # Write NOT_ASSESSABLE run
                        with conn.cursor() as cur_err:
                            cur_err.execute(
                                "INSERT INTO audit_runs (audit_run_id, tenant_id, input_snapshot_hash, rule_set_hash, clause_set_hash, engine_version, model_hash, source_data_row_counts, validation_summary, status, parent_audit_run_id) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                (audit_run_id, clean_tenant_id, "", rule_set_hash, clause_set_hash, engine_version, model_hash, "{}", json.dumps({"error": f"Tenant '{clean_tenant_id}' not found."}), "not_assessable", parent_audit_run_id)
                            )
                        conn.commit()
                        raise HTTPException(
                            status_code=404,
                            detail=f"Tenant '{clean_tenant_id}' not found in the database. Please check the Tenant ID or upload files under 'New Tenant'."
                        )

            # Enforce hash version boundaries only if tenant actually exists
            parent_hash_version = None
            if parent_audit_run_id:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT hash_version FROM audit_runs WHERE audit_run_id = %s",
                        (parent_audit_run_id,)
                    )
                    p_row = cur.fetchone()
                    if p_row:
                        parent_hash_version = p_row["hash_version"] if isinstance(p_row, dict) else p_row[0]
            
            current_version = os.getenv("HASH_VERSION", "v2")
            if parent_hash_version and parent_hash_version != current_version:
                raise HTTPException(
                    status_code=400,
                    detail=f"Re-analysis rejected: Mismatched hash version. This tenant's data was previously assessed with version '{parent_hash_version}', but current engine version is '{current_version}'. You must migrate the tenant dataset completely."
                )

        # Retrieve row counts and snapshot hash before analysis
        with get_db_connection() as conn:
            row_counts = get_tenant_row_counts(clean_tenant_id, conn)
            snapshot_hash = compute_tenant_snapshot_hash(clean_tenant_id, conn)

        analysis_result = run_compliance_analysis(clean_tenant_id)
        response = _build_full_response(analysis_result, tenant_name=tenant_name, audit_run_id=audit_run_id, run_status="completed")

        # Insert audit_runs and evaluation_results
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_runs (audit_run_id, tenant_id, input_snapshot_hash, rule_set_hash, clause_set_hash, engine_version, model_hash, source_data_row_counts, validation_summary, status, parent_audit_run_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (audit_run_id, clean_tenant_id, snapshot_hash, rule_set_hash, clause_set_hash, engine_version, model_hash, json.dumps(row_counts), json.dumps({"status": "success"}), "completed", parent_audit_run_id)
                )
                
                serializable_payload = {
                    "tenant_id": response["tenant_id"],
                    "tenant_name": tenant_name or response["tenant_id"],
                    "total_obligations": response["total_obligations"],
                    "internal_control_count": response.get("internal_control_count"),
                    "internal_controls": response.get("internal_controls"),
                    "unique_rules_violated": response["unique_rules_violated"],
                    "total_violation_occurrences": response["total_violation_occurrences"],
                    "risk_score": response["risk_score"],
                    "risk_tier": response["risk_tier"],
                    "status": response["status"],
                    "executive_summary": response["executive_summary"],
                    "total_penalty_exposure_crore": response["total_penalty_exposure_crore"],
                    "risk_contributions": response["risk_contributions"],
                    "violations": [v.model_dump() for v in response["violations"]],
                    "agent_breakdown": {k: v.model_dump() for k, v in response["agent_breakdown"].items()},
                    "remediation_priority": [r.model_dump() for r in response["remediation_priority"]],
                    "ml_layer": response.get("ml_layer"),
                    "run_metadata": response.get("run_metadata"),
                    "findings": response.get("findings"),
                    "rule_execution_statuses": response.get("rule_execution_statuses"),
                    "compliance_score": response.get("compliance_score"),
                    "audit_run_id": audit_run_id,
                    "run_status": response.get("run_status"),
                    "failed_rules_count": response.get("failed_rules_count"),
                    "not_assessable_rules_count": response.get("not_assessable_rules_count"),
                    "outcome_count_by_state": response.get("outcome_count_by_state"),
                    "disclaimer": response.get("disclaimer"),
                }
                cur.execute(
                    "INSERT INTO evaluation_results (tenant_id, result_json, risk_score, audit_run_id) "
                    "VALUES (%s, %s, %s, %s)",
                    (clean_tenant_id, json.dumps(serializable_payload, default=str), float(response["risk_score"]), audit_run_id)
                )
            conn.commit()

        return AnalyzeResponse(**response)

    except HTTPException:
        raise
    except Exception as e:
        # Write failed run
        try:
            with get_db_connection() as conn_err:
                with conn_err.cursor() as cur_err:
                    cur_err.execute(
                        "INSERT INTO audit_runs (audit_run_id, tenant_id, input_snapshot_hash, rule_set_hash, clause_set_hash, engine_version, model_hash, source_data_row_counts, validation_summary, status, parent_audit_run_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (audit_run_id, clean_tenant_id, "", rule_set_hash, clause_set_hash, engine_version, model_hash, "{}", json.dumps({"error": str(e)}), "failed", parent_audit_run_id)
                    )
                conn_err.commit()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@router.post("/analyze/upload", response_model=AnalyzeResponse)
async def analyze_upload(
    governance_config: UploadFile = File(...),
    customer_master: UploadFile = File(...),
    consent_records: UploadFile = File(...),
    transaction_events: UploadFile = File(...),
    access_logs: UploadFile = File(...),
    data_lifecycle: UploadFile = File(...),
    security_events: UploadFile = File(...),
    dsar_requests: UploadFile = File(...),
    system_inventory: UploadFile = File(...),
    policies: UploadFile = File(...),
    tenant_id: str = Form(...),
    tenant_name: str = Form(...),
    current_user: AuthUser = Depends(authenticate_user),
):
    verify_tenant_access(tenant_id, current_user)
    
    # ΓöÇΓöÇ Upload requests size limits ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB per file
    uploaded_file_map = {
        "governance_config.csv": governance_config,
        "customer_master.csv": customer_master,
        "consent_records.csv": consent_records,
        "transaction_events.csv": transaction_events,
        "access_logs.csv": access_logs,
        "data_lifecycle.csv": data_lifecycle,
        "security_events.csv": security_events,
        "dsar_requests.csv": dsar_requests,
        "system_inventory.csv": system_inventory,
        "policies.csv": policies,
    }

    for csv_filename, uploaded_file in uploaded_file_map.items():
        chunk = await uploaded_file.read(MAX_FILE_SIZE + 1)
        if len(chunk) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Upload rejected: File '{uploaded_file.filename}' exceeds maximum allowed size of 5MB."
            )
        await uploaded_file.seek(0)

    audit_run_id = f"run_{uuid.uuid4().hex}"
    rule_set_hash = compute_kb_file_hash("data/dpdp_kb/dpdp_rules.json")
    clause_set_hash = compute_kb_file_hash("data/dpdp_kb/clauses.json")
    engine_version = "2.0.0"
    model_hash = "xgboost_v1"

    with get_db_connection() as conn:
        ensure_evaluation_results_table(conn)
        parent_audit_run_id = get_latest_audit_run_id(tenant_id, conn)

    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        uploaded_file_map = {
            "governance_config.csv": governance_config,
            "customer_master.csv": customer_master,
            "consent_records.csv": consent_records,
            "transaction_events.csv": transaction_events,
            "access_logs.csv": access_logs,
            "data_lifecycle.csv": data_lifecycle,
            "security_events.csv": security_events,
            "dsar_requests.csv": dsar_requests,
            "system_inventory.csv": system_inventory,
            "policies.csv": policies,
        }

        for csv_filename, uploaded_file in uploaded_file_map.items():
            csv_bytes = await uploaded_file.read()
            csv_path = Path(temp_dir) / csv_filename
            with open(csv_path, "wb") as f:
                f.write(csv_bytes)

        loaded_data = load_tenant_csvs(Path(temp_dir), tenant_id)
        mapped_data = {}
        for table_name, df in loaded_data.items():
            mapped_data[table_name] = anonymize_dataframe(df, table_name, tenant_id)

        validate_dataset_hash_version(mapped_data)

        # Check if parent hash version matches
        parent_hash_version = None
        if parent_audit_run_id:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT hash_version FROM audit_runs WHERE audit_run_id = %s",
                        (parent_audit_run_id,)
                    )
                    p_row = cur.fetchone()
                    if p_row:
                        parent_hash_version = p_row["hash_version"] if isinstance(p_row, dict) else p_row[0]
        
        current_version = os.getenv("HASH_VERSION", "v2")
        if parent_hash_version and parent_hash_version != current_version:
            raise HTTPException(
                status_code=400,
                detail=f"Re-analysis rejected: Mismatched hash version. This tenant's data was previously assessed with version '{parent_hash_version}', but current engine version is '{current_version}'. You must migrate the tenant dataset completely."
            )

        rows_written = write_tenant_data(tenant_id, mapped_data)

    except Exception as validation_err:
        # Determine status: Validation errors make the run NOT_ASSESSABLE or FAILED
        run_status_val = "not_assessable" if isinstance(validation_err, (TenantValidationError, MissingColumnError, DsarValidationError, EnumValidationError, GovernanceValidationError, TransactionValidationError, ConsentValidationError, SecurityEventValidationError, SystemInventoryValidationError, LifecycleValidationError, CrossFileValidationError)) else "failed"
        
        # Save error info
        validation_summary = {"error": str(validation_err)}
        if hasattr(validation_err, "filename"):
            validation_summary["filename"] = getattr(validation_err, "filename")
        if hasattr(validation_err, "row_number"):
            validation_summary["row_number"] = getattr(validation_err, "row_number")
        if hasattr(validation_err, "field"):
            validation_summary["field"] = getattr(validation_err, "field")
        if hasattr(validation_err, "error_code"):
            validation_summary["error_code"] = getattr(validation_err, "error_code")
        if hasattr(validation_err, "explanation"):
            validation_summary["explanation"] = getattr(validation_err, "explanation")
        if hasattr(validation_err, "errors"):
            validation_summary["errors"] = getattr(validation_err, "errors")

        try:
            with get_db_connection() as conn_err:
                with conn_err.cursor() as cur_err:
                    cur_err.execute(
                        "INSERT INTO audit_runs (audit_run_id, tenant_id, input_snapshot_hash, rule_set_hash, clause_set_hash, engine_version, model_hash, source_data_row_counts, validation_summary, status, parent_audit_run_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (audit_run_id, tenant_id, "", rule_set_hash, clause_set_hash, engine_version, model_hash, "{}", json.dumps(validation_summary), run_status_val, parent_audit_run_id)
                    )
                conn_err.commit()
        except Exception:
            pass

        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        # Re-raise the exact exception type with appropriate HTTP response
        if isinstance(validation_err, HTTPException):
            raise validation_err
        elif isinstance(validation_err, TenantValidationError):
            raise HTTPException(status_code=400, detail={
                "error": "Tenant validation failed",
                "filename": validation_err.filename,
                "row_number": validation_err.row_number,
                "expected_tenant": validation_err.expected_tenant,
                "supplied_tenant": validation_err.supplied_tenant,
                "error_code": validation_err.error_code
            })
        elif isinstance(validation_err, MissingColumnError):
            raise HTTPException(status_code=400, detail={
                "error": "Missing required column",
                "filename": validation_err.filename,
                "field": validation_err.field,
                "error_code": validation_err.error_code,
                "explanation": validation_err.explanation
            })
        elif isinstance(validation_err, (DsarValidationError, EnumValidationError, GovernanceValidationError, TransactionValidationError, ConsentValidationError, SecurityEventValidationError, SystemInventoryValidationError, LifecycleValidationError)):
            raise HTTPException(status_code=400, detail={
                "error": validation_err.__class__.__name__.replace("ValidationError", " validation failed"),
                "filename": validation_err.filename,
                "row_number": validation_err.row_number,
                "field": validation_err.field,
                "error_code": validation_err.error_code,
                "explanation": validation_err.explanation
            })
        elif isinstance(validation_err, CrossFileValidationError):
            raise HTTPException(status_code=400, detail={"error": "Cross-file validation failed", "error_code": "CROSS_FILE_VALIDATION_FAILED", "details": validation_err.errors})
        else:
            raise HTTPException(status_code=500, detail=f"CSV ingestion failed: {str(validation_err)}")

    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    try:
        # Retrieve row counts and snapshot hash before analysis
        with get_db_connection() as conn:
            row_counts = get_tenant_row_counts(tenant_id, conn)
            snapshot_hash = compute_tenant_snapshot_hash(tenant_id, conn)

        analysis_result = run_compliance_analysis(tenant_id)
        response = _build_full_response(analysis_result, tenant_name, audit_run_id=audit_run_id, run_status="completed")
    except Exception as analysis_error:
        try:
            with get_db_connection() as conn_err:
                with conn_err.cursor() as cur_err:
                    cur_err.execute(
                        "INSERT INTO audit_runs (audit_run_id, tenant_id, input_snapshot_hash, rule_set_hash, clause_set_hash, engine_version, model_hash, source_data_row_counts, validation_summary, status, parent_audit_run_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (audit_run_id, tenant_id, "", rule_set_hash, clause_set_hash, engine_version, model_hash, "{}", json.dumps({"error": str(analysis_error)}), "failed", parent_audit_run_id)
                    )
                conn_err.commit()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Analysis engine failed: {str(analysis_error)}"
        )

    try:
        serializable_payload = {
            "tenant_id": response["tenant_id"],
            "tenant_name": tenant_name,
            "total_obligations": response["total_obligations"],
            "internal_control_count": response.get("internal_control_count"),
            "internal_controls": response.get("internal_controls"),
            "unique_rules_violated": response["unique_rules_violated"],
            "total_violation_occurrences": response["total_violation_occurrences"],
            "risk_score": response["risk_score"],
            "risk_tier": response["risk_tier"],
            "status": response["status"],
            "executive_summary": response["executive_summary"],
            "total_penalty_exposure_crore": response["total_penalty_exposure_crore"],
            "risk_contributions": response["risk_contributions"],
            "violations": [v.model_dump() for v in response["violations"]],
            "agent_breakdown": {k: v.model_dump() for k, v in response["agent_breakdown"].items()},
            "remediation_priority": [r.model_dump() for r in response["remediation_priority"]],
            "ml_layer": response.get("ml_layer"),
            "run_metadata": response.get("run_metadata"),
            "findings": response.get("findings"),
            "rule_execution_statuses": response.get("rule_execution_statuses"),
            "compliance_score": response.get("compliance_score"),
            "audit_run_id": audit_run_id,
            "run_status": response.get("run_status"),
            "failed_rules_count": response.get("failed_rules_count"),
            "not_assessable_rules_count": response.get("not_assessable_rules_count"),
            "outcome_count_by_state": response.get("outcome_count_by_state"),
            "disclaimer": response.get("disclaimer"),
        }
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_runs (audit_run_id, tenant_id, input_snapshot_hash, rule_set_hash, clause_set_hash, engine_version, model_hash, source_data_row_counts, validation_summary, status, parent_audit_run_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (audit_run_id, tenant_id, snapshot_hash, rule_set_hash, clause_set_hash, engine_version, model_hash, json.dumps(row_counts), json.dumps({"status": "success"}), "completed", parent_audit_run_id)
                )
                cur.execute(
                    "INSERT INTO evaluation_results (tenant_id, result_json, risk_score, audit_run_id) "
                    "VALUES (%s, %s, %s, %s)",
                    (tenant_id, json.dumps(serializable_payload, default=str), float(response["risk_score"]), audit_run_id)
                )
            conn.commit()
    except Exception as db_ex:
        logging.warning(f"evaluation_results / audit_runs insert failed: {db_ex}")

    return AnalyzeResponse(**response)


@router.get("/report/pdf/{tenant_id}")
def download_pdf(
    tenant_id: str,
    audit_run_id: Optional[str] = None,
    current_user: AuthUser = Depends(authenticate_user),
):
    try:
        verify_tenant_access(tenant_id, current_user)
        from src.report.pdf_generator import generate_pdf_report
        with get_db_connection() as conn:
            resolved_run_id = resolve_audit_run_id(tenant_id, audit_run_id, conn)
            pdf_buffer = generate_pdf_report(tenant_id, conn, resolved_run_id)
            
        return Response(
            content=pdf_buffer.getvalue(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=FinComply_AuditReport_{tenant_id}.pdf"
            }
        )
    except ImportError:
         raise HTTPException(status_code=501, detail="PDF module not implemented yet")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF report")


# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# RULES MANAGEMENT ENDPOINTS (SECURED WITH RBAC - Issue E-05)
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

@router.get("/rules")
def list_rules(
    current_user: AuthUser = Depends(require_authenticated)
):
    """Returns all active rules ordered by rule_id. Requires authenticated user."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT rule_id, rule_name, assigned_agent,
                       severity, enabled, dpdp_section
                FROM rules
                ORDER BY rule_id
                """
            ).fetchall()
        return [{"rule_id": r["rule_id"], "rule_name": r["rule_name"],
                 "assigned_agent": r["assigned_agent"], "severity": r["severity"],
                 "enabled": r["enabled"], "dpdp_section": r["dpdp_section"]} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rules: {str(e)}")


@router.get("/rules/proposed")
def list_proposed_rules(
    current_user: AuthUser = Depends(require_reviewer)
):
    """Returns all pending proposed rules. Requires reviewer or admin role."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT id,
                       proposed_rule->>'rule_id'   AS rule_id,
                       proposed_rule->>'rule_name' AS rule_name,
                       proposed_rule->>'severity'  AS severity,
                       (field_check->>'all_resolved')::boolean AS fields_ok,
                       status,
                       proposed_by,
                       created_at
                FROM proposed_rules
                WHERE status = 'pending'
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [{"id": r["id"], "rule_id": r["rule_id"], "rule_name": r["rule_name"],
                 "severity": r["severity"], "fields_ok": r["fields_ok"],
                 "status": r["status"], "proposed_by": r["proposed_by"],
                 "created_at": str(r["created_at"])} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch proposed rules: {str(e)}")


@router.post("/rules/approve/{proposal_id}")
def approve_rule(
    proposal_id: int,
    current_user: AuthUser = Depends(require_admin),
):
    """Activates a pending proposed rule. Requires admin role."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT id, proposed_rule, field_check, status FROM proposed_rules WHERE id = %s",
                [proposal_id],
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
            if row["status"] != "pending":
                raise HTTPException(
                    status_code=400,
                    detail=f"Proposal {proposal_id} is already '{row['status']}'"
                )

            field_check = row["field_check"]
            if not field_check.get("all_resolved", False):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot activate: missing fields {field_check.get('missing', [])}"
                )

            rule = row["proposed_rule"]
            reviewer = current_user.username

            conn.execute(
                """
                INSERT INTO rules (
                    rule_id, clause_id, rule_name, dpdp_section, description,
                    severity, risk_weight, check_type, assigned_agent,
                    primary_table, join_tables, join_key, evidence_signals,
                    violation_threshold, risk_threshold, recurrence_bonus,
                    enabled, version, effective_date, approved_by
                ) VALUES (
                    %(rule_id)s, %(clause_id)s, %(rule_name)s, %(dpdp_section)s, %(description)s,
                    %(severity)s, %(risk_weight)s, %(check_type)s, %(assigned_agent)s,
                    %(primary_table)s, %(join_tables)s, %(join_key)s, %(evidence_signals)s,
                    %(violation_threshold)s, %(risk_threshold)s, %(recurrence_bonus)s,
                    TRUE, 1, %(effective_date)s, %(approved_by)s
                )
                ON CONFLICT (rule_id) DO UPDATE SET
                    rule_name           = EXCLUDED.rule_name,
                    description         = EXCLUDED.description,
                    evidence_signals    = EXCLUDED.evidence_signals,
                    violation_threshold = EXCLUDED.violation_threshold,
                    risk_threshold      = EXCLUDED.risk_threshold,
                    version             = rules.version + 1,
                    approved_by         = EXCLUDED.approved_by,
                    updated_at          = NOW()
                """,
                {
                    "rule_id":             rule["rule_id"],
                    "clause_id":           rule["clause_id"],
                    "rule_name":           rule["rule_name"],
                    "dpdp_section":        rule.get("dpdp_section", ""),
                    "description":         rule.get("description", ""),
                    "severity":            rule.get("severity", "MEDIUM"),
                    "risk_weight":         rule.get("risk_weight", 0.5),
                    "check_type":          rule.get("check_type", "weighted_evidence"),
                    "assigned_agent":      rule["assigned_agent"],
                    "primary_table":       rule["primary_table"],
                    "join_tables":         json.dumps(rule.get("join_tables") or []),
                    "join_key":            rule.get("join_key"),
                    "evidence_signals":    json.dumps(rule["evidence_signals"]),
                    "violation_threshold": rule["violation_threshold"],
                    "risk_threshold":      rule["risk_threshold"],
                    "recurrence_bonus":    rule.get("recurrence_bonus", 0.0),
                    "effective_date":      date.today().isoformat(),
                    "approved_by":         reviewer,
                },
            )

            conn.execute(
                """
                UPDATE proposed_rules
                SET status = 'approved', reviewer = %s, reviewed_at = NOW()
                WHERE id = %s
                """,
                [reviewer, proposal_id],
            )
            conn.commit()

        log_event(
            RULE_APPROVED,
            details={"rule_id": rule["rule_id"], "proposal_id": proposal_id,
                     "approved_by": reviewer},
            user=reviewer,
        )
        return {"status": "approved", "rule_id": rule["rule_id"], "approved_by": reviewer}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")


@router.post("/rules/reject/{proposal_id}")
def reject_rule(
    proposal_id: int,
    reason: str = "No reason provided",
    current_user: AuthUser = Depends(require_reviewer),
):
    """Rejects a pending proposed rule. Requires reviewer or admin role."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT id, proposed_rule, status FROM proposed_rules WHERE id = %s",
                [proposal_id],
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
            if row["status"] != "pending":
                raise HTTPException(
                    status_code=400,
                    detail=f"Proposal {proposal_id} is already '{row['status']}'"
                )

            reviewer = current_user.username
            rule_id  = row["proposed_rule"].get("rule_id", "unknown")

            conn.execute(
                """
                UPDATE proposed_rules
                SET status = 'rejected', reviewer = %s, review_notes = %s, reviewed_at = NOW()
                WHERE id = %s
                """,
                [reviewer, reason, proposal_id],
            )
            conn.commit()

        log_event(
            RULE_REJECTED,
            details={"rule_id": rule_id, "proposal_id": proposal_id,
                     "rejected_by": reviewer, "reason": reason},
            user=reviewer,
        )
        return {"status": "rejected", "rule_id": rule_id, "rejected_by": reviewer}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rejection failed: {str(e)}")


_bias_report_cache = None

@router.get("/governance/bias-report")
async def get_bias_report(
    current_user: AuthUser = Depends(require_authenticated),
):
  global _bias_report_cache
  if _bias_report_cache is None:
    from src.governance.bias_monitor import (
      run_bias_check, save_bias_report
    )
    _bias_report_cache = run_bias_check()
    save_bias_report(_bias_report_cache)
  return _bias_report_cache


@router.get("/dashboard/{tenant_id}")
def get_dashboard_data(
    tenant_id: str,
    audit_run_id: Optional[str] = None,
    current_user: AuthUser = Depends(authenticate_user),
):
    """
    Returns dashboard analysis data for the specified tenant and audit run.
    """
    try:
        clean_tenant_id = tenant_id.strip()
        verify_tenant_access(clean_tenant_id, current_user)
        with get_db_connection() as conn:
            ensure_evaluation_results_table(conn)
            resolved_run_id = resolve_audit_run_id(clean_tenant_id, audit_run_id, conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT result_json FROM evaluation_results WHERE tenant_id = %s AND audit_run_id = %s",
                    (clean_tenant_id, resolved_run_id)
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="No evaluation results found for this run.")
                res_json = row["result_json"] if isinstance(row, dict) else row[0]
                return res_json if isinstance(res_json, dict) else json.loads(res_json)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/history/{tenant_id}")
def get_report_history(
    tenant_id: str,
    current_user: AuthUser = Depends(authenticate_user),
):
    """
    Returns all audit run history for the specified tenant.
    """
    try:
        clean_tenant_id = tenant_id.strip()
        verify_tenant_access(clean_tenant_id, current_user)
        # Verify tenant existence
        tenant_exists = False
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM governance_config WHERE tenant_id = %s LIMIT 1", (clean_tenant_id,))
                if cur.fetchone():
                    tenant_exists = True
                else:
                    cur.execute("SELECT 1 FROM customer_master WHERE tenant_id = %s LIMIT 1", (clean_tenant_id,))
                    if cur.fetchone():
                        tenant_exists = True
            
            if not tenant_exists:
                raise HTTPException(status_code=404, detail=f"Tenant '{clean_tenant_id}' not found.")

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT audit_run_id, status, created_at, validation_summary FROM audit_runs WHERE tenant_id = %s ORDER BY created_at DESC",
                    (clean_tenant_id,)
                )
                rows = cur.fetchall()
                history = []
                for r in rows:
                    if isinstance(r, dict):
                        history.append({
                            "audit_run_id": r["audit_run_id"],
                            "status": r["status"],
                            "created_at": str(r["created_at"]),
                            "validation_summary": r["validation_summary"]
                        })
                    else:
                        history.append({
                            "audit_run_id": r[0],
                            "status": r[1],
                            "created_at": str(r[2]),
                            "validation_summary": r[3]
                        })
                return {"tenant_id": clean_tenant_id, "history": history}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
