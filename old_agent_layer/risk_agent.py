import psycopg
from typing import List
from .base_agent import BaseAgent
from .violation_record import ViolationRecord

class RiskAgent(BaseAgent):
    name = "risk_agent"
    assigned_rules = ["DPDP-006", "DPDP-007", "DPDP-008", "DPDP-014"]

    def _execute(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        records = []
        records.extend(self._check_dpdp_006(tenant_id, conn))
        records.extend(self._check_dpdp_007(tenant_id, conn))
        records.extend(self._check_dpdp_008(tenant_id, conn))
        records.extend(self._check_dpdp_014(tenant_id, conn))
        return records

    def _check_dpdp_006(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-006: Unauthorized Third Party Sharing
        Evidence: Section 6(1)
        """
        records = []
        query = """
            SELECT t.event_hash, t.shared_with_third_party, t.is_cross_border, c.consent_status
            FROM transaction_events t
            LEFT JOIN consent_records c
              ON t.consent_hash = c.consent_hash
              AND t.tenant_id = c.tenant_id
            WHERE t.tenant_id = %s
        """
        signal_weights = {"S1": 0.40, "S2": 0.40, "S3": 0.20}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if row["shared_with_third_party"]:
                signals_fired.append("S1")
                signal_reasons.append("3rd party sharing enabled")
                if row["consent_status"] is None or row["consent_status"] != "active":
                    signals_fired.append("S2")
                    signal_reasons.append("consent missing or inactive")
                    
            if row["is_cross_border"]:
                signals_fired.append("S3")
                signal_reasons.append("cross-border sharing")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.55, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-006",
                    rule_name="Unauthorized Third Party Sharing",
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
                    v_thresh=0.55,
                    r_thresh=0.35
                ))
        return records

    def _check_dpdp_007(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-007: Missing Data Minimization
        Evidence: Section 4(1)(c)
        """
        records = []
        has_pii_stored = False
        col_check = """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'system_inventory' AND column_name = 'pii_stored'
        """
        if conn.execute(col_check).fetchone():
            has_pii_stored = True

        if has_pii_stored:
            query = """
                SELECT system_hash, pii_stored, data_processor_type, dpa_signed
                FROM system_inventory
                WHERE tenant_id = %s
            """
        else:
            query = """
                SELECT system_hash, False as pii_stored, data_processor_type, dpa_signed
                FROM system_inventory
                WHERE tenant_id = %s
            """
            print("WARNING: DPDP-007 S1 skipped: pii_stored not in DB yet")

        signal_weights = {"S1": 0.50, "S2": 0.50}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if row["pii_stored"] and has_pii_stored:
                signals_fired.append("S1")
                signal_reasons.append("pii_stored=true")
                
            if row["data_processor_type"] == "third_party_processor" and not row["dpa_signed"]:
                signals_fired.append("S2")
                signal_reasons.append("third_party without DPA")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.50, 0.30)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-007",
                    rule_name="Missing Data Minimization",
                    dpdp_section="Section 4(1)(c)",
                    tenant_id=tenant_id,
                    record_id=row["system_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="MEDIUM",
                    risk_weight=0.5,
                    penalty_crore=150,
                    v_thresh=0.50,
                    r_thresh=0.30
                ))
        return records

    def _check_dpdp_008(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-008: Sensitive Data Without Encryption
        Evidence: Section 8(5)
        """
        records = []
        query = """
            SELECT security_hash, pii_encrypted, encryption_type
            FROM security_events
            WHERE tenant_id = %s
        """
        signal_weights = {"S1": 0.70, "S2": 0.30}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if not row["pii_encrypted"]:
                signals_fired.append("S1")
                signal_reasons.append("pii_encrypted=false")
                
            if row["encryption_type"] == "none":
                signals_fired.append("S2")
                signal_reasons.append("encryption_type=none")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.60, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-008",
                    rule_name="Sensitive Data Without Encryption",
                    dpdp_section="Section 8(5)",
                    tenant_id=tenant_id,
                    record_id=row["security_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="CRITICAL",
                    risk_weight=0.95,
                    penalty_crore=250,
                    v_thresh=0.60,
                    r_thresh=0.35
                ))
        return records

    def _check_dpdp_014(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-014: Delayed Breach Notification
        Evidence: Section 8(6)
        """
        records = []
        query = """
            SELECT security_hash, breach_detected, notification_delay_hours, affected_user_count
            FROM security_events
            WHERE tenant_id = %s AND breach_detected = true
        """
        signal_weights = {"S1": 0.20, "S2": 0.50, "S3": 0.30}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = ["S1"]
            signal_reasons = ["breach_detected=true"]
            
            if row["notification_delay_hours"] is not None and row["notification_delay_hours"] > 72:
                signals_fired.append("S2")
                signal_reasons.append("delay > 72h")
                
            if row["affected_user_count"] in {"large", "critical"}:
                signals_fired.append("S3")
                signal_reasons.append("high user impact")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.55, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-014",
                    rule_name="Delayed Breach Notification",
                    dpdp_section="Section 8(6)",
                    tenant_id=tenant_id,
                    record_id=row["security_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="CRITICAL",
                    risk_weight=0.95,
                    penalty_crore=200,
                    v_thresh=0.55,
                    r_thresh=0.35
                ))
        return records