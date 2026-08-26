"""
rule_authoring_agent.py  (Gemini version)
=========================================
Only two things changed from the Anthropic version:
  1. Top imports — google-generativeai instead of anthropic
  2. propose_rule() — Gemini API call instead of Anthropic

Everything else is identical:
  save_proposal(), activate_rule(), reject_proposal()

Install:
    pip install google-generativeai psycopg[binary]

Set key (Windows):
    set GEMINI_API_KEY=AIzaSy-your-key-here
"""

import os
import json
import re
import psycopg
import google.generativeai as genai
from datetime import date
from typing import Optional

from agent_layer.field_registry_f import check_rule_fields, get_flat_field_list

# ── Gemini client ──────────────────────────────────────────────────────────────
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
_model = genai.GenerativeModel(
    model_name="gemini-3.6-flash",
    generation_config={
        "temperature":        0.2,
        "max_output_tokens":  2000,
        "response_mime_type": "application/json",
    }
)

# ── Prompt builder (unchanged) ─────────────────────────────────────────────────

def _build_prompt(source_text: str, conn: psycopg.Connection) -> str:
    example_row = conn.execute("""
        SELECT rule_id, clause_id, rule_name, dpdp_section, description,
               severity, risk_weight, check_type, assigned_agent,
               primary_table, join_tables, join_key,
               evidence_signals, violation_threshold, risk_threshold,
               recurrence_bonus
        FROM   rules
        WHERE  enabled = TRUE
        ORDER  BY rule_id
        LIMIT  1
    """).fetchone()

    example_rule = json.dumps(dict(example_row), indent=2, default=str) if example_row else "{}"

    last_id_row     = conn.execute("SELECT rule_id FROM rules ORDER BY rule_id DESC LIMIT 1").fetchone()
    last_num        = int(last_id_row["rule_id"].split("-")[1]) if last_id_row else 16
    next_rule_id    = f"DPDP-{str(last_num + 1).zfill(3)}"

    last_clause_row = conn.execute("SELECT clause_id FROM clauses ORDER BY clause_id DESC LIMIT 1").fetchone()
    last_clause_num = int(last_clause_row["clause_id"].split("-")[1]) if last_clause_row else 16
    next_clause_id  = f"DPDP-{str(last_clause_num + 1).zfill(3)}"

    field_list  = get_flat_field_list(conn)
    field_block = "\n".join(
        f"  {table}: {', '.join(fields)}"
        for table, fields in field_list.items()
        if fields
    )

    return f"""You are a DPDP (Digital Personal Data Protection Act 2023) compliance rule author for an Indian fintech compliance system.

Your task: given regulatory text, output a SINGLE valid JSON rule definition matching the schema below.

SCHEMA TEMPLATE (one real rule from the live system):
{example_rule}

CONSTRAINTS:
1. rule_id: Use "{next_rule_id}"
2. clause_id: Use "{next_clause_id}"
3. check_type: Always "weighted_evidence"
4. evidence_signals: 2 to 4 signals. Weights MUST sum to exactly 1.0.
5. violation_threshold must be greater than risk_threshold (both between 0 and 1)
6. recurrence_bonus: between 0.0 and 0.3
7. assigned_agent: one of regulation_agent | audit_agent | risk_agent
8. primary_table: must be one of the tables in AVAILABLE FIELDS below
9. join_tables: array of additional tables needed, or []
10. join_key: shared FK column name if joining, else null
11. evidence_signals.field: ONLY use field names from AVAILABLE FIELDS below
12. evidence_signals.operator: only in | not_in | equals | not_equals | not_matches | less_than | greater_than | is_null | is_not_null
13. Output ONLY the JSON object. No explanation. No markdown. No code fences.

AVAILABLE FIELDS PER TABLE:
{field_block}

VALID ENUM VALUES:
  consent_status:     active, expired, revoked, withdrawn, granted
  retention_status:   active, expired, pending_deletion, deleted
  fulfillment_status: pending, fulfilled, partially_fulfilled, rejected
  employee_role:      collections_agent, underwriter, customer_support, data_analyst, compliance_officer, engineer, manager
  access_outcome:     granted, denied
  encryption_type:    AES-256, AES-128, RSA-2048, none, md5
  severity:           LOW, MEDIUM, HIGH, CRITICAL
  assigned_agent:     regulation_agent, audit_agent, risk_agent

REGULATORY TEXT TO CONVERT:
{source_text}"""


