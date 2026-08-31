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
        import logging
        logger = logging.getLogger(self.__class__.__name__)
        try:
            return self._execute(tenant_id, conn)
        except Exception as e:
            logger.error(f"Agent execution failure in {self.name}: {type(e).__name__}")
            # Generate FAILED records for all assigned rules
            records = []
            for rule_id in self.assigned_rules:
                records.append(self._make_record(
                    rule_id=rule_id,
                    rule_name=f"Rule {rule_id}",
                    dpdp_section="Unknown",
                    tenant_id=tenant_id,
                    record_id="None",
                    outcome="FAILED",
                    rule_score=0.0,
                    signals_fired=[],
                    signal_reasons=["Agent execution failed: rule load/execution error."],
                    severity="HIGH",
                    risk_weight=0.5,
                    penalty_crore=100,
                    v_thresh=0.5,
                    r_thresh=0.3,
                    fields_triggered=[]
                ))
            return records

    def _execute_rules(self, tenant_id: str, conn: psycopg.Connection) -> List[ViolationRecord]:
        from .rule_loader import load_rules
        import logging
        logger = logging.getLogger(self.__class__.__name__)
        records = []
        try:
            rules = load_rules(self.name, conn)
        except Exception as e:
            logger.error(f"Failed to load rules for agent {self.name}: {type(e).__name__}")
            # propagate exception up to run() to trigger all-rules failure
            raise e

        for rule in rules:
            try:
                records.extend(self._run_rule_dynamic(rule, tenant_id, conn))
            except Exception as e:
                logger.error(
                    f"[RULE_FAILURE] Rule {rule['rule_id']} failed during execution. Exception: {type(e).__name__}"
                )
                records.append(self._make_record(
                    rule_id=rule['rule_id'],
                    rule_name=rule['rule_name'],
                    dpdp_section=rule['dpdp_section'],
                    tenant_id=tenant_id,
                    record_id="None",
                    outcome="FAILED",
                    rule_score=0.0,
                    signals_fired=[],
                    signal_reasons=["Rule execution failed due to an internal query or evaluation error."],
                    severity=rule['severity'],
                    risk_weight=rule['risk_weight'],
                    penalty_crore=rule.get('max_penalty_crore', 100),
                    v_thresh=rule['violation_threshold'],
                    r_thresh=rule['risk_threshold'],
                    fields_triggered=[]
                ))
        return records


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
        from .outcome_evaluator import determine_row_outcome
        from .result_state import RuleOutcome
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
            
            if not rows:
                missing_required_policy = rule['rule_id'] in {
                    'POLICY-001', 'POLICY-002', 'POLICY-003'
                }
                record = self._make_record(
                    rule_id=rule['rule_id'],
                    rule_name=rule['rule_name'],
                    dpdp_section=rule['dpdp_section'],
                    tenant_id=tenant_id,
                    record_id="None",
                    outcome=(
                        RuleOutcome.VIOLATION
                        if missing_required_policy
                        else RuleOutcome.NOT_APPLICABLE
                    ),
                    rule_score=0.0,
                    signals_fired=[],
                    signal_reasons=[
                        "Required internal policy is missing."
                        if missing_required_policy
                        else "No matching data/records found to evaluate this rule."
                    ],
                    severity=rule['severity'],
                    risk_weight=rule['risk_weight'],
                    penalty_crore=rule.get('max_penalty_crore', 100),
                    v_thresh=rule['violation_threshold'],
                    r_thresh=rule['risk_threshold'],
                    fields_triggered=[]
                )
                return [record]
            
            for row in rows:
                signal_results, fired_fields = evaluate_all_signals(
                    rule['rule_id'], signals, row
                )
                
                fired_signals = [s['signal_id'] for s in signals if signal_results.get(s['signal_id'], False)]
                
                outcome, reason = determine_row_outcome(
                    rule['rule_id'],
                    row,
                    fired_signals,
                    signals,
                    rule['violation_threshold'],
                    rule['risk_threshold']
                )
                
                # Find a good record_id from row hash fields
                record_id = None
                if 'primary_hash' in row and row['primary_hash']:
                    record_id = str(row['primary_hash']).strip()
                else:
                    for key in row.keys():
                        if key.endswith('_hash') or key.endswith('_id'):
                            if row[key]:
                                record_id = str(row[key]).strip()
                                break
                if not record_id:
                    record_id = "unknown"

                    
                score = sum(
                    s.get('weight', 0.0) for s in signals
                    if signal_results.get(s['signal_id'], False)
                )
                score = round(score, 4)

                reasons = [reason] if reason else [s['description'] for s in signals if signal_results.get(s['signal_id'], False)]
                if not reasons:
                    reasons = ["No violation detected"]

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
            # A rule query/evaluation exception is left as clearly distinguishable
            raise e
        return results

