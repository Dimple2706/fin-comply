"""
Phase 4 diversification, Step 3: targeted top-up for genuine COMPLIANT and
CRITICAL tenants -- the two tiers the full 1,000-tenant batch produced zero
of (COMPLIANT tenants drifted to LOW/MEDIUM from residual background noise;
CRITICAL tenants capped at the HIGH/65 floor without a second simultaneous
critical rule to push past it).

COMPLIANT (100 tenants): every field that carries any "bad" probability at
all is locked fully deterministic-clean (0%), not just the HIGH/CRITICAL
gates -- confirmed necessary since even 5-50% background noise in fields
like notice_provided/bundling/SLA/access occasionally accumulated enough to
cross into MEDIUM.

CRITICAL (100 tenants): stacks three simultaneous CRITICAL-severity rules
rather than relying on the floor from just one:
  - DPDP-008 (security_events.pii_encrypted = false) -- proven reliable.
  - DPDP-014 (security_events.breach_detected = True) -- breach_confirmed_at
    auto-populates and notification_delay_hours defaults to 100h (>72h
    threshold), so this alone guarantees a VIOLATION with no extra config.
  - DPDP-005 (customer_master.is_minor = True, combined with the
    guardian_consent_hash="null" already present in every profile's
    consent_records block) -- no valid guardian consent, guaranteed VIOLATION.
Plus every HIGH-rule gate also switched on, for maximum accumulated severity.

New tenant IDs continue from GEN-1486 (after the 1,000-tenant batch,
GEN-486 through GEN-1485).
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


def compliant_field_distributions() -> dict:
    return {
        "governance_config": {
            "dpo_assigned": True, "grievance_endpoint_available": True,
            "last_audit_date": "2025-06-01", "audit_frequency_days": 90,
            "risk_level": "LOW",
        },
        "system_inventory": {
            "encryption_type": {"AES-256": 1.0},
            "pii_stored": {"true": 0.5, "false": 0.5},
            "encryption_enabled": True,
            "dpa_signed": True,
            "data_processor_type": "internal",  # sidesteps DPDP-016 entirely
            "access_control_enabled": True,
            "retention_policy_applied": True,
        },
        "consent_records": {
            "consent_status": "active",
            "notice_provided": True,
            "is_bundled": False,
            "consent_channel": {"app": 0.6, "web": 0.4},
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
            "accessed_pii": False,
            "data_volume_accessed": "low",
            "access_reason": {"support_query": 0.4, "kyc_check": 0.3, "data_export": 0.2, "loan_review": 0.1},
            "access_outcome": "granted",
        },
        "data_lifecycle": {
            "retention_status": "active",
            "purpose_completed": False,
            "legal_hold_flag": False,
            "erasure_requested": False,
            "data_category": {"kyc_documents": 0.4, "transaction_history": 0.3, "credit_score": 0.2, "contact_info": 0.1},
        },
        "security_events": {
            "breach_detected": False,
            "pii_encrypted": True,
            "encryption_type_when_encrypted_true": "AES-256",
        },
        "dsar_requests": {
            "request_type": {"erasure": 0.4, "access": 0.4, "correction": 0.2},
            "sla_breached": False,
            "fulfillment_status": "fulfilled",
        },
        "customer_master": {
            "is_minor": False, "data_principal_type": "individual",
            "account_status": "active", "kyc_status": "verified",
        },
        "policies": {
            "policy_type": {"retention": 0.3, "consent": 0.3, "encryption": 0.2, "access_control": 0.2},
            "is_active": True, "policy_value_unit": "days",
        },
    }


def critical_field_distributions() -> dict:
    return {
        "governance_config": {
            "dpo_assigned": False, "grievance_endpoint_available": False,
            "last_audit_date": "2023-11-01", "audit_frequency_days": 400,
            "risk_level": "CRITICAL",
            # DPDP-012: SDF with no DPO + >365-day audit cadence -> VIOLATION
            "is_significant_data_fiduciary": True,
        },
        "system_inventory": {
            "encryption_type": {"md5": 1.0},
            "pii_stored": {"true": 1.0},
            "encryption_enabled": True,
            "dpa_signed": {"false": 0.95, "true": 0.05},
            "data_processor_type": {"third_party_processor": 0.7, "sub_processor": 0.2, "internal": 0.1},
            "access_control_enabled": False,
            "retention_policy_applied": False,
        },
        "consent_records": {
            "consent_status": {"expired": 0.5, "revoked": 0.3, "withdrawn": 0.2},
            "notice_provided": {"false": 0.7, "true": 0.3},
            "is_bundled": {"true": 0.6, "false": 0.4},
            "consent_channel": {"implicit": 0.5, "pre_ticked": 0.3, "app": 0.2},
            "consented_purpose": {"loan_processing": 0.6, "account_management": 0.2, "kyc_verification": 0.2},
            "guardian_consent_hash": "null",  # combined with is_minor=True below -> DPDP-005 VIOLATION
        },
        "transaction_events": {
            "event_type": {"credit_check": 0.3, "loan_disbursal": 0.3, "emi_collection": 0.2, "account_update": 0.2},
            "processing_purpose": {"loan_processing": 0.6, "account_management": 0.2, "kyc_verification": 0.2},
            "shared_with_third_party": True, "is_cross_border": True,
            # DPDP-015: cross-border transfer explicitly non-compliant -> VIOLATION
            "transfer_restriction_compliant": False,
        },
        "access_logs": {
            "employee_role": {"customer_support": 0.4, "data_analyst": 0.3, "compliance_officer": 0.2, "engineer": 0.1},
            "unauthorised_role_pct": 0.9,
            "accessed_pii_when_unauthorised": True,
            "accessed_pii_when_authorised": True,
            "data_volume_accessed_when_unauthorised": "high",
            "data_volume_accessed_when_authorised": "high",
            "access_reason": {"support_query": 0.4, "kyc_check": 0.3, "data_export": 0.2, "loan_review": 0.1},
            "access_outcome": "granted",
            # DPDP-007/DPDP-013: unauthorised-role PII access, not justified,
            # not authorized -> both VIOLATION.
            "pii_fields_justified_when_unauthorised": False,
            "access_authorized_when_unauthorised": False,
            "pii_fields_justified_when_authorised": False,
            "access_authorized_when_authorised": False,
        },
        "data_lifecycle": {
            "retention_status": "expired",
            "purpose_completed": True,
            "legal_hold_flag": False,
            "erasure_requested": {"true": 0.5, "false": 0.5},
            "data_category": {"kyc_documents": 0.4, "transaction_history": 0.3, "credit_score": 0.2, "contact_info": 0.1},
        },
        "security_events": {
            "breach_detected": True,          # DPDP-014: auto-guaranteed VIOLATION
            "pii_encrypted": False,           # DPDP-008: guaranteed VIOLATION
            "encryption_type_when_encrypted_false": "md5",
            # DPDP-014 signal S4 needs the literal string "large"/"critical",
            # not a number -- the generator's numeric default (100) can never
            # satisfy this signal, so it was silently unfireable before.
            "breach_rows": {"affected_user_count": "critical", "notification_delay_hours": 240},
        },
        "dsar_requests": {
            "request_type": {"erasure": 0.4, "access": 0.4, "correction": 0.2},
            "sla_breached": True,
            "fulfillment_status": "pending",
        },
        "customer_master": {
            "is_minor": True,                 # DPDP-005: guaranteed VIOLATION (no guardian consent above)
            "data_principal_type": "minor",
            "account_status": {"active": 0.7, "dormant": 0.3},
            "kyc_status": {"pending": 0.5, "expired": 0.3, "verified": 0.2},
        },
        "policies": {
            "policy_type": {"retention": 0.3, "consent": 0.3, "encryption": 0.2, "access_control": 0.2},
            "is_active": False,
            "policy_value_unit": "days",
        },
    }


def build_profiles(n_compliant: int, start_id: int, n_critical: int = None):
    if n_critical is None:
        n_critical = n_compliant
    profiles = []
    tid = start_id
    for i in range(n_compliant):
        profiles.append({
            "tenant_id": f"GEN-{tid}", "profile_name": f"topup_compliant_{tid}",
            "record_counts": dict(RECORD_COUNTS),
            "field_distributions": compliant_field_distributions(),
            "_target_tier": "COMPLIANT",
        })
        tid += 1
    for i in range(n_critical):
        profiles.append({
            "tenant_id": f"GEN-{tid}", "profile_name": f"topup_critical_{tid}",
            "record_counts": dict(RECORD_COUNTS),
            "field_distributions": critical_field_distributions(),
            "_target_tier": "CRITICAL",
        })
        tid += 1
    return profiles


def run_batch(profiles, report_path):
    results = []
    t0_all = time.perf_counter()
    n_ok, n_fail = 0, 0
    for idx, p in enumerate(profiles, 1):
        t0 = time.perf_counter()
        try:
            report = process_profile({k: v for k, v in p.items() if not k.startswith("_")})
            report["_target_tier"] = p["_target_tier"]
            report["_elapsed_sec"] = round(time.perf_counter() - t0, 2)
            results.append(report)
            n_ok += 1
        except Exception as e:
            results.append({"tenant_id": p["tenant_id"], "status": "error", "error": str(e),
                             "_target_tier": p["_target_tier"], "_elapsed_sec": round(time.perf_counter() - t0, 2)})
            n_fail += 1
        if idx % 20 == 0 or idx == len(profiles):
            el = time.perf_counter() - t0_all
            print(f"[{idx}/{len(profiles)}] ok={n_ok} fail={n_fail} elapsed={el/60:.1f}min", flush=True)

    print(f"\nBATCH COMPLETE: {n_ok}/{len(profiles)} ok in {(time.perf_counter()-t0_all)/60:.1f} min")
    with open(report_path, "w") as f:
        json.dump({"n_ok": n_ok, "n_fail": n_fail, "results": results}, f, indent=2)
    print(f"[OK] Report written to {report_path}")
    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n_compliant", type=int, default=150)
    ap.add_argument("--n_critical", type=int, default=200)
    ap.add_argument("--start_id", type=int, default=1486)
    ap.add_argument("--report", type=str, default="phase4_topup_report.json")
    args = ap.parse_args()
    profiles = build_profiles(args.n_compliant, args.start_id, args.n_critical)
    print(f"Generating {len(profiles)} top-up tenants "
          f"({args.n_compliant} COMPLIANT, {args.n_critical} CRITICAL), starting GEN-{args.start_id}")
    run_batch(profiles, args.report)
