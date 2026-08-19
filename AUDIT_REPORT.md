# Fin-Comply DPDP Engine — Comprehensive Code & Architecture Audit Report

**Prepared:** 2026-08-18  
**Scope:** Full codebase audit of `c:\Users\aakas\OneDrive\Desktop\capstone_f`  
**Reference PDF:** `Fin_Comply_DPDP_Engine_Remediation_Report.pdf`  
**Tenant Used for Illustration:** `QUICKLOAN-001`

---

## Executive Summary

A full codebase inspection was conducted across all layers of the Fin-Comply DPDP Compliance Engine.
**All 13 issues (E-01 through E-13)** documented in the Remediation Report were confirmed to be
actively present in the current source code. No issue was found to have been previously resolved.
Additionally, the audit uncovered code patterns that deepen the severity of several reported issues,
particularly around database ingestion, ML training methodology, and API security.

The issues span 7 layers: data ingestion, synthetic data generation, rule engine, risk scoring,
machine learning, explainability (XAI), and API/security. They form a dependency chain — bugs
upstream corrupt the outputs of every downstream layer.

**Foundational guardrail confirmed by audit:** *"Fix data before models."*  
The ML model was trained on data contaminated by manufactured placeholder records (E-04), which means
model predictions, SHAP attributions, and risk scores are all derived from a corrupted baseline.

---

## Issue Severity Legend

| Badge       | Meaning                                                                 |
|-------------|-------------------------------------------------------------------------|
| 🔴 CRITICAL | Directly corrupts compliance outputs or creates a security vulnerability |
| 🟠 HIGH     | Causes systematic misrepresentation of results                           |
| 🟡 MEDIUM   | Reduces auditability, traceability, or reproducibility                  |

---

## Layer 1 — Data Ingestion & Schema Integrity

---

### ⚠ Issue E-04 — Phantom Consent & Third-Party Record Fabrication
**Severity:** 🔴 CRITICAL  
**Files:**
- [`src/anonymization/db_writer.py` — Lines 127–151](src/anonymization/db_writer.py)
- [`src/anonymization/db_writer.py` — Lines 280–298](src/anonymization/db_writer.py)

**Description:**  
When the ingestion pipeline processes `transaction_events` and encounters a row whose `consent_hash`
or `third_party_hash` references a non-existent foreign key, `db_writer.py` does not reject the row.
Instead, it **actively inserts a fabricated record** into the database to satisfy the FK constraint.

For consent, it creates an artificial consent record with `consent_status = 'expired'`,
`notice_provided = True`, `is_bundled = False`, and `consent_channel = 'app'` — all hardcoded default
values that bear no relationship to the tenant's actual data.

For third parties, it inserts a fake `system_inventory` row with `dpa_signed = False` and
`data_processor_type = 'third_party_processor'`.

**Precise Code Evidence:**
```python
# db_writer.py Lines 127-151: Manufactured expired consent
cur.execute("""
    INSERT INTO consent_records
    (consent_hash, customer_hash, tenant_id, consent_status, ...)
    VALUES (%s, %s, %s, %s, ...)
    ON CONFLICT DO NOTHING
""", (
    consent_hash,
    customer_hash,
    tenant_for_row,
    "expired",  # <--- HARDCODED STATUS — FABRICATED VIOLATION
    ...
))

# db_writer.py Lines 280-298: Manufactured third party with dpa_signed=False
cur.execute("""
    INSERT INTO system_inventory
    (system_hash, tenant_id, system_name, ..., dpa_signed, ...)
    VALUES (%s, %s, %s, ..., %s, ...)
    ON CONFLICT DO NOTHING
""", (
    third_party_hash,
    tx["tenant_id"],
    "Derived Third Party",   # <--- FABRICATED NAME
    ...
    False,                   # <--- HARDCODED dpa_signed=False — FABRICATED NON-COMPLIANCE
    ...
))
```

