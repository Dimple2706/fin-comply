from typing import List, Dict, Any
from .explanation import ViolationExplanation

RULE_EXPLANATIONS = {
    "DPDP-001": {
        "rule_name": "Invalid or Expired Consent",
        "what_happened": "Data processing was detected without a valid active consent record. The transaction occurred after consent had expired, been revoked, or under bundled consent terms.",
        "why_violation": "DPDP Act Section 6(1) requires a Data Fiduciary to process personal data only for purposes for which the Data Principal has given free, specific, informed, and unambiguous consent. Processing under invalid or expired consent violates this mandate.",
        "root_cause": "PROCESS_GAP",
        "remediation": [
            "Obtain fresh explicit consent from affected data principals before resuming processing",
            "Implement a consent management system that blocks processing when consent_status is not active",
            "Conduct an audit of all transaction_events joined to expired consent records and pause affected workflows"
        ],
        "signal_definitions": {
            "S1": {"description": "Consent status is expired, revoked, or withdrawn", "weight": 0.40},
            "S2": {"description": "Transaction event date is after consent expiry date", "weight": 0.30},
            "S3": {"description": "Processing purpose does not match consented purpose", "weight": 0.20},
            "S4": {"description": "Consent was obtained as a bundled consent (not specific)", "weight": 0.10}
        }
    },
    "DPDP-002": {
        "rule_name": "Purpose Limitation",
        "what_happened": "Personal data was processed for a purpose different from the one stated in the consent record, even where a technically active consent exists.",
        "why_violation": "DPDP Act Section 4(1)(b) mandates that personal data be processed only for the specific lawful purpose for which it was collected. Processing for a different purpose — even under active consent — constitutes an unlawful act.",
        "root_cause": "IMPLEMENTATION_GAP",
        "remediation": [
            "Update transaction processing workflows to enforce purpose matching against consent records at runtime",
            "Review and correct all consent records where consented_purpose differs from current processing activity",
            "Implement purpose limitation controls in your data processing pipeline"
        ],
        "signal_definitions": {
            "S1": {"description": "Processing purpose does not match the consented purpose", "weight": 0.70},
            "S2": {"description": "Purpose mismatch exists even though consent status is currently active — a deliberate violation", "weight": 0.30}
        }
    },
    "DPDP-003": {
        "rule_name": "Data Retention",
        "what_happened": "Personal data is being retained beyond its approved retention period, or retained after its processing purpose has been completed.",
        "why_violation": "DPDP Act Section 8(7) requires a Data Fiduciary to delete personal data as soon as it is reasonable to assume that the purpose for which it was collected is no longer being served.",
        "root_cause": "TECHNICAL_GAP",
        "remediation": [
            "Implement automated data deletion triggers based on retention_expiry_date and purpose_completed flags",
            "Review the data_lifecycle table and immediately schedule deletion for all records where expiry has passed",
            "Update your data inventory policy to include mandatory retention period review every 90 days"
        ],
        "signal_definitions": {
            "S1": {"description": "Retention expiry date has passed", "weight": 0.50},
            "S2": {"description": "Data is still in active or expired status despite expiry passing", "weight": 0.30},
            "S3": {"description": "Purpose has been marked complete but data has not been deleted", "weight": 0.20}
        }
    },
    "DPDP-004": {
        "rule_name": "Notice Requirements",
        "what_happened": "Consent was collected without providing the required notice to the Data Principal, or through a channel that implies implicit or pre-ticked consent.",
        "why_violation": "DPDP Act Section 5 requires that before seeking consent, the Data Fiduciary must give a clear notice describing the personal data to be processed and the purpose. Consent without notice is invalid.",
        "root_cause": "PROCESS_GAP",
        "remediation": [
            "Update all consent collection flows to display a layered notice before the consent request",
            "Review and re-collect consent from all data principals where notice_provided is false",
            "Implement a consent audit trail that captures notice delivery confirmation alongside consent capture"
        ],
        "signal_definitions": {
            "S1": {"description": "Notice was not provided before consent was collected", "weight": 0.80},
            "S2": {"description": "Consent was collected through an implicit or pre-ticked channel", "weight": 0.20}
        }
    },
    "DPDP-005": {
        "rule_name": "Children's Data Processing",
        "what_happened": "Processing was identified for a minor without a verified guardian consent record.",
        "why_violation": "DPDP Act Section 9 prohibits processing personal data of children without verifiable consent from their parent or guardian. This is a CRITICAL severity obligation with a maximum penalty of ₹200 crore.",
        "root_cause": "GOVERNANCE_GAP",
        "remediation": [
            "Implement age verification at account creation and flag all minor accounts immediately",
            "Obtain and record guardian consent for all existing minor accounts before resuming data processing",
            "Restrict all data processing on minor accounts until guardian consent is confirmed and recorded"
        ],
        "signal_definitions": {
            "guardian_consent_missing_or_invalid": {"description": "Minor without valid active guardian consent", "weight": 1.0}
        }
    },
    "DPDP-006": {
        "rule_name": "Third-Party & Cross-Border Sharing",
        "what_happened": "Personal data was shared with a third party without a valid active consent, or was involved in a cross-border transfer.",
        "why_violation": "DPDP Act Section 6(1) requires explicit consent before sharing data with third parties. Cross-border transfers introduce additional regulatory exposure under DPDP Rules.",
        "root_cause": "PROCESS_GAP",
        "remediation": [
            "Review all third-party data sharing agreements and ensure explicit consent covers the sharing purpose",
            "Implement a data sharing approval gate that validates consent_status = active before any third-party transfer",
            "Audit all cross-border transfers and assess compliance with DPDP Rules on significant data fiduciaries"
        ],
        "signal_definitions": {
            "S1": {"description": "Data was shared with a third party in this event", "weight": 0.30},
            "S2": {"description": "Consent scope does not include sharing with third parties", "weight": 0.35},
            "S3": {"description": "No signed Data Processing Agreement on file for the receiving processor", "weight": 0.25},
            "S4": {"description": "Transfer is cross-border — additional DPDP Chapter V obligations apply", "weight": 0.10}
        }
    },
    "DPDP-007": {
        "rule_name": "Data Minimisation Violation",
        "what_happened": "More personal data categories were collected or accessed than necessary for the stated processing purpose.",
        "why_violation": "DPDP Act Section 4(1)(c) requires that only the minimum necessary personal data be processed. Excessive data collection or access violates the data minimisation principle.",
        "root_cause": "GOVERNANCE_GAP",
        "remediation": [
            "Conduct a data minimization audit to identify and remove personal data fields not required for the stated purpose",
            "Execute signed Data Processing Agreements with all third-party processors before any data sharing",
            "Review system_inventory and classify each system's data retention requirement against its stated purpose"
        ],
        "signal_definitions": {
            "S1": {"description": "Data volume accessed is disproportionately large relative to stated purpose", "weight": 0.45},
            "S2": {"description": "System stores PII categories beyond what the declared processing purpose requires", "weight": 0.30},
            "S3": {"description": "Stated access reason does not align with the processing purpose for this data category", "weight": 0.25}
        }
    },
    "DPDP-008": {
        "rule_name": "Sensitive Data Stored Without Encryption",
        "what_happened": "Personal data is being processed or stored without encryption, leaving it exposed to unauthorized access or breach.",
        "why_violation": "DPDP Act Section 8(5) requires Data Fiduciaries to implement reasonable security safeguards to prevent personal data breaches. Absence of encryption is a direct failure of this obligation.",
        "root_cause": "TECHNICAL_GAP",
        "remediation": [
            "Immediately enable AES-256 encryption for all databases and storage systems containing PII",
            "Audit all systems in system_inventory for encryption status and prioritize unencrypted systems",
            "Conduct a security assessment and produce an encryption implementation roadmap within 30 days"
        ],
        "signal_definitions": {
            "S1": {"description": "PII is stored without any encryption", "weight": 0.50},
            "S2": {"description": "System-level encryption is disabled for a PII-storing system", "weight": 0.30},
            "S3": {"description": "Encryption algorithm used is below the minimum acceptable standard (AES-256)", "weight": 0.20}
        }
    },
    "DPDP-009": {
        "rule_name": "Grievance Mechanism",
        "what_happened": "The organization does not have a functioning grievance mechanism available for Data Principals to raise complaints.",
        "why_violation": "DPDP Act Section 13 requires every Data Fiduciary to publish a contact for a Data Protection Officer or Grievance Officer and ensure complaints can be lodged and responded to.",
        "root_cause": "GOVERNANCE_GAP",
        "remediation": [
            "Appoint a named Grievance Officer and publish their contact details on your website and in your privacy notice immediately",
            "Establish a formal grievance intake and response workflow with SLA tracking",
            "Set grievance_endpoint_available to true in your governance config once the mechanism is live"
        ],
        "signal_definitions": {
            "S1": {"description": "Grievance endpoint is not available", "weight": 1.00}
        }
    },
    "DPDP-010": {
        "rule_name": "Data Subject Rights (Erasure)",
        "what_happened": "An erasure request submitted by a Data Principal has not been fulfilled within the SLA period or remains in pending status.",
        "why_violation": "DPDP Act Section 12(a) grants Data Principals the right to erasure of their personal data. Failure to honor this right within the prescribed SLA is a direct statutory violation.",
        "root_cause": "PROCESS_GAP",
        "remediation": [
            "Implement an automated DSAR workflow with SLA countdown tracking and escalation alerts",
            "Assign a responsible team to process all pending erasure requests within 24 hours",
            "Conduct a review of all dsar_requests where sla_breached is true and provide a remediation timeline to the Board"
        ],
        "signal_definitions": {
            "S1": {"description": "The SLA for this erasure request has been breached", "weight": 0.60},
            "S2": {"description": "The erasure request is still in pending status", "weight": 0.40}
        }
    },
    "DPDP-011": {
        "rule_name": "Purpose Completion",
        "what_happened": "Personal data is being retained even though the processing purpose has been completed and no deletion has been initiated.",
        "why_violation": "DPDP Act Section 8(7)(a) requires that personal data not be retained beyond the period necessary for the purpose for which it was processed.",
        "root_cause": "TECHNICAL_GAP",
        "remediation": [
            "Deploy automated retention management that triggers deletion when purpose_completed = true",
            "Run an immediate purge job on all data_lifecycle records where purpose_completed is true and status is not deleted or pending_deletion",
            "Update your data lifecycle policy to include a mandatory deletion SLA after purpose completion"
        ],
        "signal_definitions": {
            "S1": {"description": "Processing purpose has been marked as completed", "weight": 0.50},
            "S2": {"description": "Data has not been deleted or queued for deletion despite purpose completion", "weight": 0.50}
        }
    },
    "DPDP-012": {
        "rule_name": "Audit Logging",
        "what_happened": "Audit logging is either disabled, infrequent, or overdue, meaning processing activity cannot be verified or investigated.",
        "why_violation": "DPDP Act Section 8(4) requires Data Fiduciaries to maintain a complete and accessible audit trail of all personal data processing activities.",
        "root_cause": "GOVERNANCE_GAP",
        "remediation": [
            "Enable comprehensive audit logging on all systems processing personal data immediately",
            "Implement a SIEM solution with automated alerting for unauthorized access events",
            "Schedule mandatory audit reviews at the frequency set in governance_config and assign an owner"
        ],
        "signal_definitions": {
            "S1": {"description": "Audit frequency is set to more than 180 days", "weight": 0.50},
            "S2": {"description": "No audit date is recorded", "weight": 0.30},
            "S3": {"description": "Last audit date is older than the configured audit frequency", "weight": 0.20}
        }
    },
    "DPDP-013": {
        "rule_name": "Access Control (RBAC)",
        "what_happened": "An employee without an authorized role accessed personal data, indicating a role-based access control failure.",
        "why_violation": "DPDP Act Section 8(5) requires that access to personal data be restricted to personnel with a legitimate need. Unauthorized access is a breach of this security obligation.",
        "root_cause": "HUMAN_ERROR",
        "remediation": [
            "Implement RBAC immediately to restrict PII access to compliance_officer, underwriter, and data_analyst roles only",
            "Review all access_logs for unauthorized PII access and investigate each instance",
            "Conduct a mandatory access control audit and revoke excess permissions within 48 hours"
        ],
        "signal_definitions": {
            "S1": {"description": "Accessing employee's role is not in the authorised roles list for PII access", "weight": 0.40},
            "S2": {"description": "PII fields were accessed during this event", "weight": 0.30},
            "S3": {"description": "Access was denied — repeated denied attempts indicate probing behaviour", "weight": 0.15},
            "S4": {"description": "Large volume of data accessed — potential bulk extraction by unauthorised actor", "weight": 0.15}
        }
    },
    "DPDP-014": {
        "rule_name": "Delayed Breach Notification",
        "what_happened": "A data breach was detected but notification to the authorities was delayed beyond the required 72-hour window, and/or a significant number of users were affected.",
        "why_violation": "DPDP Act Section 8(6) requires the Data Fiduciary to notify the Data Protection Board of India of any personal data breach. Delayed notification is a direct violation of this obligation.",
        "root_cause": "PROCESS_GAP",
        "remediation": [
            "Establish a documented breach response plan with a named incident response lead and a 72-hour notification SLA",
            "Implement automated breach detection with immediate escalation to the DPO and legal team",
            "Train all technical and security staff on breach identification, containment, and DPDP notification requirements"
        ],
        "signal_definitions": {
            "S1": {"description": "A personal data breach has been detected for this tenant", "weight": 0.20},
            "S2": {"description": "Notification delay exceeds 72-hour threshold — CERT-In and DPDP S.8(6) violation", "weight": 0.40},
            "S3": {"description": "Breach confirmation timestamp is missing — notification clock cannot be verified", "weight": 0.25},
            "S4": {"description": "Large number of Data Principals affected — elevated regulatory scrutiny expected", "weight": 0.15}
        }
    },
    "DPDP-015": {
        "rule_name": "Cross-Border Transfer Without Authorisation",
        "what_happened": "Personal data was transferred outside India without meeting Chapter V requirements of the DPDP Act.",
        "why_violation": "DPDP Act Section 16 restricts transfer of personal data to countries not on the approved list unless adequate safeguards are in place. Cross-border transfers without authorisation expose the organisation to significant penalties.",
        "root_cause": "GOVERNANCE_GAP",
        "remediation": [
            "Audit all cross-border data flows and map destination countries against the DPDP approved list",
            "Execute Standard Contractual Clauses or Binding Corporate Rules for all international transfers",
            "Implement a transfer impact assessment process before initiating any new cross-border data flow"
        ],
        "signal_definitions": {
            "S1": {"description": "Transfer is flagged as cross-border — Chapter V obligations triggered", "weight": 0.35},
            "S2": {"description": "Destination country is not on India's approved transfer list under Section 16", "weight": 0.40},
            "S3": {"description": "No Data Processing Agreement covers this cross-border transfer", "weight": 0.25}
        }
    },
    "DPDP-016": {
        "rule_name": "Processor Accountability Failure",
        "what_happened": "A third-party data processor lacks a valid Data Processing Agreement or has an expired agreement.",
        "why_violation": "DPDP Act Section 8(2) requires the Data Fiduciary to ensure all processors operate under a valid, binding DPA. Processors without DPAs create direct fiduciary liability.",
        "root_cause": "GOVERNANCE_GAP",
        "remediation": [
            "Execute signed DPAs with all third-party processors immediately",
            "Implement DPA expiry tracking with automated renewal alerts 60 days before expiry",
            "Conduct a processor audit and suspend data sharing with any processor lacking a valid DPA"
        ],
        "signal_definitions": {
            "S1": {"description": "No Data Processing Agreement signed with this processor — S.8(2) direct violation", "weight": 0.50},
            "S2": {"description": "DPA has expired — processor relationship is no longer legally governed", "weight": 0.35},
            "S3": {"description": "Processor stores PII — the absence of a DPA creates direct fiduciary liability", "weight": 0.15}
        }
    }
}

