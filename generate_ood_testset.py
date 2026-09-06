"""
OOD Holdout v2 generator (Test-side redesign, 2026-09-06).

Why this exists: the previous 90-tenant holdout (data/training/holdout_*_unique.csv)
was mostly (65/90) built by the SAME tier-first, fixed-recipe generator used for
training data (see generate_pilot_batch*.py / generate_full_batch.py /
generate_topup_batch.py). Reusing that generator for the test set means the model
is evaluated on the same generating distribution it trained on -- not a genuine
out-of-distribution test. This script uses a structurally different mechanism:

  1. A pairwise covering array (allpairspy) over 14 binary rule-violation factors
     (one per confirmed-reliable DPDP rule; DPDP-002/006 are excluded -- see
     src/agent_layer/outcome_evaluator.py, they are permanently unfireable in the
     current schema). This guarantees every PAIR of rule states (on/off x on/off)
     is exercised at least once, which the training generator's fixed tier
     recipes never attempted.
  2. Randomized company-size / record-count bands per tenant (small/medium/large),
     decorrelated from training's fixed RECORD_COUNTS block.
  3. The ACTUAL resulting risk_tier is observed via the real pipeline
     (process_profile -> anonymization -> compliance engine) -- never forced.
  4. A bucket-and-fill pass tops up under-represented tiers using randomized
     k-hot factor vectors (standard rejection/stratified sampling for
     class-imbalanced synthetic sets) plus explicit all-on / all-off boost
     variants for CRITICAL and COMPLIANT, which the topup batch already proved
     necessary to reach those tiers at all.

The 25 hand-authored OOD personas (GEN-001..025) are kept as-is and are NOT
regenerated here; this script only produces their ~375-tenant replacement for
the 65 mechanical filler tenants (GEN-251..315) that the v1 holdout used.

Tenant IDs: GEN-20000+ -- a block far above every ID used by training generation
(raw_synthetic currently spans GEN-1..GEN-9405), chosen to make v2 test tenants
trivially identifiable and impossible to collide with the training pool.
"""
import sys
import time
import json
import random
import argparse
from pathlib import Path
from collections import Counter

from allpairspy import AllPairs

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.generate_data import process_profile

START_ID = 20000

FACTORS = [
    "DPDP-001", "DPDP-003", "DPDP-004", "DPDP-005", "DPDP-007", "DPDP-008",
    "DPDP-009", "DPDP-010", "DPDP-011", "DPDP-012", "DPDP-013", "DPDP-014",
    "DPDP-015", "DPDP-016",
]

TIER_TARGET = {"COMPLIANT": 70, "LOW": 70, "MEDIUM": 70, "HIGH": 70, "CRITICAL": 70}

SIZE_BANDS = {
    "small":  dict(n_customers=(15, 30),  n_consent_records=(20, 40),  n_transaction_events=(40, 90),
                   n_access_logs=(30, 70),  n_data_lifecycle=(25, 50),  n_security_events=(5, 10),
                   n_dsar_requests=(5, 12), n_system_inventory=(3, 8),  n_policies=(4, 8)),
    "medium": dict(n_customers=(40, 80),  n_consent_records=(50, 100), n_transaction_events=(100, 200),
                   n_access_logs=(80, 150), n_data_lifecycle=(60, 110), n_security_events=(10, 20),
                   n_dsar_requests=(12, 25), n_system_inventory=(8, 15), n_policies=(6, 12)),
    "large":  dict(n_customers=(90, 160), n_consent_records=(110, 200), n_transaction_events=(220, 400),
                   n_access_logs=(160, 300), n_data_lifecycle=(120, 220), n_security_events=(18, 35),
                   n_dsar_requests=(20, 40), n_system_inventory=(12, 20), n_policies=(8, 15)),
}


def random_record_counts() -> dict:
    band = SIZE_BANDS[random.choice(list(SIZE_BANDS.keys()))]
    counts = {k: random.randint(*v) for k, v in band.items()}
    counts["n_governance_configs"] = 1
    return counts


