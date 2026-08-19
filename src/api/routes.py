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
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response

from src.governance.audit_logger import log_event, RULE_APPROVED, RULE_REJECTED
from src.api.auth import require_admin, require_reviewer, require_authenticated, AuthUser

from src.api.schemas import (
    AnalyzeRequest, AnalyzeResponse, ViolationItem,
    FullExplanation, SignalDetail, AgentBreakdown, RemediationItem,
)
from src.anonymization.csv_loader import load_tenant_csvs
from src.anonymization.field_mapper import anonymize_dataframe
from src.anonymization.db_writer import write_tenant_data
from src.agent_layer.orchestrator import run_compliance_analysis
from src.explainability.service import enrich_violations, generate_executive_summary, RULE_EXPLANATIONS
from src.explainability.report_builder import URGENCY_ORDER, SEVERITY_TO_URGENCY

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'compliance_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD')   # Must be set in .env Ã¢â‚¬â€ no hardcoded fallback

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
    Create evaluation_results if missing, so inserts never fail silently.
    """
    with conn.cursor() as cur:
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


# ─────────────────────────────────────────────────────────────
# SHARED HELPERS — used by both /analyze and /analyze/upload
# ─────────────────────────────────────────────────────────────

def _build_full_response(analysis_result: dict, tenant_name: str = "") -> dict:
    tenant_id = analysis_result["tenant_id"]
    contributions = analysis_result.get("risk_contributions", {})

    all_records = (
        analysis_result.get("violations", [])
        + analysis_result.get("warnings", [])
    )
    enriched = enrich_violations(all_records, contributions)

    display_name = tenant_name or tenant_id

    # ── Executive Summary (fail-safe) ──
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

    # ── Group violations by rule_id ──
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
                reason=s.get("reason", "—"),
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

    return {
        "tenant_id": tenant_id,
        "total_obligations": int(analysis_result.get("total_obligations", 0)),
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
        "ml_layer": analysis_result.get("ml_layer"),
        "run_metadata": analysis_result.get("run_metadata"),
    }


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# ENDPOINTS
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

@router.get("/health")
def health_check():
    return {
        "status": "running",
        "service": "Fin-Comply Ã¢â‚¬â€ DPDP Compliance Engine"
    }

@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_tenant(
    request: AnalyzeRequest,
):
    try:
        clean_tenant_id = request.tenant_id.strip()
        if not clean_tenant_id:
            raise HTTPException(status_code=400, detail="Tenant ID cannot be empty.")
            
        # Verify tenant existence in database
        tenant_name = ""
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
                        raise HTTPException(
                            status_code=404,
                            detail=f"Tenant '{clean_tenant_id}' not found in the database. Please check the Tenant ID or upload files under 'New Tenant'."
                        )

        analysis_result = run_compliance_analysis(clean_tenant_id)
        response = _build_full_response(analysis_result, tenant_name=tenant_name)

        try:
            serializable_payload = {
                "tenant_id": response["tenant_id"],
                "tenant_name": tenant_name or response["tenant_id"],
                "total_obligations": response["total_obligations"],
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
            }
            with get_db_connection() as conn:
                ensure_evaluation_results_table(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO evaluation_results "
                        "(tenant_id, result_json, risk_score) "
                        "VALUES (%s, %s, %s)",
                        (
                            clean_tenant_id,
                            json.dumps(serializable_payload, default=str),
                            float(response["risk_score"]),
                        ),
                    )
                conn.commit()
        except Exception as db_ex:
            logging.warning(f"evaluation_results insert failed: {db_ex}")

        return AnalyzeResponse(**response)

    except HTTPException:
        raise
    except Exception as e:
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
):
    try:
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

            rows_written = write_tenant_data(tenant_id, mapped_data)

        except Exception as loader_error:
            raise HTTPException(
                status_code=500,
                detail=f"CSV ingestion failed: {str(loader_error)}"
            )
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

        try:
            analysis_result = run_compliance_analysis(tenant_id)
            response = _build_full_response(analysis_result, tenant_name)
        except Exception as analysis_error:
            raise HTTPException(
                status_code=500,
                detail=f"Analysis engine failed: {str(analysis_error)}"
            )

        try:
            # Serialize the FULL response including violations, agent_breakdown, remediation
            serializable_payload = {
                "tenant_id": response["tenant_id"],
                "tenant_name": tenant_name,
                "total_obligations": response["total_obligations"],
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
            }
            with get_db_connection() as conn:
                ensure_evaluation_results_table(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO evaluation_results "
                        "(tenant_id, result_json, risk_score) "
                        "VALUES (%s, %s, %s)",
                        (
                            tenant_id,
                            json.dumps(serializable_payload, default=str),
                            float(response["risk_score"]),
                        ),
                    )
                conn.commit()
        except Exception as db_ex:
            logging.warning(f"evaluation_results insert failed: {db_ex}")

        return AnalyzeResponse(**response)

    except HTTPException:
        raise
    except ValueError as val_error:
        raise HTTPException(
            status_code=400,
            detail=f"Validation error: {str(val_error)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Upload analysis failed: {str(e)}"
        )


@router.get("/report/pdf/{tenant_id}")
def download_pdf(
    tenant_id: str,
):
    """
    Placeholder PDF endpoint. (PDF Generation module to be built in Phase 4).
    """
    try:
        from src.report.pdf_generator import generate_pdf_report
        with get_db_connection() as conn:
            pdf_buffer = generate_pdf_report(tenant_id, conn)
            
        return Response(
            content=pdf_buffer.getvalue(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=FinComply_AuditReport_{tenant_id}.pdf"
            }
        )
    except ImportError:
         raise HTTPException(status_code=501, detail="PDF module not implemented yet")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF report")


# ─────────────────────────────────────────────────────────────
# RULES MANAGEMENT ENDPOINTS (SECURED WITH RBAC - Issue E-05)
# ─────────────────────────────────────────────────────────────

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
async def get_bias_report():
  global _bias_report_cache
  if _bias_report_cache is None:
    from src.governance.bias_monitor import (
      run_bias_check, save_bias_report
    )
    _bias_report_cache = run_bias_check()
    save_bias_report(_bias_report_cache)
  return _bias_report_cache

