"""
src/modeling/build_train_v2_features.py
=========================================
Assembles the EXPANDED training corpus (Phase 4 diversification tenants,
generated across generate_pilot_batch.py / generate_pilot_batch_v2.py /
generate_full_batch.py / generate_topup_batch.py) into
train_features_v2.csv / train_metadata_v2.csv.

The model has been training on only the original 225-tenant family pool
(GEN-026..250) since Phase 4 diversification generated ~1650 more tenants
into raw CSVs + evaluation_results, but nobody ever assembled those into a
features file -- train_features_family.csv was simply never refreshed.

Tenant set (from the phase4_*.json generation reports -- excludes the small
sanity/dev-probe batches phase4_topup_sanity*.json and phase4_sanity_v2, which
are throwaway verification runs, not real training volume):
  - GEN-026..250   (225) original family pool
  - GEN-401..425   (25)  phase4 pilot batch
  - GEN-484..485   (2)   phase4 pilot v2
  - GEN-486..1485  (1000) phase4 full batch
  - GEN-1486..1835 (350) phase4 topup batch (COMPLIANT/CRITICAL top-up)
  Total: 1602 tenants

Excludes GEN-001..025 (personas, reserved for the OOD holdout) and
GEN-251..315 (old mechanical filler tenants, dropped from holdout v2 and
never part of "family" training data to begin with).

Writes: data/training/train_features_v2.csv
        data/training/train_metadata_v2.csv
(train_features_family.csv / train_metadata_family.csv are left untouched).
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

FAMILY = [f"GEN-{i:03d}" for i in range(26, 251)]
PHASE4_PILOT = [f"GEN-{i}" for i in range(401, 426)]
PHASE4_PILOT_V2 = [f"GEN-{i}" for i in range(484, 486)]
PHASE4_FULL = [f"GEN-{i}" for i in range(486, 1486)]
PHASE4_TOPUP = [f"GEN-{i}" for i in range(1486, 1836)]

TENANT_IDS = FAMILY + PHASE4_PILOT + PHASE4_PILOT_V2 + PHASE4_FULL + PHASE4_TOPUP


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
          f"({len(FAMILY)} family + {len(PHASE4_PILOT)} pilot + {len(PHASE4_PILOT_V2)} pilot_v2 "
          f"+ {len(PHASE4_FULL)} full_batch + {len(PHASE4_TOPUP)} topup)")

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
    features_path = os.path.join(out_dir, "train_features_v2.csv")
    metadata_path = os.path.join(out_dir, "train_metadata_v2.csv")

    with open(features_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_COLS)
        writer.writeheader()
        writer.writerows(feature_rows)

    with open(metadata_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=META_COLS)
        writer.writeheader()
        writer.writerows(metadata_rows)

    print(f"[OK] train_features_v2.csv -> {features_path}")
    print(f"[OK] train_metadata_v2.csv -> {metadata_path}")

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