**Impact on QUICKLOAN-001:**  
If QuickLoan uploads a transaction referencing an unmatched consent ID, the engine creates a
fabricated expired consent record. QuickLoan is then flagged for `DPDP-001` (Invalid Consent)
based on a record that was **never uploaded by the tenant**. This is a false positive that
corrupts the risk score, the audit trail, and ML training labels.

**Classification:** Data Integrity Breach — Corrupts audit baseline for all downstream layers.

---

### ⚠ Issue E-10 — Stale Data Accumulation via `ON CONFLICT DO NOTHING`
**Severity:** 🔴 CRITICAL  
**File:** [`src/anonymization/db_writer.py`](src/anonymization/db_writer.py)  
**Occurrences:** Lines 69, 134, 166, 188, 210, 231, 253, 286, 306, 327, 351, 372, 402

**Description:**  
Every single `INSERT` statement across all ten tables in `db_writer.py` uses `ON CONFLICT DO NOTHING`.
This means that when a tenant re-uploads corrected data (e.g. after obtaining fresh consents, fixing
DPA agreements, or correcting retention dates), the database ignores all updates and silently retains
the original stale rows.

**Precise Code Evidence (representative sample):**
```sql
-- db_writer.py Line 134 — consent_records:
INSERT INTO consent_records (...) VALUES (...) ON CONFLICT DO NOTHING;

-- db_writer.py Line 188 — system_inventory:
INSERT INTO system_inventory (...) VALUES (...) ON CONFLICT DO NOTHING;
```

**Impact on QUICKLOAN-001:**  
QuickLoan renews consent agreements and re-uploads `consent_records.csv` with `consent_status='active'`
for all customers. Because the original `consent_status='expired'` rows still exist in the database,
`ON CONFLICT DO NOTHING` leaves them unchanged. The compliance engine continues to flag
QuickLoan as violating DPDP-001, even though the corrected data was uploaded.

**Classification:** Data Integrity — Prevents tenant data from being corrected without manual SQL intervention.

---

### ⚠ Issue E-08 — Field Mapper Overwrites Uploaded DPA Flags with Hardcoded Values
**Severity:** 🟠 HIGH  
**File:** [`src/anonymization/field_mapper.py` — Lines 378–383](src/anonymization/field_mapper.py)

**Description:**  
The `_anonymize_system_inventory` function in `field_mapper.py` completely ignores the `dpa_signed`
column uploaded by the tenant. Instead, it determines `dpa_signed` purely from `data_processor_type`:
`internal` → forced to `False`; all other types → forced to `True`. This preempts both rule
evaluation and actual tenant reality.

**Precise Code Evidence:**
```python
# field_mapper.py Lines 378–383:
if data_processor_type == "internal":
    dpa_signed = False          # <--- OVERWRITES UPLOADED VALUE — CANNOT DETECT REAL VIOLATIONS
    dpa_expiry_date = None
else:
    dpa_signed = True           # <--- OVERWRITES UPLOADED VALUE — HIDES REAL NON-COMPLIANCE
    dpa_expiry_date = ...

# Also present in pipeline.py Lines 59-61 (legacy mapper, still active):
"data_processor_type": "internal",
"dpa_signed": False,            # <--- HARDCODED
```

**Impact on QUICKLOAN-001:**  
QuickLoan uses an external credit bureau (`data_processor_type = 'third_party_processor'`) but
has not signed a Data Processing Agreement yet (`dpa_signed = False` in their upload). The mapper
forces `dpa_signed = True`, so the violation for DPDP-016 is suppressed and never triggered.
The compliance engine falsely certifies QuickLoan as compliant with third-party DPA requirements.

**Classification:** Logic Error — Masks genuine compliance violations.

---

## Layer 2 — Synthetic Data Generation

---

