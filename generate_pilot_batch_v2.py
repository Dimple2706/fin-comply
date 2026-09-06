"""
Phase 4 diversification, Step 1 (v2): corrected boundary-targeted pilot.

Fixes over the first pilot (GEN-401..425):
  - security_events.pii_encrypted is now ALWAYS compliant ("true") in both
    groups. In v1, a leftover 10% chance of "false" there independently fired
    DPDP-008 (CRITICAL) even in the group that was supposed to have no
    critical trigger at all -- that's why 8/12 "45-boundary" tenants
    incorrectly landed at 65.0/HIGH instead of near 45.
  - Group A (65-boundary) now varies a continuous severity gradient across
    SIX fields at once (consent status, notice, bundling, retention, DPA,
    DSAR SLA breach) instead of one weak "noise" knob, so the pre-floor
    score has a real chance of clearing 65 at the high end while staying
    clearly below it at the low end.

New tenant IDs (GEN-426 onward) so the v1 batch (GEN-401-425, already valid,
already in the DB) is left untouched for comparison.
"""
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.generate_data import process_profile

RECORD_COUNTS = {
    "n_customers": 60, "n_consent_records": 70, "n_transaction_events": 160,
    "n_access_logs": 109, "n_data_lifecycle": 80, "n_security_events": 15,
    "n_dsar_requests": 20, "n_system_inventory": 12, "n_policies": 10,
    "n_governance_configs": 1,
}


def lerp_weight(good_at_0: float, good_at_1: float, sev: float) -> float:
    """Interpolate the 'good outcome' probability as severity 0->1."""
    return good_at_0 + (good_at_1 - good_at_0) * sev


def group_a_field_distributions(sev: float) -> dict:
    """
    sev in [0,1]: 0 = minimal extra findings (floor should clamp to exactly
    65), 1 = maximum extra findings (pre-floor score should have a real
    chance of exceeding 65). Exactly one CRITICAL trigger throughout
    (system_inventory encryption only) -- security_events stays compliant
    so DPDP-008 fires via exactly one path, not two.
    """
    good_consent = lerp_weight(0.9, 0.15, sev)
    good_notice = lerp_weight(0.9, 0.15, sev)
    good_bundle = lerp_weight(0.9, 0.15, sev)
    good_retention = lerp_weight(0.85, 0.1, sev)
    good_dpa = lerp_weight(0.9, 0.1, sev)
    good_sla = lerp_weight(0.85, 0.15, sev)

    return {
        "governance_config": {
            "dpo_assigned": True, "grievance_endpoint_available": True,
            "last_audit_date": "2025-06-01", "audit_frequency_days": 90,
            "risk_level": "HIGH",
        },
        "system_inventory": {
            "encryption_type": {"md5": 1.0},
            "pii_stored": {"true": 1.0},
            "encryption_enabled": True,
            "dpa_signed": {"true": good_dpa, "false": 1 - good_dpa},
            "data_processor_type": {"internal": 0.2, "third_party_processor": 0.7, "sub_processor": 0.1},
            "access_control_enabled": True,
            "retention_policy_applied": True,
        },
        "consent_records": {
            "consent_status": {"active": good_consent, "expired": (1 - good_consent) * 0.5,
                                "revoked": (1 - good_consent) * 0.3, "withdrawn": (1 - good_consent) * 0.2},
            "notice_provided": {"true": good_notice, "false": 1 - good_notice},
            "is_bundled": {"false": good_bundle, "true": 1 - good_bundle},
            "consent_channel": {"app": 0.5, "web": 0.3, "implicit": 0.2},
            "consented_purpose": {"loan_processing": 0.6, "account_management": 0.2, "kyc_verification": 0.2},
            "guardian_consent_hash": "null",
        },
        "transaction_events": {
            "event_type": {"credit_check": 0.3, "loan_disbursal": 0.3, "emi_collection": 0.2, "account_update": 0.2},
            "processing_purpose": {"loan_processing": 0.6, "account_management": 0.2, "kyc_verification": 0.2},
            "shared_with_third_party": False, "is_cross_border": False,
        },
        "access_logs": {
            "employee_role": {"customer_support": 0.4, "data_analyst": 0.3, "compliance_officer": 0.2, "engineer": 0.1},
            "accessed_pii": {"true": lerp_weight(0.2, 0.6, sev), "false": lerp_weight(0.8, 0.4, sev)},
            "data_volume_accessed": {"low": lerp_weight(0.7, 0.2, sev), "medium": 0.2, "high": lerp_weight(0.1, 0.6, sev)},
            "access_reason": {"support_query": 0.4, "kyc_check": 0.3, "data_export": 0.2, "loan_review": 0.1},
            "access_outcome": {"granted": 0.9, "denied": 0.1},
        },
        "data_lifecycle": {
            "retention_status": {"active": good_retention, "expired": (1 - good_retention) * 0.7,
                                  "pending_deletion": (1 - good_retention) * 0.3},
            "purpose_completed": {"false": 0.5, "true": 0.5},
            "legal_hold_flag": False,
            "erasure_requested": {"false": 0.8, "true": 0.2},
            "data_category": {"kyc_documents": 0.4, "transaction_history": 0.3, "credit_score": 0.2, "contact_info": 0.1},
        },
        "security_events": {
            "breach_detected": False,
            # pii_encrypted is the ONLY field DPDP-008 actually reads
            # (query_builder.py selects solely from security_events; the
            # system_inventory.encryption_type field is unrelated to this
            # rule -- that was the v2 mistake). Locking this false is what
            # actually produces the single guaranteed CRITICAL trigger.
            "pii_encrypted": {"false": 1.0},
            "encryption_type_when_encrypted_false": "md5",
            "encryption_type_when_encrypted_true": "AES-256",
        },
        "dsar_requests": {
            "request_type": {"erasure": 0.4, "access": 0.4, "correction": 0.2},
            "sla_breached": {"false": good_sla, "true": 1 - good_sla},
            "fulfillment_status": {"pending": 0.3, "fulfilled": 0.5, "partially_fulfilled": 0.2},
        },
        "customer_master": {
            "is_minor": False, "data_principal_type": "individual",
            "account_status": {"active": 0.85, "dormant": 0.1, "closed": 0.05},
            "kyc_status": {"verified": 0.8, "pending": 0.15, "expired": 0.05},
        },
        "policies": {
            "policy_type": {"retention": 0.3, "consent": 0.3, "encryption": 0.2, "access_control": 0.2},
            "is_active": True, "policy_value_unit": "days",
        },
    }


