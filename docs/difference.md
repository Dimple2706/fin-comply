What stays exactly the same

The FastAPI entry points (POST /analyze, POST /analyze/upload)
The entire anonymization layer (csv_loader.py, field_mapper.py, db_writer.py) — untouched
Tenant isolation via tenant_id
The ViolationRecord structure
The risk scoring formula and tier system (LOW/MEDIUM/HIGH/CRITICAL)
The agents-only-read, never-mutate principle
The overall sequence: ingest → validate → anonymize → persist → analyze → score → explain → report

These are solid. Nothing we designed touches them.

What changes and why
1. Where rules live
ExistingNewHardcoded _check_dpdp_XXX() methods inside each agent Python filerules table in Postgres — agents query at runtimeAdding a rule = editing Python + redeployingAdding a rule = inserting a DB rowdpdp_rules.json read once at startuprules table queried fresh on every compliance run
The agents themselves become thin — each one is now a 5-line loop over whatever rules the DB says belong to it. The _check_dpdp_XXX methods are deleted entirely.

2. How rules are evaluated
ExistingNewEach rule method has its own SQL query hardcodedGeneric query_builder.py builds SQL from rule's primary_table + join_tablesEach signal has its own if/else blockGeneric signal_evaluator.py evaluates any signal against any rowLogic scattered across 3 agent filesOne _run_rule_dynamic() in base_agent.py handles everything

3. A completely new path exists: Rule Authoring
The existing system has no way to add rules except editing code. The new system adds a parallel path that never existed before:
Regulatory text / amendment
        │
        ▼
LLM (Gemini) proposes structured rule JSON
        │
        ▼
Field Registry checks all signal fields exist in schema
        │
        ▼
proposed_rules table (status = pending)
        │
        ▼
Human reviews → Approve / Reject (CLI now, Streamlit later)
        │
        ▼
Live rules table → agents pick up next run
This entire path is new. The existing workflow has nothing equivalent.

4. Agent count: 3 → 5
ExistingNewRegulationAgent, AuditAgent, RiskAgent+ PolicyAgent, ReportingAgentAll hardcodedAll dynamic — load rules from DB by assigned_agent name
PolicyAgent validates rule definitions against the client's policies table. ReportingAgent assembles the 5 report types and triggers LLM narration.

5. Explainability layer
This is the most significant philosophical change:
Existing (src/explainability/service.py)NewFully deterministic — templates, no external callsStill deterministic scoring, but narration via LLMGenerates: what happened, why it's a violation, signals, remediationSame output + richer plain-English explanation grounded in actual clause textNo external dependencyGemini API call per fired rule (narration only — never makes compliance decisions)src/modeling is empty and unusedStill unused — no trained models, by design
The key point: the LLM in the new explainability layer is narrating a decision that was already made deterministically. It's not deciding anything. The score, tier, and violation status are all computed before the LLM is called.

6. Schema gains forward-compatibility
ExistingNewFixed columns per table+ additional_attributes JSONB on all 10 tablesNew rule needing new data = schema migrationNew rule needing new data = JSONB key (no migration)dpdp_rules.json static filerules + clauses + proposed_rules tables in DB

7. Governance layer (entirely new)
The existing workflow has no self-compliance mechanism. The new system adds:

PII boundary scanner — checks every outbound LLM prompt for raw PII before sending
Audit log — every rule change, LLM call, login, report written to an append-only table
RBAC — Admin / Reviewer / Viewer roles gate who can edit rules vs. view reports
Bias check — periodic score distribution comparison across tenant segments

None of these exist in the current codebase.

What the existing workflow.md says that needs updating
Two things in workflow.md are now outdated:

"The explainability layer is deterministic and does not call an external model" — this is no longer fully true. Scoring and detection remain deterministic; narration now uses Gemini. The document should clarify this distinction.
"src/modeling — files are empty and not part of the live workflow" — this stays true and should be kept that way. Our design deliberately avoids trained ML models.


One-line summary of the delta
The existing system is a static rule engine with deterministic explainability. The new system is the same engine made dynamic (rules from DB, generically evaluated), extensible (LLM-assisted rule authoring with human review), and self-governing (audit log, RBAC, PII boundary, bias check) — with LLM used only at the narration and authoring boundaries, never inside the compliance decision itself.