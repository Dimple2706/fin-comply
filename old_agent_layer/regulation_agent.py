import psycopg
from typing import List
from .base_agent import BaseAgent
from .violation_record import ViolationRecord

class RegulationAgent(BaseAgent):
    name = "regulation_agent"
    assigned_rules = ["DPDP-001", "DPDP-002", "DPDP-004", "DPDP-005"]

    def _execute(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        records = []
        records.extend(self._check_dpdp_001(tenant_id, conn))
        records.extend(self._check_dpdp_002(tenant_id, conn))
        records.extend(self._check_dpdp_004(tenant_id, conn))
        records.extend(self._check_dpdp_005(tenant_id, conn))
        return records

    def _check_dpdp_001(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-001: Invalid/Missing Consent Before Processing
        Evidence: Section 6(1)
        """
        records = []
        query = """
            SELECT t.event_hash, t.event_date, t.processing_purpose,
                   c.consent_status, c.expiry_date, c.consented_purpose, c.is_bundled
            FROM transaction_events t
            JOIN consent_records c
              ON t.consent_hash = c.consent_hash
              AND t.tenant_id = c.tenant_id
            WHERE t.tenant_id = %s
        """
        signal_weights = {"S1": 0.40, "S2": 0.30, "S3": 0.20, "S4": 0.10}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if row["consent_status"] in {"expired", "revoked", "withdrawn"}:
                signals_fired.append("S1")
                signal_reasons.append(f"consent_status={row['consent_status']}")
                
            if row["event_date"] and row["expiry_date"] and str(row["event_date"]) > str(row["expiry_date"]):
                signals_fired.append("S2")
                signal_reasons.append("event_date > expiry_date")
                
            if row["processing_purpose"] != row["consented_purpose"]:
                signals_fired.append("S3")
                signal_reasons.append("processing_purpose mismatch")
                
            if row["is_bundled"]:
                signals_fired.append("S4")
                signal_reasons.append("is_bundled=true")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.60, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-001",
                    rule_name="Invalid/Missing Consent Before Processing",
                    dpdp_section="Section 6(1)",
                    tenant_id=tenant_id,
                    record_id=row["event_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="HIGH",
                    risk_weight=0.9,
                    penalty_crore=150,
                    v_thresh=0.60,
                    r_thresh=0.35
                ))
        return records

    def _check_dpdp_002(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-002: Processing Beyond Stated Purpose
        Evidence: Section 4(1)(b)
        """
        records = []
        query = """
            SELECT t.event_hash, t.event_date, t.processing_purpose,
                   c.consent_status, c.expiry_date, c.consented_purpose, c.is_bundled
            FROM transaction_events t
            JOIN consent_records c
              ON t.consent_hash = c.consent_hash
              AND t.tenant_id = c.tenant_id
            WHERE t.tenant_id = %s
        """
        signal_weights = {"S1": 0.70, "S2": 0.30}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if row["processing_purpose"] != row["consented_purpose"]:
                signals_fired.append("S1")
                signal_reasons.append("processing_purpose mismatch")
                if row["consent_status"] == "active":
                    signals_fired.append("S2")
                    signal_reasons.append("purpose mismatch while consent is active")
                    
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.60, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-002",
                    rule_name="Processing Beyond Stated Purpose",
                    dpdp_section="Section 4(1)(b)",
                    tenant_id=tenant_id,
                    record_id=row["event_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="HIGH",
                    risk_weight=0.85,
                    penalty_crore=150,
                    v_thresh=0.60,
                    r_thresh=0.35
                ))
        return records

    def _check_dpdp_004(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-004: Missing Notice to Data Principal
        Evidence: Section 5
        """
        records = []
        query = """
            SELECT consent_hash, notice_provided, consent_channel
            FROM consent_records
            WHERE tenant_id = %s
        """
        signal_weights = {"S1": 0.80, "S2": 0.20}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if not row["notice_provided"]:
                signals_fired.append("S1")
                signal_reasons.append("notice_provided=false")
                
            if row["consent_channel"] and row["consent_channel"] in {"implicit", "pre_ticked"}:
                signals_fired.append("S2")
                signal_reasons.append(f"consent_channel={row['consent_channel']}")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.60, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-004",
                    rule_name="Missing Notice to Data Principal",
                    dpdp_section="Section 5",
                    tenant_id=tenant_id,
                    record_id=row["consent_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="MEDIUM",
                    risk_weight=0.6,
                    penalty_crore=50,
                    v_thresh=0.60,
                    r_thresh=0.35
                ))
        return records

    def _check_dpdp_005(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-005: Children's Data Without Guardian Consent
        Evidence: Section 9
        """
        records = []
        query = """
            SELECT cm.customer_hash, cm.is_minor, cr.guardian_consent_hash
            FROM customer_master cm
            LEFT JOIN consent_records cr
              ON cm.customer_hash = cr.customer_hash
              AND cr.tenant_id = cm.tenant_id
            WHERE cm.tenant_id = %s
        """
        signal_weights = {"S1": 0.50, "S2": 0.50}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if row["is_minor"]:
                signals_fired.append("S1")
                signal_reasons.append("is_minor=true")
                
            if row["guardian_consent_hash"] is None:
                signals_fired.append("S2")
                signal_reasons.append("guardian_consent_hash IS NULL")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.40, 0.30)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-005",
                    rule_name="Children's Data Without Guardian Consent",
                    dpdp_section="Section 9",
                    tenant_id=tenant_id,
                    record_id=row["customer_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="CRITICAL",
                    risk_weight=1.0,
                    penalty_crore=200,
                    v_thresh=0.40,
                    r_thresh=0.30
                ))
        return records