def group_b_field_distributions(high_count: int) -> dict:
    """No critical trigger at all: AES-256 everywhere, security_events fully
    compliant. high_count (0-3) is now an explicit staircase over exactly
    which of {DPDP-001 via consent, DPDP-003 via retention, DPDP-016 via DPA}
    are switched genuinely ON vs genuinely OFF -- not a mild probability
    shift. v2's mistake was using 90%/10% splits, which still left enough
    violating records (~10% of 70-80 rows) to trigger all three HIGH rules
    even at high_count=0. Clean means ~99% clean now, violating means ~95%+
    violating, so the staircase actually separates:
      hc=0: 0 of the 3 HIGH rules fire   (all three genuinely clean)
      hc=1: DPDP-016 only                (DPA violating, rest clean)
      hc=2: DPDP-016 + DPDP-003          (DPA + retention violating)
      hc=3: DPDP-016 + DPDP-003 + DPDP-001 (all three violating -> 3+ HIGH floor)
    """
    consent_violating = high_count >= 3
    retention_violating = high_count >= 2
    dpa_violating = high_count >= 1

    return {
        "governance_config": {
            "dpo_assigned": True, "grievance_endpoint_available": True,
            "last_audit_date": "2025-06-01", "audit_frequency_days": 90,
            "risk_level": "MEDIUM",
        },
        "system_inventory": {
            "encryption_type": {"AES-256": 1.0},
            "pii_stored": {"true": 0.5, "false": 0.5},
            "encryption_enabled": True,
            "dpa_signed": {"false": 0.97, "true": 0.03} if dpa_violating else True,
            "data_processor_type": {"internal": 0.3, "third_party_processor": 0.6, "sub_processor": 0.1},
            "access_control_enabled": True,
            "retention_policy_applied": True,
        },
        "consent_records": {
            "consent_status": (
                {"expired": 0.55, "revoked": 0.25, "withdrawn": 0.15, "active": 0.05} if consent_violating
                else "active"
            ),
            "notice_provided": {"false": 0.1, "true": 0.9},
            "is_bundled": {"true": 0.1, "false": 0.9},
            "consent_channel": {"app": 0.6, "web": 0.3, "implicit": 0.1},
            "consented_purpose": {"loan_processing": 0.6, "account_management": 0.2, "kyc_verification": 0.2},
            "guardian_consent_hash": "null",
        },
        "transaction_events": {
            "event_type": {"credit_check": 0.3, "loan_disbursal": 0.3, "emi_collection": 0.2, "account_update": 0.2},
            "processing_purpose": {"loan_processing": 0.6, "account_management": 0.2, "kyc_verification": 0.2},
            "shared_with_third_party": False, "is_cross_border": False,
        },
        "access_logs": {
            "employee_role": {"customer_support": 0.4, "data_analyst": 0.3, "compliance_officer": 0.2, "engineer": 0.1},
            "accessed_pii": {"true": 0.3, "false": 0.7},
            "data_volume_accessed": {"low": 0.7, "medium": 0.2, "high": 0.1},
            "access_reason": {"support_query": 0.4, "kyc_check": 0.3, "data_export": 0.2, "loan_review": 0.1},
            "access_outcome": {"granted": 0.9, "denied": 0.1},
        },
        "data_lifecycle": {
            "retention_status": (
                {"expired": 0.9, "pending_deletion": 0.08, "active": 0.02} if retention_violating
                else "active"
            ),
            "purpose_completed": {"false": 0.6, "true": 0.4},
            "legal_hold_flag": False,
            "erasure_requested": {"false": 0.85, "true": 0.15},
            "data_category": {"kyc_documents": 0.4, "transaction_history": 0.3, "credit_score": 0.2, "contact_info": 0.1},
        },
        "security_events": {
            "breach_detected": False,
            "pii_encrypted": {"true": 1.0},  # locked compliant -- the v1 fix
            "encryption_type_when_encrypted_false": "md5",
            "encryption_type_when_encrypted_true": "AES-256",
        },
        "dsar_requests": {
            "request_type": {"erasure": 0.4, "access": 0.4, "correction": 0.2},
            "sla_breached": {"false": 0.7, "true": 0.3},
            "fulfillment_status": {"pending": 0.3, "fulfilled": 0.5, "partially_fulfilled": 0.2},
        },
        "customer_master": {
            "is_minor": False, "data_principal_type": "individual",
            "account_status": {"active": 0.85, "dormant": 0.1, "closed": 0.05},
            "kyc_status": {"verified": 0.8, "pending": 0.15, "expired": 0.05},
        },
        "policies": {
            "policy_type": {"retention": 0.3, "consent": 0.3, "encryption": 0.2, "access_control": 0.2},
            "is_active": True, "policy_value_unit": "days",
        },
    }