# ── propose_rule — only function that changed ──────────────────────────────────

def propose_rule(source_text: str, conn: psycopg.Connection) -> dict:
    prompt   = _build_prompt(source_text, conn)
    response = _model.generate_content(prompt, request_options={"timeout": 10.0})
    raw      = response.text.strip()

    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$",          "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini output was not valid JSON.\nError: {e}\nRaw:\n{raw}")


# ── Everything below is identical to the Anthropic version ────────────────────

def save_proposal(
    proposed_rule: dict,
    source_text:   str,
    conn:          psycopg.Connection,
    proposed_by:   str = "llm_authoring_agent"
) -> int:
    field_check = check_rule_fields(proposed_rule, conn)

    row = conn.execute("""
        INSERT INTO proposed_rules
            (proposed_by, source_text, proposed_rule, field_check, status)
        VALUES (%s, %s, %s, %s, 'pending')
        RETURNING id
    """, [
        proposed_by,
        source_text,
        json.dumps(proposed_rule),
        json.dumps(field_check),
    ]).fetchone()

    conn.commit()
    proposal_id = row["id"]

    from src.governance.audit_logger import log_event, RULE_PROPOSED
    log_event(
      RULE_PROPOSED,
      details={
        'proposed_rule_id': proposal_id,
        'source': 'gemini_rule_authoring_agent'
      }
    )

    print(f"\n── Proposal saved (id={proposal_id}) ──")
    print(f"  Rule ID   : {proposed_rule.get('rule_id')}")
    print(f"  Rule Name : {proposed_rule.get('rule_name')}")
    print(f"  Agent     : {proposed_rule.get('assigned_agent')}")
    print(f"  Severity  : {proposed_rule.get('severity')}")
    print(f"\n── Field Registry Result ──")
    print(f"  All resolved : {field_check['all_resolved']}")
    if field_check.get("resolved"):
        print(f"  Resolved     : {[r['field'] for r in field_check['resolved']]}")
    if field_check.get("in_jsonb"):
        print(f"  In JSONB     : {[r['field'] for r in field_check['in_jsonb']]}")
    if field_check.get("missing"):
        print(f"  ⚠ MISSING    : {field_check['missing']}")
        print("  → Cannot approve until missing fields are resolved.")

    return proposal_id


def activate_rule(
    proposal_id:  int,
    reviewer:     str,
    conn:         psycopg.Connection,
    review_notes: Optional[str] = None
) -> str:
    row = conn.execute("""
        SELECT id, proposed_rule, field_check, status
        FROM   proposed_rules WHERE id = %s
    """, [proposal_id]).fetchone()

    if not row:
        raise ValueError(f"No proposal found with id={proposal_id}")
    if row["status"] != "pending":
        raise ValueError(f"Proposal {proposal_id} is already '{row['status']}'.")

    field_check = row["field_check"]
    if not field_check.get("all_resolved", False):
        raise ValueError(
            f"Cannot activate proposal {proposal_id}: "
            f"missing fields: {field_check.get('missing', [])}"
        )

    rule = row["proposed_rule"]

    conn.execute("""
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
    """, {
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
    })

    conn.execute("""
        UPDATE proposed_rules
        SET    status       = 'approved',
               reviewer     = %s,
               review_notes = %s,
               reviewed_at  = NOW()
        WHERE  id = %s
    """, [reviewer, review_notes, proposal_id])

    conn.commit()
    rule_id = rule["rule_id"]
    print(f"\n✅ Rule {rule_id} activated.")
    print(f"   Approved by : {reviewer}")
    if review_notes:
        print(f"   Notes       : {review_notes}")
    return rule_id


def reject_proposal(
    proposal_id:  int,
    reviewer:     str,
    review_notes: str,
    conn:         psycopg.Connection
) -> None:
    conn.execute("""
        UPDATE proposed_rules
        SET    status       = 'rejected',
               reviewer     = %s,
               review_notes = %s,
               reviewed_at  = NOW()
        WHERE  id = %s
    """, [reviewer, review_notes, proposal_id])
    conn.commit()
    print(f"✗ Proposal {proposal_id} rejected by {reviewer}.")
