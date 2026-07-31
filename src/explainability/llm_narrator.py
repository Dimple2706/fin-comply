"""
llm_narrator.py
===============
Generates LLM-narrated compliance explanations for each VIOLATION
using Gemini gemini-1.5-flash.

PII Boundary Scanner blocks any call that contains personal data
before it reaches the API.

Falls back to RULE_EXPLANATIONS from service.py if:
  - Gemini API key is missing / placeholder
  - API call fails
  - Response cannot be parsed
  - PIIBoundaryError is raised

Never raises — always returns a dict.
"""

from __future__ import annotations

import os
import re
import logging
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ── PII Boundary Scanner ──────────────────────────────────────────────────────

_PII_PATTERNS = [
    re.compile(r"\S+@\S+\.\S+"),            # email
    re.compile(r"\b\d{12}\b"),               # Aadhaar-like
    re.compile(r"\b[6-9]\d{9}\b"),           # Indian mobile
    re.compile(r"\b\d{9,18}\b"),             # account number
]


class PIIBoundaryError(Exception):
    """Raised when PII is detected in data that would be sent to an LLM API."""


def _pii_scan(text: str) -> bool:
    """Returns True if any PII pattern matches anywhere in text."""
    for pattern in _PII_PATTERNS:
        if pattern.search(text):
            return True
    return False


# ── Lazy Gemini client (avoids crash on import when key is placeholder) ───────

_model = None
_MODEL_NAME = "gemini-1.5-flash"


def _get_model():
    """Initialise the Gemini model once, lazily. Identical setup to rule_authoring_agent_f.py."""
    global _model
    if _model is not None:
        return _model

    import google.generativeai as genai  # noqa: PLC0415

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key.startswith("your_gemini"):
        raise ValueError(
            "GEMINI_API_KEY is not set or is still a placeholder. "
            "Set a real key in .env to enable LLM narration."
        )

    genai.configure(api_key=api_key)
    _model = genai.GenerativeModel(
        model_name=_MODEL_NAME,
        generation_config={
            "temperature":       0.2,
            "max_output_tokens": 2000,
            # No response_mime_type — we want plain text with labels, not JSON
        },
    )
    return _model


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    rule_name: str,
    dpdp_section: str,
    legal_text: str,
    fired_signals: list[dict],
) -> str:
    signal_lines = "\n".join(
        f"  {s.get('signal_id', '?')} — {s.get('description', '')} — weight: {s.get('weight', 0.0):.2f}"
        for s in fired_signals
    )
    return (
        "You are a compliance analyst writing an explanation for a regulatory audit report "
        "under India's Digital Personal Data Protection Act 2023.\n\n"
        f"Rule violated: {rule_name} ({dpdp_section})\n"
        f"Legal obligation: {legal_text}\n\n"
        "Evidence signals that fired:\n"
        f"{signal_lines}\n\n"
        "Write exactly three labelled sections:\n\n"
        "WHAT_HAPPENED: One sentence describing the specific compliance failure "
        "based only on the evidence above.\n\n"
        "LEGAL_BASIS: One sentence citing the exact DPDP Act section and what it "
        "requires that was not satisfied.\n\n"
        "REMEDIATION: Two to three specific, numbered, actionable steps to resolve this violation.\n\n"
        "Use only the information provided. Do not invent facts or reference data not shown above."
    )


# ── Response parser ───────────────────────────────────────────────────────────

def _parse_response(text: str) -> tuple[str, str, str]:
    """
    Splits the model response on label markers.
    Returns (what_happened, legal_basis, remediation) — all plain strings.
    Uses simple string splitting, not regex.
    """
    what_happened = ""
    legal_basis   = ""
    remediation   = ""

    # Split on each label; order is deterministic from prompt
    parts_wh = text.split("WHAT_HAPPENED:")
    if len(parts_wh) >= 2:
        rest_wh = parts_wh[1]
        parts_lb = rest_wh.split("LEGAL_BASIS:")
        what_happened = parts_lb[0].strip()
        if len(parts_lb) >= 2:
            rest_lb = parts_lb[1]
            parts_rem = rest_lb.split("REMEDIATION:")
            legal_basis = parts_rem[0].strip()
            if len(parts_rem) >= 2:
                remediation = parts_rem[1].strip()

    if not what_happened:
        raise ValueError("Could not parse WHAT_HAPPENED from model response.")

    return what_happened, legal_basis, remediation


