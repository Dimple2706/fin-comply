"""
src/modeling/train_risk_model.py
================================
Trains the XGBoost compliance risk classification model with:
- Strict train/test isolation (20% sealed holdout test set)
- Encapsulated SMOTE within an imblearn pipeline (E-02a fix: zero data leakage)
- Multi-class Macro F1, MCC, and Confusion Matrix metrics (E-02b fix)
- TreeExplainer SHAP feature importance calculation
- Complete persistence of risk_model.pkl, training_data.npy, and metadata
"""

import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
import shap
from pathlib import Path
import warnings

from xgboost import XGBClassifier
from imblearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_validate
from sklearn.metrics import (
    classification_report,
    f1_score,
    matthews_corrcoef,
    confusion_matrix,
    accuracy_score
)

LABEL_NAMES = ["COMPLIANT", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

def train_pipeline():
    print("==================================================")
    print("FIN-COMPLY XGBOOST RISK MODEL TRAINING (E-02a & E-02b)")
    print("==================================================\n")

    # STEP 1: Load and validate dataset
    features_csv = "data/training/training_features.csv"
    if not os.path.exists(features_csv):
        raise FileNotFoundError(f"Missing {features_csv}. Run prepare_risk_features.py first.")

    df = pd.read_csv(features_csv)
    X = df.drop(columns=["label"])
    y = df["label"].astype(int)

    feature_names = X.columns.tolist()
    print("Dataset Summary:")
    print(f"  Total Profiles: {len(df)}")
    print(f"  Features ({len(feature_names)}): {feature_names}")
    print(f"  Classes ({len(np.unique(y))}): {sorted(np.unique(y).tolist())}\n")

    print("Class Distribution in Full Dataset:")
    counts = y.value_counts()
    for cls in sorted(counts.index):
        pct = (counts[cls] / len(y)) * 100
        print(f"  Class {cls} ({LABEL_NAMES[cls]:<9}): {counts[cls]:>4} ({pct:>5.1f}%)")
    print()

    # STEP 2 [E-02a FIX]: Reserve untouched holdout FIRST
    print("Step 2: Splitting 80% Train / 20% Sealed Test Holdout (Stratified)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.20,
        stratify=y,
        random_state=42
    )
    print(f"  Training set size : {len(X_train)} samples")
    print(f"  Sealed test holdout: {len(X_test)} samples\n")

    # STEP 3 [E-02a FIX]: Construct imblearn Pipeline (SMOTE isolated to training folds)
    xgb_clf = XGBClassifier(
        max_depth=3,
        n_estimators=100,
        learning_rate=0.1,
        reg_lambda=1.0,
        reg_alpha=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="mlogloss",
        random_state=42
    )

    pipeline = Pipeline([
        ("smote", SMOTE(random_state=42)),
        ("xgb", xgb_clf)
    ])

    # STEP 4: 5-Fold Cross-Validation strictly on training data
    print("Step 3: 5-Fold Cross-Validation on Training Set (SMOTE in-fold only)...")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_validate(
        pipeline,
        X_train,
        y_train,
        cv=skf,
        scoring={
            "f1_macro": "f1_macro",
            "mcc": lambda est, x, y_t: matthews_corrcoef(y_t, est.predict(x)),
            "accuracy": "accuracy"
        },
        return_train_score=False
    )

    mean_f1_macro = np.mean(cv_scores["test_f1_macro"])
    std_f1_macro = np.std(cv_scores["test_f1_macro"])
    mean_mcc = np.mean(cv_scores["test_mcc"])
    mean_acc = np.mean(cv_scores["test_accuracy"])

    print(f"  CV Macro F1 : {mean_f1_macro:.4f} ± {std_f1_macro:.4f}")
    print(f"  CV MCC      : {mean_mcc:.4f}")
    print(f"  CV Accuracy : {mean_acc:.4f}\n")

    # STEP 5: Fit Pipeline on full Training Set and Evaluate on Sealed Holdout Test Set
    print("Step 4: Fitting Pipeline on Training Set & Evaluating on Sealed Holdout...")
    pipeline.fit(X_train, y_train)

    y_pred_test = pipeline.predict(X_test)
    test_macro_f1 = f1_score(y_test, y_pred_test, average="macro")
    test_mcc = matthews_corrcoef(y_test, y_pred_test)
    test_acc = accuracy_score(y_test, y_pred_test)
    cm = confusion_matrix(y_test, y_pred_test)

    print("\n" + "=" * 60)
    print("SEALED HOLDOUT TEST SET EVALUATION REPORT (E-02b)")
    print("=" * 60)
    print(f"Holdout Macro F1 Score : {test_macro_f1:.4f} (Primary Metric)")
    print(f"Holdout MCC Score      : {test_mcc:.4f} (Primary Metric)")
    print(f"Holdout Accuracy       : {test_acc:.4f} (Secondary Metric)\n")

    present_classes = sorted(np.unique(np.concatenate([y_test, y_pred_test])).tolist())
    target_names = [LABEL_NAMES[c] for c in present_classes]

    print("Classification Report on Sealed Holdout:")
    print(classification_report(y_test, y_pred_test, target_names=target_names, digits=4))

    print("Confusion Matrix on Sealed Holdout:")
    print(cm)
    print("=" * 60 + "\n")

    # STEP 6: SHAP Global Feature Importance
    print("Step 5: Computing SHAP Feature Attributions...")
    fitted_xgb = pipeline.named_steps["xgb"]
    explainer = shap.TreeExplainer(fitted_xgb)
    shap_values = explainer(X_train)

    if isinstance(shap_values.values, list):
        mean_abs_shap = np.mean([np.abs(sv).mean(axis=0) for sv in shap_values.values], axis=0)
    elif len(shap_values.values.shape) == 3:
        mean_abs_shap = np.abs(shap_values.values).mean(axis=(0, 2))
    else:
        mean_abs_shap = np.abs(shap_values.values).mean(axis=0)

    shap_dict = {feat: float(val) for feat, val in zip(feature_names, mean_abs_shap)}
    sorted_features = sorted(shap_dict.items(), key=lambda x: x[1], reverse=True)
    top_3 = [x[0] for x in sorted_features[:3]]

    print("Top Features by Global SHAP Importance:")
    for rank, (feat, val) in enumerate(sorted_features[:5], 1):
        print(f"  {rank}. {feat:<28}: mean |SHAP| = {val:.4f}")
    print()

    # STEP 7: Save model artifacts
    print("Step 6: Saving Model Artifacts...")
    Path("src/modeling").mkdir(parents=True, exist_ok=True)
    Path("outputs/explanations").mkdir(parents=True, exist_ok=True)
    Path("data/training").mkdir(parents=True, exist_ok=True)

    # Save fitted XGBoost classifier
    model_path = "src/modeling/risk_model.pkl"
    joblib.dump(fitted_xgb, model_path)
    native_model_path = "src/modeling/risk_model.json"
    fitted_xgb.save_model(native_model_path)

    # Save training numpy data for LIME / explainability background
    data_path = "data/training/training_data.npy"
    np.save(data_path, X_train.values)

    # Save feature names
    feat_path = "data/training/feature_names.json"
    with open(feat_path, "w") as f:
        json.dump(feature_names, f, indent=2)

    # Save label map
    label_map_path = "src/modeling/label_map.json"
    label_map = {
        "0": "COMPLIANT",
        "1": "LOW",
        "2": "MEDIUM",
        "3": "HIGH",
        "4": "CRITICAL"
    }
    with open(label_map_path, "w") as f:
        json.dump(label_map, f, indent=2)

    # Save SHAP global output
    shap_path = "outputs/explanations/shap_global.json"
    shap_output = {
        "feature_names": feature_names,
        "mean_abs_shap_values": shap_dict,
        "top_3_features": top_3,
        "model_version": "xgboost_leakage_free_v2",
        "trained_on_samples": len(X_train),
        "test_holdout_macro_f1": round(test_macro_f1, 4),
        "test_holdout_mcc": round(test_mcc, 4)
    }
    with open(shap_path, "w") as f:
        json.dump(shap_output, f, indent=2)

    print(f"  [OK] Saved {model_path} ({os.path.getsize(model_path)} bytes)")
    print(f"  [OK] Saved {native_model_path} ({os.path.getsize(native_model_path)} bytes)")
    print(f"  [OK] Saved {data_path} ({X_train.shape})")
    print(f"  [OK] Saved {feat_path}")
    print(f"  [OK] Saved {label_map_path}")
    print(f"  [OK] Saved {shap_path}")

    # STEP 8: Sanity check on sample profiles against their true metadata labels
    print("\nStep 7: Sanity Check on Sample Profiles...")
    meta_path = "data/training/training_metadata.csv"
    if os.path.exists(meta_path):
        meta_df = pd.read_csv(meta_path)
        # Sample 1 from each class to verify
        for target_label in range(5):
            sub = meta_df[meta_df["label"] == target_label]
            if not sub.empty:
                idx = sub.index[0]
                target_id = sub.iloc[0]["tenant_id"]
                true_label_name = sub.iloc[0]["label_name"]
                vec = X.iloc[[idx]]
                pred_cls = fitted_xgb.predict(vec)[0]
                prob = fitted_xgb.predict_proba(vec)[0]
                pred_label = label_map[str(pred_cls)]
                print(f"  - {target_id} (True: {true_label_name}): Predicted = {pred_label} (Prob: {prob[pred_cls]*100:.1f}%)")
                assert pred_label == true_label_name, f"Mismatch for {target_id}: expected {true_label_name}, got {pred_label}"

    print("\n==================================================")
    print("PHASE 6 (E-02a & E-02b) TRAINING & EVALUATION COMPLETE!")
    print("==================================================")

if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    train_pipeline()
