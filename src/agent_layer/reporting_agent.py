"""
reporting_agent.py
==================
Assembles the structured five-section compliance report from
all ViolationRecords produced by the four evaluation agents.

This is an assembler, not an evaluator — it does not inherit
BaseAgent and does not produce ViolationRecords itself.
"""

from __future__ import annotations

import datetime
from typing import List

# Severity ordering for sorting (lower index = higher priority)
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# Must match ALL_RULE_WEIGHTS in orchestrator.py
_MAX_POSSIBLE_SCORE = 14.45  # sum of all 19 rule weights

_TOTAL_OBLIGATIONS = 19


class ReportingAgent:
    """
    Assembles a structured compliance report from ViolationRecords.

    All DB access uses parameterised queries.
    Assembly errors return a safe error dict rather than raising.
    """

    def assemble_report(
        self,
        tenant_id: str,
        all_violations: list,
        risk_score: float,
        risk_tier: str,
        compliance_score: float,
        conn,
    ) -> dict:
        """
        Returns a dict with exactly five keys:
          violation_report, risk_insights, compliance_score,
          mapped_regulations, explainable_insights
        """
        try:
            return self._build(
                tenant_id, all_violations, risk_score,
                risk_tier, compliance_score, conn
            )
        except Exception as exc:
            return {
                "error": f"ReportingAgent.assemble_report failed: {exc}",
                "tenant_id": tenant_id,
            }

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _build(
        self,
        tenant_id: str,
        all_violations: list,
        risk_score: float,
        risk_tier: str,
        compliance_score: float,
        conn,
    ) -> dict:

        violations_only = [v for v in all_violations if v.outcome == "VIOLATION"]
        warnings_only   = [v for v in all_violations if v.outcome == "WARNING"]
        non_pass        = [v for v in all_violations if v.outcome in ("VIOLATION", "WARNING")]

        # ── collect unique rule_ids that have at least one non-PASS result ──
        violation_rule_ids = list({v.rule_id for v in violations_only})
        warning_rule_ids   = list({v.rule_id for v in warnings_only})
        flagged_rule_ids   = list({v.rule_id for v in non_pass})

        # ── fetch clause + rule metadata in a single JOIN query ──────────────
        clause_rule_map = self._fetch_clause_rule_data(flagged_rule_ids, conn)

        # ── fetch max_penalty_crore for violation rules ──────────────────────
        penalty_map = {
            rid: clause_rule_map[rid]["max_penalty_crore"]
            for rid in violation_rule_ids
            if rid in clause_rule_map
        }

        return {
            "violation_report":    self._build_violation_report(violations_only, penalty_map),
            "risk_insights":       self._build_risk_insights(
                                       violations_only, risk_score, risk_tier,
                                       penalty_map
                                   ),
            "compliance_score":    self._build_compliance_score(
                                       compliance_score,
                                       violation_rule_ids,
                                       warning_rule_ids,
                                       flagged_rule_ids
                                   ),
            "mapped_regulations":  self._build_mapped_regulations(
                                       non_pass, clause_rule_map
                                   ),
            "explainable_insights": self._build_explainable_insights(
                                        violations_only, clause_rule_map
                                    ),
        }

    # ── KEY 1 ─────────────────────────────────────────────────────────────────

    def _build_violation_report(self, violations: list, penalty_map: dict) -> list:
        """
        Sorted by severity (CRITICAL → HIGH → MEDIUM → LOW).
        One entry per unique rule_id (aggregates multiple affected records).
        """
        # group by rule_id
        groups: dict[str, list] = {}
        for v in violations:
            groups.setdefault(v.rule_id, []).append(v)

        entries = []
        for rule_id, vs in groups.items():
            rep = vs[0]  # representative record for metadata
            all_signals = set()
            all_fields = set()
            for v in vs:
                all_signals.update(v.signals_fired)
                all_fields.update(getattr(v, "fields_triggered", []))

            entries.append({
                "rule_id":                rule_id,
                "rule_name":              rep.rule_name,
                "dpdp_section":           rep.dpdp_section,
                "severity":               rep.severity,
                "outcome":                rep.outcome,
                "score":                  round(max(v.rule_score for v in vs), 4),
                "signals_fired":          sorted(all_signals),
                "fields_triggered":       sorted(all_fields),
                "affected_records_count": len(vs),
                "penalty_exposure_crore": penalty_map.get(rule_id, rep.penalty_exposure_crore),
            })

        entries.sort(key=lambda e: _SEVERITY_ORDER.get(e["severity"], 99))
        return entries

    # ── KEY 2 ─────────────────────────────────────────────────────────────────

    def _build_risk_insights(
        self,
        violations: list,
        risk_score: float,
        risk_tier: str,
        penalty_map: dict,
    ) -> dict:
        groups: dict[str, list] = {}
        for v in violations:
            groups.setdefault(v.rule_id, []).append(v)

        per_rule = []
        for rule_id, vs in groups.items():
            rep = vs[0]
            # contribution_percentage = (rule_score * risk_weight / max_possible) * 100
            contribution_pct = round(
                (rep.rule_score * float(rep.risk_weight) / _MAX_POSSIBLE_SCORE) * 100, 2
            )
            per_rule.append({
                "rule_id":                  rule_id,
                "contribution_percentage":  contribution_pct,
                "outcome":                  rep.outcome,
            })

        per_rule.sort(key=lambda x: x["contribution_percentage"], reverse=True)

        critical_rules = [
            v.rule_id for v in violations
            if v.severity == "CRITICAL" and v.outcome == "VIOLATION"
        ]
        # deduplicate while preserving order
        seen: set[str] = set()
        critical_rules_deduped = [
            r for r in critical_rules if not (r in seen or seen.add(r))
        ]

        total_penalty = sum(penalty_map.values())

        return {
            "overall_score":               risk_score,
            "risk_tier":                   risk_tier,
            "per_rule_contributions":      per_rule,
            "critical_rules":              critical_rules_deduped,
            "total_penalty_exposure_crore": total_penalty,
        }

    # ── KEY 3 ─────────────────────────────────────────────────────────────────

    def _build_compliance_score(
        self,
        compliance_score: float,
        violation_rule_ids: list,
        warning_rule_ids: list,
        flagged_rule_ids: list,
    ) -> dict:
        violated_count = len(set(violation_rule_ids))
        warning_count  = len(set(warning_rule_ids) - set(violation_rule_ids))
        satisfied      = _TOTAL_OBLIGATIONS - len(set(flagged_rule_ids))

        return {
            "score_percentage":      round(compliance_score, 2),
            "satisfied_obligations": max(satisfied, 0),
            "violated_obligations":  violated_count,
            "warning_obligations":   warning_count,
            "total_obligations":     _TOTAL_OBLIGATIONS,
        }

    # ── KEY 4 ─────────────────────────────────────────────────────────────────

    def _build_mapped_regulations(
        self, non_pass: list, clause_rule_map: dict
    ) -> list:
        seen: set[str] = set()
        entries = []

        for v in non_pass:
            if v.rule_id in seen:
                continue
            seen.add(v.rule_id)

            meta = clause_rule_map.get(v.rule_id, {})
            join_tables = meta.get("join_tables", [])
            primary     = meta.get("primary_table", "")
            tables      = [primary] + (join_tables if isinstance(join_tables, list) else [])

            entry = {
                "rule_id":                v.rule_id,
                "dpdp_section":           v.dpdp_section,
                "legal_title":            meta.get("legal_title", ""),
                "plain_english_obligation": meta.get("plain_english_obligation", ""),
                "system_tables_involved": [t for t in tables if t],
                "agent_responsible":      meta.get("assigned_agent", v.agent_name),
                "violation_status":       v.outcome,
            }

            # ── Semantic enrichment (additive — never breaks the pipeline) ────
            try:
                from src.intelligence.regulation_mapper import enrich_mapped_regulation
                entry = enrich_mapped_regulation(entry)
            except Exception as _enrich_exc:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "[reporting_agent] Regulation mapping enrichment failed "
                    "for %s: %s", entry.get("rule_id"), _enrich_exc
                )

            entries.append(entry)

        # sort: VIOLATION before WARNING, then by severity
        entries.sort(key=lambda e: (
            0 if e["violation_status"] == "VIOLATION" else 1,
        ))
        return entries

    # ── KEY 5 ─────────────────────────────────────────────────────────────────

    def _build_explainable_insights(
        self, violations: list, clause_rule_map: dict
    ) -> list:
        from src.explainability.llm_narrator import narrate_violation, PIIBoundaryError  # noqa: PLC0415

        seen: set[str] = set()
        entries = []

        for v in violations:
            if v.rule_id in seen:
                continue
            seen.add(v.rule_id)

            meta             = clause_rule_map.get(v.rule_id, {})
            signal_mapping   = meta.get("signal_mapping", {})  # JSONB dict {S1: text, ...}
            legal_text       = meta.get("legal_text", "")
            evidence_signals = meta.get("evidence_signals", [])  # list from rules.evidence_signals

            fired_set = set(v.signals_fired)

            # what_happened: signal_mapping text for each fired signal only
            what_happened = {
                sig_id: desc
                for sig_id, desc in signal_mapping.items()
                if sig_id in fired_set
            }

            # record_evidence: signal_id → reason string for each fired signal
            record_evidence: dict = {}
            for sig_id, reason in zip(v.signals_fired, v.signal_reasons):
                record_evidence[sig_id] = reason

            # signal_attribution: one entry per signal in rule definition
            signal_attribution = []
            for sig in evidence_signals:
                sid = sig.get("signal_id", "")
                signal_attribution.append({
                    "signal_id":   sid,
                    "weight":      sig.get("weight", 0.0),
                    "fired":       sid in fired_set,
                    "description": sig.get("description", ""),
                })

            # fired signal dicts (full definitions) for narration
            fired_signal_defs = [
                sig for sig in evidence_signals
                if sig.get("signal_id", "") in fired_set
            ]

            # ── LLM narration ─────────────────────────────────────────────────
            try:
                narration = narrate_violation(
                    rule_id=v.rule_id,
                    rule_name=v.rule_name,
                    dpdp_section=v.dpdp_section,
                    legal_text=legal_text,
                    fired_signals=fired_signal_defs,
                )
            except PIIBoundaryError as pii_exc:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "[reporting_agent] PII blocked narration for %s: %s", v.rule_id, pii_exc
                )
                from src.explainability.llm_narrator import _fallback  # noqa
                narration = _fallback(v.rule_id, f"PIIBoundaryError: {pii_exc}")
            except Exception as exc:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "[reporting_agent] narrate_violation failed for %s: %s", v.rule_id, exc
                )
                from src.explainability.llm_narrator import _fallback  # noqa
                narration = _fallback(v.rule_id, str(exc))

            entry = {
                "rule_id":             v.rule_id,
                "rule_name":           v.rule_name,
                "what_happened":       narration.get("what_happened", what_happened),
                "legal_basis":         narration.get("legal_basis", ""),
                "dpdp_act_obligation": legal_text,
                "record_evidence":     record_evidence,
                "remediation_steps":   narration.get("remediation_steps", "LLM narration pending"),
                "signal_attribution":  signal_attribution,
                "narrated_by":         narration.get("narrated_by", "unknown"),
                "grounded":            narration.get("grounded", False),
            }
            if "fallback_reason" in narration:
                entry["fallback_reason"] = narration["fallback_reason"]

            entries.append(entry)

        return entries


    # ── DB fetch (single JOIN) ────────────────────────────────────────────────

    def _fetch_clause_rule_data(
        self, rule_ids: list, conn
    ) -> dict[str, dict]:
        """
        Fetches clause + rule metadata for the given rule_ids in a single JOIN.
        Returns {rule_id: {legal_title, plain_english_obligation, legal_text,
                           signal_mapping, max_penalty_crore, primary_table,
                           join_tables, assigned_agent, evidence_signals}}
        """
        if not rule_ids:
            return {}

        placeholders = ",".join(["%s"] * len(rule_ids))
        sql = f"""
            SELECT
                r.rule_id,
                r.primary_table,
                r.join_tables,
                r.assigned_agent,
                r.evidence_signals,
                c.legal_title,
                c.plain_english_obligation,
                c.legal_text,
                c.signal_mapping,
                c.max_penalty_crore
            FROM rules r
            JOIN clauses c ON c.clause_id = r.clause_id
            WHERE r.rule_id IN ({placeholders})
        """
        try:
            rows = conn.execute(sql, rule_ids).fetchall()
        except Exception as exc:
            print(f"[ReportingAgent] DB query failed: {exc}")
            return {}

        result = {}
        for row in rows:
            # handle both dict-rows (psycopg dict_row) and plain tuples
            if isinstance(row, dict):
                r = row
            else:
                keys = [
                    "rule_id", "primary_table", "join_tables", "assigned_agent",
                    "evidence_signals", "legal_title", "plain_english_obligation",
                    "legal_text", "signal_mapping", "max_penalty_crore"
                ]
                r = dict(zip(keys, row))

            result[r["rule_id"]] = {
                "primary_table":            r["primary_table"],
                "join_tables":              r["join_tables"] if r["join_tables"] else [],
                "assigned_agent":           r["assigned_agent"],
                "evidence_signals":         r["evidence_signals"] if r["evidence_signals"] else [],
                "legal_title":              r["legal_title"],
                "plain_english_obligation": r["plain_english_obligation"],
                "legal_text":               r["legal_text"],
                "signal_mapping":           r["signal_mapping"] if r["signal_mapping"] else {},
                "max_penalty_crore":        r["max_penalty_crore"],
            }

        return result