### ⚠ Issue E-07 — Schema Field Name Mismatch: `guardian_consent_id` vs `guardian_consent_hash`
**Severity:** 🟠 HIGH  
**Files:**
- [`src/preprocessing/field_config.json` — Line 140](src/preprocessing/field_config.json): defines `guardian_consent_id` as source
- [`src/anonymization/field_mapper.py` — Line 206](src/anonymization/field_mapper.py): uses `_hash_or_none(row.get("guardian_consent_id"), ...)`
- [`src/agent_layer/field_registry_f.py` — Line 36](src/agent_layer/field_registry_f.py): expects `guardian_consent_hash`
- [`data/generate_data.py` — Lines 257–265](data/generate_data.py): generates column named `guardian_consent_id`
- [`data/generate_test_tenants.py` — Lines 342–352`](data/generate_test_tenants.py): uses `guardian_consent_hash`

**Description:**  
The old generator (`generate_data.py`) outputs a field named `guardian_consent_id` (a raw ID string).
The new generator (`generate_test_tenants.py`) outputs `guardian_consent_hash` (pre-hashed). The
field_config mapper reads `guardian_consent_id` but the field registry and rule engine query
`guardian_consent_hash`. This mismatch causes valid guardian consent records to appear absent
during rule evaluation.

**Impact on QUICKLOAN-001:**  
A minor customer at QuickLoan has a valid guardian consent record. The generator writes it as
`guardian_consent_id`, but the rule engine queries `guardian_consent_hash`. Because the DB column
is `NULL` (the mapping was never executed correctly), QuickLoan is falsely flagged for DPDP-005
(Children's Data Without Guardian Consent) on a record where consent genuinely exists.

**Classification:** Schema Mismatch — Creates systematic false positives for DPDP-005 violations.

---

### ⚠ Issue E-09 — Two Incompatible, Conflicting Generator Scripts
**Severity:** 🟠 HIGH  
**Files:**
- [`data/generate_data.py`](data/generate_data.py) — profile-driven, 46 KB, outputs raw schema fields
- [`data/generate_test_tenants.py`](data/generate_test_tenants.py) — fixed tenants, 29 KB, outputs pre-hashed fields
- Root-level scripts: [`generate_225_configs.py`](generate_225_configs.py), [`generate_topup_configs.py`](generate_topup_configs.py)

**Description:**  
Two fundamentally incompatible generators co-exist, each producing CSV files with different column
sets, different FK resolution strategies, and different hashing decisions. There is no single
authoritative data generation path.

- `generate_data.py` outputs: `event_id, customer_id, consent_id` (raw IDs)
- `generate_test_tenants.py` outputs: `event_hash, customer_hash, consent_hash` (pre-hashed)

There is no deterministic seed mechanism that guarantees identical datasets across runs.

**Impact:** Non-reproducible test scenarios. ML training data generated from one run cannot be
validated against a second run. Rule-specific violation rates drift between test cycles.

**Classification:** Process Gap — Prevents reproducibility of test data and validation results.

---

## Layer 3 — Rule Engine & Evidence

---

### ⚠ Issue E-11 — `fields_triggered` Always Returns Empty List
**Severity:** 🟡 MEDIUM  
**File:** [`src/api/routes.py` — Line 224](src/api/routes.py)

**Description:**  
The `ViolationItem` schema includes `fields_triggered: List[str]` intended to identify which
specific data fields caused a rule to fire. However, in `routes.py`, this is hardcoded as an
empty list for every violation, regardless of what the signal evaluator detected.

**Precise Code Evidence:**
```python
# routes.py Line 224:
violation_items.append(
    ViolationItem(
        ...
        fields_triggered=[],    # <--- ALWAYS EMPTY — SIGNAL EVIDENCE DISCARDED
        ...
    )
)
```

**Impact on QUICKLOAN-001:**  
A QuickLoan DPDP-001 violation is fired because `consent_status='expired'` AND
`event_date > expiry_date`. The API returns `fields_triggered: []`, so automated audit tools,
the frontend dashboard, and PDF reports cannot identify which specific fields caused the trigger.

**Classification:** Functional Gap — Disables signal-level transparency in compliance reports.

---

## Layer 4 — Risk Scoring

---

### ⚠ Issue E-01 (Denominator) — Raw Table Count Dilutes Rule-Specific Violation Rates
**Severity:** 🔴 CRITICAL  
**File:** [`src/agent_layer/orchestrator.py` — Lines 119–152, 227–236](src/agent_layer/orchestrator.py)

**Description:**  
The `compute_risk_score` function determines `prevalence_ratio` by dividing the number of
violation occurrences by the total row count of the rule's **entire source table** —
not by the count of rows that were actually within the rule's scope.

**Precise Code Evidence:**
```python
# orchestrator.py Lines 132-144: Counts ALL rows in table
row = conn.execute(
    f"SELECT COUNT(*) AS count FROM {table} WHERE tenant_id = %s",
    [tenant_id]
).fetchone()
table_counts[table] = max(row["count"] if row else 1, 1)

# orchestrator.py Lines 233-236: Divides by total, not applicable count
prevalence_ratio = min(affected_rows / total_rows, 1.0)
```

**Impact on QUICKLOAN-001:**  
`DPDP-006` (Third-Party Sharing Without Consent) evaluates only `transaction_events` where
`shared_with_third_party = TRUE`. For QuickLoan, 200 such transactions exist and 200 of them
fail the DPA check — a 100% failure rate on applicable records. But because QuickLoan has
50,000 total transactions, the formula computes $200 / 50000 = 0.4\%$, a near-zero prevalence
ratio. The DPDP-006 contribution to the risk score is reduced to negligible noise, and a
100%-failure compliance scenario appears to be a minor issue.

**Classification:** Scoring Logic Error — Systematically under-reports violations on targeted data subsets.

---

### ⚠ Issue E-01 (Severity) — No Severity Floor for Critical Findings
**Severity:** 🔴 CRITICAL  
**File:** [`src/agent_layer/orchestrator.py` — Lines 329–369](src/agent_layer/orchestrator.py)

**Description:**  
The risk tier assignment is purely computed from the normalized weighted sum of all rule contributions.
There is no post-aggregation policy floor that guarantees a minimum score or tier when a
`CRITICAL` severity finding is present.

**Precise Code Evidence:**
```python
# orchestrator.py Lines 329-368: Pure weighted normalization — no floor
if risk_score == 0:
    tier = "COMPLIANT"
elif risk_score < 30:
    tier = "LOW"
elif risk_score < 55:
    tier = "MEDIUM"
elif risk_score < 75:
    tier = "HIGH"
else:
    tier = "CRITICAL"
# No exception for CRITICAL severity violations. None at all.
```

**Impact on QUICKLOAN-001:**  
QuickLoan has 1 minor customer whose guardian consent is not recorded — a `CRITICAL` DPDP-005
violation carrying a maximum penalty of ₹200 crore under the DPDP Act. But QuickLoan passes
all other 19 rules. The weighted normalization produces a risk score of ~12.5, classified as
`LOW`. A company with a maximum statutory exposure of ₹200 crore is labeled `LOW` risk.

**Classification:** Scoring Policy Gap — Compliance verdicts are legally incorrect for critical violations.

---

## Layer 5 — Machine Learning

---

### ⚠ Issue E-02 (Leakage) — SMOTE Applied Before Cross-Validation Splitting
**Severity:** 🔴 CRITICAL  
**File:** [`src/modeling/train_risk_model.py` — Lines 34–70](src/modeling/train_risk_model.py)

**Description:**  
`SMOTE.fit_resample(X, y)` is called on the full dataset at Line 36 before
`StratifiedKFold.split()` is called at Line 68. This means synthetic samples are generated
by interpolating between real training AND validation samples. When the data is then split
into folds, validation folds contain synthetic data that was interpolated from validation instances,
which directly caused data leakage into training folds.

**Precise Code Evidence:**
```python
# train_risk_model.py Lines 35-36:
smote = SMOTE(random_state=42)
X_smote, y_smote = smote.fit_resample(X, y)    # <--- LEAKAGE: ENTIRE DATASET RESAMPLED

# train_risk_model.py Lines 62-68: Folds created AFTER SMOTE (too late)
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
for train_idx, val_idx in skf.split(X_smote, y_smote):
    X_train_f, X_val_f = X_smote.iloc[train_idx], X_smote.iloc[val_idx]
    # X_val_f already contains synthetic samples from validation instances

# train_risk_model.py Lines 120-122: Final report on TRAINING data (not test holdout)
y_pred_full = final_model.predict(X_smote)      # <--- EVALUATED ON TRAINING DATA
print(classification_report(y_smote, y_pred_full))
```

**Impact:** Cross-validation scores are inflated. The final classification report shows in-sample
training performance, not generalization performance. The model has never been evaluated on data
it has genuinely not seen.

**Classification:** ML Methodology Error — Produces unreliable model performance estimates.

---

### ⚠ Issue E-02 (Metrics) — Misleading Evaluation Metrics Hide Critical Class Failures
**Severity:** 🟠 HIGH  
**File:** [`src/modeling/train_risk_model.py` — Lines 86–100](src/modeling/train_risk_model.py)

**Description:**  
Cross-validation uses `accuracy_score` and `f1_score(..., average='weighted')` as primary metrics.
On an imbalanced 5-class dataset (COMPLIANT/LOW/MEDIUM/HIGH/CRITICAL), overall accuracy and
weighted F1 are dominated by the majority class and can score > 0.95 even if the model
misclassifies 100% of `CRITICAL` instances.

**Precise Code Evidence:**
```python
# train_risk_model.py Lines 87-92:
acc = accuracy_score(y_val_f, preds)
f1 = f1_score(y_val_f, preds, average="weighted")   # <--- WEIGHTED, NOT MACRO
```

**Classification:** Evaluation Methodology Gap — Critical class detection is never verified.

---

## Layer 6 — Explainability (XAI)

---

### ⚠ Issue E-06 — Deterministic Rule Weights Falsely Labeled as SHAP Values
**Severity:** 🟠 HIGH  
**Files:**
- [`src/explainability/service.py` — Lines 15–97](src/explainability/service.py)
- [`src/api/schemas.py` — Lines 24–51`](src/api/schemas.py)
- [`src/api/routes.py` — Lines 192–196`](src/api/routes.py)
- [`src/report/pdf_generator.py` — Lines 417–418`](src/report/pdf_generator.py)

