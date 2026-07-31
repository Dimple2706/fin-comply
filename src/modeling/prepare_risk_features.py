"""
src/modeling/prepare_risk_features.py
======================================
Part 2 of the XGBoost ML training pipeline.

Reads evaluation_results, extracts 13 features from each tenant's
result_json, computes total_penalty_exposure independently from the
clauses table (to prevent leakage), assigns a label, and writes:
  - data/training/training_features.csv   (model input - no tenant_id)
  - data/training/training_metadata.csv   (debug info - not used in training)

result_json top-level keys confirmed from orchestrator.py:
  tenant_id, run_timestamp, status, total_violations, total_warnings,
  risk_score, risk_tier, risk_contributions, agent_breakdown,
  violation_report, risk_insights, compliance_score,
  mapped_regulations, explainable_insights

violation_report entry keys confirmed from live DB inspection:
  rule_id, rule_name, dpdp_section, severity, outcome, score,
  signals_fired, affected_records_count, penalty_exposure_crore

risk_insights keys confirmed:
  risk_tier, overall_score, critical_rules, per_rule_contributions,
  total_penalty_exposure_crore
"""

import os
import sys
import csv
import json
from collections import Counter

# Make project root importable
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import psycopg
from psycopg.rows import dict_row


# ── DB connection ─────────────────────────────────────────────────────────────
DB_DSN = "dbname=compliance_db user=postgres password=mysql@1703"

def _conn():
    return psycopg.connect(DB_DSN, row_factory=dict_row)


# ── Label thresholds (penalty exposure in crore) ──────────────────────────────
def _assign_label(total_crore: float) -> int:
    """
    Recalibrated thresholds:
      0 crore           -> 0 (COMPLIANT)   No violations.
      1-300 crore       -> 1 (LOW)         Tier 3/4 rules only.
      301-750 crore     -> 2 (MEDIUM)      1 HIGH severity + minor issues.
      751-1500 crore    -> 3 (HIGH)        3+ HIGH or 2 CRITICAL violations.
      above 1500 crore  -> 4 (CRITICAL)    Multiple CRITICAL violations.
    """
    if total_crore == 0:
        return 0
    elif total_crore <= 300:
        return 1
    elif total_crore <= 750:
        return 2
    elif total_crore <= 1500:
        return 3
    else:
        return 4


LABEL_NAMES = {0: "COMPLIANT", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}

# ── Rule groupings for domain features ───────────────────────────────────────
CONSENT_RULES     = {"DPDP-001", "DPDP-002", "DPDP-004", "DPDP-007"}
RETENTION_RULES   = {"DPDP-003", "DPDP-011"}
ENCRYPTION_RULES  = {"DPDP-008"}
ACCESS_RULES      = {"DPDP-013"}
POLICY_RULES      = {"POLICY-001", "POLICY-002", "POLICY-003"}

FEATURE_COLS = [
    "n_violations", "n_warnings", "n_critical_rules_fired",
    "n_high_rules_fired", "breach_rule_fired", "minor_data_rule_fired",
    "max_rule_score", "max_prevalence_ratio", "consent_violation_count",
    "retention_violation_count", "encryption_violation_count",
    "access_violation_count", "policy_violation_count", "label"
]

META_COLS = [
    "tenant_id", "profile_name", "risk_score", "risk_tier",
    "violated_rules", "total_penalty_exposure", "label", "label_name"
]


