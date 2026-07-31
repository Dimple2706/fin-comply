import json

def get_base_record_counts():
    return {
        "n_customers": 60,
        "n_consent_records": 70,
        "n_transaction_events": 160,
        "n_access_logs": 109,
        "n_data_lifecycle": 80,
        "n_security_events": 15,
        "n_dsar_requests": 20,
        "n_system_inventory": 12,
        "n_policies": 10,
        "n_governance_configs": 1
    }

def get_base_field_distributions():
    return {
        "governance_config": {
            "dpo_assigned": True,
            "grievance_endpoint_available": True,
            "last_audit_date": "2026-07-01",
            "audit_frequency_days": 30,
            "risk_level": "LOW"
        },
        "system_inventory": {
            "encryption_type": "AES-256",
            "pii_stored": True,
            "encryption_enabled": True,
            "dpa_signed": True,
            "data_processor_type": "internal",
            "access_control_enabled": True,
            "retention_policy_applied": True
        },
        "consent_records": {
            "consent_status": { "active": 1.0 },
            "notice_provided": True,
            "is_bundled": False,
            "consent_channel": { "app": 0.5, "web": 0.5 },
            "consented_purpose": { "loan_processing": 0.5, "account_management": 0.5 },
            "guardian_consent_hash": "null"
        },
        "transaction_events": {
            "event_type": { "loan_disbursal": 0.5, "emi_collection": 0.5 },
            "processing_purpose": { "loan_processing": 0.5, "account_management": 0.5 },
            "shared_with_third_party": False,
            "is_cross_border": False
        },
        "access_logs": {
            "employee_role": { "underwriter": 0.5, "manager": 0.5 },
            "accessed_pii": { "false": 1.0 },
            "data_volume_accessed": { "low": 1.0 },
            "access_reason": { "loan_review": 1.0 },
            "access_outcome": { "granted": 1.0 }
        },
        "data_lifecycle": {
            "retention_status": { "active": 1.0 },
            "purpose_completed": { "false": 1.0 },
            "legal_hold_flag": False,
            "erasure_requested": False,
            "data_category": { "transaction_history": 1.0 }
        },
        "security_events": {
            "breach_detected": False,
            "pii_encrypted": True,
            "encryption_type_when_encrypted_true": "AES-256"
        },
        "dsar_requests": {
            "request_type": { "access": 1.0 },
            "sla_breached": False,
            "fulfillment_status": { "fulfilled": 1.0 }
        },
        "customer_master": {
            "is_minor": False,
            "data_principal_type": "individual",
            "account_status": { "active": 1.0 },
            "kyc_status": { "verified": 1.0 }
        },
        "policies": {
            "policy_type": { "access_control": 1.0 },
            "is_active": True,
            "policy_value_unit": "days"
        }
    }

configs = []
for i in range(26, 251):
    tenant_id = f"GEN-{i:03d}"
    profile = {
        "tenant_id": tenant_id,
        "record_counts": get_base_record_counts(),
        "field_distributions": get_base_field_distributions()
    }
    
    if 26 <= i <= 75:
        # COMPLIANT (0 Cr)
        profile["profile_name"] = f"compliant_fintech_{i}"
        profile["description"] = "A highly compliant company."
        # Keep defaults
        
    elif 76 <= i <= 125:
        # LOW (1-300 Cr)
        profile["profile_name"] = f"low_risk_fintech_{i}"
        profile["description"] = "Low risk with minor policy misses."
        fd = profile["field_distributions"]
        fd["governance_config"]["grievance_endpoint_available"] = False # DPDP-009: 10
        fd["governance_config"]["last_audit_date"] = "2025-01-01" # DPDP-012: 50
        fd["consent_records"]["notice_provided"] = { "false": 0.1, "true": 0.9 } # DPDP-004: 50
        fd["policies"]["policy_type"] = { "retention": 1.0 }
        fd["policies"]["is_active"] = False # POLICY-001: 50
        # Total: 160 Cr

    elif 126 <= i <= 175:
        # MEDIUM (301-750 Cr)
        profile["profile_name"] = f"medium_risk_fintech_{i}"
        profile["description"] = "Medium risk with processor issues."
        fd = profile["field_distributions"]
        fd["system_inventory"]["data_processor_type"] = { "third_party_processor": 1.0 }
        fd["system_inventory"]["dpa_signed"] = { "false": 1.0 } # DPDP-016: 250
        fd["governance_config"]["last_audit_date"] = "2025-01-01" # DPDP-012: 50
        fd["governance_config"]["grievance_endpoint_available"] = False # DPDP-009: 10
        # Total: 310 Cr

    elif 176 <= i <= 213:
        # HIGH (751-1500 Cr)
        profile["profile_name"] = f"high_risk_fintech_{i}"
        profile["description"] = "High risk with minor data."
        fd = profile["field_distributions"]
        fd["customer_master"]["is_minor"] = True # DPDP-005: 250
        fd["system_inventory"]["data_processor_type"] = { "third_party_processor": 1.0 }
        fd["system_inventory"]["dpa_signed"] = { "false": 1.0 } # DPDP-016: 250
        fd["data_lifecycle"]["retention_status"] = { "expired": 1.0 }
        fd["data_lifecycle"]["purpose_completed"] = { "true": 1.0 } # DPDP-011: 200
        fd["governance_config"]["last_audit_date"] = "2025-01-01" # DPDP-012: 50
        fd["governance_config"]["grievance_endpoint_available"] = False # DPDP-009: 10
        # Total: 760 Cr

    elif 214 <= i <= 250:
        # CRITICAL (>1500 Cr)
        profile["profile_name"] = f"critical_risk_fintech_{i}"
        profile["description"] = "Critical risk with breaches and purpose mismatch."
        fd = profile["field_distributions"]
        fd["customer_master"]["is_minor"] = True # DPDP-005: 250
        
        fd["security_events"]["breach_detected"] = { "true": 1.0 }
        fd["security_events"]["breach_rows"] = {
            "notification_delay_hours": 96,
            "affected_user_count": "large",
            "pii_encrypted": False
        } # DPDP-014: 250
        
        fd["system_inventory"]["data_processor_type"] = { "third_party_processor": 1.0 }
        fd["system_inventory"]["dpa_signed"] = { "false": 1.0 } # DPDP-016: 250
        
        fd["security_events"]["pii_encrypted"] = { "false": 1.0 } # DPDP-008: 250
        
        fd["transaction_events"]["processing_purpose"] = { "fraud_detection": 1.0 }
        fd["consent_records"]["consented_purpose"] = { "loan_processing": 1.0 } # DPDP-002: 250
        
        fd["data_lifecycle"]["retention_status"] = { "expired": 1.0 }
        fd["data_lifecycle"]["purpose_completed"] = { "true": 1.0 }
        fd["data_lifecycle"]["legal_hold_flag"] = False # DPDP-003: 200
        
        fd["governance_config"]["last_audit_date"] = "2025-01-01" # DPDP-012: 50
        fd["governance_config"]["grievance_endpoint_available"] = False # DPDP-009: 10
        # Total: 1510 Cr

    configs.append(profile)

with open("data/generator_config.json", "r") as f:
    data = json.load(f)

# Ensure only 25 configs are there initially
data = data[:25]
data.extend(configs)

with open("data/generator_config.json", "w") as f:
    json.dump(data, f, indent=2)

print("Generated and appended 225 profiles successfully.")
