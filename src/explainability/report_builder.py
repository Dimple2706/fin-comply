import uuid
import datetime
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.explainability.explanation import ViolationExplanation
from src.explainability.service import generate_executive_summary

URGENCY_ORDER = {
    "IMMEDIATE": 1,
    "HIGH": 2,
    "MEDIUM": 3,
    "LOW": 4
}

SEVERITY_TO_URGENCY = {
    "CRITICAL": "IMMEDIATE",
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW"
}

def build_compliance_report(
    tenant_id: str,
    tenant_name: Optional[str],
    analysis_result: Dict[str, Any],
    all_explanations: List[ViolationExplanation]
) -> Dict[str, Any]:
    """
    Builds the complete compliance report for a given tenant.

    Args:
        tenant_id: The ID of the tenant.
        tenant_name: The human-readable name of the tenant. If None, will be fetched from DB.
        analysis_result: The raw agent orchestrator analysis dictionary.
        all_explanations: A list of enriched ViolationExplanation objects.

    Returns:
        A fully constructed and JSON-serializable report dictionary.
    """
    # 1. Resolve tenant_name if not provided
    if not tenant_name:
        try:
            from src.agent_layer.db_connection import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    res = cur.execute(
                        "SELECT tenant_name FROM governance_config WHERE tenant_id = %s",
                        (tenant_id,)
                    ).fetchone()
                    if res and res.get("tenant_name"):
                        tenant_name = res["tenant_name"]
                    else:
                        tenant_name = tenant_id
        except Exception:
            tenant_name = tenant_id

    # 2. Separate explanations into violations and warnings
    violation_exps = [e for e in all_explanations if e.outcome == "VIOLATION"]
    warning_exps = [e for e in all_explanations if e.outcome == "WARNING"]

    # Rank violations by risk_contribution descending
    violation_exps.sort(key=lambda e: e.risk_contribution, reverse=True)
    
    # 3. Compile tier description and risk metrics
    tier_descriptions = {
        "COMPLIANT": "No violations detected. All DPDP obligations appear to be met.",
        "LOW": "Minor compliance gaps identified. Remediation recommended within 90 days.",
        "MEDIUM": "Moderate compliance failures present. Remediation required within 30 days.",
        "HIGH": "Significant violations found. Immediate remediation required.",
        "CRITICAL": "Critical DPDP violations detected. Board-level escalation recommended."
    }
    tier = analysis_result.get("risk_tier", "COMPLIANT")
    
    # Deduplicate maximum penalty exposure by rule_id
    seen_rules = set()
    total_penalty = 0
    for v in violation_exps:
        if v.rule_id not in seen_rules:
            total_penalty += v.penalty_exposure_crore
            seen_rules.add(v.rule_id)
            
    rules_violated = len(seen_rules)
    rules_with_warnings = len({e.rule_id for e in warning_exps})

    # Prepare Executive Summary
    exec_summary = generate_executive_summary(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        explanations=all_explanations,
        risk_score=analysis_result.get("risk_score", 0.0),
        tier=tier
    )

    # 4. Remediation Priority
    urgency_sort_map = {
        "CRITICAL": 1,
        "HIGH": 2,
        "MEDIUM": 3,
        "LOW": 4
    }
    urgency_string_map = {
        "CRITICAL": "IMMEDIATE",
        "HIGH": "HIGH",
        "MEDIUM": "MEDIUM",
        "LOW": "LOW"
    }

    def sort_key(v: ViolationExplanation):
        u_score = urgency_sort_map.get(v.severity, 4)
        return (u_score, -v.risk_contribution, -v.penalty_exposure_crore)

    sorted_for_rem = sorted(violation_exps, key=sort_key)
    rem_priority = []
    seen_rem = set()
    priority_counter = 1
    
    for v in sorted_for_rem:
        if v.rule_id not in seen_rem:
            u_str = urgency_string_map.get(v.severity, "LOW")
            first_action = v.remediation_steps[0] if v.remediation_steps else "Review violation"
            rem_priority.append({
                "priority": priority_counter,
                "rule_id": v.rule_id,
                "rule_name": v.rule_name,
                "action": first_action,
                "urgency": u_str,
                "penalty_exposure_crore": v.penalty_exposure_crore
            })
            seen_rem.add(v.rule_id)
            priority_counter += 1

    # 5. Structure final report
    report_violations = []
    for rank, e in enumerate(violation_exps, start=1):
        # Insert rank at the top level
        report_violations.append({
            "rank": rank,
            **e.to_dict()
        })

    report = {
        "report_id": uuid.uuid4().hex[:8],
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "executive_summary": exec_summary,
        "risk_assessment": {
            "score": analysis_result.get("risk_score", 0.0),
            "tier": tier,
            "tier_description": tier_descriptions.get(tier, ""),
            "max_penalty_exposure_crore": total_penalty,
            "rules_violated": rules_violated,
            "rules_with_warnings": rules_with_warnings,
            "rules_checked": analysis_result.get("total_obligations", 16)
        },
        "violations": report_violations,
        "warnings": [e.to_dict() for e in warning_exps],
        "agent_breakdown": analysis_result.get("agent_breakdown", {}),
        "remediation_priority": rem_priority
    }
    
    return report

def save_report(report: Dict[str, Any], tenant_id: str) -> Path:
    """
    Saves the JSON generated report to the outputs/reports/ directory. 
    Handles basic serialization for Datetimes.
    """
    out_dir = Path("outputs/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{tenant_id}_{timestamp}.json"
    path = out_dir / filename
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
        
    return path
