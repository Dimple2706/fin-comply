# src/api/schemas.py

from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class UserRegisterRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    role: Optional[str] = "admin"


class AnalyzeRequest(BaseModel):
    """
    What the client sends to our API.
    """
    tenant_id: str
    audit_run_id: Optional[str] = None


# ── XAI Signal Attribution ──────────────────────────────

class SignalDetail(BaseModel):
    """
    Deterministic rule signal attribution.
    signal_contribution = weight × fired (1 if fired, 0 if not).
    Evidence: Deterministic heuristic rule scoring.
    """
    signal: str                                  # "S1", "S2", etc.
    description: str                             # Human-readable meaning
    weight: float                                # Signal weight in rule definition
    fired: bool                                  # Whether this signal fired
    reason: str                                  # Why it fired (from agent)
    signal_contribution: float                   # Deterministic contribution
    phi: Optional[float] = None                  # Backward-compatible alias for signal_contribution


class FullExplanation(BaseModel):
    """
    Complete XAI explanation for a compliance violation.
    Maps to ViolationExplanation from the explainability engine.
    All data is computed from real agent signals — nothing hardcoded.
    """
    why_detected: str                            # what_happened (rule template)
    evidence: str                                # what_happened_specific (dynamic, per-record)
    risk_reason: str                             # why_violation (legal citation)
    mitigation: List[str]                        # remediation_steps (structured list)
    signals_analysis: List[SignalDetail]         # Rule signal attribution table
    top_contributing_signal: str                 # Which signal contributed most
    total_signal_weight: float                   # Sum of fired signal weights
    total_shap: Optional[float] = None           # Backward-compatible alias for total_signal_weight
    root_cause: str                              # PROCESS_GAP / TECHNICAL_GAP / etc.
    penalty_exposure_crore: int                  # Financial exposure under DPDP Act
    penalty_exposure_message: Optional[str] = "Maximum statutory exposure estimate — not an actual or certain fine."



# ── Violation ────────────────────────────────────────────

class ViolationItem(BaseModel):
    """
    One unique violated rule in the compliance check.
    Groups all occurrences of the same rule into one item.
    """
    rule_id:               str
    rule_name:             str
    dpdp_section:          str
    severity:              str
    risk_weight:           float
    occurrence_count:      int
    contribution_to_score: float
    reason:                str
    explanation:           FullExplanation
    penalty_exposure_crore: int
    penalty_exposure_message: Optional[str] = "Maximum statutory exposure estimate — not an actual or certain fine."
    root_cause:            str
    matched_record_ids:    List[str] = []
    fields_triggered:      List[str] = []
    matched_logs_count:    int = 0


# ── Agent Breakdown ──────────────────────────────────────

class AgentBreakdown(BaseModel):
    violations: int
    warnings:   int


# ── Remediation Item ─────────────────────────────────────

class RemediationItem(BaseModel):
    priority:               int
    rule_id:                str
    rule_name:              str
    action:                 str
    urgency:                str
    penalty_exposure_crore: int


# ── Run Metadata & Governance Versioning ─────────────────

class RunMetadata(BaseModel):
    engine_version:     str = "1.0.0"
    schema_version:     str = "2026.1"
    active_rule_count:  int
    model_version:      str = "1.0"
    model_sha256:       Optional[str] = None
    evaluated_at:       str


class FindingItem(BaseModel):
    rule_id: str
    record_id: str
    outcome: str
    reason: Optional[str] = None


class RuleExecutionStatus(BaseModel):
    rule_id: str
    status: str
    error_message: Optional[str] = None
    partial_results_discarded: bool = False


# ── Full Analysis Response ───────────────────────────────

class AnalyzeResponse(BaseModel):
    tenant_id:                    str
    total_obligations:            int
    unique_rules_violated:        int
    total_violation_occurrences:  int
    risk_score:                   float
    risk_tier:                    str
    violations:                   List[ViolationItem]
    status:                       str
    executive_summary:            Optional[str] = None
    agent_breakdown:              Optional[Dict[str, AgentBreakdown]] = None
    risk_contributions:           Optional[Dict[str, float]] = None
    remediation_priority:         Optional[List[RemediationItem]] = None
    total_penalty_exposure_crore: Optional[int] = None
    ml_layer:                     Optional[Dict[str, Any]] = None
    run_metadata:                 Optional[RunMetadata] = None
    findings:                     Optional[List[FindingItem]] = None
    rule_execution_statuses:      Optional[List[RuleExecutionStatus]] = None
    compliance_score:             Optional[Dict[str, Any]] = None
    penalty_exposure_message:     Optional[str] = "Maximum statutory exposure estimate — not an actual or certain fine."
    audit_run_id:                 Optional[str] = None
    run_status:                   Optional[str] = None
    failed_rules_count:           Optional[int] = None
    not_assessable_rules_count:   Optional[int] = None
    outcome_count_by_state:       Optional[Dict[str, int]] = None
    disclaimer:                   Optional[str] = "Maximum statutory exposure estimate — not an actual or certain fine."

