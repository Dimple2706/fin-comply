# Fin-Comply

**An explainable hybrid framework for DPDP Act, 2023 compliance assessment in FinTech.**

Fin-Comply takes a financial-technology company's operational records (customers, consent, transactions, access logs, retention, security events, data-subject requests, policies, systems and governance), pseudonymizes them, checks them against **16 codified DPDP Act obligations and 3 internal policy rules**, and produces a traceable **five-tier risk assessment** (Compliant / Low / Medium / High / Critical) with an evidence trail for every finding.

It checks what an organization *actually did* (its records), not what its documents *say* it does.

> Fin-Comply is a decision-support tool. Its output is not a legal determination and does not replace review by a qualified compliance or legal professional.

---

## How it works

```
 Tenant CSVs (10 files)
        │
        ▼
 1. Authentication & authorization   JWT login; every request is scoped to the tenants the user may access
        │
        ▼
 2. Ingestion & pseudonymization     field-by-field allow-list, enum validation, tenant-scoped HMAC-SHA-256 hashing
        │
        ▼
 3. Deterministic rule engine        4 agents evaluate 16 DPDP + 3 policy rules as weighted evidence signals
        │
        ▼
 4. Risk scoring                     prevalence × recurrence × impact, normalized to 0–100, with severity floors
        │                            (any Critical finding → score ≥ 65;  3+ High findings → score ≥ 45)
        ▼
 5. Supplementary ML classifier      XGBoost predicts the tier independently from 14 evidence features;
        │                            SHAP + LIME explain it. Advisory only — it never overrides a rule finding.
        ▼
 6. Application layer                FastAPI backend + React dashboard + downloadable PDF audit report
```

**The four rule-engine agents**

| Agent | Responsibility | Rules |
|---|---|---|
| RegulationAgent | Was data lawfully collected and used? (consent, notice, purpose, minors) | DPDP-001, 002, 004, 005, 007, 012 |
| AuditAgent | How is data handled over its lifetime? (retention, grievance, DSAR, audit trail) | DPDP-003, 009, 010, 011, 013 |
| RiskAgent | Exposure to higher-consequence events (sharing, encryption, breach, cross-border, processors) | DPDP-006, 008, 014, 015, 016 |
| PolicyAgent | Completeness of the tenant's own policy documentation | POLICY-001 to 003 |

Risk tiers: `0` Compliant · `<30` Low · `<55` Medium · `<75` High · `≥75` Critical.

---

## Validation results

The system is validated along four independent streams (details in `paper.tex`).

| Stream | What was tested | Result |
|---|---|---|
| **Compliancy validation** | Data minimization, hashing & pseudonymization, retention & deletion, authentication & authorization, end-to-end data integrity — using adversarial inputs, canary values and direct database inspection | All behaviours confirmed; e.g. 95/95 spot-checked rows matched exactly, raw identifiers never persisted |
| **Risk-scoring validation** | Severity floors, monotonicity, score spread | Critical floor clamps to exactly 65.0, high-count floor to exactly 45.0; duplicated rows don't inflate the score |
| **ML layer validation** | XGBoost on an independent 470-tenant **out-of-distribution** holdout built with a combinatorial covering array | **Macro F1 0.7896 · MCC 0.7401 · Accuracy 0.7851**; every error is an adjacent-tier confusion |
| **System validation** | Reproducibility and tenant isolation | 100/100 identical repeated runs; changing one tenant's data never affects another tenant |

All data is synthetic, because DPDP and banking-privacy rules prohibit using real customer records.

---

## Running it locally

**Requirements:** Python 3.11+, Node.js 18+, PostgreSQL.

### 1. Backend

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env              # then fill in the DB credentials and SECRET_KEY (≥32 chars)
```

`ANONYMIZATION_HMAC_SECRET` (≥32 chars) is required when `ENV=production`; in development a built-in fallback is used.

Create the database tables (⚠️ this drops every table in the target database first):

```bash
set DPDP_TEST_DATABASE_URL=postgresql://postgres:<password>@localhost:5432/compliance_db
python db/apply_schema_fresh.py
```

Load the five demo tenants, then start the API:

```bash
python data/ingest_test_tenants.py
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Pending schema migrations are applied automatically when the backend starts.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

### 3. Tests

Tests run against a separate database (default `dpdp_test_isolated`) and never touch your real data.
Create it once with `db/apply_schema_fresh.py` (pointing `DPDP_TEST_DATABASE_URL` at it), then:

```bash
pytest tests
```

---

## Demo walkthrough

1. **Sign in** (or create an account — each new account claims one tenant ID; claiming an existing tenant is refused with a 409).
2. **Upload** the 10 CSV files of a demo tenant from `data/test_tenants/` (e.g. `PAYFLEX-002`), or analyze an existing tenant.
3. **Dashboard:** risk score and tier, violated obligations with the exact records and fields that triggered them, penalty exposure, remediation priorities, and the ML cross-check with its SHAP/LIME explanation.
4. **Download PDF** — a full audit report for that specific audit run.
5. **Rules library** — browse all active rules and their severities.

Demo tenants: `QUICKLOAN-001`, `PAYFLEX-002`, `WEALTHNEST-003`, `RURALCRED-004`, `NEXUSNEOBANK-005`.

---

## Repository structure

```
src/
  api/              FastAPI app, routes, JWT auth and tenant authorization, request/response schemas
  anonymization/    CSV loader, field mapper (allow-list), tenant-scoped HMAC hasher, DB writer
  agent_layer/      Orchestrator, the four rule agents, signal evaluator, risk scoring
  modeling/         XGBoost training, feature extraction, ML inference layer + trained model
  explainability/   SHAP / LIME services and explanation builders
  governance/       Audit logging and bias monitoring
  intelligence/     Regulation mapper (sentence-transformer)
  report/           PDF report generator
frontend/           React + Vite dashboard
db/                 Base schema, incremental migrations, rule and policy seeders
data/
  dpdp_kb/          DPDP rules and clauses knowledge base (JSON)
  test_tenants/     The five demo tenants (10 CSVs each)
  training/         ML training features, OOD holdout features and evaluation results
  generate_data.py  Synthetic tenant generator used by every corpus-generation script
tests/              Pytest suite and deterministic fixtures
docs/               Architecture, scoring model, auth, hashing and explainability notes
docs/history/       Earlier audit reports and remediation plans (kept for reference)
outputs/            SHAP/LIME explanation outputs, bias report, per-tenant decisions
logs/               Append-only audit log
paper.tex           Research paper source
```

**Reproducibility scripts (repository root)** — these regenerate the ML datasets and reproduce the reported numbers:

| Script | Purpose |
|---|---|
| `generate_225_configs.py`, `run_phase4_batch.py` | Generate the original 225-tenant training family |
| `generate_pilot_batch.py`, `generate_pilot_batch_v2.py`, `generate_full_batch.py`, `generate_topup_batch.py` | Generate the expanded training corpus (1,602 tenants in total) |
| `generate_ood_testset.py`, `run_compliant_topup.py` | Generate the 470-tenant covering-array out-of-distribution holdout |
| `evaluate_holdout_v2.py` | Score the trained model on the OOD holdout (reports Macro F1 0.7896) |

Rebuild features and retrain with `src/modeling/build_train_v2_features.py`, `src/modeling/build_holdout_v2_features.py` and `src/modeling/train_risk_model.py`.

---

## Tech stack

Python · FastAPI · PostgreSQL · React · Vite · Tailwind CSS · XGBoost · SHAP · LIME · imbalanced-learn (SMOTE) · sentence-transformers · ReportLab · JWT · HMAC-SHA-256 · bcrypt
