"""
field_registry.py
=================
P1 deliverable — handed to P2 for use in rule_authoring_agent.py

Builds a live registry of every valid field name across all 10 core
tables (base columns + JSONB keys in additional_attributes).

Two public functions:
    check_rule_fields()   — validates a proposed rule before DB insert
    get_flat_field_list() — returns field list per table for LLM prompt
"""

import psycopg
from typing import Dict, List

CORE_TABLES = [
    "access_logs",
    "consent_records",
    "customer_master",
    "data_lifecycle",
    "dsar_requests",
    "governance_config",
    "policies",
    "security_events",
    "system_inventory",
    "transaction_events",
]

# Columns that are infrastructure/PKs — excluded from LLM prompt
# (no rule ever needs to filter by these)
_EXCLUDE_FROM_PROMPT = {
    "tenant_id", "customer_hash", "access_hash", "consent_hash",
    "lifecycle_hash", "dsar_hash", "policy_hash", "security_hash",
    "system_hash", "event_hash", "employee_hash",
    "guardian_consent_hash", "third_party_hash",
}


def _build_registry(conn: psycopg.Connection) -> Dict[str, List[str]]:
    """
    Internal — builds the full registry dict.
    {
      "access_logs":                      ["access_hash", "employee_role", ...],
      "access_logs.additional_attributes":["pii_fields_justified"],
      ...
    }
    """
    registry = {}

    # ── 1. Base columns from information_schema ───────────────────────────
    placeholders = ",".join(["%s"] * len(CORE_TABLES))
    rows = conn.execute(f"""
        SELECT table_name, column_name
        FROM   information_schema.columns
        WHERE  table_schema = 'public'
          AND  table_name   IN ({placeholders})
        ORDER  BY table_name, ordinal_position
    """, CORE_TABLES).fetchall()

    for row in rows:
        registry.setdefault(row["table_name"], []).append(row["column_name"])

    # ── 2. JSONB keys from additional_attributes (sampled) ────────────────
    for table in CORE_TABLES:
        jsonb_key = f"{table}.additional_attributes"
        try:
            sample = conn.execute(f"""
                SELECT DISTINCT jsonb_object_keys(additional_attributes) AS k
                FROM   {table}
                WHERE  additional_attributes IS NOT NULL
                  AND  additional_attributes != '{{}}'::jsonb
                LIMIT  100
            """).fetchall()
            registry[jsonb_key] = [r["k"] for r in sample]
        except Exception:
            registry[jsonb_key] = []

    return registry


def check_rule_fields(rule: dict, conn: psycopg.Connection) -> dict:
    """
    Validates that every `field` in a rule's evidence_signals resolves
    to a real column or JSONB key in the tables the rule queries.

    Args:
        rule — proposed rule dict (from LLM output or manual JSON)
        conn — active psycopg connection

    Returns dict with keys:
        all_resolved  bool   — True only if missing is empty
        resolved      list   — fields found as base columns
        in_jsonb      list   — fields found inside additional_attributes
        missing       list   — fields not found anywhere (block activation)

    Example return:
        {
            "all_resolved": False,
            "resolved":  [{"field": "consent_status", "table": "consent_records"}],
            "in_jsonb":  [{"field": "pii_fields_justified",
                           "table": "access_logs.additional_attributes"}],
            "missing":   ["nonexistent_field"],
        }
    """
    registry      = _build_registry(conn)
    primary_table = rule.get("primary_table", "")
    join_tables   = rule.get("join_tables") or []
    all_tables    = [primary_table] + [t for t in join_tables if t]
    signals       = rule.get("evidence_signals", [])

    resolved = []
    in_jsonb = []
    missing  = []

    for signal in signals:
        field = signal.get("field", "").strip()
        if not field:
            continue

        found = False

        # Check base columns first
        for table in all_tables:
            if field in registry.get(table, []):
                resolved.append({"field": field, "table": table})
                found = True
                break

        if found:
            continue

        # Check JSONB keys
        for table in all_tables:
            jkey = f"{table}.additional_attributes"
            if field in registry.get(jkey, []):
                in_jsonb.append({"field": field, "table": jkey})
                found = True
                break

        if not found:
            missing.append(field)

    return {
        "all_resolved": len(missing) == 0,
        "resolved":     resolved,
        "in_jsonb":     in_jsonb,
        "missing":      missing,
    }


def get_flat_field_list(conn: psycopg.Connection) -> Dict[str, List[str]]:
    """
    Returns usable fields per table for embedding in LLM prompts.
    Excludes PK/hash/infrastructure columns the LLM should never reference.

    Format:
        {
            "consent_records": [
                "consent_status", "expiry_date", "consented_purpose",
                "notice_provided", "is_bundled", "consent_channel",
                "additional_attributes.pii_fields_justified"
            ],
            ...
        }
    """
    registry = _build_registry(conn)
    flat     = {}

    for table in CORE_TABLES:
        base_cols  = [c for c in registry.get(table, [])
                      if c not in _EXCLUDE_FROM_PROMPT]
        jsonb_keys = [f"additional_attributes.{k}"
                      for k in registry.get(f"{table}.additional_attributes", [])]
        flat[table] = base_cols + jsonb_keys

    return flat
