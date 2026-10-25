# Fin-Comply ML Readiness Audit Report

**Date:** July 23, 2026
**Subject:** Readiness Assessment for XGBoost, SHAP, and LIME Integration

This report details the current state of the Fin-Comply repository regarding the proposed integration of a machine learning (ML) risk scoring layer built on XGBoost, SHAP, and LIME.

---

## 1. Current State of Machine Learning Infrastructure

### 1.1 `src/modeling/` Directory
The scaffolding for the ML layer exists, but the implementation is entirely missing.
* `__init__.py`: **Empty** (0 bytes)
* `prepare_risk_features.py`: **Empty** (0 bytes)
* `train_risk_model.py`: **Empty** (0 bytes)

**Assessment:** The project structure anticipates an ML layer, but no feature engineering or model training code has been written.

### 1.2 Data Generation and Configuration
The scripts required to generate synthetic violation profiles for training the XGBoost model are entirely absent from the repository.
* `generate_data.py`: **Missing**
* `generator_config.json`: **Missing**

**Assessment:** Without a data generator, we currently have no way to produce the training datasets required to teach the XGBoost model how different rule violations interact.

### 1.3 Dependencies (`requirements.txt`)
The Python environment is partially configured for the ML layer:
* `xgboost==3.2.0` (Present)
* `shap==0.51.0` (Present)
* `lime` (**Missing**)

**Assessment:** The `lime` package must be added to `requirements.txt` before we can build the counterfactual explanation layer.

---

## 2. Current State of the Orchestrator and Risk Scoring

### 2.1 The `orchestrator.py` Runtime
The `run_compliance_analysis()` function successfully coordinates the agent layer (Regulation, Audit, Risk, Policy) and returns a structured dictionary containing the following keys:
* `tenant_id` (str), `run_timestamp` (str), `status` (str)
* `total_violations` (int), `total_warnings` (int)
* `risk_score` (float), `risk_tier` (str), `risk_contributions` (dict)
* `agent_breakdown` (dict), `violation_report` (list), `risk_insights` (dict)
* `compliance_score` (dict), `mapped_regulations` (list), `explainable_insights` (list)

### 2.2 Feature Vectors vs. Raw Violations
Currently, the orchestrator does **not** compute a tenant-level "Feature Vector". It strictly relies on a deterministic mathematical formula (`Likelihood x Impact x Risk Weight`) applied directly to raw `ViolationRecord` objects.

**Assessment:** We will need to inject a feature extraction pipeline into `orchestrator.py` to aggregate raw violations into the structured feature vector (e.g., `critical_rule_count`, `max_prevalence_ratio`) that XGBoost expects.

---

## 3. Explanability (SHAP & LIME) Footprint

While the actual ML implementation is missing, the frontend schemas, PDF generator, and output directories are already aggressively hardcoded to expect SHAP and LIME outputs.

### 3.1 Hardcoded "Mock" Explanations
The repository contains JSON files with mock SHAP and LIME structures (all values set to `0.0`), indicating where the real ML outputs should eventually go:
* `outputs/explanations/shap_local.json`
* `outputs/explanations/shap_global.json`
* `outputs/explanations/lime_explanation.json`

### 3.2 PDF and API Expectations
The API schemas and PDF reporting logic currently "fake" SHAP values by re-branding the deterministic signal weights as "Analytical SHAP":
* `src/report/pdf_generator.py` explicitly renders tables titled **"Signal Attribution (SHAP-equivalent)"** and contains text stating: *"Signal attribution uses analytical SHAP (Lundberg & Lee, 2017) for linear additive scoring models."*
* `src/api/schemas.py` defines fields like `phi: float # SHAP value` for signal-level attribution.

---

## 4. Training Data Availability

Querying the `evaluation_results` table in the PostgreSQL `compliance_db` reveals the following schema:
* `id` (bigint)
* `tenant_id` (character varying)
* `result_json` (jsonb)
* `risk_score` (numeric)
* `created_at` (timestamp with time zone)

**Assessment:** The `result_json` column stores the full historical output of every orchestrator run. This historical JSON data can be queried and flattened to generate initial training data for the XGBoost model, supplementing the synthetic data generation we still need to build.

---

## Conclusion & Next Steps

The repository is currently operating exclusively on the deterministic engine. The ML layer is fully stubbed out (empty modeling files, mock JSON outputs, and PDF tables waiting for data), but the actual logic is entirely unwritten.

To build the XGBoost ML layer, the following steps are required:
1. Add `lime` to `requirements.txt`.
2. Write the `generate_data.py` script to create synthetic tenant violation profiles.
3. Write `src/modeling/prepare_risk_features.py` to convert `result_json` rows into XGBoost feature vectors.
4. Write `src/modeling/train_risk_model.py` to train the XGBoost classifier.
5. Update `orchestrator.py` to load the trained model, calculate SHAP/LIME values at runtime, and replace the mock values with genuine ML predictions.
