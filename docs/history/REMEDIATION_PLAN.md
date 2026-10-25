# Fin-Comply DPDP Engine — Remediation Steps & Implementation Plan

**Prepared:** 2026-08-18
**Based On:** Full codebase audit (see `AUDIT_REPORT.md`)
**Tenant Reference:** `QUICKLOAN-001` used throughout for concrete examples

---

## Document Purpose

This document details every remediation step being applied to resolve the 15 issues identified
in the audit report. It is organized in strict execution sequence - each phase must be verified
before proceeding to the next, because upstream fixes eliminate the root causes of downstream bugs.

**The foundational rule governing all phases:**
'Fix data before models. Incorrect data ingested into the database will corrupt every downstream
layer - rule evaluations, risk scores, ML training labels, and explainability outputs.'

---

## Remediation Dependency Chain

Phase 1: Fix Ingestion (E-04, E-08, E-10)
   -> Phase 2: Reconcile Generators (E-07, E-09)
      -> Phase 3: Clean Database Reset and Re-ingestion
         -> Phase 4: Fix Rule Engine Evidence (E-11)
            -> Phase 5: Fix Risk Scoring (E-01a, E-01b)
               -> Phase 6: Fix ML Pipeline (E-02a, E-02b)
                  -> Phase 7: Fix Explainability and API Passthrough (E-03, E-06)
                     -> Phase 8: Security, SQL Hardening and Governance (E-05, E-12, E-13)

---

## Phase 1 - Fix Ingestion Integrity and Schema Mapper

**Issues Resolved:** E-04, E-08, E-10
**Target Files:** src/anonymization/db_writer.py, src/anonymization/field_mapper.py

### Remediation 1.1 - Stop Phantom FK Fabrication (E-04)

The Problem: When transaction_events references a consent_hash that does not exist in consent_records,
db_writer.py inserts a fake expired consent record. Similarly, missing third_party_hash values cause
insertion of fake system_inventory rows with dpa_signed=False.

BEFORE (db_writer.py Lines 127-151 — WRONG):
    Inserts consent record with consent_status='expired' (hardcoded fabricated violation)

AFTER (CORRECT):
    Step 1: Query consent_records WHERE consent_hash = %s AND tenant_id = %s
    Step 2: If not found, log a WARNING and skip the transaction row (continue)
    Step 3: Never execute a placeholder INSERT

Apply same pattern for third_party_hash:
    Step 1: Query system_inventory WHERE system_hash = %s AND tenant_id = %s
    Step 2: If not found, set tx['third_party_hash'] = None and log a WARNING
    Step 3: Never insert a fake system entry

Verification for QUICKLOAN-001:
  - Upload transaction CSV with non-existent consent ID
  - Confirm: zero rows created in consent_records
  - Confirm: [E-04] warning appears in application log
  - Confirm: no DPDP-001 violation generated for the skipped row

---

### Remediation 1.2 - Preserve Uploaded DPA Flags (E-08)

The Problem: field_mapper.py overwrites dpa_signed using data_processor_type:
  - internal -> forced False (hides real non-compliance)
  - other    -> forced True  (hides real non-compliance the other way)

BEFORE (field_mapper.py Lines 378-383 — WRONG):
    if data_processor_type == 'internal':
        dpa_signed = False
    else:
        dpa_signed = True

AFTER (CORRECT):
    dpa_signed = _safe_bool(row.get('dpa_signed'))
    dpa_expiry_date = _truncate_to_date(row.get('dpa_expiry_date')) or None

    Rule DPDP-016 handles applicability internally:
      - If data_processor_type == 'internal': rule skips evaluation
      - If data_processor_type != 'internal' AND dpa_signed == False: rule fires

Also update legacy pipeline.py (Lines 59-60):
    WRONG:  'dpa_signed': False  (hardcoded)
    RIGHT:  'dpa_signed': _safe_bool(row.get('dpa_signed'))

Verification:
  - Upload system_inventory with external processor marked dpa_signed=False
  - Confirm DB stores dpa_signed=FALSE
  - Confirm DPDP-016 fires for that system

---

### Remediation 1.3 - Atomic Tenant Slice Replacement (E-10)

The Problem: All 12+ INSERT statements in db_writer.py use ON CONFLICT DO NOTHING,
causing corrected re-uploads to be silently ignored.

BEFORE: INSERT INTO consent_records (...) VALUES (...) ON CONFLICT DO NOTHING

