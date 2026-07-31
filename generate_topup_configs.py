import json
import random

def create_topup_configs():
    with open("data/generator_config.json", "r") as f:
        existing = json.load(f)

    start_id = 251
    new_profiles = []

    # 1. Generate 10 COMPLIANT
    for _ in range(10):
        tenant_id = f"GEN-{start_id:03d}"
        start_id += 1
        p = {
            "tenant_id": tenant_id,
            "profile_name": f"topup_compliant_{tenant_id}",
            "expected_risk_tier": "COMPLIANT",
            "record_counts": {
                "n_customers": 50, "n_consent_records": 50, "n_transaction_events": 100,
                "n_access_logs": 50, "n_data_lifecycle": 50, "n_security_events": 5,
                "n_dsar_requests": 5, "n_system_inventory": 5, "n_policies": 5, "n_governance_configs": 1
            },
            "field_distributions": {
                "governance_config": {
                    "dpo_assigned": True, "grievance_endpoint_available": True,
                    "last_audit_date": "2026-07-01", "risk_level": "LOW"
                },
                "system_inventory": {
                    "pii_stored": True, "encryption_enabled": True, "dpa_signed": True,
                    "access_control_enabled": True, "retention_policy_applied": True
                },
                "customer_master": {
                    "is_minor": { "false": 1.0 },
                    "kyc_status": { "verified": 1.0 }
                },
                "consent_records": {
                    "consent_status": { "active": 1.0 },
                    "notice_provided": True,
                    "consented_purpose": { "account_management": 1.0 }
                },
                "transaction_events": {
                    "processing_purpose": { "account_management": 1.0 },
                    "shared_with_third_party": False,
                    "is_cross_border": False
                },
                "data_lifecycle": {
                    "retention_status": { "active": 1.0 },
                    "purpose_completed": { "false": 1.0 }
                }
            }
        }
        new_profiles.append(p)

    # 2. Generate 5 HIGH
    for _ in range(5):
        tenant_id = f"GEN-{start_id:03d}"
        start_id += 1
        p = {
            "tenant_id": tenant_id,
            "profile_name": f"topup_high_{tenant_id}",
            "expected_risk_tier": "HIGH",
            "record_counts": {
                "n_customers": 50, "n_consent_records": 50, "n_transaction_events": 100,
                "n_access_logs": 50, "n_data_lifecycle": 50, "n_security_events": 5,
                "n_dsar_requests": 5, "n_system_inventory": 5, "n_policies": 5, "n_governance_configs": 1
            },
            "field_distributions": {
                "governance_config": {
                    "dpo_assigned": False, "grievance_endpoint_available": False,
                    "last_audit_date": "2021-01-01", "risk_level": "HIGH"
                },
                "system_inventory": {
                    "pii_stored": True, "encryption_enabled": True, "dpa_signed": False,
                    "access_control_enabled": True, "retention_policy_applied": False
                },
                "customer_master": {
                    "is_minor": { "false": 1.0 },
                    "kyc_status": { "verified": 1.0 }
                },
                "consent_records": {
                    "consent_status": { "active": 1.0 },
                    "notice_provided": False,
                    "consented_purpose": { "account_management": 1.0 }
                },
                "transaction_events": {
                    "processing_purpose": { "marketing": 1.0 },
                    "shared_with_third_party": True,
                    "is_cross_border": False
                },
                "data_lifecycle": {
                    "retention_status": { "active": 1.0 },
                    "purpose_completed": { "true": 1.0 }
                }
            }
        }
        new_profiles.append(p)

    # 3. Generate 50 CRITICAL (Absolutely terrible compliance)
    for _ in range(50):
        tenant_id = f"GEN-{start_id:03d}"
        start_id += 1
        p = {
            "tenant_id": tenant_id,
            "profile_name": f"topup_critical_{tenant_id}",
            "expected_risk_tier": "CRITICAL",
            "record_counts": {
                "n_customers": 50, "n_consent_records": 50, "n_transaction_events": 100,
                "n_access_logs": 50, "n_data_lifecycle": 50, "n_security_events": 5,
                "n_dsar_requests": 5, "n_system_inventory": 5, "n_policies": 5, "n_governance_configs": 1
            },
            "field_distributions": {
                "governance_config": {
                    "dpo_assigned": False, "grievance_endpoint_available": False,
                    "last_audit_date": "2018-01-01", "risk_level": "CRITICAL"
                },
                "system_inventory": {
                    "pii_stored": True, "encryption_enabled": False, "dpa_signed": False,
                    "access_control_enabled": False, "retention_policy_applied": False,
                    "data_processor_type": "external"
                },
                "customer_master": {
                    "is_minor": { "true": 1.0 },
                    "kyc_status": { "rejected": 0.5, "verified": 0.5 }
                },
                "consent_records": {
                    "consent_status": { "withdrawn": 1.0 },
                    "notice_provided": False,
                    "is_bundled": True,
                    "guardian_consent_hash": "null",
                    "consented_purpose": { "account_management": 1.0 }
                },
                "transaction_events": {
                    "processing_purpose": { "marketing": 1.0, "data_brokering": 1.0 },
                    "shared_with_third_party": True,
                    "is_cross_border": True
                },
                "data_lifecycle": {
                    "retention_status": { "active": 1.0 },
                    "purpose_completed": { "true": 1.0 },
                    "erasure_requested": True
                }
            }
        }
        new_profiles.append(p)

    existing.extend(new_profiles)
    with open("data/generator_config.json", "w") as f:
        json.dump(existing, f, indent=2)
        
    print(f"Generated {len(new_profiles)} new profiles (GEN-251 to GEN-{start_id-1})")

if __name__ == "__main__":
    create_topup_configs()
