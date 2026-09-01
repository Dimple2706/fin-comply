from datetime import date, datetime
from datetime import date, datetime
from typing import List, Tuple
from .result_state import RuleOutcome


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        return None


def _as_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "1", "yes", "y"}:
        return True
    if normalized in {"false", "f", "0", "no", "n"}:
        return False
    return None

def determine_row_outcome(rule_id: str, row: dict, signals_fired: List[str], signals: List[dict], v_threshold: float, r_threshold: float) -> Tuple[RuleOutcome, str]:
    """
    Determine the explicit rule outcome state for a single row.
    Returns (RuleOutcome, reason_text).
    """
    
    # 1. DPDP-001
    if rule_id == "DPDP-001":
        consent_status = row.get("consent_status")
        event_date = _as_date(row.get("event_date"))
        expiry_date = _as_date(row.get("expiry_date"))
        if consent_status is None or event_date is None or expiry_date is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing consent status, processing date, or consent-expiry evidence"
        if str(consent_status).lower() not in {"active", "granted"}:
            return RuleOutcome.VIOLATION, "Processing used consent that was not active or granted"
        if expiry_date < event_date:
            return RuleOutcome.VIOLATION, "Processing occurred after the evidenced consent expiry date"
        return RuleOutcome.PASS, "Processing occurred under active, unexpired consent"
        
    # 2. DPDP-002
    elif rule_id == "DPDP-002":
        consented_purpose = row.get("consented_purpose")
        processing_purpose = row.get("processing_purpose")
        if consented_purpose is None or processing_purpose is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing consented-purpose or processing-purpose evidence"
        if str(consented_purpose).strip().lower() != str(processing_purpose).strip().lower():
            return RuleOutcome.VIOLATION, "Processing purpose differs from the purpose evidenced by consent"
        return RuleOutcome.PASS, "Processing purpose matches the consented purpose"
            
    # 3. DPDP-003
    elif rule_id == "DPDP-003":
        expiry_date = _as_date(row.get("retention_expiry_date"))
        retention_status = row.get("retention_status")
        legal_hold = _as_bool(row.get("legal_hold_flag"))
        if expiry_date is None or retention_status is None or legal_hold is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing retention-expiry, status, or legal-hold evidence"
        if legal_hold:
            return RuleOutcome.PASS, "Continued retention is supported by an evidenced legal hold"
        if str(retention_status).lower() == "deleted":
            return RuleOutcome.PASS, "Data is recorded as deleted"
        if expiry_date < date.today():
            return RuleOutcome.VIOLATION, "Data remains retained after its evidenced retention-expiry date without legal hold"
        return RuleOutcome.PASS, "Retention-expiry date has not passed"
            
    # 4. DPDP-004
    elif rule_id == "DPDP-004":
        if "notice_provided" not in row or row.get("notice_provided") is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing notice_provided flag"
            
    # 5. DPDP-005
    elif rule_id == "DPDP-005":
        is_minor = row.get("is_minor")
        if is_minor is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing is_minor field"
        
        # Convert to boolean
        if isinstance(is_minor, str):
            is_minor = is_minor.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            is_minor = bool(is_minor)
            
        if not is_minor:
            return RuleOutcome.NOT_APPLICABLE, "Customer is an adult, child data rule is not applicable"

        # Check guardian consent missing/invalid -> VIOLATION
        # Note: only the GUARDIAN's own consent record matters here. The minor's
        # own consent_status is not evaluated by DPDP-005 (that's DPDP-001's
        # concern) — a minor cannot give legally valid consent themselves, so
        # their own consent_status is irrelevant to whether guardian consent
        # was obtained.
        guardian_consent = row.get("guardian_consent_hash")
        guardian_status = row.get("guardian_consent_status")

        if not guardian_consent or guardian_status != "active":
            return RuleOutcome.VIOLATION, "Child data missing or invalid guardian consent"
            
        return RuleOutcome.PASS, "Minor customer has active guardian consent"

    # 6. DPDP-006
    elif rule_id == "DPDP-006":
        shared = row.get("shared_with_third_party")
        if shared is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing shared_with_third_party evidence"
        if isinstance(shared, str):
            shared = shared.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            shared = bool(shared)
            
        if not shared:
            return RuleOutcome.NOT_APPLICABLE, "Transaction not shared with a third party"
            
        permitted = row.get("third_party_sharing_permitted")
        dpa_signed = row.get("dpa_signed")
        
        if permitted is None or dpa_signed is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing sharing-permission or DPA evidence"
            
        if isinstance(permitted, str):
            permitted = permitted.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            permitted = bool(permitted)
            
        if isinstance(dpa_signed, str):
            dpa_signed = dpa_signed.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            dpa_signed = bool(dpa_signed)
            
        if not permitted:
            return RuleOutcome.VIOLATION, "Explicitly denied sharing permission in consent"
        if not dpa_signed:
            return RuleOutcome.VIOLATION, "No active DPA covering third-party sharing"
            
        return RuleOutcome.PASS, "Authorized third-party sharing with active DPA"

    # 7. DPDP-007
    elif rule_id == "DPDP-007":
        accessed_pii = row.get("accessed_pii")
        if accessed_pii is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing accessed_pii evidence"
        if isinstance(accessed_pii, str):
            accessed_pii = accessed_pii.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            accessed_pii = bool(accessed_pii)
        if not accessed_pii:
            return RuleOutcome.NOT_APPLICABLE, "Access did not touch PII"

        justified = row.get("pii_fields_justified")
        if justified is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing pii_fields_justified evidence"
            
        if isinstance(justified, str):
            justified = justified.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            justified = bool(justified)
            
        if not justified:
            return RuleOutcome.VIOLATION, "Access to PII is not justified (pii_fields_justified is False)"
            
        return RuleOutcome.PASS, "Access to PII is fully justified"

            
    # 8. DPDP-008
    elif rule_id == "DPDP-008":
        pii_encrypted = row.get("pii_encrypted")
        if pii_encrypted is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing pii_encrypted evidence"
            
        if isinstance(pii_encrypted, str):
            pii_encrypted = pii_encrypted.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            pii_encrypted = bool(pii_encrypted)
            
        if not pii_encrypted:
            return RuleOutcome.VIOLATION, "Sensitive data is recorded as stored without encryption"

        encryption_type = row.get("encryption_type")
        if encryption_type is None or not str(encryption_type).strip():
            return RuleOutcome.NOT_ASSESSABLE, "Missing encryption_type evidence"

        if str(encryption_type).strip().lower() in {"none", "md5", "sha1", "des", "rc4"}:
            return RuleOutcome.VIOLATION, "Recorded protection uses a weak or non-encryption algorithm"

        return RuleOutcome.PASS, "Recorded sensitive data is encrypted with an accepted algorithm"


            
    # 9. DPDP-009
    elif rule_id == "DPDP-009":
        grievance_available = row.get("grievance_endpoint_available")
        if grievance_available is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing grievance_endpoint_available evidence"
        if isinstance(grievance_available, str):
            grievance_available = grievance_available.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            grievance_available = bool(grievance_available)
        if not grievance_available:
            return RuleOutcome.VIOLATION, "No readily available grievance redressal mechanism is recorded"
        return RuleOutcome.PASS, "A grievance redressal mechanism is recorded as available"

    # 10. DPDP-010
    elif rule_id == "DPDP-010":
        request_type = row.get("request_type")
        if request_type is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing request_type evidence"
        if str(request_type).lower() != "erasure":
            return RuleOutcome.NOT_APPLICABLE, "Request is not an erasure request"
        sla_breached = row.get("sla_breached")
        if sla_breached is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing SLA breach evidence"
        retention_status = row.get("retention_status")
        legal_hold = row.get("legal_hold_flag")
        if retention_status is None or legal_hold is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing erasure outcome or legal-hold evidence"
        legal_hold = _as_bool(legal_hold)
        sla_breached = _as_bool(sla_breached)
        if legal_hold is None or sla_breached is None:
            return RuleOutcome.NOT_ASSESSABLE, "Invalid erasure SLA or legal-hold evidence"
        if legal_hold:
            return RuleOutcome.PASS, "Erasure is withheld under an evidenced legal hold"
        if sla_breached and str(retention_status).lower() != "deleted":
            return RuleOutcome.VIOLATION, "Erasure remains incomplete after the tenant's evidenced service deadline"
        return RuleOutcome.PASS, "No overdue, incomplete erasure is evidenced"

    # 11. DPDP-011
    elif rule_id == "DPDP-011":
        purpose_completed = _as_bool(row.get("purpose_completed"))
        retention_status = row.get("retention_status")
        legal_hold = _as_bool(row.get("legal_hold_flag"))
        if purpose_completed is None or retention_status is None or legal_hold is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing purpose-completion, retention-status, or legal-hold evidence"
        if not purpose_completed:
            return RuleOutcome.NOT_APPLICABLE, "Processing purpose is not recorded as completed"
        if legal_hold:
            return RuleOutcome.PASS, "Continued retention is supported by an evidenced legal hold"
        if str(retention_status).lower() in {"deleted", "pending_deletion"}:
            return RuleOutcome.PASS, "Deletion is completed or pending after purpose completion"
        return RuleOutcome.VIOLATION, "Data remains actively retained after purpose completion without legal hold"

    # 12. DPDP-012 -- additional Section 10 duties apply only to an SDF.
    elif rule_id == "DPDP-012":
        is_sdf = row.get("is_significant_data_fiduciary")
        if is_sdf is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing explicit Significant Data Fiduciary applicability evidence"
        if isinstance(is_sdf, str):
            is_sdf = is_sdf.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            is_sdf = bool(is_sdf)
        if not is_sdf:
            return RuleOutcome.NOT_APPLICABLE, "Tenant is not designated as a Significant Data Fiduciary"

        if row.get("last_audit_date") is None or row.get("audit_frequency_days") is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing SDF audit date or audit-frequency evidence"
        dpo_assigned = row.get("dpo_assigned")
        if dpo_assigned is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing SDF DPO-assignment evidence"
        if isinstance(dpo_assigned, str):
            dpo_assigned = dpo_assigned.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            dpo_assigned = bool(dpo_assigned)
        if not dpo_assigned:
            return RuleOutcome.VIOLATION, "Significant Data Fiduciary has no DPO assigned"

        if int(row.get("audit_frequency_days")) > 365:
            return RuleOutcome.VIOLATION, "SDF audit frequency exceeds the annual maximum required by Rule 13"
        return RuleOutcome.PASS, "SDF has an assigned DPO and a recorded annual-or-more-frequent audit cadence"

    # 13. DPDP-013 -- role names are not a legal authorization allowlist.
    elif rule_id == "DPDP-013":
        accessed_pii = row.get("accessed_pii")
        if accessed_pii is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing accessed_pii evidence"
        if isinstance(accessed_pii, str):
            accessed_pii = accessed_pii.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            accessed_pii = bool(accessed_pii)
        if not accessed_pii:
            return RuleOutcome.NOT_APPLICABLE, "Access event did not expose PII"

        access_authorized = row.get("access_authorized")
        if access_authorized is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing explicit access_authorized evidence"
        if isinstance(access_authorized, str):
            access_authorized = access_authorized.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            access_authorized = bool(access_authorized)

        if not access_authorized:
            return RuleOutcome.VIOLATION, "PII was accessed without recorded authorization"
        return RuleOutcome.PASS, "PII access has explicit authorization evidence"

    # 14. DPDP-014
    elif rule_id == "DPDP-014":
        detected = row.get("breach_detected")
        if detected is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing breach_detected evidence"
        if isinstance(detected, str):
            detected = detected.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            detected = bool(detected)
        if not detected:
            return RuleOutcome.NOT_APPLICABLE, "No security breach detected"
            
        if row.get("breach_confirmed_date") is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing breach confirmation date evidence"

        delay_hours = row.get("notification_delay_hours")
        if delay_hours is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing Board notification-delay evidence"
        try:
            delay_hours = int(delay_hours)
        except (TypeError, ValueError):
            return RuleOutcome.NOT_ASSESSABLE, "Invalid Board notification-delay evidence"
        if delay_hours > 72:
            return RuleOutcome.VIOLATION, "Detailed breach notice to the Board exceeded the 72-hour limit in Rule 7"
        return RuleOutcome.PASS, "Detailed breach notice to the Board was recorded within 72 hours"

    # 15. DPDP-015
    elif rule_id == "DPDP-015":
        cross = row.get("is_cross_border")
        if cross is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing is_cross_border evidence"
        if isinstance(cross, str):
            cross = cross.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            cross = bool(cross)
        if not cross:
            return RuleOutcome.NOT_APPLICABLE, "Transaction is not cross-border"
            
        country = row.get("transfer_country")
        restriction_compliant = row.get("transfer_restriction_compliant")
        assessment_reference = row.get("transfer_assessment_reference")
        if country is None or restriction_compliant is None or not assessment_reference:
            return RuleOutcome.NOT_ASSESSABLE, "Missing destination or Section 16 transfer-assessment evidence"

        if isinstance(restriction_compliant, str):
            restriction_compliant = restriction_compliant.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            restriction_compliant = bool(restriction_compliant)

        if not restriction_compliant:
            return RuleOutcome.VIOLATION, "Transfer is recorded as non-compliant with applicable Section 16 restrictions"

        return RuleOutcome.PASS, "Transfer has a recorded compliant Section 16 assessment and evidence reference"

    # 16. DPDP-016
    elif rule_id == "DPDP-016":
        processor_type = row.get("data_processor_type")
        if processor_type is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing data_processor_type evidence"
        if str(processor_type).lower() not in {"third_party_processor", "sub_processor"}:
            return RuleOutcome.NOT_APPLICABLE, "System is not recorded as an external processor"

        pii_stored = _as_bool(row.get("pii_stored"))
        if pii_stored is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing pii_stored evidence"
        if not pii_stored:
            return RuleOutcome.NOT_APPLICABLE, "Processor system is not recorded as handling personal data"

        dpa_signed = _as_bool(row.get("dpa_signed"))
        if dpa_signed is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing processor-contract evidence"
        if not dpa_signed:
            return RuleOutcome.VIOLATION, "External processor has no recorded valid contract"

        expiry_date = _as_date(row.get("dpa_expiry_date"))
        if expiry_date is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing processor-contract expiry evidence"
        if expiry_date < date.today():
            return RuleOutcome.VIOLATION, "External processor contract is expired"
        return RuleOutcome.PASS, "External processor has a current recorded contract"

    # Internal policy controls are evaluated only against their own policy row.
    elif rule_id in {"POLICY-001", "POLICY-002", "POLICY-003"}:
        target_type = {
            "POLICY-001": "retention",
            "POLICY-002": "encryption",
            "POLICY-003": "consent",
        }[rule_id]
        if row.get("policy_type") != target_type:
            return RuleOutcome.NOT_APPLICABLE, f"Row is not a {target_type} policy"

        is_active = row.get("is_active")
        if is_active is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing is_active policy evidence"
        if isinstance(is_active, str):
            is_active = is_active.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            is_active = bool(is_active)
        if not is_active:
            return RuleOutcome.VIOLATION, f"Required internal {target_type} policy is inactive"

        if rule_id == "POLICY-001":
            return RuleOutcome.PASS, "Active internal retention policy is recorded"

        policy_value = row.get("policy_value_text")
        if policy_value is None or not str(policy_value).strip():
            return RuleOutcome.NOT_ASSESSABLE, "Missing policy_value_text evidence"
        normalized = str(policy_value).strip().lower()

        if rule_id == "POLICY-002" and normalized in {"none", "md5", "sha1", "des", "rc4"}:
            return RuleOutcome.VIOLATION, "Internal encryption policy declares a weak algorithm"
        if rule_id == "POLICY-003" and normalized in {"implicit", "pre_ticked", "inferred", "bundled"}:
            return RuleOutcome.VIOLATION, "Internal consent policy lacks a clear affirmative mechanism"

        return RuleOutcome.PASS, f"Active internal {target_type} policy has assessable evidence"

    # Dynamic classification using signal scores for other cases and standard scoring
    score = sum(s.get('weight', 0.0) for s in signals if s['signal_id'] in signals_fired)
    score = round(score, 4)
    if score >= v_threshold:
        return RuleOutcome.VIOLATION, f"Breached violation threshold ({score} >= {v_threshold})"
    elif score >= r_threshold:
        return RuleOutcome.VIOLATION, f"Breached risk threshold ({score} >= {r_threshold})" # Treat warning/risk as VIOLATION/high-risk findings
    return RuleOutcome.PASS, "No violations detected for this record"
