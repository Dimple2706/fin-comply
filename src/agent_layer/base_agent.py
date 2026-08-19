import abc
import psycopg
from typing import List, Dict
from .violation_record import ViolationRecord

class BaseAgent(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """
        Agent name (e.g. regulation_agent).
        """
        pass

    @property
    @abc.abstractmethod
    def assigned_rules(self) -> List[str]:
        """
        Assigned DPDP rules.
        """
        pass

    @abc.abstractmethod
    def _execute(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        """
        Implementation-specific logic.
        """
        pass

    def run(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        try:
            return self._execute(tenant_id, conn)
        except Exception as e:
            print(f"Error in {self.name} for tenant {tenant_id}: {e}")
            return []

    def _compute_rule_score(self, signals_fired: List[str], signal_weights: Dict[str, float]) -> float:
        total = sum(signal_weights[s] for s in signals_fired)
        return round(total, 4)

    def _classify_outcome(self, score: float, v_threshold: float, r_threshold: float) -> str:
        if score >= v_threshold:
            return "VIOLATION"
        if score >= r_threshold:
            return "WARNING"
        return "PASS"

    def _make_record(
        self, rule_id: str, rule_name: str, dpdp_section: str,
        tenant_id: str, record_id: str, outcome: str,
        rule_score: float, signals_fired: List[str], signal_reasons: List[str],
        severity: str, risk_weight: float,
        penalty_crore: int, v_thresh: float, r_thresh: float,
        fields_triggered: List[str] = None
    ) -> ViolationRecord:
        return ViolationRecord(
            rule_id=rule_id,
            rule_name=rule_name,
            dpdp_section=dpdp_section,
            agent_name=self.name,
            tenant_id=tenant_id,
            record_id=record_id,
            outcome=outcome,
            rule_score=float(rule_score) if rule_score is not None else None,
            signals_fired=signals_fired,
            signal_reasons=signal_reasons,
            severity=severity,
            risk_weight=float(risk_weight) if risk_weight is not None else None,
            penalty_exposure_crore=float(penalty_crore) if penalty_crore is not None else None,
            violation_threshold=float(v_thresh) if v_thresh is not None else None,
            risk_threshold=float(r_thresh) if r_thresh is not None else None,
            fields_triggered=fields_triggered or []
        )

    def _run_rule_dynamic(self, rule: dict, tenant_id: str, conn) -> list:
        from .query_builder import build_query
        from .signal_evaluator import evaluate_all_signals
        import logging

        if not hasattr(self, 'logger'):
            self.logger = logging.getLogger(self.__class__.__name__)

        results = []
        try:
            sql, params = build_query(rule, tenant_id)
            rows = conn.execute(sql, params).fetchall()
            
            # Convert rows to dicts
            if rows and not isinstance(rows[0], dict):
                col_names = [desc[0] for desc in conn.description]
                rows = [dict(zip(col_names, row)) for row in rows]

            signals = rule.get('evidence_signals', [])
            
            for row in rows:
                signal_results, fired_fields = evaluate_all_signals(
                    rule['rule_id'], signals, row
                )
                
                score = sum(
                    s.get('weight', 0.0) for s in signals
                    if signal_results.get(s['signal_id'], False)
                )
                score = round(score, 4)
                
                outcome = self._classify_outcome(
                    score,
                    rule['violation_threshold'],
                    rule['risk_threshold']
                )
                
                if outcome != 'PASS':
                    # Find a good record_id from row hash fields
                    record_id = None
                    for key in row.keys():
                        if key.endswith('_hash') or key.endswith('_id'):
                            # prefer hash or id
                            record_id = row[key]
                            break
                    if not record_id:
                        record_id = "unknown"
                        
                    reasons = [s['description'] for s in signals if signal_results.get(s['signal_id'], False)]
                    fired_signals = [s['signal_id'] for s in signals if signal_results.get(s['signal_id'], False)]

                    record = self._make_record(
                        rule_id=rule['rule_id'],
                        rule_name=rule['rule_name'],
                        dpdp_section=rule['dpdp_section'],
                        tenant_id=tenant_id,
                        record_id=record_id,
                        outcome=outcome,
                        rule_score=score,
                        signals_fired=fired_signals,
                        signal_reasons=reasons,
                        severity=rule['severity'],
                        risk_weight=rule['risk_weight'],
                        penalty_crore=rule.get('max_penalty_crore', 100),
                        v_thresh=rule['violation_threshold'],
                        r_thresh=rule['risk_threshold'],
                        fields_triggered=fired_fields
                    )
                    results.append(record)
                    
        except Exception as e:
            conn.rollback()
            self.logger.error(
                f"Dynamic eval failed for {rule['rule_id']}: {e}"
            )
        
        return results