**Description:**  
`RULE_EXPLANATIONS` in `service.py` defines static hand-crafted weights for each signal (e.g.
`"S1": {"weight": 0.40}`). In `routes.py`, these weights are assigned to a field named `phi`
when a signal fires, and summed into `total_shap`. The `SignalDetail` schema in `schemas.py`
carries the docstring: *"SHAP-equivalent attribution... Evidence: Lundberg & Lee (2017) NeurIPS."*

**Precise Code Evidence:**
```python
# schemas.py Lines 26-36: Falsely labeled
class SignalDetail(BaseModel):
    """
    SHAP-equivalent attribution for one signal.
    phi = weight × fired (1 if fired, 0 if not).
    Evidence: Lundberg & Lee (2017) NeurIPS.
    """
    phi: float   # <--- NOT SHAP. This is a deterministic rule weight.

# routes.py Line 192:
phi=s.get("weight", 0.0) if s.get("fired", False) else 0.0  # <--- WEIGHT, NOT SHAP

# routes.py Lines 195-196:
total_shap = sum(sig.phi for sig in signals)  # <--- TOTAL RULE WEIGHT LABELED AS SHAP
```

**Impact:** The compliance reports, API responses, and PDF outputs misrepresent engineered
heuristics as mathematically-computed Shapley values. This is both factually incorrect
and academically misleading.

