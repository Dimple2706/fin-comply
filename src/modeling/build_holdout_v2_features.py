"""
src/modeling/build_holdout_v2_features.py
==========================================
Assembles the OOD holdout v2 features/metadata CSVs from the covering-array
generated tenants (see generate_ood_testset.py) plus the 25 kept personas.

Unlike prepare_risk_features.py (which reads *everything* currently in
evaluation_results), this script filters to an EXPLICIT tenant_id list --
evaluation_results now also holds the training family pool, the old v1
holdout, thousands of earlier Phase 4 tenants, and leftover verification
tenants from designing this generator, all mixed together in one table.

Reuses the exact feature-extraction/labeling logic from prepare_risk_features.py
so the v2 holdout's features are computed identically to training's.

Writes: data/training/holdout_features_v2.csv
        data/training/holdout_metadata_v2.csv
(the original holdout_*_unique.csv files are left untouched for comparison).
"""
import os
import sys
import csv
import json
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import psycopg
from psycopg.rows import dict_row
import dotenv
dotenv.load_dotenv()

from src.modeling.prepare_risk_features import (
    extract_features, _assign_label, LABEL_NAMES, TIER_TO_LABEL,
    FEATURE_COLS, META_COLS,
)

PERSONAS = [f"GEN-{i:03d}" for i in range(1, 26)]
FULL_RUN = [f"GEN-{i}" for i in range(21000, 21250)]
TOPUP_LOW_MEDIUM = [f"GEN-{i}" for i in range(22000, 22150)]
COMPLIANT_TOPUP = [f"GEN-{i}" for i in range(22150, 22195)]

TENANT_IDS = PERSONAS + FULL_RUN + TOPUP_LOW_MEDIUM + COMPLIANT_TOPUP


def _conn():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "tenant_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        row_factory=dict_row,
    )


def main():
    print(f"[INFO] Target tenant set: {len(TENANT_IDS)} "
          f"({len(PERSONAS)} personas + {len(FULL_RUN)} full-run + "
          f"{len(TOPUP_LOW_MEDIUM)} low/medium topup + {len(COMPLIANT_TOPUP)} compliant topup)")

    conn = _conn()
    cur = conn.cursor()

    cur.execute("SELECT clause_id, max_penalty_crore FROM clauses")
    penalty_map = {r["clause_id"]: int(r["max_penalty_crore"]) for r in cur.fetchall()}
    print(f"[INFO] Loaded {len(penalty_map)} entries from clauses table.")

    cur.execute(
        """
        SELECT DISTINCT ON (tenant_id) tenant_id, result_json, risk_score
        FROM evaluation_results
        WHERE tenant_id = ANY(%s)
        ORDER BY tenant_id, id DESC
        """,
        (TENANT_IDS,),
    )
    db_rows = cur.fetchall()
    conn.close()

    present = {r["tenant_id"] for r in db_rows}
    missing = set(TENANT_IDS) - present
    print(f"[INFO] Found {len(db_rows)}/{len(TENANT_IDS)} tenant rows in evaluation_results.")
    if missing:
        print(f"[WARNING] Missing {len(missing)} tenant_ids: {sorted(missing)[:20]}"
              f"{' ...' if len(missing) > 20 else ''}")

    feature_rows = []
    metadata_rows = []
    nan_flags = {}

    for row in db_rows:
        tid = row["tenant_id"]
        risk_score = float(row["risk_score"])
        rj = row["result_json"]
        if isinstance(rj, str):
            rj = json.loads(rj)

        profile_name = rj.get("profile_name", tid)
        feats = extract_features(rj, risk_score)

        for k, v in feats.items():
            if v is None:
                nan_flags.setdefault(tid, []).append(k)
                feats[k] = 0

        vr = rj.get("violation_report", [])
        violated_rule_ids = list({e["rule_id"] for e in vr if e.get("outcome") == "VIOLATION"})
        total_exposure = sum(penalty_map.get(rid, 0) for rid in violated_rule_ids)
        risk_tier = rj.get("risk_tier", "UNKNOWN")

        if risk_tier in TIER_TO_LABEL:
            label = TIER_TO_LABEL[risk_tier]
        else:
            label = _assign_label(total_exposure)

        feature_rows.append({**feats, "total_penalty_exposure": total_exposure, "label": label})
        metadata_rows.append({
            "tenant_id": tid,
            "profile_name": profile_name,
            "risk_score": risk_score,
            "risk_tier": risk_tier,
            "violated_rules": ",".join(sorted(violated_rule_ids)),
            "total_penalty_exposure": total_exposure,
            "label": label,
            "label_name": LABEL_NAMES[label],
        })

    out_dir = os.path.join(ROOT, "data", "training")
    features_path = os.path.join(out_dir, "holdout_features_v2.csv")
    metadata_path = os.path.join(out_dir, "holdout_metadata_v2.csv")

    with open(features_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_COLS)
        writer.writeheader()
        writer.writerows(feature_rows)

    with open(metadata_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=META_COLS)
        writer.writeheader()
        writer.writerows(metadata_rows)

    print(f"[OK] holdout_features_v2.csv -> {features_path}")
    print(f"[OK] holdout_metadata_v2.csv -> {metadata_path}")

    label_dist = Counter(r["label"] for r in metadata_rows)
    print("\n--- Label Distribution ---")
    for lbl in sorted(label_dist):
        print(f"  Label {lbl} ({LABEL_NAMES[lbl]:<10}): {label_dist[lbl]} tenants")

    if nan_flags:
        print("\n--- NaN/None Values ---")
        for tid, fields in nan_flags.items():
            print(f"  {tid}: {fields} -> filled with 0")

    print("\n[DONE]")


if __name__ == "__main__":
    main()
