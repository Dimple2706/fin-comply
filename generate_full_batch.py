"""
Phase 4 diversification, Step 2 (v2): full ~1,000-tenant generation.

Corrected design after the v1 sanity check collapsed all 5 tiers into just
two output values (45.0/MEDIUM and 65.0/HIGH). Root cause: a rule appears to
count as "fired" for severity-floor purposes the moment ANY single row
violates it, not once some meaningful fraction of records are bad -- so
probabilistic "2% bad" settings still produced enough absolute bad rows
(from 60-160 records/table) to trip multiple HIGH rules regardless of
intended tier.

Fix: fields that gate a HIGH or CRITICAL rule are now discrete switches
(true 0% or true high%, never a small in-between probability) for each tier.
Randomization is reserved for fields that don't gate a floor (MEDIUM/LOW
severity rules, company size, minor operational variation) -- that's still
where the real diversity-within-a-tier comes from.

Proven, verified levers (confirmed empirically in Step 1, not assumed):
  - security_events.pii_encrypted=false -> DPDP-008 (CRITICAL), reliable both
    directions.
  - consent_records.consent_status=100% active -> DPDP-001 silent; mostly
    bad -> DPDP-001 fires. Reliable both directions.
  - data_lifecycle.retention_status=100% active -> DPDP-003 silent; mostly
    expired -> DPDP-003 fires. Reliable both directions.
  - system_inventory.data_processor_type=100% internal -> DPDP-016
    structurally NOT_APPLICABLE (sidesteps an unresolved firing pattern with
    dpa_signed rather than relying on it).

New tenant IDs continue from GEN-486 (after the ~85 pilot tenants, GEN-401
through GEN-485, which remain valid and are kept).
"""
import sys
import time
import json
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.generate_data import process_profile

TIER_WEIGHTS = {
    "COMPLIANT": 0.15,
    "LOW": 0.25,
    "MEDIUM": 0.25,
    "HIGH": 0.20,
    "CRITICAL": 0.15,
}

N_TENANTS = 1000
START_ID = 486


def record_counts(rng: random.Random) -> dict:
    size = rng.choice(["small", "medium", "large"])
    mult = {"small": 0.6, "medium": 1.0, "large": 1.7}[size]
    base = {
        "n_customers": 60, "n_consent_records": 70, "n_transaction_events": 160,
        "n_access_logs": 109, "n_data_lifecycle": 80, "n_security_events": 15,
        "n_dsar_requests": 20, "n_system_inventory": 12, "n_policies": 10,
        "n_governance_configs": 1,
    }
    return {k: (v if k == "n_governance_configs" else max(5, int(v * mult * rng.uniform(0.85, 1.15))))
            for k, v in base.items()}