def apply_factor(fd: dict, rule_id: str, on: bool):
    """Mutate fd (table -> field_distributions) to switch one rule on/off.
    Each rule's controlling fields were empirically isolated against
    src/agent_layer/outcome_evaluator.py + the DB rules table on 2026-09-05
    (see memory: feedback-rule-engine-discrete-gates)."""
    if rule_id == "DPDP-001":
        fd["consent_records"]["consent_status"] = "expired" if on else "active"

    elif rule_id == "DPDP-003":
        fd["data_lifecycle"]["retention_expiry_date_past_for_pct"] = 1.0 if on else 0.0
        fd["data_lifecycle"]["retention_status_for_past"] = "expired"
        # generate_data_lifecycle()'s default retention_status_for_current is
        # {"active": 0.90, "pending_deletion": 0.10} -- the 10% pending_deletion
        # rows then hit the generator's own DB-constraint safety patch (a
        # "pending_deletion" row can't carry a future expiry date, so it gets
        # backdated to 2023-01-01), which silently manufactures a past-expiry
        # non-deleted row and fires DPDP-003 even when this factor is "off".
        # Force the current-branch status fully deterministic to close the leak.
        fd["data_lifecycle"]["retention_status_for_current"] = "active"
        fd["data_lifecycle"]["legal_hold_flag"] = False

    elif rule_id == "DPDP-004":
        fd["consent_records"]["notice_provided"] = not on

    elif rule_id == "DPDP-005":
        fd["customer_master"]["is_minor"] = on

    elif rule_id == "DPDP-007":
        fd["access_logs"]["accessed_pii_when_authorised"] = True
        fd["access_logs"]["pii_fields_justified_when_authorised"] = not on

    elif rule_id == "DPDP-008":
        fd["security_events"]["pii_encrypted"] = not on

    elif rule_id == "DPDP-009":
        fd["governance_config"]["grievance_endpoint_available"] = not on

    elif rule_id == "DPDP-010":
        fd["dsar_requests"]["request_type"] = "erasure" if on else "access"
        fd["dsar_requests"]["sla_breached"] = on
        fd["data_lifecycle"].setdefault("legal_hold_flag", False)

    elif rule_id == "DPDP-011":
        fd["data_lifecycle"]["purpose_completed"] = on
        fd["data_lifecycle"].setdefault("legal_hold_flag", False)

    elif rule_id == "DPDP-012":
        fd["governance_config"]["is_significant_data_fiduciary"] = on
        if on:
            fd["governance_config"]["dpo_assigned"] = False
            fd["governance_config"]["audit_frequency_days"] = 400

    elif rule_id == "DPDP-013":
        fd["access_logs"]["accessed_pii_when_authorised"] = True
        fd["access_logs"]["access_authorized_when_authorised"] = not on

    elif rule_id == "DPDP-014":
        fd["security_events"]["breach_detected"] = on
        if on:
            fd["security_events"]["breach_rows"] = {"affected_user_count": "critical", "notification_delay_hours": 240}

    elif rule_id == "DPDP-015":
        fd["transaction_events"]["is_cross_border"] = on
        if on:
            fd["transaction_events"]["transfer_restriction_compliant"] = False

    elif rule_id == "DPDP-016":
        if on:
            fd["system_inventory"]["data_processor_type"] = "third_party_processor"
            fd["system_inventory"]["pii_stored"] = True
            fd["system_inventory"]["dpa_signed"] = False
        else:
            fd["system_inventory"]["data_processor_type"] = "internal"
            fd["system_inventory"]["dpa_signed"] = True

    else:
        raise ValueError(f"Unknown factor {rule_id}")


def field_distributions_from_vector(vector: dict) -> dict:
    fd = {
        "governance_config": {}, "system_inventory": {}, "consent_records": {},
        "transaction_events": {}, "access_logs": {}, "data_lifecycle": {},
        "security_events": {}, "dsar_requests": {}, "customer_master": {}, "policies": {},
    }
    for rule_id, on in vector.items():
        apply_factor(fd, rule_id, on)
    return fd