def build_profiles():
    # Small confirming batch only: Group A already confirmed working
    # (13/13 correctly hit 65/HIGH in the previous run), so this run is
    # just to confirm Group B's re-fixed staircase actually separates
    # hc=0/1/2 (no floor, should differ from each other) from hc=3
    # (3+ HIGH -> floor at 45), 2 tenants per level.
    profiles = []
    tid_counter = 484

    for i, hc in enumerate([0, 3]):
        fd = group_b_field_distributions(hc)
        profiles.append({
            "tenant_id": f"GEN-{tid_counter}",
            "profile_name": f"boundary_high_floor_v3_{i+1}_hc{hc}",
            "record_counts": dict(RECORD_COUNTS),
            "field_distributions": fd,
            "_target": f"45-boundary-hc{hc}",
        })
        tid_counter += 1

    return profiles


def main():
    profiles = build_profiles()
    print(f"Generating {len(profiles)} corrected boundary-targeted pilot tenants "
          f"(GEN-451 to GEN-{450+len(profiles)})\n")

    results = []
    t_start_all = time.perf_counter()
    for p in profiles:
        t0 = time.perf_counter()
        try:
            report = process_profile({k: v for k, v in p.items() if not k.startswith("_")})
            elapsed = time.perf_counter() - t0
            report["_target"] = p["_target"]
            report["_elapsed_sec"] = round(elapsed, 2)
            results.append(report)
            print(f"  -> {p['tenant_id']} [{p['_target']}]: "
                  f"score={report.get('risk_score')} tier={report.get('risk_tier')} "
                  f"({elapsed:.2f}s)")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  -> {p['tenant_id']} FAILED after {elapsed:.2f}s: {e}")
            results.append({"tenant_id": p["tenant_id"], "status": "error",
                             "error": str(e), "_elapsed_sec": round(elapsed, 2),
                             "_target": p["_target"]})

    t_total = time.perf_counter() - t_start_all
    times = [r["_elapsed_sec"] for r in results]
    avg = sum(times) / len(times) if times else 0

    print("\n" + "=" * 60)
    print(f"PILOT BATCH v2 COMPLETE: {len(results)} tenants in {t_total:.1f}s")
    print(f"Average per tenant : {avg:.2f}s")
    print("=" * 60)

    with open("phase4_pilot_report_v2.json", "w") as f:
        json.dump({
            "n_tenants": len(results),
            "total_seconds": round(t_total, 2),
            "avg_seconds_per_tenant": round(avg, 3),
            "results": results,
        }, f, indent=2)
    print("\n[OK] Report written to phase4_pilot_report_v2.json")


if __name__ == "__main__":
    main()
