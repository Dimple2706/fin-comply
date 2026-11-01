import os
import json
import logging
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

# --- PART A: Module-level initialization ---
_MODEL = None
_TRAINING_DATA = None
_FEATURE_NAMES = None
_LABEL_MAP = None
_SHAP_EXPLAINER = None
_LIME_CLASS_NAMES = ['COMPLIANT', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

# Expected class labels for probability validation
_EXPECTED_CLASSES = {'COMPLIANT', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}

# This order is the inference contract used to train risk_model.json.
# Keep feature construction name-based so adding a feature cannot silently
# shift the meaning of every value that follows it.
RUNTIME_FEATURE_NAMES = [
    "n_violations",
    "n_warnings",
    "n_critical_rules_fired",
    "n_high_rules_fired",
    "breach_rule_fired",
    "minor_data_rule_fired",
    "max_rule_score",
    "max_prevalence_ratio",
    "consent_violation_count",
    "retention_violation_count",
    "encryption_violation_count",
    "access_violation_count",
    "policy_violation_count",
    "total_penalty_exposure",
]

try:
    import joblib
    import shap
    from xgboost import XGBClassifier
    from lime.lime_tabular import LimeTabularExplainer

    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    _NATIVE_MODEL_PATH = Path(__file__).with_name("risk_model.json")
    if _NATIVE_MODEL_PATH.exists():
        _MODEL = XGBClassifier()
        _MODEL.load_model(_NATIVE_MODEL_PATH)
    else:
        _MODEL = joblib.load(Path(__file__).with_name("risk_model.pkl"))
    _TRAINING_DATA = np.load(_PROJECT_ROOT / 'data/training/training_data.npy')
    
    with open(_PROJECT_ROOT / 'data/training/feature_names.json', 'r', encoding='utf-8') as f:
        _FEATURE_NAMES = json.load(f)

    if _FEATURE_NAMES != RUNTIME_FEATURE_NAMES:
        raise ValueError(
            "ML feature contract mismatch between runtime extraction and "
            "data/training/feature_names.json"
        )

    model_feature_count = int(_MODEL.get_booster().num_features())
    if model_feature_count != len(_FEATURE_NAMES):
        raise ValueError(
            f"Model expects {model_feature_count} features but the feature "
            f"contract defines {len(_FEATURE_NAMES)}"
        )

    if _TRAINING_DATA.ndim != 2 or _TRAINING_DATA.shape[1] != len(_FEATURE_NAMES):
        raise ValueError(
            "LIME training data does not match the model feature contract: "
            f"expected {len(_FEATURE_NAMES)} columns, got "
            f"{_TRAINING_DATA.shape[1] if _TRAINING_DATA.ndim == 2 else 'invalid shape'}"
        )
        
    with open(Path(__file__).with_name('label_map.json'), 'r', encoding='utf-8') as f:
        _LABEL_MAP = json.load(f)

    _SHAP_EXPLAINER = shap.TreeExplainer(_MODEL)

    # LIME explainer is created per-call in run_ml_layer for reproducibility
    # (random_state=42 reset each time). Module-level artifacts stored above.
except Exception as e:
    logger.error(f"Failed to initialize ML layer components: {e}")


def _validate_ml_output(result: dict) -> dict:
    """
    Validate ML output contract before returning to the API.
    Returns the result if valid, or an error dict if any check fails.
    """
    probs = result.get('probabilities', {})

    # Check 1: Exactly five class probabilities
    if set(probs.keys()) != _EXPECTED_CLASSES:
        return {
            'ml_available': False,
            'reason': f'Expected 5 class probabilities {sorted(_EXPECTED_CLASSES)}, '
                      f'got {sorted(probs.keys())}'
        }

    # Check 2: Every probability is finite
    for cls, val in probs.items():
        if not np.isfinite(val):
            return {
                'ml_available': False,
                'reason': f'Non-finite probability for {cls}: {val}'
            }

    # Check 3: Every probability is in [0, 100]
    for cls, val in probs.items():
        if val < 0 or val > 100:
            return {
                'ml_available': False,
                'reason': f'Probability for {cls} out of range [0, 100]: {val}'
            }

    # Check 4: Sum ≈ 100 (tolerance ±1.0 for rounding)
    prob_sum = sum(probs.values())
    if abs(prob_sum - 100.0) > 1.0:
        return {
            'ml_available': False,
            'reason': f'Probabilities sum to {prob_sum:.2f}, expected ≈100'
        }

    # Check 5: predicted_tier is the class with the highest probability
    predicted = result.get('predicted_tier')
    max_class = max(probs, key=probs.get)
    if predicted != max_class:
        return {
            'ml_available': False,
            'reason': f'predicted_tier={predicted} but highest probability '
                      f'class is {max_class} ({probs[max_class]}%)'
        }

    # Check 6: confidence_percent matches predicted_tier probability
    conf = result.get('confidence_percent')
    expected_conf = probs[predicted]
    if conf is None or abs(conf - expected_conf) > 0.01:
        return {
            'ml_available': False,
            'reason': f'confidence_percent={conf} does not match '
                      f'probabilities[{predicted}]={expected_conf}'
        }

    return result


def extract_features(report: dict) -> np.ndarray:
    """
    Extracts the complete model feature contract in training order.
    """
    violation_report = report.get("violation_report", [])
    risk_insights = report.get("risk_insights", {})
    
    # Pre-compute some counts/lists
    violations_only = [v for v in violation_report if v.get("outcome") == "VIOLATION"]
    warnings_only = [v for v in violation_report if v.get("outcome") == "WARNING"]
    
    # Training uses the full occurrence counts stored at report level. The
    # violation_report is intentionally grouped to one entry per rule for
    # presentation, so its length is only a fallback for small/unit reports.
    n_violations = int(report.get("total_violations", len(violations_only)))
    n_warnings = int(report.get("total_warnings", len(warnings_only)))
    
    critical_rules_fired = set(v.get("rule_id") for v in violations_only if v.get("severity") == "CRITICAL")
    n_critical_rules_fired = len(critical_rules_fired)
    
    high_rules_fired = set(v.get("rule_id") for v in violations_only if v.get("severity") == "HIGH")
    n_high_rules_fired = len(high_rules_fired)
    
    breach_rule_fired = 1 if any(v.get("rule_id") == "DPDP-014" for v in violations_only) else 0
    minor_data_rule_fired = 1 if any(v.get("rule_id") == "DPDP-005" for v in violations_only) else 0
    
    max_rule_score = 0.0
    if violation_report:
        scores = [v.get("score", 0.0) for v in violation_report if "score" in v]
        if scores:
            max_rule_score = float(max(scores))
        else:
            per_rule_contribs = risk_insights.get("per_rule_contributions", [])
            if per_rule_contribs:
                max_rule_score = float(max(c.get("contribution_percentage", 0.0) for c in per_rule_contribs))
                
    per_rule_contribs = risk_insights.get("per_rule_contributions", [])
    max_prevalence_ratio = 0.0
    if per_rule_contribs:
        max_prevalence_ratio = float(max(c.get("contribution_percentage", 0.0) for c in per_rule_contribs)) / 100.0
        
    consent_rules = {'DPDP-001', 'DPDP-002', 'DPDP-004', 'DPDP-007'}
    consent_violation_count = sum(1 for v in violations_only if v.get("rule_id") in consent_rules)
    
    retention_rules = {'DPDP-003', 'DPDP-011'}
    retention_violation_count = sum(1 for v in violations_only if v.get("rule_id") in retention_rules)
    
    encryption_violation_count = sum(1 for v in violations_only if v.get("rule_id") == 'DPDP-008')
    access_violation_count = sum(1 for v in violations_only if v.get("rule_id") == 'DPDP-013')
    
    # Must match prepare_risk_features.extract_features exactly: count POLICY-*
    # violations in violation_report. Internal-control findings are reported
    # separately and never appear there, so this is 0 in all training data;
    # counting them at inference would feed the model values it never saw.
    policy_rules = {'POLICY-001', 'POLICY-002', 'POLICY-003'}
    policy_violation_count = sum(1 for v in violations_only if v.get("rule_id") in policy_rules)

    # The training pipeline derives this value from the maximum statutory
    # exposure attached to the unique violated DPDP rules. ReportingAgent has
    # already calculated the same value for the current assessment.
    total_penalty_exposure = risk_insights.get(
        "total_penalty_exposure_crore",
        report.get("total_penalty_exposure_crore", 0.0),
    )
    if total_penalty_exposure is None:
        total_penalty_exposure = 0.0

    feature_values = {
        "n_violations": n_violations,
        "n_warnings": n_warnings,
        "n_critical_rules_fired": n_critical_rules_fired,
        "n_high_rules_fired": n_high_rules_fired,
        "breach_rule_fired": breach_rule_fired,
        "minor_data_rule_fired": minor_data_rule_fired,
        "max_rule_score": max_rule_score,
        "max_prevalence_ratio": max_prevalence_ratio,
        "consent_violation_count": consent_violation_count,
        "retention_violation_count": retention_violation_count,
        "encryption_violation_count": encryption_violation_count,
        "access_violation_count": access_violation_count,
        "policy_violation_count": policy_violation_count,
        "total_penalty_exposure": total_penalty_exposure,
    }

    feature_list = [float(feature_values[name]) for name in RUNTIME_FEATURE_NAMES]
    return np.asarray(feature_list, dtype=float).reshape(1, len(RUNTIME_FEATURE_NAMES))


def run_ml_layer(report: dict) -> dict:
    if _MODEL is None:
        return {'ml_available': False, 'reason': 'Model artifacts failed to load'}
        
    feature_vector = extract_features(report)

    if _FEATURE_NAMES != RUNTIME_FEATURE_NAMES:
        raise ValueError("Runtime feature order no longer matches the trained model contract")
    if feature_vector.shape[1] != len(_FEATURE_NAMES):
        raise ValueError(
            f"Feature shape mismatch, expected {len(_FEATURE_NAMES)}, "
            f"got {feature_vector.shape[1]}"
        )
    
    prediction_int = int(_MODEL.predict(feature_vector)[0])
    prediction_label = _LABEL_MAP[str(prediction_int)]
    
    probabilities = _MODEL.predict_proba(feature_vector)[0]
    prob_dict = {
        _LABEL_MAP[str(i)]: round(float(p) * 100, 1)
        for i, p in enumerate(probabilities)
    }
    
    # SHAP local explanation
    if _SHAP_EXPLAINER is not None:
        shap_values = _SHAP_EXPLAINER.shap_values(feature_vector)
        
        # Multiclass XGBoost returns a list of arrays or a 3D array depending on shap version
        if isinstance(shap_values, list):
            target_shap_vals = shap_values[prediction_int][0]
        elif len(shap_values.shape) == 3:
            target_shap_vals = shap_values[0, :, prediction_int]
        else:
            target_shap_vals = shap_values[0]
        
        raw_shap_dict = {
            feature_name: round(float(shap_val), 4)
            for feature_name, shap_val in zip(_FEATURE_NAMES, target_shap_vals)
        }
        
        # Sort by absolute value descending
        sorted_shap = sorted(raw_shap_dict.items(), key=lambda x: abs(x[1]), reverse=True)
        
        feature_contributions = []
        for rank, (feat, val) in enumerate(sorted_shap, 1):
            feat_idx = _FEATURE_NAMES.index(feat)
            feat_val = feature_vector[0][feat_idx]
            feature_contributions.append({
                "rank": rank,
                "feature": feat,
                "value": float(feat_val),
                "shap_value": val,
                "direction": "positive" if val >= 0 else "negative"
            })
            
        shap_local = {
            "type": "local",
            "instance_index": 0,
            "prediction": {
                "class": prediction_label,
                "confidence": float(probabilities[prediction_int]),
                "class_probabilities": {k: float(v)/100.0 for k, v in prob_dict.items()}
            },
            "base_value": round(float(_SHAP_EXPLAINER.expected_value[prediction_int]), 4) if isinstance(_SHAP_EXPLAINER.expected_value, (list, np.ndarray)) else round(float(_SHAP_EXPLAINER.expected_value), 4),
            "feature_contributions": feature_contributions,
            "top_positive_features": [f["feature"] for f in feature_contributions if f["direction"] == "positive"][:3],
            "top_negative_features": [f["feature"] for f in feature_contributions if f["direction"] == "negative"][:3],
            # include the exact requested dict structure just in case
            "raw_contributions": {f: v for f, v in sorted_shap}
        }
    else:
        shap_local = {'error': 'SHAP unavailable'}
        
    # LIME explanation — fresh explainer per call for reproducibility
    if _TRAINING_DATA is not None and _FEATURE_NAMES is not None:
        from lime.lime_tabular import LimeTabularExplainer as _LimeExplainer
        _lime_local = _LimeExplainer(
            _TRAINING_DATA,
            feature_names=_FEATURE_NAMES,
            class_names=_LIME_CLASS_NAMES,
            mode='classification',
            random_state=42
        )
        exp = _lime_local.explain_instance(
            feature_vector[0],
            _MODEL.predict_proba,
            num_samples=500,
            labels=[prediction_int]
        )
        lime_list = exp.as_list(label=prediction_int)
        
        feature_contributions_lime = []
        for feat_str, weight in lime_list:
            feature_contributions_lime.append({
                "feature": feat_str,
                "coefficient": round(float(weight), 4),
                "abs_contribution": abs(round(float(weight), 4)),
                "direction": "positive" if weight >= 0 else "negative"
            })
            
        lime_explanation = {
            "type": "local_lime",
            "instance_index": 0,
            "prediction": {
                "class": prediction_label,
                "confidence": float(probabilities[prediction_int]),
                "class_probabilities": {k: float(v)/100.0 for k, v in prob_dict.items()}
            },
            "model": "xgboost_severity_aligned_v3",
            "num_samples": 500,
            "feature_contributions": feature_contributions_lime,
            "explanation": f"Key factors driving {prediction_label} prediction. To improve tier, focus on reducing: {lime_list[0][0] if lime_list else 'N/A'}",
            
            # The exact keys requested in the prompt
            "predicted_class": prediction_label,
            "top_features": [
                {'feature': feat, 'weight': round(float(w), 4)}
                for feat, w in lime_list[:5]
            ],
            "counterfactual_summary": (
                f"Key factors driving {prediction_label} prediction. "
                f"To improve tier, focus on reducing: "
                f"{lime_list[0][0] if lime_list else 'N/A'}"
            )
        }
    else:
        lime_explanation = {'error': 'LIME unavailable'}
        
    # API inference is side-effect free by default. Optional diagnostic exports
    # must be explicitly enabled and directed to an operator-controlled path.
    output_dir = os.getenv("ML_EXPLANATION_OUTPUT_DIR")
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        if 'error' not in shap_local:
            with open(os.path.join(output_dir, 'shap_local.json'), 'w', encoding='utf-8') as f:
                json.dump(shap_local, f, indent=2)

        if 'error' not in lime_explanation:
            with open(os.path.join(output_dir, 'lime_explanation.json'), 'w', encoding='utf-8') as f:
                json.dump(lime_explanation, f, indent=2)
            
    confidence_pct = prob_dict.get(prediction_label, 0.0)

    result = {
        'ml_available': True,
        'predicted_tier': prediction_label,
        'predicted_tier_int': prediction_int,
        'probabilities': prob_dict,
        'probability_unit': 'percent',
        'confidence_percent': confidence_pct,
        'feature_vector': {
            name: float(val) for name, val in zip(_FEATURE_NAMES, feature_vector[0])
        },
        'shap_explanation': shap_local,
        'lime_explanation': lime_explanation,
        'model_version': 'xgboost_severity_aligned_v3',
        'agrees_with_deterministic': (
            prediction_label == report.get('risk_tier')
        )
    }

    return _validate_ml_output(result)
