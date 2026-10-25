
from collections import defaultdict
from typing import Any


def build_task_evidence(
    raw_violations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Aggregate confirmed violation evidence by rule and signal.

    This function does not evaluate compliance rules.
    It only processes outcomes already classified as VIOLATION.
    """

    grouped = defaultdict(set)

    for violation in raw_violations:
        if violation.get("outcome") != "VIOLATION":
            continue

        rule_id = violation.get("rule_id")
        record_id = violation.get("record_id")
        signals = violation.get("signals_fired") or []

        if not rule_id or not isinstance(signals, list):
            continue

        for signal_id in signals:
            if not signal_id:
                continue

            # Distinct affected records for each rule/signal.
            # A missing record identifier must not become a
            # fabricated affected-record count.
            if record_id and str(record_id) != "unknown":
                grouped[(rule_id, signal_id)].add(str(record_id))
            else:
                grouped.setdefault((rule_id, signal_id), set())

    return [
        {
            "rule_id": rule_id,
            "signal_id": signal_id,
            "affected_records_count": len(record_ids),
        }
        for (rule_id, signal_id), record_ids in sorted(grouped.items())
    ]


def save_task_evidence(
    conn,
    tenant_id: str,
    audit_run_id: str,
    raw_violations: list[dict[str, Any]],
) -> int:
    """
    Store task evidence for one tenant and audit run.

    Only active task templates are saved.
    Contextual/inactive signals are excluded by the SQL join.

    Must be called within the transaction that saves the audit run.
    The caller owns commit/rollback.
    """

    if not tenant_id or not audit_run_id:
        raise ValueError("tenant_id and audit_run_id are required")

    evidence = build_task_evidence(raw_violations)

    with conn.cursor() as cur:
        # Verify audit run belongs to the requested tenant.
        cur.execute(
            """
            SELECT 1
            FROM audit_runs
            WHERE audit_run_id = %s
              AND tenant_id = %s
            """,
            (audit_run_id, tenant_id),
        )

        if cur.fetchone() is None:
            raise ValueError(
                "Audit run does not exist for the specified tenant"
            )

        # Clear previous evidence for this specific run so that
        # reprocessing is idempotent.
        cur.execute(
            """
            DELETE FROM task_evidence
            WHERE tenant_id = %s
              AND audit_run_id = %s
            """,
            (tenant_id, audit_run_id),
        )

        inserted = 0

        for item in evidence:
            cur.execute(
                """
                INSERT INTO task_evidence (
                    tenant_id,
                    audit_run_id,
                    rule_id,
                    signal_id,
                    affected_records_count
                )
                SELECT
                    %s, %s, t.rule_id, t.signal_id, %s
                FROM task_templates AS t
                WHERE t.rule_id = %s
                  AND t.signal_id = %s
                  AND t.is_active = TRUE
                ON CONFLICT (
                    tenant_id,
                    audit_run_id,
                    rule_id,
                    signal_id
                )
                DO UPDATE SET
                    affected_records_count =
                        EXCLUDED.affected_records_count
                RETURNING id
                """,
                (
                    tenant_id,
                    audit_run_id,
                    item["affected_records_count"],
                    item["rule_id"],
                    item["signal_id"],
                ),
            )

            if cur.fetchone() is not None:
                inserted += 1

    return inserted


def get_task_assignments(
    conn,
    tenant_id: str,
    audit_run_id: str,
) -> list[dict[str, Any]]:
    """
    Retrieve assignments for an exact tenant and audit run.
    """

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                t.rule_id,
                t.signal_id,
                t.task_title,
                t.task_description,
                t.responsible_team,
                t.priority,
                t.remediation_steps,
                e.affected_records_count,
                e.audit_run_id,
                e.tenant_id
            FROM task_evidence AS e
            JOIN task_templates AS t
              ON t.rule_id = e.rule_id
             AND t.signal_id = e.signal_id
            JOIN audit_runs AS ar
              ON ar.audit_run_id = e.audit_run_id
             AND ar.tenant_id = e.tenant_id
            WHERE e.tenant_id = %s
              AND e.audit_run_id = %s
              AND t.is_active = TRUE
            ORDER BY
                CASE t.priority
                    WHEN 'Critical' THEN 1
                    WHEN 'High' THEN 2
                    WHEN 'Medium' THEN 3
                    WHEN 'Low' THEN 4
                    ELSE 5
                END,
                t.rule_id,
                t.signal_id
            """,
            (tenant_id, audit_run_id),
        )

        return cur.fetchall()