# ── Feature extraction ────────────────────────────────────────────────────────
def extract_features(rj: dict, risk_score: float) -> dict:
    vr         = rj.get("violation_report", [])
    violations = [e for e in vr if e.get("outcome") == "VIOLATION"]
    warnings   = [e for e in vr if e.get("outcome") == "WARNING"]

    # F1: total violations — top-level key from orchestrator
    n_violations = int(rj.get("total_violations", len(violations)))

    # F2: total warnings — top-level key from orchestrator
    n_warnings = int(rj.get("total_warnings", len(warnings)))

    # F3: distinct CRITICAL rule_ids that fired as VIOLATION
    n_critical = len({e["rule_id"] for e in violations if e.get("severity") == "CRITICAL"})

    # F4: distinct HIGH rule_ids that fired as VIOLATION
    n_high = len({e["rule_id"] for e in violations if e.get("severity") == "HIGH"})

    # F5: breach rule binary
    breach_fired = int(any(e["rule_id"] == "DPDP-014" for e in violations))

    # F6: minor data rule binary
    minor_fired = int(any(e["rule_id"] == "DPDP-005" for e in violations))

    # F7: max rule_score across ALL violation_report entries (both VIOLATION and WARNING)
    all_scores = [e.get("score", 0.0) for e in vr if e.get("score") is not None]
    max_rule_score = round(max(all_scores), 4) if all_scores else 0.0

    # F8: max_prevalence_ratio
    # APPROXIMATION: Use the highest contribution_percentage from
    # risk_insights.per_rule_contributions divided by 100.
    # per_rule_contributions is confirmed present in risk_insights.
    per_rule_contribs = rj.get("risk_insights", {}).get("per_rule_contributions", [])
    if per_rule_contribs and isinstance(per_rule_contribs, list) and len(per_rule_contribs) > 0:
        max_contrib_pct = max(
            e.get("contribution_percentage", 0.0)
            for e in per_rule_contribs
            if isinstance(e, dict)
        )
        max_prevalence_ratio = round(max_contrib_pct / 100.0, 4)
    else:
        # final fallback: normalized risk score
        max_prevalence_ratio = round(risk_score / 100.0, 4)

    # F9-F13: domain violation counts
    consent_count    = sum(1 for e in violations if e["rule_id"] in CONSENT_RULES)
    retention_count  = sum(1 for e in violations if e["rule_id"] in RETENTION_RULES)
    encryption_count = sum(1 for e in violations if e["rule_id"] in ENCRYPTION_RULES)
    access_count     = sum(1 for e in violations if e["rule_id"] in ACCESS_RULES)
    policy_count     = sum(1 for e in violations if e["rule_id"] in POLICY_RULES)

    return {
        "n_violations":               n_violations,
        "n_warnings":                 n_warnings,
        "n_critical_rules_fired":     n_critical,
        "n_high_rules_fired":         n_high,
        "breach_rule_fired":          breach_fired,
        "minor_data_rule_fired":      minor_fired,
        "max_rule_score":             max_rule_score,
        "max_prevalence_ratio":       max_prevalence_ratio,
        "consent_violation_count":    consent_count,
        "retention_violation_count":  retention_count,
        "encryption_violation_count": encryption_count,
        "access_violation_count":     access_count,
        "policy_violation_count":     policy_count,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    conn = _conn()
    cur  = conn.cursor()

    # ── TASK 0: Deduplicate evaluation_results ────────────────────────────────
    cur.execute("""
        DELETE FROM evaluation_results
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM evaluation_results
            GROUP BY tenant_id
        )
    """)
    conn.commit()
    cur.execute("SELECT COUNT(*) AS cnt FROM evaluation_results")
    row_count = cur.fetchone()["cnt"]
    print(f"[TASK 0] Rows after deduplication: {row_count}")
    # Also remove TENANT-001 if present (integration-test artifact, not a GEN-* profile)
    cur.execute("DELETE FROM evaluation_results WHERE tenant_id = 'TENANT-001'")
    if cur.rowcount > 0:
        conn.commit()
        print(f"[TASK 0] Removed TENANT-001 (integration-test artifact).")
        cur.execute("SELECT COUNT(*) AS cnt FROM evaluation_results")
        row_count = cur.fetchone()["cnt"]
        print(f"[TASK 0] Rows after TENANT-001 removal: {row_count}")
    if row_count != 25:
        cur.execute("SELECT tenant_id FROM evaluation_results ORDER BY tenant_id")
        present  = {r["tenant_id"] for r in cur.fetchall()}
        expected = {f"GEN-{i:03d}" for i in range(1, 26)}
        missing  = expected - present
        extra    = present - expected
        print(f"  WARNING - expected 25 GEN-* rows.")
        if missing:
            print(f"  Missing:    {sorted(missing)}")
        if extra:
            print(f"  Unexpected: {sorted(extra)}")

    # ── Load penalty map from clauses table ───────────────────────────────────
    cur.execute("SELECT clause_id, max_penalty_crore FROM clauses")
    penalty_map = {r["clause_id"]: int(r["max_penalty_crore"]) for r in cur.fetchall()}
    print(f"[INFO] Loaded {len(penalty_map)} entries from clauses table.")
    print(f"[INFO] Clause penalty map: { {k: v for k, v in sorted(penalty_map.items())} }")

    # ── Read evaluation_results ───────────────────────────────────────────────
    cur.execute("""
        SELECT tenant_id, result_json, risk_score
        FROM evaluation_results
        ORDER BY tenant_id
    """)
    db_rows = cur.fetchall()
    conn.close()
    print(f"[INFO] Processing {len(db_rows)} tenant rows.\n")

    feature_rows  = []
    metadata_rows = []
    nan_flags     = {}

    for row in db_rows:
        tid        = row["tenant_id"]
        risk_score = float(row["risk_score"])

        # psycopg returns JSONB as a Python dict; guard against string fallback
        rj = row["result_json"]
        if isinstance(rj, str):
            rj = json.loads(rj)

        profile_name = rj.get("profile_name", tid)

        # Extract 13 features
        feats = extract_features(rj, risk_score)

        # Fill any None values with 0 and record
        for k, v in feats.items():
            if v is None:
                nan_flags.setdefault(tid, []).append(k)
                feats[k] = 0

        # Compute total_penalty_exposure independently from clauses table
        # This is the label source — NOT a feature (prevents leakage)
        vr = rj.get("violation_report", [])
        violated_rule_ids = list({e["rule_id"] for e in vr if e.get("outcome") == "VIOLATION"})
        total_exposure = sum(penalty_map.get(rid, 0) for rid in violated_rule_ids)
        label = _assign_label(total_exposure)

        risk_tier = rj.get("risk_tier", "UNKNOWN")

        feature_rows.append({**feats, "label": label})
        metadata_rows.append({
            "tenant_id":              tid,
            "profile_name":           profile_name,
            "risk_score":             risk_score,
            "risk_tier":              risk_tier,
            "violated_rules":         ",".join(sorted(violated_rule_ids)),
            "total_penalty_exposure": total_exposure,
            "label":                  label,
            "label_name":             LABEL_NAMES[label],
        })

    # ── Write CSVs ────────────────────────────────────────────────────────────
    out_dir = os.path.join(ROOT, "data", "training")
    os.makedirs(out_dir, exist_ok=True)
    features_path = os.path.join(out_dir, "training_features.csv")
    metadata_path = os.path.join(out_dir, "training_metadata.csv")

    with open(features_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_COLS)
        writer.writeheader()
        writer.writerows(feature_rows)

    with open(metadata_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=META_COLS)
        writer.writeheader()
        writer.writerows(metadata_rows)

    print(f"[OK] training_features.csv  -> {features_path}")
    print(f"[OK] training_metadata.csv  -> {metadata_path}")

    # ── TASK 2: Verification ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  VERIFICATION REPORT")
    print("=" * 70)

    print("\n--- training_features.csv ---")
    with open(features_path) as f:
        print(f.read())

    print("\n--- training_metadata.csv ---")
    with open(metadata_path) as f:
        print(f.read())

    # 1. Label distribution
    label_dist = Counter(r["label"] for r in metadata_rows)
    print("\n--- Label Distribution ---")
    for lbl in sorted(label_dist):
        print(f"  Label {lbl} ({LABEL_NAMES[lbl]:<10}): {label_dist[lbl]} tenants")

    # 2. Tier disagreements
    tier_to_label = {"COMPLIANT": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    print("\n--- Tier vs Penalty Label Disagreements ---")
    any_disagree = False
    for mr in metadata_rows:
        det_label = tier_to_label.get(mr["risk_tier"], -1)
        pen_label = mr["label"]
        if det_label != pen_label:
            any_disagree = True
            print(
                f"  {mr['tenant_id']:<12} | det={mr['risk_tier']:<8} "
                f"(lbl={det_label}) | pen_label={pen_label} ({LABEL_NAMES[pen_label]}) "
                f"| exposure={mr['total_penalty_exposure']} Cr"
            )
    if not any_disagree:
        print("  None.")

    # 3. Approximations used
    print("\n--- Feature Approximations ---")
    print("  Feature 8 (max_prevalence_ratio): approximated as")
    print("    max(risk_insights.per_rule_contributions[].contribution_percentage) / 100")
    print("  This is the rule contribution that most dominates the risk profile.")
    print("  Fallback to risk_score/100 only if per_rule_contributions is empty.")

    # 4. NaN report
    print("\n--- NaN/None Values ---")
    if nan_flags:
        for tid, fields in nan_flags.items():
            print(f"  {tid}: {fields} -> filled with 0")
    else:
        print("  None - all 13 features fully populated for all tenants.")

    # 5. Side-by-side GEN-010 vs GEN-005
    feature_by_tid = {
        metadata_rows[i]["tenant_id"]: feature_rows[i]
        for i in range(len(metadata_rows))
    }
    meta_by_tid = {mr["tenant_id"]: mr for mr in metadata_rows}

    f10 = feature_by_tid.get("GEN-010", {})
    f05 = feature_by_tid.get("GEN-005", {})
    m10 = meta_by_tid.get("GEN-010", {})
    m05 = meta_by_tid.get("GEN-005", {})

    print("\n--- Feature Vectors: GEN-010 (multi_failure_critical) vs GEN-005 (well_governed_enterprise) ---")
    print(f"  {'Feature':<34} {'GEN-010':>12} {'GEN-005':>12}")
    print(f"  {'-' * 62}")
    for col in [c for c in FEATURE_COLS if c != "label"]:
        print(f"  {col:<34} {str(f10.get(col, 'N/A')):>12} {str(f05.get(col, 'N/A')):>12}")
    print(f"  {'label':<34} {str(m10.get('label', 'N/A')):>12} {str(m05.get('label', 'N/A')):>12}")
    print(f"  {'label_name':<34} {m10.get('label_name', 'N/A'):>12} {m05.get('label_name', 'N/A'):>12}")
    print(f"  {'total_penalty_exposure (Cr)':<34} {str(m10.get('total_penalty_exposure', 'N/A')):>12} {str(m05.get('total_penalty_exposure', 'N/A')):>12}")

    print("\n[DONE]")


if __name__ == "__main__":
    main()