AFTER:
  Step 1: Within a single DB transaction, DELETE existing tenant data in FK-safe order:
    DELETE FROM dsar_requests      WHERE tenant_id = %s
    DELETE FROM security_events    WHERE tenant_id = %s
    DELETE FROM data_lifecycle     WHERE tenant_id = %s
    DELETE FROM access_logs        WHERE tenant_id = %s
    DELETE FROM transaction_events WHERE tenant_id = %s
    DELETE FROM consent_records    WHERE tenant_id = %s
    DELETE FROM customer_master    WHERE tenant_id = %s
    DELETE FROM policies           WHERE tenant_id = %s
    DELETE FROM system_inventory   WHERE tenant_id = %s
    DELETE FROM governance_config  WHERE tenant_id = %s

  Step 2: Run plain INSERT statements (no ON CONFLICT clause)
  Step 3: COMMIT the entire transaction atomically

Verification:
  - Upload expired consents, then re-upload with active consents
  - Confirm only active records exist in the database after re-upload
  - Confirm DPDP-001 does not fire after the corrected re-upload

---

## Phase 2 - Reconcile Synthetic Data Generators (E-07, E-09)

**Target Files:** data/generate_test_tenants.py, src/preprocessing/field_config.json

### Remediation 2.1 - Single Canonical Generator (E-09)

The Problem: Two incompatible generators (generate_data.py and generate_test_tenants.py) produce
different column sets, different hashing strategies, and non-deterministic output.

The Fix: Adopt generate_test_tenants.py as the single authoritative generator. Deprecate generate_data.py.

Enforce these guarantees:
  1. Deterministic seed: --seed 42 + same profile produces identical CSVs every run
  2. FK chain generation order (no forward references):
       governance_config -> system_inventory -> policies ->
       customer_master -> consent_records -> transaction_events ->
       access_logs -> data_lifecycle -> security_events -> dsar_requests
  3. Third-party FK integrity:
       tp_systems = [s for s in system_rows if s.data_processor_type != 'internal']
       third_party_id = random.choice(tp_systems) if is_tp_share and tp_systems else None
  4. Guardian consent FK integrity:
       all_real_consent_ids = [c.consent_id for c in consent_rows]
       guardian_consent_id = random.choice(all_real_consent_ids) if is_minor and ok else None

---

### Remediation 2.2 - Canonical Field Naming for Guardian Consent (E-07)

The Problem: generate_data.py emits guardian_consent_id (raw ID), generate_test_tenants.py
emits guardian_consent_hash (pre-hashed). The field registry and rule engine expect guardian_consent_hash.

Standard to enforce:
  - Raw CSV column name    : guardian_consent_id  (the raw source value)
  - After field_mapper.py  : becomes guardian_consent_hash in DB (via HMAC-SHA256)
  - Database column name   : guardian_consent_hash (in consent_records)
  - Rule query references  : always guardian_consent_hash

Verify in field_config.json:
    "guardian_consent_id": {
        "redacted_name": "guardian_consent_hash",
        "technique": "HMAC-SHA256 tokenization"
    }

---

## Phase 3 - Clean Database Reset and Re-ingestion

Pre-condition: Phases 1 and 2 must be complete.

Steps:
  1. TRUNCATE all tenant tables in FK-safe reverse order
  2. Re-run canonical generator for all 5 test tenants:
       QUICKLOAN-001, PAYFLEX-002, WEALTHNEST-003, RURALCRED-004, NEXUSNEOBANK-005
  3. Ingest via updated field_mapper.py and db_writer.py
  4. Verify zero phantom rows in consent_records or system_inventory
  5. Verify all guardian_consent_hash values reference real parent consent rows

---

## Phase 4 - Fix Rule Engine Evidence (E-11)

**Target Files:** src/agent_layer/signal_evaluator.py, src/api/routes.py

### Remediation 4.1 - Dynamic fields_triggered (E-11)

The Problem: routes.py Line 224 hardcodes fields_triggered=[] for every violation.

Fix in signal_evaluator.py:
    def evaluate(row_dict, signals) -> tuple[set, list, list]:
        signals_fired, signal_reasons, fields_triggered = set(), [], []
        for signal in signals:
            if _evaluate_single_signal(row_dict, signal):
                signals_fired.add(signal['signal_id'])
                signal_reasons.append(signal.get('reason', ''))
                if signal.get('field'):
                    fields_triggered.append(signal['field'])
        return signals_fired, signal_reasons, fields_triggered

Fix in violation_record.py:
    Add field: fields_triggered: List[str] = field(default_factory=list)

Fix in routes.py Line 224:
    WRONG:  fields_triggered=[]
    RIGHT:  fields_triggered=rv.get('fields_triggered', [])

