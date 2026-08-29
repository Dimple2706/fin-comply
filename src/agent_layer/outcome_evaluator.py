from typing import List, Tuple
from .result_state import RuleOutcome

def determine_row_outcome(rule_id: str, row: dict, signals_fired: List[str], signals: List[dict], v_threshold: float, r_threshold: float) -> Tuple[RuleOutcome, str]:
    """
    Determine the explicit rule outcome state for a single row.
    Returns (RuleOutcome, reason_text).
    """
    
    # 1. DPDP-001
    if rule_id == "DPDP-001":
        if "consent_status" not in row or row.get("consent_status") is None or "event_date" not in row or row.get("event_date") is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing critical fields consent_status or event_date"
        
    # 2. DPDP-002
    elif rule_id == "DPDP-002":
        if "notice_provided" not in row or row.get("notice_provided") is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing notice_provided evidence"
            
    # 3. DPDP-003
    elif rule_id == "DPDP-003":
        if "retention_expiry_date" not in row or row.get("retention_expiry_date") is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing retention_expiry_date"
            
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
        guardian_consent = row.get("guardian_consent_hash")
        guardian_status = row.get("guardian_consent_status")
        consent_status = row.get("consent_status")
        
        if not guardian_consent or guardian_status != "active" or consent_status != "active":
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
        detected = row.get("breach_detected")
        if detected is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing breach_detected evidence"
        if isinstance(detected, str):
            detected = detected.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            detected = bool(detected)
        if not detected:
            return RuleOutcome.NOT_APPLICABLE, "No security breach detected"
            
        pii_encrypted = row.get("pii_encrypted")
        if pii_encrypted is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing pii_encrypted evidence"
            
        if isinstance(pii_encrypted, str):
            pii_encrypted = pii_encrypted.lower() in ('true', 't', '1', 'yes', 'y')
        else:
            pii_encrypted = bool(pii_encrypted)
            
        if not pii_encrypted:
            return RuleOutcome.VIOLATION, "Sensitive data stored without encryption during breach"
            
        return RuleOutcome.PASS, "Sensitive data is encrypted"


            
    # 9. DPDP-009
    elif rule_id == "DPDP-009":
        assigned = row.get("dpo_assigned")
        if assigned is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing dpo_assigned evidence"

    # 10. DPDP-010
    elif rule_id == "DPDP-010":
        sla_breached = row.get("sla_breached")
        if sla_breached is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing SLA breach evidence"

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
        dpa_signed = row.get("dpa_signed")
        if country is None or dpa_signed is None:
            return RuleOutcome.NOT_ASSESSABLE, "Missing destination country or safeguard evidence"

    # Dynamic classification using signal scores for other cases and standard scoring
    score = sum(s.get('weight', 0.0) for s in signals if s['signal_id'] in signals_fired)
    score = round(score, 4)
    if score >= v_threshold:
        return RuleOutcome.VIOLATION, f"Breached violation threshold ({score} >= {v_threshold})"
    elif score >= r_threshold:
        return RuleOutcome.VIOLATION, f"Breached risk threshold ({score} >= {r_threshold})" # Treat warning/risk as VIOLATION/high-risk findings
    return RuleOutcome.PASS, "No violations detected for this record"