**Classification:** Misrepresentation — Incorrectly cites published ML research to describe simple arithmetic.

---

## Layer 7 — API & Security

---

### ⚠ Issue E-03 — ML Layer Payload Dropped Before API Response
**Severity:** 🟠 HIGH  
**Files:**
- [`src/agent_layer/orchestrator.py` — Lines 594–628`](src/agent_layer/orchestrator.py)
- [`src/api/schemas.py` — Lines 99–112`](src/api/schemas.py)

**Description:**  
`orchestrator.py` computes a full `ml_layer` dict (containing XGBoost prediction, confidence,
SHAP values, and risk class) and assigns it to `report["ml_layer"]` (Lines 604–619). However,
the Pydantic `AnalyzeResponse` schema in `schemas.py` does not include an `ml_layer` field.
FastAPI silently drops any extra fields during response serialization.

**Precise Code Evidence:**
```python
# orchestrator.py Line 736-739: ML result included in internal report dict
"ml_layer": report.get("ml_layer")

# schemas.py Lines 99-112: AnalyzeResponse has NO ml_layer field
class AnalyzeResponse(BaseModel):
    tenant_id: str
    total_obligations: int
    ...
    total_penalty_exposure_crore: Optional[int] = None
    # ml_layer is completely absent — FastAPI drops it silently
```

