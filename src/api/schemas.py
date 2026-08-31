# src/api/schemas.py

import re

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any


# ── Auth Schemas ─────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    email: str = Field(min_length=3, max_length=254)
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    tenant_id: str = Field(min_length=1, max_length=64)
    tenant_name: str = Field(min_length=2, max_length=128)

    @field_validator("name", "tenant_name")
    @classmethod
    def validate_display_text(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 2 or any(ord(char) < 32 for char in clean):
            raise ValueError("must contain at least two printable characters")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        clean = value.strip().lower()
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", clean):
            raise ValueError("must be a valid email address")
        return clean

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        clean = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", clean):
            raise ValueError("must use 3-64 letters, numbers, underscores, or hyphens")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("must be at most 72 UTF-8 bytes for bcrypt")
        checks = (
            any(char.islower() for char in value),
            any(char.isupper() for char in value),
            any(char.isdigit() for char in value),
            any(not char.isalnum() for char in value),
        )
        if not all(checks):
            raise ValueError(
                "must include uppercase, lowercase, number, and special character"
            )
        return value

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, value: str) -> str:
        clean = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{1,64}", clean):
            raise ValueError("must use only letters, numbers, underscores, or hyphens")
        return clean


class UserLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def normalize_login_username(cls, value: str) -> str:
        clean = value.strip()
        if not clean or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", clean):
            raise ValueError("invalid username format")
        return clean

    @field_validator("password")
    @classmethod
    def validate_login_password_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password is too long")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    name: str
    role: str
    tenant_id: Optional[str] = None   # First authorized tenant (for auto-fill)


class UserPublic(BaseModel):
    id: int
    name: str
    email: str
    username: str
    role: str
    tenant_id: Optional[str] = None   # First authorized tenant
    created_at: Optional[str] = None


# ── Analyze Request ──────────────────────────────────────

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
    engine_version:         str = "1.0.0"
    schema_version:         str = "2026.1"
    active_rule_count:      int
    model_version:          str = "1.0"
    model_sha256:           Optional[str] = None
    evaluated_at:           str
    statutory_rule_count:   Optional[int] = None
    internal_control_count: Optional[int] = None


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
    internal_control_count:       Optional[int] = None
    internal_controls:            Optional[Dict[str, Any]] = None
    regulatory_context:           Optional[Dict[str, Any]] = None