def covering_array(order: int = 3) -> list:
    """t-way covering array over the 14 binary factors. Plain pairwise (order=2)
    collapses to only 9 rows for 14 all-binary factors -- too thin to be a
    meaningful structured core -- so this defaults to 3-way coverage (14 rows),
    a strictly stronger interaction guarantee, and lets the bucket-fill pass
    supply the bulk of the volume via randomized k-hot sampling."""
    rows = []
    for row in AllPairs([[False, True]] * len(FACTORS), n=order):
        rows.append(dict(zip(FACTORS, row)))
    return rows


def vector_tag(vector: dict) -> str:
    return "".join("1" if vector[f] else "0" for f in FACTORS)


def build_profile(vector: dict, tenant_id: str, tag: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "profile_name": f"oodv2_{tag}_{tenant_id}",
        "record_counts": random_record_counts(),
        "field_distributions": field_distributions_from_vector(vector),
        "_vector": vector,
    }


CRITICAL_SEV_FACTORS = ["DPDP-005", "DPDP-008", "DPDP-014"]


def random_k_hot_vector(k: int = None) -> dict:
    if k is None:
        k = random.randint(0, len(FACTORS))
    on_factors = set(random.sample(FACTORS, k))
    return {f: (f in on_factors) for f in FACTORS}


def all_on_vector() -> dict:
    return {f: True for f in FACTORS}


def all_off_vector() -> dict:
    return {f: False for f in FACTORS}


HIGH_SEV_FACTORS = ["DPDP-001", "DPDP-003", "DPDP-010", "DPDP-013", "DPDP-015", "DPDP-016"]
LIGHT_SEV_FACTORS = ["DPDP-004", "DPDP-007", "DPDP-011", "DPDP-012", "DPDP-009"]  # MEDIUM + LOW severity


def low_target_vector() -> dict:
    """LOW tier (0<score<30): the max_possible denominator only counts rules
    that are actually 'applicable' for the generated data, which shrinks hard
    once most factors are off -- so even a single HIGH-severity violation can
    swing the score a large discrete jump (confirmed empirically: 1 HIGH +
    light factors landed at 45.0/MEDIUM in testing, not the ~15-20 expected).
    Zero HIGH-severity factors is the only combination confirmed to land
    reliably in LOW; light-severity-only factors stay well clear of the
    HIGH-tier floors entirely."""
    n_light = random.randint(1, 3)
    on = set(random.sample(LIGHT_SEV_FACTORS, n_light))
    return {f: (f in on) for f in FACTORS}


def medium_target_vector() -> dict:
    """MEDIUM tier (30<=score<55): no CRITICAL-severity factor, and exactly 3
    HIGH-severity factors to trigger the '3+ HIGH violations' floor (45)
    without also clearing the CRITICAL-only floor (65)."""
    on = set(random.sample(HIGH_SEV_FACTORS, 3))
    n_light = random.randint(0, 3)
    on |= set(random.sample(LIGHT_SEV_FACTORS, n_light))
    return {f: (f in on) for f in FACTORS}


def build_topup_profiles(start_id: int, n_low: int, n_medium: int) -> list:
    tid = start_id
    profiles = []

    def add(vector, tag):
        nonlocal tid
        profiles.append(build_profile(vector, f"GEN-{tid}", tag))
        tid += 1

    for _ in range(n_low):
        add(low_target_vector(), "topup_low")
    for _ in range(n_medium):
        add(medium_target_vector(), "topup_medium")
    return profiles


