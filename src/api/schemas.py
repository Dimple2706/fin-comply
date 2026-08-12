# src/api/schemas.py

from pydantic import BaseModel
from typing import List, Optional, Dict


class UserRegisterRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    role: Optional[str] = "admin"


class AnalyzeRequest(BaseModel):
    """
    What the client sends to our API.
    Just the tenant_id for now.
    """
    tenant_id: str


# ── XAI Signal Attribution ──────────────────────────────

class SignalDetail(BaseModel):
    """
    SHAP-equivalent attribution for one signal.
    phi = weight × fired (1 if fired, 0 if not).
    Exact for linear additive scoring models.
    Evidence: Lundberg & Lee (2017) NeurIPS.
    """
    signal: str              # "S1", "S2", etc.
    description: str         # Human-readable meaning
    weight: float            # Signal weight in model
    fired: bool              # Whether this signal fired
    reason: str              # Why it fired (from agent)
    phi: float               # SHAP value


class FullExplanation(BaseModel):
    """
    Complete XAI explanation for a compliance violation.
    Maps to ViolationExplanation from the explainability engine.
    All data is computed from real agent signals — nothing hardcoded.
    """
    why_detected: str                     # what_happened (rule template)
    evidence: str                         # what_happened_specific (dynamic, per-record)
    risk_reason: str                      # why_violation (legal citation)
    mitigation: List[str]                 # remediation_steps (structured list)
    signals_analysis: List[SignalDetail]  # Full SHAP attribution table
    top_contributing_signal: str          # Which signal contributed most
    total_shap: float                     # Sum of all phi values
    root_cause: str                       # PROCESS_GAP / TECHNICAL_GAP / etc.
    penalty_exposure_crore: int           # Financial exposure under DPDP Act


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


# ── Full Analysis Response ───────────────────────────────

class AnalyzeResponse(BaseModel):
    tenant_id:                   str
    unique_rules_violated:       int
    total_violation_occurrences: int
    risk_score:                  float
    risk_tier:                   str
    violations:                  List[ViolationItem]
    status:                      str
    executive_summary:           Optional[str] = None
    agent_breakdown:             Optional[Dict[str, AgentBreakdown]] = None
    risk_contributions:          Optional[Dict[str, float]] = None
    remediation_priority:        Optional[List[RemediationItem]] = None
    total_penalty_exposure_crore: Optional[int] = None