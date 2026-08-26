import os
import json
from pathlib import Path

FIXTURE_DIR = Path("tests/fixtures/deterministic_compliance_package")

# Common compliant templates
GOV_HEADER = "tenant_id,tenant_name,grievance_endpoint_available,dpo_assigned,dpo_contact_masked,audit_frequency_days,last_audit_date,risk_level\n"
CUST_HEADER = "customer_id,tenant_id,is_minor,data_principal_type,account_status,kyc_status,country,created_at\n"
CONSENT_HEADER = "consent_id,customer_id,tenant_id,consent_status,consented_purpose,notice_provided,is_bundled,consent_channel,guardian_consent_id,consent_date,expiry_date,third_party_sharing_permitted\n"
SYSTEM_HEADER = "system_id,tenant_id,system_name,system_type,pii_stored,encryption_enabled,access_control_enabled,data_processor_type,retention_policy_applied,dpa_signed,dpa_expiry_date\n"
TX_HEADER = "event_id,customer_id,tenant_id,consent_id,event_type,processing_purpose,event_date,shared_with_third_party,third_party_id,is_cross_border,transfer_country\n"
ACCESS_HEADER = "access_id,customer_id,tenant_id,employee_id,employee_role,accessed_pii,pii_fields_accessed,access_reason,access_outcome,data_volume_accessed,access_date,pii_fields_justified\n"
LIFECYCLE_HEADER = "lifecycle_id,customer_id,tenant_id,data_category,retention_expiry_date,retention_status,purpose_completed,erasure_requested,erasure_date,legal_hold_flag,erasure_request_source\n"
SECURITY_HEADER = "security_id,customer_id,tenant_id,pii_encrypted,encryption_type,breach_detected,breach_confirmed_date,notification_delay_hours,affected_user_count,data_categories_breached,security_audit_flag\n"
DSAR_HEADER = "dsar_id,customer_id,tenant_id,request_type,submitted_date,acknowledged_date,sla_due_date,sla_breached,fulfilled_date,fulfillment_status,rejection_reason\n"
POLICIES_HEADER = "policy_id,tenant_id,policy_type,policy_name,policy_value_numeric,policy_value_unit,effective_date,last_updated,is_active,policy_value_text\n"

def get_clean_tenant_files(tenant_id):
    files = {
        "governance_config.csv": GOV_HEADER + f"{tenant_id},Clean Tenant,True,True,dpo@test.local,90,2026-08-01,MEDIUM\n",
        "customer_master.csv": CUST_HEADER + f"C1,{tenant_id},False,individual,active,verified,IN,2026-08-01\n",
        "consent_records.csv": CONSENT_HEADER + f"CON1,C1,{tenant_id},granted,marketing,True,False,web,,2026-08-01,2027-08-01,True\n",
        "system_inventory.csv": SYSTEM_HEADER + f"SYS1,{tenant_id},CRM,crm,True,True,True,internal,True,True,\n",
        "transaction_events.csv": TX_HEADER + f"TX1,C1,{tenant_id},CON1,marketing_push,marketing,2026-08-15,True,SYS1,False,\n",
        "access_logs.csv": ACCESS_HEADER + f"ACC1,C1,{tenant_id},E1,compliance_officer,True,name,loan_review,granted,low,2026-08-02,True\n",
        "data_lifecycle.csv": LIFECYCLE_HEADER,
        "security_events.csv": SECURITY_HEADER + f"SEC1,C1,{tenant_id},True,AES-256,False,,,0,,False\n",
        "dsar_requests.csv": DSAR_HEADER + f"DS1,C1,{tenant_id},access,2026-08-01,2026-08-02,2026-08-31,False,,pending,\n",
        "policies.csv": POLICIES_HEADER + f"P1,{tenant_id},retention,Retention Policy,365,days,2026-08-01,2026-08-01,True,\n"
    }
    return files