def build_field_distributions(tier: str, rng: random.Random) -> dict:
    # Discrete gates for the fields that control HIGH/CRITICAL rules.
    # consent_gate/retention_gate: True = allowed to fire (DPDP-001/003)
    # critical_gate: True = exactly-1-critical trigger fires (DPDP-008)
    # allow_external_processor: True = DPDP-016 becomes structurally possible
    if tier == "COMPLIANT":
        consent_gate, retention_gate, critical_gate, allow_external = False, False, False, False
    elif tier == "LOW":
        consent_gate, retention_gate, critical_gate, allow_external = False, False, False, False
    elif tier == "MEDIUM":
        # Exactly one of {consent, retention} allowed to fire -- never both,
        # so max 1 HIGH rule, well under the 3+ floor.
        consent_gate = rng.random() < 0.5
        retention_gate = not consent_gate
        critical_gate, allow_external = False, False
    elif tier == "HIGH":
        # The proven lever: exactly one critical trigger. Secondary HIGH
        # rules may also fire (natural diversity) -- floor already
        # guarantees >=65 regardless.
        consent_gate = rng.random() < 0.5
        retention_gate = rng.random() < 0.5
        critical_gate = True
        allow_external = rng.random() < 0.3
    else:  # CRITICAL: stack multiple simultaneous violations, aiming to
           # clear 65 on natural severity accumulation, not just hit the floor.
        consent_gate, retention_gate, critical_gate, allow_external = True, True, True, True

    # Non-gating "noise" fields: free to vary continuously regardless of
    # tier -- this is where genuine within-tier diversity comes from,
    # since these map to MEDIUM/LOW-severity rules with no floor of their own.
    notice_bad = rng.uniform(0.05, 0.5)
    bundle_bad = rng.uniform(0.05, 0.4)
    sla_bad = rng.uniform(0.1, 0.5)
    access_bad = rng.uniform(0.05, 0.4)
    dpo_assigned = rng.random() > (0.1 if tier in ("COMPLIANT", "LOW") else 0.4)

    return {
        "governance_config": {
            "dpo_assigned": dpo_assigned,
            "grievance_endpoint_available": rng.random() > (0.1 if tier in ("COMPLIANT", "LOW") else 0.4),
            "last_audit_date": rng.choice(["2025-06-01", "2024-11-15", "2025-01-20", "2024-03-10"]),
            "audit_frequency_days": rng.choice([90, 180, 365]),
            "risk_level": tier if tier in ("HIGH", "MEDIUM", "CRITICAL") else "LOW",
        },
        "system_inventory": {
            "encryption_type": {"AES-256": 1.0},
            "pii_stored": {"true": 0.6, "false": 0.4},
            "encryption_enabled": True,
            "dpa_signed": True,  # not relied upon; data_processor_type gates DPDP-016 instead
            "data_processor_type": (
                {"third_party_processor": 0.7, "sub_processor": 0.15, "internal": 0.15}
                if allow_external else "internal"
            ),
            "access_control_enabled": True,
            "retention_policy_applied": rng.random() > (0.1 if tier in ("COMPLIANT", "LOW") else 0.4),
        },
        "consent_records": {
            "consent_status": (
                {"expired": 0.5, "revoked": 0.3, "withdrawn": 0.2} if consent_gate else "active"
            ),
            "notice_provided": {"true": 1 - notice_bad, "false": notice_bad},
            "is_bundled": {"false": 1 - bundle_bad, "true": bundle_bad},
            "consent_channel": {"app": 0.5, "web": 0.3, "implicit": 0.2},
            "consented_purpose": {"loan_processing": 0.6, "account_management": 0.2, "kyc_verification": 0.2},
            "guardian_consent_hash": "null",
        },
        "transaction_events": {
            "event_type": {"credit_check": 0.3, "loan_disbursal": 0.3, "emi_collection": 0.2, "account_update": 0.2},
            "processing_purpose": {"loan_processing": 0.6, "account_management": 0.2, "kyc_verification": 0.2},
            "shared_with_third_party": rng.random() < (0.3 if tier in ("HIGH", "CRITICAL") else 0.05),
            "is_cross_border": rng.random() < (0.15 if tier in ("HIGH", "CRITICAL") else 0.02),
        },
        "access_logs": {
            "employee_role": {"customer_support": 0.4, "data_analyst": 0.3, "compliance_officer": 0.2, "engineer": 0.1},
            "accessed_pii": {"true": access_bad, "false": 1 - access_bad},
            "data_volume_accessed": {"low": 1 - access_bad, "medium": access_bad * 0.6, "high": access_bad * 0.4},
            "access_reason": {"support_query": 0.4, "kyc_check": 0.3, "data_export": 0.2, "loan_review": 0.1},
            "access_outcome": {"granted": 1 - access_bad * 0.3, "denied": access_bad * 0.3},
        },
        "data_lifecycle": {
            "retention_status": (
                {"expired": 0.8, "pending_deletion": 0.2} if retention_gate else "active"
            ),
            "purpose_completed": {"false": 0.6, "true": 0.4},
            "legal_hold_flag": False,
            "erasure_requested": {"false": 0.85, "true": 0.15},
            "data_category": {"kyc_documents": 0.4, "transaction_history": 0.3, "credit_score": 0.2, "contact_info": 0.1},
        },
        "security_events": {
            "breach_detected": critical_gate and tier == "CRITICAL" and rng.random() < 0.6,
            "pii_encrypted": False if critical_gate else True,
            "encryption_type_when_encrypted_false": "md5",
            "encryption_type_when_encrypted_true": "AES-256",
        },
        "dsar_requests": {
            "request_type": {"erasure": 0.4, "access": 0.4, "correction": 0.2},
            "sla_breached": {"false": 1 - sla_bad, "true": sla_bad},
            "fulfillment_status": {"pending": sla_bad, "fulfilled": max(0.1, 1 - sla_bad - 0.1), "partially_fulfilled": 0.1},
        },
        "customer_master": {
            "is_minor": False,
            "data_principal_type": "individual",
            "account_status": {"active": 0.85, "dormant": 0.1, "closed": 0.05},
            "kyc_status": {"verified": 0.8, "pending": 0.15, "expired": 0.05},
        },
        "policies": {
            "policy_type": {"retention": 0.3, "consent": 0.3, "encryption": 0.2, "access_control": 0.2},
            "is_active": rng.random() > (0.05 if tier in ("COMPLIANT", "LOW") else 0.3),
            "policy_value_unit": "days",
        },
    }