def explain_violation(v: Dict[str, Any], risk_contribution: float) -> ViolationExplanation:
    rule_id = v.get("rule_id", "UNKNOWN")
    template = RULE_EXPLANATIONS.get(rule_id, {
        "rule_name": "Unknown Rule",
        "what_happened": "An automated compliance check produced a finding for an unrecognized rule.",
        "why_violation": "The relevant DPDP requirement could not be automatically determined.",
        "root_cause": "TECHNICAL_GAP",
        "remediation": ["Review the specific record to manually ascertain the required corrective action."],
        "signal_definitions": {}
    })
    
    signals_analysis = []
    signals_fired = v.get("signals_fired", [])
    signal_reasons = v.get("signal_reasons", [])
    
    top_contributing_signal = "—"
    top_signal_weight = 0.0
    
    signal_defs = template.get("signal_definitions", {})
    for signal_key, definition in signal_defs.items():
        weight = definition["weight"]
        fired = signal_key in signals_fired
        reason = "—"
        if fired:
            try:
                idx = signals_fired.index(signal_key)
                reason = signal_reasons[idx] if idx < len(signal_reasons) else "—"
            except ValueError:
                pass
                
            if weight > top_signal_weight:
                top_signal_weight = weight
                top_contributing_signal = signal_key

        contrib = weight if fired else 0.0
        signals_analysis.append({
            "signal": signal_key,
            "weight": weight,
            "fired": fired,
            "reason": reason,
            "signal_contribution": round(contrib, 4),
            "phi": round(contrib, 4),
        })
        
    return ViolationExplanation(
        rule_id=rule_id,
        rule_name=v.get("rule_name", template.get("rule_name", "Unknown")),
        dpdp_section=v.get("dpdp_section", "Unknown"),
        agent_name=v.get("agent_name", "Unknown"),
        outcome=v.get("outcome", "UNKNOWN"),
        severity=v.get("severity", "LOW"),
        what_happened=template.get("what_happened", ""),
        why_violation=template.get("why_violation", ""),
        signals_analysis=signals_analysis,
        top_contributing_signal=top_contributing_signal,
        top_signal_weight=top_signal_weight,
        penalty_exposure_crore=v.get("penalty_exposure_crore", 0),
        root_cause=template.get("root_cause", "UNKNOWN"),
        remediation_steps=template.get("remediation", []),
        risk_contribution=risk_contribution
    )