def generate_fixtures():
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Clean tenant: t_clean
    t_clean_dir = FIXTURE_DIR / "t_clean"
    t_clean_dir.mkdir(exist_ok=True)
    clean_files = get_clean_tenant_files("t_clean")
    for fname, content in clean_files.items():
        with open(t_clean_dir / fname, "w", encoding="utf-8") as f:
            f.write(content)
            
    # 2. DPDP violation tenants
    for rule_num in range(1, 17):
        tenant_id = f"t_dpdp{rule_num:03d}"
        tenant_dir = FIXTURE_DIR / tenant_id
        tenant_dir.mkdir(exist_ok=True)
        files = get_clean_tenant_files(tenant_id)
        
        # Inject rule-specific violation evidence
        if rule_num == 1:
            # DPDP-001: Expired consent status
            files["consent_records.csv"] = CONSENT_HEADER + f"CON1,C1,{tenant_id},expired,marketing,True,False,web,,2026-08-01,2027-08-01,True\n"
        elif rule_num == 2:
            # DPDP-002: Purpose mismatch between consent and transaction
            files["transaction_events.csv"] = TX_HEADER + f"TX1,C1,{tenant_id},CON1,marketing_push,loan_processing,2026-08-15,True,SYS1,False,\n"
        elif rule_num == 3:
            # DPDP-003: Past retention expiry date without legal hold
            files["data_lifecycle.csv"] = LIFECYCLE_HEADER + f"L1,C1,{tenant_id},kyc_documents,2025-08-01,active,False,False,,False,\n"
        elif rule_num == 4:
            # DPDP-004: Notice provided is False
            files["consent_records.csv"] = CONSENT_HEADER + f"CON1,C1,{tenant_id},granted,marketing,False,False,web,,2026-08-01,2027-08-01,True\n"
        elif rule_num == 5:
            # DPDP-005: Minor without guardian consent
            files["customer_master.csv"] = CUST_HEADER + f"C1,{tenant_id},True,individual,active,verified,IN,2026-08-01\n"
            files["consent_records.csv"] = CONSENT_HEADER + f"CON1,C1,{tenant_id},granted,marketing,True,False,web,,2026-08-01,2027-08-01,True\n"
        elif rule_num == 6:
            # DPDP-006: DPA not signed
            files["system_inventory.csv"] = SYSTEM_HEADER + f"SYS1,{tenant_id},CRM,crm,True,True,True,third_party_processor,True,False,\n"
        elif rule_num == 7:
            # DPDP-007: Bulk PII access without justification
            files["access_logs.csv"] = ACCESS_HEADER + f"ACC1,C1,{tenant_id},E1,collections_agent,True,name,loan_review,granted,bulk,2026-08-02,False\n"
        elif rule_num == 8:
            # DPDP-008: Security breach on unencrypted data
            files["security_events.csv"] = SECURITY_HEADER + f"SEC1,C1,{tenant_id},False,none,True,2026-08-23,24,100,kyc_documents,False\n"
        elif rule_num == 9:
            # DPDP-009: DPO not assigned
            files["governance_config.csv"] = GOV_HEADER + f"{tenant_id},Violation Tenant 9,True,False,,90,2026-08-01,MEDIUM\n"
        elif rule_num == 10:
            # DPDP-010: Erasure request SLA breached and status active
            files["dsar_requests.csv"] = DSAR_HEADER + f"DS1,C1,{tenant_id},erasure,2026-08-01,2026-08-02,2026-08-31,True,,pending,\n"
            files["data_lifecycle.csv"] = LIFECYCLE_HEADER + f"L1,C1,{tenant_id},kyc_documents,2027-08-01,active,False,False,,False,\n"
        elif rule_num == 11:
            # DPDP-011: Purpose completed, not deleted, and no legal hold
            files["data_lifecycle.csv"] = LIFECYCLE_HEADER + f"L1,C1,{tenant_id},kyc_documents,2027-08-01,active,True,False,,False,\n"
        elif rule_num == 12:
            # DPDP-012: Overdue audit (last audit date > audit frequency)
            files["governance_config.csv"] = GOV_HEADER + f"{tenant_id},Violation Tenant 12,True,True,dpo@test.local,90,2025-08-01,MEDIUM\n"
        elif rule_num == 13:
            # DPDP-013: Unauthorized employee role accessing PII
            files["access_logs.csv"] = ACCESS_HEADER + f"ACC1,C1,{tenant_id},E1,collections_agent,True,name,loan_review,granted,low,2026-08-02,True\n"
        elif rule_num == 14:
            # DPDP-014: Security breach notification delayed > 72 hours
            files["security_events.csv"] = SECURITY_HEADER + f"SEC1,C1,{tenant_id},True,AES-256,True,2026-08-20,80,100,kyc_documents,False\n"
        elif rule_num == 15:
            # DPDP-015: Destination country not approved (unapproved US)
            files["transaction_events.csv"] = TX_HEADER + f"TX1,C1,{tenant_id},CON1,marketing_push,marketing,2026-08-15,True,SYS1,True,US\n"
            files["system_inventory.csv"] = SYSTEM_HEADER + f"SYS1,{tenant_id},CRM,crm,True,True,True,third_party_processor,True,True,2027-08-01\n"


        elif rule_num == 16:
            # DPDP-016: DPA expired for processor system
            files["system_inventory.csv"] = SYSTEM_HEADER + f"SYS1,{tenant_id},CRM,crm,True,True,True,third_party_processor,True,True,2025-08-01\n"
        for fname, content in files.items():
            with open(tenant_dir / fname, "w", encoding="utf-8") as f:
                f.write(content)

    # 3. Create expected_results.json manifest
    manifest = {
        "t_clean": {
            "violations_count": 0,
            "risk_score": 0.0,
            "failed_rules_count": 0,
            "statutory_exposure_crore": 0.0
        }
    }
    for rule_num in range(1, 17):
        rule_id = f"DPDP-{rule_num:03d}"
        tenant_id = f"t_dpdp{rule_num:03d}"
        manifest[tenant_id] = {
            "violations_count": 1,
            "failed_rules_count": 1,
            "target_violated_rule": rule_id
        }
        
    with open(FIXTURE_DIR / "expected_results.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)

    # 4. Create README.md
    readme_text = """# Deterministic Compliance Fixtures Package

This package contains ground truth test-data profiles for compliance scoring validation under Section 12 requirements.

## Scenarios
- `t_clean`: One genuinely clean tenant with zero violations.
- `t_dpdp001` - `t_dpdp016`: Individual tenants containing exactly one target violation for their corresponding DPDP rule.
"""
    with open(FIXTURE_DIR / "README.md", "w", encoding="utf-8") as f:
        f.write(readme_text)

    print("Deterministic compliance fixtures package generated successfully.")

if __name__ == "__main__":
    generate_fixtures()
