"""
review_proposed_rule.py
=======================
CLI tool for human review of LLM-proposed rules.
P4 will later wire this same flow into the Streamlit UI —
the underlying activate_rule() / reject_proposal() functions are identical.

Usage:
    # Propose a new rule from regulatory text
    python review_proposed_rule.py --propose "path/to/amendment.txt"

    # Review a pending proposal
    python review_proposed_rule.py --review 3

    # List all pending proposals
    python review_proposed_rule.py --list
"""

import argparse
import json
import psycopg
from psycopg.rows import dict_row

from agent_layer.rule_authoring_agent_f import propose_rule, save_proposal, activate_rule, reject_proposal

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "dpdp_db",
    "user":     "postgres",
    "password": "your_password",
}


def get_conn():
    return psycopg.connect(**DB_CONFIG, row_factory=dict_row)


def cmd_propose(text_path: str):
    """Read regulatory text from file, propose a rule, save to staging."""
    with open(text_path) as f:
        source_text = f.read().strip()

    print(f"\nProposing rule for text ({len(source_text)} chars)...")
    conn = get_conn()

    proposed = propose_rule(source_text, conn)

    print("\n── Proposed Rule ──")
    print(json.dumps(proposed, indent=2))

    confirm = input("\nSave this proposal for review? [y/N]: ").strip().lower()
    if confirm == "y":
        proposal_id = save_proposal(proposed, source_text, conn)
        print(f"\nProposal #{proposal_id} saved. Run --review {proposal_id} to approve or reject.")
    else:
        print("Discarded — nothing saved.")

    conn.close()


def cmd_list():
    """List all pending proposals."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT id,
               proposed_rule->>'rule_id'   AS rule_id,
               proposed_rule->>'rule_name' AS rule_name,
               proposed_rule->>'severity'  AS severity,
               (field_check->>'all_resolved')::boolean AS fields_ok,
               status,
               created_at
        FROM   proposed_rules
        WHERE  status = 'pending'
        ORDER  BY created_at DESC
    """).fetchall()

    if not rows:
        print("\nNo pending proposals.")
        conn.close()
        return

    print(f"\n{'ID':<5} {'Rule ID':<12} {'Name':<40} {'Sev':<8} {'Fields OK':<10} {'Created'}")
    print("-" * 90)
    for r in rows:
        ok = "✓" if r["fields_ok"] else "✗ MISSING"
        print(f"{r['id']:<5} {r['rule_id'] or '?':<12} {(r['rule_name'] or '?')[:38]:<40} "
              f"{r['severity'] or '?':<8} {ok:<10} {str(r['created_at'])[:16]}")

    conn.close()


def cmd_review(proposal_id: int):
    """Interactive review of a single proposal."""
    conn = get_conn()

    row = conn.execute("""
        SELECT * FROM proposed_rules WHERE id = %s
    """, [proposal_id]).fetchone()

    if not row:
        print(f"No proposal found with id={proposal_id}")
        conn.close()
        return

    if row["status"] != "pending":
        print(f"Proposal {proposal_id} is already '{row['status']}'.")
        conn.close()
        return

    rule        = row["proposed_rule"]
    field_check = row["field_check"]

    print("\n" + "═" * 60)
    print(f"PROPOSAL #{proposal_id} — REVIEW")
    print("═" * 60)

    print("\n── Source Text (first 400 chars) ──")
    print(row["source_text"][:400] + ("..." if len(row["source_text"]) > 400 else ""))

    print("\n── Proposed Rule ──")
    print(json.dumps(rule, indent=2))

    print("\n── Field Registry Check ──")
    print(f"  All resolved : {field_check.get('all_resolved')}")
    if field_check.get("resolved"):
        print(f"  Resolved     : {[r['field'] for r in field_check['resolved']]}")
    if field_check.get("in_jsonb"):
        print(f"  In JSONB     : {[r['field'] for r in field_check['in_jsonb']]}")
    if field_check.get("missing"):
        print(f"  ⚠ MISSING    : {field_check['missing']}")
        print("  → Cannot approve until all missing fields are resolved.")
        print("    Fix: add them to additional_attributes in generator_config.json")
        print("    and re-run generate_data.py, then run field_registry again.")

    print("\n" + "─" * 60)

    if not field_check.get("all_resolved"):
        print("⚠  Cannot approve — fields missing. Options: [R]eject or [Q]uit")
        action = input("Action [R/Q]: ").strip().upper()
    else:
        action = input("Action [A]pprove / [R]eject / [Q]uit: ").strip().upper()

    reviewer = input("Your name: ").strip() or "anonymous"

    if action == "A":
        notes = input("Approval notes (optional): ").strip() or None
        try:
            rule_id = activate_rule(proposal_id, reviewer, conn, notes)
            from src.governance.audit_logger import log_event, RULE_APPROVED
            log_event(
              RULE_APPROVED,
              details={'rule_id': rule_id, 'approved_by': reviewer}
            )
        except ValueError as e:
            print(f"\n✗ Activation failed: {e}")

    elif action == "R":
        notes = input("Rejection reason (required): ").strip()
        if not notes:
            print("Rejection reason required.")
        else:
            reject_proposal(proposal_id, reviewer, notes, conn)
            from src.governance.audit_logger import log_event, RULE_REJECTED
            log_event(
              RULE_REJECTED,
              details={'rule_id': rule.get('rule_id', 'unknown'), 'rejected_by': reviewer}
            )

    else:
        print("No action taken.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DPDP Rule Authoring CLI")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--propose", metavar="FILE",
                       help="Path to text file with regulatory text to convert into a rule")
    group.add_argument("--review",  metavar="ID", type=int,
                       help="Review a pending proposal by its ID")
    group.add_argument("--list",    action="store_true",
                       help="List all pending proposals")

    args = parser.parse_args()

    if args.propose:
        cmd_propose(args.propose)
    elif args.review:
        cmd_review(args.review)
    elif args.list:
        cmd_list()