def enrich_violations(violations: List[Dict[str, Any]], contributions: Dict[str, float]) -> List[ViolationExplanation]:
    explanations = []
    for v in violations:
        rule_id = v.get("rule_id", "")
        contribution = contributions.get(rule_id, 0.0)
        explanations.append(explain_violation(v, contribution))
    return explanations

def generate_executive_summary(
    tenant_id: str, 
    tenant_name: str, 
    explanations: List[ViolationExplanation], 
    risk_score: float, 
    tier: str
) -> str:
    violation_exps = [e for e in explanations if e.outcome == "VIOLATION"]
    n = len(violation_exps)
    
    if n == 0:
        return f"{tenant_name} passed all DPDP compliance checks with a risk score of {risk_score}/100 ({tier})."
        
    unique_rules = {e.rule_id for e in violation_exps}
    rules_count = len(unique_rules)
    
    # Sort for top contributors
    sorted_viols = sorted(violation_exps, key=lambda x: x.risk_contribution, reverse=True)
    top = sorted_viols[0] if sorted_viols else None
    
    # Deduplicated penalty summing
    seen_rules = set()
    total_penalty = 0
    for e in violation_exps:
        if e.rule_id not in seen_rules:
            total_penalty += e.penalty_exposure_crore
            seen_rules.add(e.rule_id)
            
    # Top 3 rule IDs by risk contribution
    seen_top3 = set()
    top_3 = []
    for e in sorted_viols:
        if e.rule_id not in seen_top3:
            top_3.append(e.rule_id)
            seen_top3.add(e.rule_id)
        if len(top_3) == 3:
            break
            
    return (
        f"{tenant_name} achieved a DPDP compliance risk score of {risk_score}/100, classified as {tier}. "
        f"{n} violations were detected across {rules_count} DPDP Act sections, with a combined maximum penalty exposure of "
        f"₹{total_penalty} crore. The highest-risk finding is {top.rule_id} ({top.rule_name}) under Section "
        f"{top.dpdp_section}, contributing {top.risk_contribution} to the overall risk score. "
        f"Immediate remediation is recommended for: {', '.join(top_3)}."
    )