**Impact:** The entire ML prediction layer is computed but never delivered to the frontend or
to any API consumer. The XGBoost model and its SHAP attributions are operationally dead.

**Classification:** Integration Gap — ML output is produced but permanently discarded.

---

### ⚠ Issue E-05 — Rule Management Endpoints Require No Authentication
**Severity:** 🔴 CRITICAL  
**File:** [`src/api/routes.py` — Lines 589, 690`](src/api/routes.py)

**Description:**  
The `approve_rule` endpoint (`POST /rules/approve/{proposal_id}`) and `reject_rule` endpoint
(`POST /rules/reject/{proposal_id}`) have no authentication or authorization dependency. Any
caller — authenticated or not — can approve or reject proposed compliance rules, directly
altering the active rule set in the PostgreSQL database.

**Precise Code Evidence:**
```python
# routes.py Lines 589-592:
@router.post("/rules/approve/{proposal_id}")
def approve_rule(
    proposal_id: int,
    # NO Depends(get_current_user), NO role check
):
```

**Impact:** An unauthenticated HTTP request from any network-accessible client can disable,
approve, or reject any compliance rule. A malicious actor could disable `DPDP-005` (Children's
Data) or `DPDP-001` (Consent) with a single API call.

**Classification:** Security Vulnerability — Critical unauthenticated write access to system rules.

---

### ⚠ Issue E-12 — Dynamic SQL Table Identifiers via f-String Interpolation
**Severity:** 🔴 CRITICAL  
**File:** [`src/agent_layer/orchestrator.py` — Lines 132–139`](src/agent_layer/orchestrator.py)

**Description:**  
Table names sourced from the `rules` database table are inserted directly into SQL queries
via Python f-string formatting. If a malicious or malformed rule is inserted into the `rules`
table, the `primary_table` field can contain SQL injection payloads.

**Precise Code Evidence:**
```python
# orchestrator.py Lines 132-139:
row = conn.execute(
    f"""
    SELECT COUNT(*) AS count
    FROM {table}          # <--- RAW f-STRING — SQL INJECTION RISK
    WHERE tenant_id = %s
    """,
    [tenant_id]
).fetchone()
```

**Impact:** If `primary_table` contains `"consent_records; DROP TABLE customers; --"`, the
query drops the customers table. Even without malicious intent, a typo in a rule entry
can cause database errors that crash the compliance analysis pipeline.

**Classification:** Security Vulnerability — SQL Injection via unsanitized identifier interpolation.

---