def build_profiles(n: int, start_id: int, seed: int):
    rng = random.Random(seed)
    tiers = list(TIER_WEIGHTS.keys())
    weights = list(TIER_WEIGHTS.values())

    profiles = []
    for i in range(n):
        tid = start_id + i
        tier = rng.choices(tiers, weights=weights)[0]
        fd = build_field_distributions(tier, rng)
        profiles.append({
            "tenant_id": f"GEN-{tid}",
            "profile_name": f"diversified_{tier.lower()}_{tid}",
            "record_counts": record_counts(rng),
            "field_distributions": fd,
            "_target_tier": tier,
        })
    return profiles


def run_batch(profiles, report_path):
    results = []
    t_start_all = time.perf_counter()
    n_ok, n_fail = 0, 0
    for idx, p in enumerate(profiles, 1):
        t0 = time.perf_counter()
        try:
            report = process_profile({k: v for k, v in p.items() if not k.startswith("_")})
            elapsed = time.perf_counter() - t0
            report["_target_tier"] = p["_target_tier"]
            report["_elapsed_sec"] = round(elapsed, 2)
            results.append(report)
            n_ok += 1
        except Exception as e:
            elapsed = time.perf_counter() - t0
            results.append({"tenant_id": p["tenant_id"], "status": "error", "error": str(e),
                             "_target_tier": p["_target_tier"], "_elapsed_sec": round(elapsed, 2)})
            n_fail += 1

        if idx % 25 == 0 or idx == len(profiles):
            elapsed_all = time.perf_counter() - t_start_all
            rate = elapsed_all / idx
            remaining = (len(profiles) - idx) * rate
            print(f"[{idx}/{len(profiles)}] ok={n_ok} fail={n_fail} "
                  f"elapsed={elapsed_all/60:.1f}min avg={rate:.2f}s/tenant "
                  f"ETA={remaining/60:.1f}min", flush=True)

    t_total = time.perf_counter() - t_start_all
    print(f"\nBATCH COMPLETE: {n_ok}/{len(profiles)} succeeded in {t_total/60:.1f} minutes")

    with open(report_path, "w") as f:
        json.dump({"n_tenants": len(results), "n_ok": n_ok, "n_fail": n_fail,
                   "total_minutes": round(t_total / 60, 2), "results": results}, f, indent=2)
    print(f"[OK] Report written to {report_path}")
    return results


if __name__ == "__main__":
    profiles = build_profiles(N_TENANTS, START_ID, seed=20260903)
    print(f"Would generate {len(profiles)} tenants (GEN-{START_ID} to GEN-{START_ID+N_TENANTS-1})")
    run_batch(profiles, "phase4_full_batch_report.json")