def critical_boost_vector() -> dict:
    """>=2 of the 3 CRITICAL-severity factors on, plus a random spread of
    the rest -- CRITICAL tier (score>=75) needs multiple stacked violations,
    not just one (a single CRITICAL-severity rule only floors the score at
    65/HIGH), confirmed empirically via the all-on/all-off boundary check."""
    n_crit = random.choice([2, 3])
    on = set(random.sample(CRITICAL_SEV_FACTORS, n_crit))
    others = [f for f in FACTORS if f not in CRITICAL_SEV_FACTORS]
    on |= set(random.sample(others, random.randint(6, len(others))))
    return {f: (f in on) for f in FACTORS}


def build_full_profiles(start_id: int, total: int) -> list:
    tid = start_id
    profiles = []

    def add(vector, tag):
        nonlocal tid
        profiles.append(build_profile(vector, f"GEN-{tid}", tag))
        tid += 1

    # Structured core: t-way covering array, 2 variants per skeleton row.
    array = covering_array()
    for i, vector in enumerate(array):
        for v in range(2):
            add(vector, f"core{i}v{v}")

    n_core = len(profiles)
    n_compliant_boost = 20
    n_critical_boost = 20
    n_fill = max(total - n_core - n_compliant_boost - n_critical_boost, 0)

    for _ in range(n_compliant_boost):
        add(all_off_vector(), "compliant_boost")

    for _ in range(n_critical_boost):
        add(critical_boost_vector(), "critical_boost")

    for _ in range(n_fill):
        add(random_k_hot_vector(), "fill")

    return profiles[:total] if len(profiles) > total else profiles


def run_batch(profiles: list, report_path: str) -> list:
    results = []
    t0_all = time.perf_counter()
    n_ok, n_fail = 0, 0
    tier_counts = Counter()
    for idx, p in enumerate(profiles, 1):
        t0 = time.perf_counter()
        try:
            report = process_profile({k: v for k, v in p.items() if not k.startswith("_")})
            report["_vector"] = {k: v for k, v in p["_vector"].items()}
            report["_elapsed_sec"] = round(time.perf_counter() - t0, 2)
            results.append(report)
            if report["status"].startswith("success"):
                n_ok += 1
                tier_counts[report["risk_tier"]] += 1
            else:
                n_fail += 1
        except Exception as e:
            results.append({"tenant_id": p["tenant_id"], "status": "error", "error": str(e),
                             "_vector": p["_vector"], "_elapsed_sec": round(time.perf_counter() - t0, 2)})
            n_fail += 1
        if idx % 10 == 0 or idx == len(profiles):
            el = time.perf_counter() - t0_all
            print(f"[{idx}/{len(profiles)}] ok={n_ok} fail={n_fail} elapsed={el/60:.1f}min tiers={dict(tier_counts)}", flush=True)

    print(f"\nBATCH COMPLETE: {n_ok}/{len(profiles)} ok in {(time.perf_counter()-t0_all)/60:.1f} min")
    print(f"Tier distribution: {dict(tier_counts)}")
    with open(report_path, "w") as f:
        json.dump({"n_ok": n_ok, "n_fail": n_fail, "tier_counts": dict(tier_counts), "results": results}, f, indent=2, default=str)
    print(f"[OK] Report written to {report_path}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["sanity", "full", "topup"], default="sanity")
    ap.add_argument("--report", type=str, default="ood_v2_sanity_report.json")
    ap.add_argument("--start_id", type=int, default=START_ID)
    ap.add_argument("--total", type=int, default=250)
    ap.add_argument("--n_low", type=int, default=75)
    ap.add_argument("--n_medium", type=int, default=75)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.mode == "sanity":
        array = covering_array()
        print(f"Covering array: {len(array)} skeleton rows for {len(FACTORS)} factors")
        tid = args.start_id
        profiles = []
        for vector in array:
            profiles.append(build_profile(vector, f"GEN-{tid}", vector_tag(vector)))
            tid += 1
    elif args.mode == "topup":
        profiles = build_topup_profiles(args.start_id, args.n_low, args.n_medium)
    else:
        profiles = build_full_profiles(args.start_id, args.total)

    print(f"Generating {len(profiles)} tenants, starting {profiles[0]['tenant_id']}")
    run_batch(profiles, args.report)