Verification:
  - Trigger DPDP-001 on QUICKLOAN-001
  - Confirm API returns fields_triggered: ["consent_status", "expiry_date"]

---

## Phase 5 - Fix Risk Scoring (E-01a, E-01b)

**Target Files:** src/agent_layer/orchestrator.py, db/schema.sql

### Remediation 5.1 - Join-Aware Opportunity Denominator (E-01a)

The Problem: prevalence_ratio = affected_rows / total_table_rows
A 100% failure rate on a 200-row subset of a 50,000-row table scores as 0.4%.

Step 1: Add opportunity_query column to rules table:
    ALTER TABLE rules ADD COLUMN IF NOT EXISTS opportunity_query TEXT;

    UPDATE rules SET opportunity_query =
        'SELECT COUNT(*) FROM transaction_events WHERE tenant_id = %(tenant_id)s'
        WHERE rule_id IN ('DPDP-001', 'DPDP-002');

    UPDATE rules SET opportunity_query =
        'SELECT COUNT(*) FROM transaction_events
         WHERE tenant_id = %(tenant_id)s AND shared_with_third_party = TRUE'
        WHERE rule_id = 'DPDP-006';

    UPDATE rules SET opportunity_query =
        'SELECT COUNT(*) FROM customer_master
         WHERE tenant_id = %(tenant_id)s AND is_minor = TRUE'
        WHERE rule_id = 'DPDP-005';

Step 2: Update orchestrator.py compute_risk_score():
    opportunity_query = rule_metadata[rule_id].get('opportunity_query')
    if opportunity_query:
        row = conn.execute(opportunity_query, {'tenant_id': tenant_id}).fetchone()
        opportunity_count = max(row[0] if row else 1, 1)
    else:
        row = conn.execute(safe_count_query(table), [tenant_id]).fetchone()
        opportunity_count = max(row[0] if row else 1, 1)
    prevalence_ratio = min(affected_rows / opportunity_count, 1.0)

Verification:
  - QUICKLOAN-001: 200/200 third-party failures out of 50,000 total transactions
  - BEFORE: prevalence_ratio = 0.4%
  - AFTER:  prevalence_ratio = 100% (correct)

---

### Remediation 5.2 - Severity Floor Policy (E-01b)

The Problem: A CRITICAL finding (e.g. children's data, 200Cr max penalty) can produce a LOW tier
score after weighted normalization when other rules pass.

Fix in orchestrator.py — add AFTER computing risk_score:
    has_critical = any(v.severity == 'CRITICAL' for v in violations)
    high_count   = sum(1 for v in violations if v.severity == 'HIGH')

    if has_critical:
        risk_score = max(risk_score, 65.0)   # CRITICAL -> minimum HIGH tier
    if high_count >= 3:
        risk_score = max(risk_score, 45.0)   # 3+ HIGH  -> minimum MEDIUM tier

    # Document as explicit project policy: DPDP Act Section 9 violations
    # (minor data, max 200Cr penalty) must never be classified as LOW risk.

Verification:
  - QUICKLOAN-001 triggers DPDP-005 (CRITICAL)
  - Weighted score = 12.5 -> floor clamps to 65.0
  - risk_tier = HIGH (not LOW)

---

## Phase 6 - Fix ML Pipeline (E-02a, E-02b)

**Target File:** src/modeling/train_risk_model.py
**Pre-condition:** Phase 3 (clean re-ingestion) must be complete before retraining.

### Remediation 6.1 - Encapsulate SMOTE in imblearn Pipeline (E-02a)

The Problem: smote.fit_resample(X, y) at Line 36 runs on the full dataset before
StratifiedKFold splits at Line 68. Validation data leaks into SMOTE synthetic samples.
Final report evaluates on training data, not a holdout.

Fix:
    from imblearn.pipeline import Pipeline
    from imblearn.over_sampling import SMOTE
    from sklearn.model_selection import train_test_split, StratifiedKFold, cross_validate

    # Step 1: Reserve untouched holdout FIRST
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42
    )

    # Step 2: Wrap SMOTE inside Pipeline (SMOTE only sees training fold data)
    model_pipeline = Pipeline([
        ('smote', SMOTE(random_state=42)),
        ('xgb', XGBClassifier(max_depth=3, n_estimators=100, ...))
    ])

    # Step 3: Cross-validate on training set only
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_results = cross_validate(model_pipeline, X_train, y_train, cv=cv,
                                scoring=['f1_macro', 'matthews_corrcoef'])

    # Step 4: Evaluate on sealed holdout
    model_pipeline.fit(X_train, y_train)
    y_pred = model_pipeline.predict(X_test)

---

### Remediation 6.2 - Replace Misleading Metrics (E-02b)