### ⚠ Issue E-13 — No Run-Level Versioning or Reproducibility Metadata
**Severity:** 🟡 MEDIUM  
**Files:**
- [`src/governance/audit_logger.py`](src/governance/audit_logger.py)
- [`src/agent_layer/orchestrator.py` — Lines 743–780`](src/agent_layer/orchestrator.py)

**Description:**  
Governance audit logs record `risk_score`, `tenant_id`, and `timestamp` but do not persist:
- Which version of the rules was active during the run
- The model file hash of the XGBoost `risk_model.pkl` used
- The schema version of the ingested data
- The git commit hash of the codebase at run time

Without these, it is impossible to reproduce any historical compliance result.

**Classification:** Governance Gap — Non-reproducible audit history violates DPDP audit trail principles.

---

## Complete Issue Summary Table

| Issue ID | Layer | Description | Severity | File(s) |
|----------|-------|-------------|----------|---------|
| **E-04** | Ingestion | Phantom consent & third-party record fabrication | 🔴 CRITICAL | `db_writer.py` |
| **E-10** | Ingestion | Stale data via `ON CONFLICT DO NOTHING` | 🔴 CRITICAL | `db_writer.py` |
| **E-08** | Mapper | DPA flags overwritten by hardcoded mapper logic | 🟠 HIGH | `field_mapper.py` |
| **E-07** | Generator | Field name mismatch: `guardian_consent_id` vs `_hash` | 🟠 HIGH | `generate_data.py`, `field_mapper.py` |
| **E-09** | Generator | Two incompatible, non-deterministic generator scripts | 🟠 HIGH | `generate_data.py`, `generate_test_tenants.py` |
| **E-11** | Rule Engine | `fields_triggered` hardcoded to empty list | 🟡 MEDIUM | `routes.py` |
| **E-01a** | Scoring | Denominator dilution via total table row count | 🔴 CRITICAL | `orchestrator.py` |
| **E-01b** | Scoring | No severity floor for CRITICAL findings | 🔴 CRITICAL | `orchestrator.py` |
| **E-02a** | ML | SMOTE leakage before cross-validation split | 🔴 CRITICAL | `train_risk_model.py` |
| **E-02b** | ML | Misleading evaluation metrics (weighted F1, accuracy) | 🟠 HIGH | `train_risk_model.py` |
| **E-06** | XAI | Rule weights mislabeled as SHAP/phi values | 🟠 HIGH | `service.py`, `routes.py`, `schemas.py` |
| **E-03** | API | ML layer dropped before API response | 🟠 HIGH | `schemas.py`, `orchestrator.py` |
| **E-05** | Security | Unauthenticated rule approval/rejection endpoints | 🔴 CRITICAL | `routes.py` |
| **E-12** | Security | SQL injection via f-string table identifier interpolation | 🔴 CRITICAL | `orchestrator.py` |
| **E-13** | Governance | No run-level versioning or model hash in audit logs | 🟡 MEDIUM | `audit_logger.py`, `orchestrator.py` |

**Critical Issues: 7 · High Issues: 6 · Medium Issues: 2**

---

## Dependency Chain of Corruption

```
E-04 (Phantom Records) ─────────────────────────────────────┐
                                                              ↓
E-10 (Stale Data) ──────────────────────┐          E-01 (Scoring Dilution)
                                         ↓                    ↓
E-07/E-08/E-09 (Generator/Mapper) ──→ Corrupt DB ──→ Corrupt ML Training (E-02)
                                                              ↓
                                               Inflated Cross-Val Scores (E-02b)
                                                              ↓
                                        E-06 (Fake SHAP) + E-03 (ML Dropped)
                                                              ↓
                                          E-05/E-12 (Security — system-level)
                                                              ↓
                                          E-13 (No Audit Trail — governance-level)
```

All downstream layers (rules, scoring, ML, explainability, API, governance) are built on a
corrupted data foundation introduced by E-04, E-07, E-08, E-09, and E-10.

---

*End of Audit Report — Version 1.0 — 2026-08-18*
