"""
migrate_policy_rules.py
=======================
Reads policy_rules.json and inserts policy rules + matching clauses into
compliance_db (clauses table first, then rules table).

Follows the exact same structure as migrate_rules_to_db.py.

Usage:
    python db/migrate_policy_rules.py
    python db/migrate_policy_rules.py --dry-run   # prints what would be inserted, no DB write

Requirements:
    pip install psycopg[binary]
"""

import json
import argparse
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE        = Path(__file__).resolve().parent.parent
RULES_JSON  = BASE / "data" / "dpdp_kb" / "policy_rules.json"

# ── DB Config (matches db_connection.py pattern) ──────────────────────────────
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "compliance_db")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
# ──────────────────────────────────────────────────────────────────────────────


def get_connection() -> psycopg.Connection:
    """Connect using psycopg v3, matching the db_connection.py pattern."""
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        row_factory=dict_row,
        autocommit=False,
    )


def load_json(path: Path) -> list[dict]:
    """Load JSON — handles both a single object {} and an array [{}]."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def validate_signals(rule: dict) -> None:
    """
    Checks evidence_signals weights sum to ~1.0.
    Raises ValueError if not — catches authoring errors before they hit the DB.
    """
    signals = rule.get("evidence_signals", [])
    total = sum(s["weight"] for s in signals)
    if not (0.98 <= total <= 1.02):
        raise ValueError(
            f"Rule {rule['rule_id']}: evidence_signal weights sum to {total:.3f}, "
            f"expected 1.0 (±0.02). Fix in policy_rules.json before migrating."
        )


def validate_thresholds(rule: dict) -> None:
    """risk_threshold must be below violation_threshold — mirrors the DB CHECK constraint."""
    if rule["risk_threshold"] >= rule["violation_threshold"]:
        raise ValueError(
            f"Rule {rule['rule_id']}: risk_threshold ({rule['risk_threshold']}) "
            f"must be less than violation_threshold ({rule['violation_threshold']})."
        )


# ── Clause definitions for each policy rule ───────────────────────────────────
POLICY_CLAUSES = {
    "POLICY-001": {
        "clause_id":                 "POLICY-001",
        "legal_title":               "Internal Retention Policy Control",
        "dpdp_section":              ["Internal control aligned with Section 8(7)"],
        "legal_text":                (
            "This internal control checks that a documented retention policy is active. "
            "The DPDP framework ties erasure and retention to purpose and applicable law; "
            "this control does not create a universal statutory day limit."
        ),
        "plain_english_obligation":  (
            "Maintain an active retention policy and assess actual retention periods against "
            "the processing purpose and any applicable legal requirement."
        ),
        "severity_weight":           0.55,
        "evidence_required":         ["active retention policy"],
        "signal_mapping":            {"S1": "is_active equals false"},
        "penalty_tier":              "INTERNAL_CONTROL",
        "max_penalty_crore":         0,
        "keywords":                  ["retention", "data erasure", "storage limitation", "section 8(7)"],
    },
    "POLICY-002": {
        "clause_id":                 "POLICY-002",
        "legal_title":               "Internal Encryption Policy Control",
        "dpdp_section":              ["Internal control aligned with Section 8(5)"],
        "legal_text":                (
            "This internal control checks whether an active encryption policy names a modern "
            "protection algorithm. It is supporting security-readiness evidence and is not, by "
            "itself, a determination of statutory liability."
        ),
        "plain_english_obligation":  (
            "You must maintain an active encryption policy that mandates a strong, "
            "modern encryption standard. Weak or deprecated algorithms (none, MD5, SHA-1, DES, RC4) "
            "are flagged as internal security-control gaps requiring remediation."
        ),
        "severity_weight":           0.80,
        "evidence_required":         ["active encryption policy", "strong encryption standard"],
        "signal_mapping":            {
            "S1": "is_active equals false",
            "S2": "policy_value_text in [none, md5, sha1, des, rc4]"
        },
        "penalty_tier":              "INTERNAL_CONTROL",
        "max_penalty_crore":         0,
        "keywords":                  ["encryption", "security safeguards", "data protection", "section 8(5)", "weak algorithm"],
    },
    "POLICY-003": {
        "clause_id":                 "POLICY-003",
        "legal_title":               "Internal Consent Mechanism Control",
        "dpdp_section":              ["Internal control aligned with Section 6"],
        "legal_text":                (
            "This internal control checks whether the organisation's consent policy requires "
            "a clear affirmative action. It is supporting readiness evidence and is reported "
            "separately from statutory findings."
        ),
        "plain_english_obligation":  (
            "You must have an active consent mechanism policy that mandates only "
            "compliant, explicit consent channels. Policies permitting implicit, pre-ticked, "
            "inferred or bundled collection are flagged for review."
        ),
        "severity_weight":           0.75,
        "evidence_required":         ["active consent policy", "compliant consent channel"],
        "signal_mapping":            {
            "S1": "is_active equals false",
            "S2": "policy_value_text in [implicit, pre_ticked, inferred, bundled]"
        },
        "penalty_tier":              "INTERNAL_CONTROL",
        "max_penalty_crore":         0,
        "keywords":                  ["consent", "consent mechanism", "bundled consent", "implicit consent", "section 6"],
    },
}
# ──────────────────────────────────────────────────────────────────────────────


def insert_clause(cur, clause: dict, dry_run: bool) -> None:
    sql = """
        INSERT INTO clauses (
            clause_id, legal_title, dpdp_section, legal_text,
            plain_english_obligation, severity_weight,
            evidence_required, signal_mapping,
            penalty_tier, max_penalty_crore, keywords
        ) VALUES (
            %(clause_id)s, %(legal_title)s, %(dpdp_section)s, %(legal_text)s,
            %(plain_english_obligation)s, %(severity_weight)s,
            %(evidence_required)s, %(signal_mapping)s,
            %(penalty_tier)s, %(max_penalty_crore)s, %(keywords)s
        )
        ON CONFLICT (clause_id) DO UPDATE SET
            legal_title = EXCLUDED.legal_title,
            dpdp_section = EXCLUDED.dpdp_section,
            legal_text = EXCLUDED.legal_text,
            plain_english_obligation = EXCLUDED.plain_english_obligation,
            severity_weight = EXCLUDED.severity_weight,
            evidence_required = EXCLUDED.evidence_required,
            signal_mapping = EXCLUDED.signal_mapping,
            penalty_tier = EXCLUDED.penalty_tier,
            max_penalty_crore = EXCLUDED.max_penalty_crore,
            keywords = EXCLUDED.keywords;
    """
    params = {
        "clause_id":               clause["clause_id"],
        "legal_title":             clause["legal_title"],
        "dpdp_section":            Jsonb(clause["dpdp_section"]),
        "legal_text":              clause["legal_text"],
        "plain_english_obligation": clause["plain_english_obligation"],
        "severity_weight":         clause["severity_weight"],
        "evidence_required":       Jsonb(clause["evidence_required"]),
        "signal_mapping":          Jsonb(clause["signal_mapping"]),
        "penalty_tier":            clause["penalty_tier"],
        "max_penalty_crore":       clause["max_penalty_crore"],
        "keywords":                Jsonb(clause["keywords"]),
    }
    if dry_run:
        print(f"  [DRY RUN] Would insert clause: {clause['clause_id']} - {clause['legal_title']}")
    else:
        cur.execute(sql, params)
        print(f"  OK Clause inserted (or already exists): {clause['clause_id']}")


def insert_rule(cur, rule: dict, dry_run: bool) -> None:
    sql = """
        INSERT INTO rules (
            rule_id, clause_id, rule_name, dpdp_section,
            description, severity, risk_weight, check_type,
            assigned_agent, primary_table, join_tables, join_key,
            evidence_signals, violation_threshold, risk_threshold,
            recurrence_bonus, enabled, version, effective_date, approved_by
        ) VALUES (
            %(rule_id)s, %(clause_id)s, %(rule_name)s, %(dpdp_section)s,
            %(description)s, %(severity)s, %(risk_weight)s, %(check_type)s,
            %(assigned_agent)s, %(primary_table)s, %(join_tables)s, %(join_key)s,
            %(evidence_signals)s, %(violation_threshold)s, %(risk_threshold)s,
            %(recurrence_bonus)s, %(enabled)s, %(version)s, CURRENT_DATE, %(approved_by)s
        )
        ON CONFLICT (rule_id) DO UPDATE SET
            rule_name = EXCLUDED.rule_name,
            dpdp_section = EXCLUDED.dpdp_section,
            description = EXCLUDED.description,
            severity = EXCLUDED.severity,
            risk_weight = EXCLUDED.risk_weight,
            check_type = EXCLUDED.check_type,
            assigned_agent = EXCLUDED.assigned_agent,
            primary_table = EXCLUDED.primary_table,
            join_tables = EXCLUDED.join_tables,
            join_key = EXCLUDED.join_key,
            evidence_signals = EXCLUDED.evidence_signals,
            violation_threshold = EXCLUDED.violation_threshold,
            risk_threshold = EXCLUDED.risk_threshold,
            recurrence_bonus = EXCLUDED.recurrence_bonus,
            enabled = EXCLUDED.enabled,
            version = rules.version + 1,
            updated_at = NOW();
    """
    params = {
        "rule_id":             rule["rule_id"],
        "clause_id":           rule["clause_id"],
        "rule_name":           rule["rule_name"],
        "dpdp_section":        rule["dpdp_section"],
        "description":         rule["description"],
        "severity":            rule["severity"],
        "risk_weight":         rule["risk_weight"],
        "check_type":          rule.get("check_type", "weighted_evidence"),
        "assigned_agent":      rule["assigned_agent"],
        "primary_table":       rule["primary_table"],
        "join_tables":         Jsonb(rule.get("join_tables", [])),
        "join_key":            rule.get("join_key"),   # None → NULL
        "evidence_signals":    Jsonb(rule["evidence_signals"]),
        "violation_threshold": rule["violation_threshold"],
        "risk_threshold":      rule["risk_threshold"],
        "recurrence_bonus":    rule.get("recurrence_bonus", 0.0),
        "enabled":             rule.get("enabled", True),
        "version":             1,
        "approved_by":         "migration_script",
    }
    if dry_run:
        print(f"  [DRY RUN] Would insert rule: {rule['rule_id']} - {rule['rule_name']}")
    else:
        cur.execute(sql, params)
        print(f"  OK Rule inserted (or already exists): {rule['rule_id']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview inserts without writing to DB")
    args = parser.parse_args()

    # ── Load rules file ───────────────────────────────────────────────────────
    print(f"\nLoading {RULES_JSON}...")
    rules = load_json(RULES_JSON)
    print(f"  Found {len(rules)} rule(s)")

    # ── Validate before touching the DB ──────────────────────────────────────
    print("\nValidating rules...")
    errors = []
    for rule in rules:
        try:
            validate_signals(rule)
            validate_thresholds(rule)
            print(f"  OK {rule['rule_id']} - signals and thresholds OK")
        except ValueError as e:
            errors.append(str(e))
            print(f"  FAIL {e}")

    if errors:
        print(f"\n{len(errors)} validation error(s) found. Fix before migrating.\n")
        sys.exit(1)

    if args.dry_run:
        print("\n-- DRY RUN - no changes will be written to the database --")

    # ── Connect and run ───────────────────────────────────────────────────────
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Clauses first — rules FK references them
        print("\nInserting clauses...")
        for rule in rules:
            clause = POLICY_CLAUSES[rule["rule_id"]]
            insert_clause(cur, clause, args.dry_run)

        # Rules second
        print("\nInserting rules...")
        for rule in rules:
            insert_rule(cur, rule, args.dry_run)

        if not args.dry_run:
            conn.commit()
            print(f"\nDONE Migration complete — {len(rules)} clause(s) and {len(rules)} rule(s) written.")
        else:
            print(f"\nDONE Dry run complete — {len(rules)} rule(s) previewed.")

        cur.close()
        conn.close()

    except psycopg.Error as e:
        print(f"\nERROR DB error: {e}")
        if conn and not args.dry_run:
            conn.rollback()
        sys.exit(1)


if __name__ == "__main__":
    main()