The Problem: accuracy_score and f1_score(average='weighted') mask failures on minority
classes (CRITICAL, HIGH).

Fix: Replace with Macro F1, MCC, and confusion matrix as primary metrics.
    from sklearn.metrics import classification_report, matthews_corrcoef, confusion_matrix

    print(classification_report(
        y_test, y_pred,
        target_names=['COMPLIANT', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
    ))
    print('Macro F1:', f1_score(y_test, y_pred, average='macro'))
    print('MCC:', matthews_corrcoef(y_test, y_pred))
    print('Confusion Matrix:', confusion_matrix(y_test, y_pred))

    # Overall accuracy is reported last as secondary metric only

---

## Phase 7 - Fix Explainability and API Passthrough (E-03, E-06)

**Target Files:** src/api/schemas.py, src/api/routes.py, src/explainability/service.py

### Remediation 7.1 - Correctly Label Rule Contributions vs SHAP (E-06)

The Problem: Static rule signal weights are labeled phi, total_shap, and described as
'SHAP-equivalent attribution... Evidence: Lundberg & Lee (2017) NeurIPS.' They are not SHAP.

Fix in schemas.py - rename SignalDetail fields:
    WRONG:  phi: float  (with NeurIPS citation in docstring)
    RIGHT:  signal_contribution: float
            # Deterministic rule-engine heuristic. NOT TreeSHAP.
            # TreeSHAP values are only in the ml_layer field.

Fix in routes.py:
    WRONG:  phi=s.get('weight', 0.0) if s.get('fired') else 0.0
            total_shap = sum(sig.phi for sig in signals)
    RIGHT:  signal_contribution=s.get('weight', 0.0) if s.get('fired') else 0.0
            total_signal_weight = sum(sig.signal_contribution for sig in signals)

Fix in pdf_generator.py Line 417:
    WRONG:  Paragraph('<b>Total SHAP</b>', ...)
    RIGHT:  Paragraph('<b>Total Signal Weight</b>', ...)

---

### Remediation 7.2 - Expose ML Layer in API Response (E-03)

The Problem: AnalyzeResponse in schemas.py has no ml_layer field. FastAPI silently drops
the computed XGBoost predictions and SHAP values from every API response.

Fix in schemas.py:
    class AnalyzeResponse(BaseModel):
        # ... existing fields ...
        ml_layer: Optional[Dict[str, Any]] = None   # ADD THIS

Fix in routes.py (AnalyzeResponse constructor):
    return AnalyzeResponse(
        ...,
        ml_layer=analysis_result.get('ml_layer'),   # WIRE THROUGH
    )

---

## Phase 8 - Security, SQL Hardening and Run Versioning (E-05, E-12, E-13)

**Target Files:** src/api/routes.py, src/agent_layer/orchestrator.py, db/schema.sql

### Remediation 8.1 - Authenticate Rule Management Endpoints (E-05)

The Problem: POST /rules/approve and POST /rules/reject accept unauthenticated requests.

Fix in routes.py:
    def require_role(required_role):
        def dependency(current_user: User = Depends(get_current_user)):
            if current_user.role not in ['admin', required_role]:
                raise HTTPException(status_code=403, detail='Insufficient role')
            return current_user
        return dependency

    @router.post('/rules/approve/{proposal_id}')
    def approve_rule(
        proposal_id: int,
        current_user: User = Depends(require_role('admin'))   # ADD THIS
    ): ...

    @router.post('/rules/reject/{proposal_id}')
    def reject_rule(
        proposal_id: int,
        current_user: User = Depends(require_role('admin'))   # ADD THIS
    ): ...

Verification: curl -X POST /api/rules/approve/1 (no token) -> 401 Unauthorized

---

### Remediation 8.2 - Safe SQL Identifier Composition (E-12)

The Problem: orchestrator.py Line 133 interpolates table names from the DB directly via f-strings.
    f'SELECT COUNT(*) FROM {table} WHERE tenant_id = %s'

Fix:
    from psycopg.sql import SQL, Identifier

    ALLOWED_TABLES = {
        'customer_master', 'consent_records', 'transaction_events',
        'access_logs', 'data_lifecycle', 'security_events',
        'dsar_requests', 'governance_config', 'system_inventory', 'policies'
    }

    def _safe_count(table, tenant_id, conn):
        if table not in ALLOWED_TABLES:
            logger.error(f'[E-12] Rejected unsafe table name: {table}')
            return 1
        query = SQL('SELECT COUNT(*) FROM {t} WHERE tenant_id = %s').format(
            t=Identifier(table)
        )
        row = conn.execute(query, [tenant_id]).fetchone()
        return max(row[0] if row else 1, 1)

---

### Remediation 8.3 - Run-Level Versioning and Audit Metadata (E-13)

The Problem: Audit logs record only risk_score and timestamp. No model hash, rule version,
or schema version is persisted, making historical runs non-reproducible.

Step 1: Add run_metadata table to db/schema.sql:
    CREATE TABLE IF NOT EXISTS run_metadata (
        run_id          SERIAL PRIMARY KEY,
        tenant_id       VARCHAR(50) NOT NULL,
        run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        rules_version   INTEGER,        -- MAX(id) from rules table at run time
        schema_version  VARCHAR(20),    -- Hardcoded string e.g. v1.2
        model_hash      VARCHAR(64),    -- SHA-256 of risk_model.pkl
        git_commit      VARCHAR(40),    -- Optional: git rev-parse HEAD
        risk_score      FLOAT,
        risk_tier       VARCHAR(20),
        total_violations INTEGER
    );

Step 2: Write to run_metadata at end of each analysis run in orchestrator.py:
    import hashlib
    with open('src/modeling/risk_model.pkl', 'rb') as f:
        model_hash = hashlib.sha256(f.read()).hexdigest()

    conn.execute(INSERT INTO run_metadata ..., {
        'tenant_id': tenant_id,
        'rules_v': conn.execute('SELECT MAX(id) FROM rules').fetchone()[0],
        'schema_v': 'v1.2',
        'model_hash': model_hash,
        'risk_score': risk_score,
        'risk_tier': tier,
        'violations': len(violations_only)
    })

---

## Complete Remediation Summary

| Phase | Issue   | Files Modified                    | Fix Type                          | Effort |
|-------|---------|-----------------------------------|-----------------------------------|--------|
| 1.1   | E-04    | db_writer.py                      | FK validation + skip-with-log     | Medium |
| 1.2   | E-08    | field_mapper.py, pipeline.py      | Read uploaded DPA value           | Small  |
| 1.3   | E-10    | db_writer.py                      | Atomic tenant delete + re-insert  | Medium |
| 2.1   | E-09    | generate_test_tenants.py          | Canonical generator, FK chain     | Medium |
| 2.2   | E-07    | field_config.json, field_mapper   | Canonical guardian_consent naming | Small  |
| 3     | -       | Database                          | Truncate and re-ingest all tenants| Ops    |
| 4.1   | E-11    | signal_evaluator.py, routes.py    | Wire fields_triggered from signals| Small  |
| 5.1   | E-01a   | orchestrator.py, db/schema.sql    | Opportunity query per rule        | Medium |
| 5.2   | E-01b   | orchestrator.py                   | Post-aggregation severity floors  | Small  |
| 6.1   | E-02a   | train_risk_model.py               | imblearn Pipeline + holdout set   | Medium |
| 6.2   | E-02b   | train_risk_model.py               | Macro F1 + MCC + confusion matrix | Small  |
| 7.1   | E-06    | service.py, routes.py, schemas.py | Rename to signal_contribution     | Small  |
| 7.2   | E-03    | schemas.py, routes.py             | Add ml_layer field to schema      | Small  |
| 8.1   | E-05    | routes.py                         | FastAPI auth dependency on rules  | Small  |
| 8.2   | E-12    | orchestrator.py                   | ALLOWED_TABLES + Identifier       | Small  |
| 8.3   | E-13    | orchestrator.py, db/schema.sql    | run_metadata table + SHA-256 hash | Medium |

---

## Verification Checklist - QUICKLOAN-001

After all phases are complete:

- [ ] Upload CSV with non-existent consent_id -> zero phantom rows in consent_records
- [ ] Upload system_inventory with dpa_signed=False (external) -> DB stores FALSE
- [ ] Re-upload corrected consent data -> stale records replaced, DPDP-001 clears
- [ ] Trigger DPDP-001 -> fields_triggered contains ['consent_status', 'expiry_date']
- [ ] 200/200 third-party DPDP-006 failures -> prevalence_ratio = 100% (not 0.4%)
- [ ] DPDP-005 CRITICAL triggered -> risk_score >= 65, risk_tier = HIGH
- [ ] POST /api/rules/approve/1 (no auth) -> 401 Unauthorized
- [ ] GET /api/analyze response -> ml_layer field is present with XGBoost prediction
- [ ] signals_analysis[0] -> has signal_contribution field (not phi or shap)
- [ ] run_metadata table -> new row with model_hash after each /analyze call

---

*End of Remediation Plan - Version 1.0 - 2026-08-18*
