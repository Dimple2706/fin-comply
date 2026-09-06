"""
Phase 4 diversification, Step 1: timing pilot + boundary-targeted tenants.

Generates ~25 new tenants (GEN-401 onward) deliberately aimed at the two
severity-floor boundaries diagnosed this session:
  - Group A (~13 tenants): exactly one CRITICAL trigger (weak/no encryption on
    a PII-storing system -> DPDP-008), with varying background noise so the
    pre-floor score sometimes exceeds 65 and sometimes sits below it (floor
    then clamps to exactly 65.0) -> real diversity around the HIGH/CRITICAL
    boundary.
  - Group B (~12 tenants): no CRITICAL trigger, with the count of HIGH-rule
    triggers (DPDP-001 consent, DPDP-003 retention, DPDP-016 missing DPA)
    deliberately varied between 2 and 3, to compare "no floor" vs "3+ HIGH ->
    floor at 45" directly.

This is also the timing pilot: wall-clock time is recorded per tenant so we
know, empirically, whether ~1,000 full-pipeline tenants fits the remaining
time budget, instead of guessing.

These tenants are NOT throwaway -- they become the first real slice of the
diversified training corpus, continuing the GEN- numbering after GEN-315.
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


def base_field_distributions(critical_trigger: bool, high_count: int) -> dict:
    """
    critical_trigger: if True, force exactly one weak-encryption PII system
                       (-> DPDP-008, CRITICAL). If False, all systems AES-256.
    high_count: how many of {DPDP-001, DPDP-003, DPDP-016} to bias toward
                firing (0-3). Only meaningful when critical_trigger=False,
                to isolate the 45-floor boundary from the 65-floor boundary.
    """
    fd = {
        "governance_config": {
            "dpo_assigned": True,
            "grievance_endpoint_available": True,
            "last_audit_date": "2025-06-01",
            "audit_frequency_days": 90,
            "risk_level": "MEDIUM",
        },
        "system_inventory": {
            "encryption_type": {"md5": 1.0} if critical_trigger else {"AES-256": 1.0},
            "pii_stored": {"true": 1.0 if critical_trigger else 0.5, "false": 0.0 if critical_trigger else 0.5},
            "encryption_enabled": True,
            "dpa_signed": {"false": 0.9, "true": 0.1} if high_count >= 3 else (
                {"false": 0.5, "true": 0.5} if high_count == 2 else {"false": 0.1, "true": 0.9}
            ),
            "data_processor_type": {"internal": 0.3, "third_party_processor": 0.6, "sub_processor": 0.1},
            "access_control_enabled": True,
            "retention_policy_applied": True,
        },
        "consent_records": {
            "consent_status": (
                {"active": 0.4, "expired": 0.3, "revoked": 0.2, "withdrawn": 0.1} if high_count >= 1
                else {"active": 0.9, "expired": 0.05, "revoked": 0.03, "withdrawn": 0.02}
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
            "shared_with_third_party": False,
            "is_cross_border": False,
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
                {"expired": 0.6, "active": 0.3, "pending_deletion": 0.1} if high_count >= 2
                else {"active": 0.85, "expired": 0.1, "pending_deletion": 0.05}
            ),
            "purpose_completed": {"false": 0.6, "true": 0.4},
            "legal_hold_flag": False,
            "erasure_requested": {"false": 0.85, "true": 0.15},
            "data_category": {"kyc_documents": 0.4, "transaction_history": 0.3, "credit_score": 0.2, "contact_info": 0.1},
        },
        "security_events": {
            "breach_detected": False,
            "pii_encrypted": {"false": 1.0} if critical_trigger else {"true": 0.9, "false": 0.1},
            "encryption_type_when_encrypted_false": "md5",
            "encryption_type_when_encrypted_true": "AES-256",
        },
        "dsar_requests": {
            "request_type": {"erasure": 0.4, "access": 0.4, "correction": 0.2},
            "sla_breached": {"false": 0.7, "true": 0.3},
            "fulfillment_status": {"pending": 0.3, "fulfilled": 0.5, "partially_fulfilled": 0.2},
        },
        "customer_master": {
            "is_minor": False,
            "data_principal_type": "individual",
            "account_status": {"active": 0.85, "dormant": 0.1, "closed": 0.05},
            "kyc_status": {"verified": 0.8, "pending": 0.15, "expired": 0.05},
        },
        "policies": {
            "policy_type": {"retention": 0.3, "consent": 0.3, "encryption": 0.2, "access_control": 0.2},
            "is_active": True,
            "policy_value_unit": "days",
        },
    }
    return fd


def build_profiles():
    profiles = []
    tid_counter = 401

    # Group A: 13 tenants, exactly-1-critical (DPDP-008), varying noise level
    # so pre-floor score sometimes clears 65 and sometimes sits under it.
    for i, noise in enumerate([0, 1, 1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4]):
        fd = base_field_distributions(critical_trigger=True, high_count=min(noise, 3))
        profiles.append({
            "tenant_id": f"GEN-{tid_counter}",
            "profile_name": f"boundary_critical_floor_{i+1}",
            "record_counts": dict(RECORD_COUNTS),
            "field_distributions": fd,
            "_target": "65-boundary",
        })
        tid_counter += 1

    # Group B: 12 tenants, no critical trigger, HIGH-rule count deliberately
    # varied 0-3 to straddle the 45-floor boundary (3+ HIGH -> floor).
    for i, hc in enumerate([0, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3]):
        fd = base_field_distributions(critical_trigger=False, high_count=hc)
        profiles.append({
            "tenant_id": f"GEN-{tid_counter}",
            "profile_name": f"boundary_high_floor_{i+1}_hc{hc}",
            "record_counts": dict(RECORD_COUNTS),
            "field_distributions": fd,
            "_target": "45-boundary",
        })
        tid_counter += 1

    return profiles


def main():
    profiles = build_profiles()
    print(f"Generating {len(profiles)} boundary-targeted pilot tenants "
          f"(GEN-401 to GEN-{400+len(profiles)})\n")

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
    print(f"PILOT BATCH COMPLETE: {len(results)} tenants in {t_total:.1f}s")
    print(f"Average per tenant : {avg:.2f}s")
    print(f"Extrapolated for 1000 tenants: {avg*1000/60:.1f} minutes ({avg*1000/3600:.2f} hours)")
    print("=" * 60)

    with open("phase4_pilot_report.json", "w") as f:
        json.dump({
            "n_tenants": len(results),
            "total_seconds": round(t_total, 2),
            "avg_seconds_per_tenant": round(avg, 3),
            "extrapolated_1000_tenants_minutes": round(avg * 1000 / 60, 1),
            "results": results,
        }, f, indent=2)
    print("\n[OK] Report written to phase4_pilot_report.json")


if __name__ == "__main__":
    main()