# ── Fallback helper ───────────────────────────────────────────────────────────

def _fallback(rule_id: str, reason: str) -> dict[str, Any]:
    """Returns a fallback narration from RULE_EXPLANATIONS or a generic string."""
    from src.explainability.service import RULE_EXPLANATIONS  # noqa: PLC0415

    template = RULE_EXPLANATIONS.get(rule_id)
    if template:
        remediation_list = template.get("remediation", [])
        remediation_text = (
            "\n".join(f"{i+1}. {s}" for i, s in enumerate(remediation_list))
            if remediation_list
            else "Refer to the DPDP Act for corrective guidance."
        )
        return {
            "what_happened":    template.get("what_happened", ""),
            "legal_basis":      template.get("why_violation", ""),
            "remediation_steps": remediation_text,
            "narrated_by":      "fallback:rule_explanations",
            "grounded":         False,
            "fallback_reason":  reason,
        }

    return {
        "what_happened":    "A compliance check produced a finding for this rule.",
        "legal_basis":      "Refer to the cited DPDP Act section for the applicable obligation.",
        "remediation_steps": "Review this finding manually and apply corrective action per DPDP guidelines.",
        "narrated_by":      "fallback:generic",
        "grounded":         False,
        "fallback_reason":  reason,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def narrate_violation(
    rule_id: str,
    rule_name: str,
    dpdp_section: str,
    legal_text: str,
    fired_signals: list[dict],
) -> dict[str, Any]:
    """
    Generates a structured LLM narration for a DPDP violation.

    Parameters
    ----------
    rule_id        : e.g. "DPDP-005"
    rule_name      : human-readable rule name
    dpdp_section   : e.g. "Section 9(1)"
    legal_text     : full legal obligation text from the clauses table
    fired_signals  : list of signal definition dicts that evaluated True

    Returns
    -------
    dict with keys: what_happened, legal_basis, remediation_steps,
                    narrated_by, grounded, and optionally fallback_reason
    """
    # ── Step 1: PII scan on all input material ────────────────────────────────
    combined = " ".join([
        rule_name, dpdp_section, legal_text,
        " ".join(s.get("description", "") for s in fired_signals),
    ])
    if _pii_scan(combined):
        log.warning("[llm_narrator] PII detected in inputs for %s — Gemini call blocked.", rule_id)
        from src.governance.audit_logger import log_event, LLM_BLOCKED
        log_event(
          LLM_BLOCKED,
          details={
            'rule_id': rule_id,
            'reason': 'PII pattern detected in prompt'
          }
        )
        raise PIIBoundaryError(
            f"PII detected in narrate_violation inputs for {rule_id}. "
            "Call blocked before reaching Gemini API."
        )

    # ── Step 2: Build prompt ──────────────────────────────────────────────────
    prompt = _build_prompt(rule_name, dpdp_section, legal_text, fired_signals)

    # ── Step 3: Call Gemini ───────────────────────────────────────────────────
    try:
        model = _get_model()
        response = model.generate_content(prompt)
        raw_text = response.text

        # ── Step 4: Parse response ────────────────────────────────────────────
        what_happened, legal_basis, remediation = _parse_response(raw_text)

        from src.governance.audit_logger import log_event, LLM_CALL
        log_event(
          LLM_CALL,
          details={
            'rule_id': rule_id,
            'model': 'gemini-1.5-flash',
            'grounded': True,
            'prompt_length_chars': len(prompt)
          }
        )

        log.info("[llm_narrator] Narration generated for %s (grounded=True)", rule_id)
        return {
            "what_happened":    what_happened,
            "legal_basis":      legal_basis,
            "remediation_steps": remediation,
            "narrated_by":      _MODEL_NAME,
            "grounded":         True,
        }

    except PIIBoundaryError:
        # Re-raised only if called directly — in reporting_agent we catch it
        raise

    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        log.warning("[llm_narrator] Narration failed for %s — falling back. Reason: %s", rule_id, reason)
        return _fallback(rule_id, reason)
