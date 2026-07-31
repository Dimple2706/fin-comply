import datetime
import psycopg
from typing import List
from .base_agent import BaseAgent
from .violation_record import ViolationRecord

class AuditAgent(BaseAgent):
    name = "audit_agent"
    assigned_rules = ["DPDP-003", "DPDP-009", "DPDP-010", "DPDP-011", "DPDP-012", "DPDP-013"]

    def _execute(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        records = []
        records.extend(self._check_dpdp_003(tenant_id, conn))
        records.extend(self._check_dpdp_009(tenant_id, conn))
        records.extend(self._check_dpdp_010(tenant_id, conn))
        records.extend(self._check_dpdp_011(tenant_id, conn))
        records.extend(self._check_dpdp_012(tenant_id, conn))
        records.extend(self._check_dpdp_013(tenant_id, conn))
        return records

    def _check_dpdp_003(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-003: Retention Beyond Allowed Period
        Evidence: Section 8(7)
        """
        records = []
        query = """
            SELECT lifecycle_hash, retention_expiry_date, retention_status, purpose_completed
            FROM data_lifecycle
            WHERE tenant_id = %s
        """
        signal_weights = {"S1": 0.50, "S2": 0.30, "S3": 0.20}
        today_str = str(datetime.date.today())
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            s1_true = row["retention_expiry_date"] and str(row["retention_expiry_date"]) < today_str
            if s1_true:
                signals_fired.append("S1")
                signal_reasons.append("retention_expiry_date < today")
                
                if row["retention_status"] in {"expired", "active"}:
                    signals_fired.append("S2")
                    signal_reasons.append("status is active/expired past expiry")
                    
            if row["purpose_completed"] and row["retention_status"] not in {"deleted", "pending_deletion"}:
                signals_fired.append("S3")
                signal_reasons.append("purpose complete but not deleted")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.55, 0.30)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-003",
                    rule_name="Retention Beyond Allowed Period",
                    dpdp_section="Section 8(7)",
                    tenant_id=tenant_id,
                    record_id=row["lifecycle_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="HIGH",
                    risk_weight=0.8,
                    penalty_crore=150,
                    v_thresh=0.55,
                    r_thresh=0.30
                ))
        return records

    def _check_dpdp_009(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-009: Missing Grievance Mechanism
        Evidence: Section 13
        """
        records = []
        query = """
            SELECT tenant_id, grievance_endpoint_available
            FROM governance_config
            WHERE tenant_id = %s
        """
        signal_weights = {"S1": 1.00}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if not row["grievance_endpoint_available"]:
                signals_fired.append("S1")
                signal_reasons.append("grievance endpoint unavailable")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.80, 0.50)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-009",
                    rule_name="Missing Grievance Mechanism",
                    dpdp_section="Section 13",
                    tenant_id=tenant_id,
                    record_id=row["tenant_id"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="LOW",
                    risk_weight=0.3,
                    penalty_crore=10,
                    v_thresh=0.80,
                    r_thresh=0.50
                ))
        return records

    def _check_dpdp_010(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-010: Failure to Honor Erasure Request
        Evidence: Section 12(a)
        """
        records = []
        query = """
            SELECT dsar_hash, sla_breached, fulfillment_status
            FROM dsar_requests
            WHERE tenant_id = %s AND request_type = 'erasure'
        """
        signal_weights = {"S1": 0.60, "S2": 0.40}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if row["sla_breached"]:
                signals_fired.append("S1")
                signal_reasons.append("SLA breached")
                
            if row["fulfillment_status"] == "pending":
                signals_fired.append("S2")
                signal_reasons.append("fulfillment pending")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.55, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-010",
                    rule_name="Failure to Honor Erasure Request",
                    dpdp_section="Section 12(a)",
                    tenant_id=tenant_id,
                    record_id=row["dsar_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="HIGH",
                    risk_weight=0.85,
                    penalty_crore=150,
                    v_thresh=0.55,
                    r_thresh=0.35
                ))
        return records

    def _check_dpdp_011(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-011: Excess Retention Without Purpose
        Evidence: Section 8(7)(a)
        """
        records = []
        query = """
            SELECT lifecycle_hash, purpose_completed, retention_status
            FROM data_lifecycle
            WHERE tenant_id = %s
        """
        signal_weights = {"S1": 0.50, "S2": 0.50}
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if row["purpose_completed"]:
                signals_fired.append("S1")
                signal_reasons.append("purpose complete")
                
            if row["retention_status"] not in {"deleted", "pending_deletion"}:
                signals_fired.append("S2")
                signal_reasons.append("not pending deletion or deleted")
                
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.60, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-011",
                    rule_name="Excess Retention Without Purpose",
                    dpdp_section="Section 8(7)(a)",
                    tenant_id=tenant_id,
                    record_id=row["lifecycle_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="MEDIUM",
                    risk_weight=0.6,
                    penalty_crore=150,
                    v_thresh=0.60,
                    r_thresh=0.35
                ))
        return records

    def _check_dpdp_012(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-012: Missing Audit Logs
        Evidence: Section 8(4)
        """
        records = []
        query = """
            SELECT tenant_id, audit_frequency_days, last_audit_date
            FROM governance_config
            WHERE tenant_id = %s
        """
        signal_weights = {"S1": 0.50, "S2": 0.30, "S3": 0.20}
        today = datetime.date.today()
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            freq = row["audit_frequency_days"]
            
            if freq and freq > 180:
                signals_fired.append("S1")
                signal_reasons.append("audit freq > 180 days")
                
            if row["last_audit_date"] is None:
                signals_fired.append("S2")
                signal_reasons.append("last_audit_date missing")
            else:
                last_dt = datetime.date.fromisoformat(str(row["last_audit_date"]))
                if (today - last_dt).days > freq:
                    signals_fired.append("S3")
                    signal_reasons.append("audit overdue")
                    
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.55, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-012",
                    rule_name="Missing Audit Logs",
                    dpdp_section="Section 8(4)",
                    tenant_id=tenant_id,
                    record_id=row["tenant_id"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="MEDIUM",
                    risk_weight=0.55,
                    penalty_crore=50,
                    v_thresh=0.55,
                    r_thresh=0.35
                ))
        return records

    def _check_dpdp_013(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        DPDP-013: Unauthorized Employee PII Access
        Evidence: Section 8(5)
        """
        records = []
        query = """
            SELECT access_hash, accessed_pii, employee_role
            FROM access_logs
            WHERE tenant_id = %s
        """
        signal_weights = {"S1": 0.40, "S2": 0.60}
        auth_roles = frozenset({"compliance_officer", "underwriter", "data_analyst"})
        
        for row in conn.execute(query, [tenant_id]).fetchall():
            signals_fired = []
            signal_reasons = []
            
            if row["accessed_pii"]:
                signals_fired.append("S1")
                signal_reasons.append("accessed_pii=true")
                if row["employee_role"] not in auth_roles:
                    signals_fired.append("S2")
                    signal_reasons.append(f"unauthorized role: {row['employee_role']}")
                    
            score = self._compute_rule_score(signals_fired, signal_weights)
            outcome = self._classify_outcome(score, 0.60, 0.35)
            
            if outcome != "PASS":
                records.append(self._make_record(
                    rule_id="DPDP-013",
                    rule_name="Unauthorized Employee PII Access",
                    dpdp_section="Section 8(5)",
                    tenant_id=tenant_id,
                    record_id=row["access_hash"],
                    outcome=outcome,
                    rule_score=score,
                    signals_fired=signals_fired,
                    signal_reasons=signal_reasons,
                    severity="HIGH",
                    risk_weight=0.9,
                    penalty_crore=250,
                    v_thresh=0.60,
                    r_thresh=0.35
                ))
        return records