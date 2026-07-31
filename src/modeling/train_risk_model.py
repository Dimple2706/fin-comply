import pandas as pd
import numpy as np
import joblib
import json
import os
import shap
from pathlib import Path
from xgboost import XGBClassifier
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score, f1_score, classification_report

def main():
    print("=== FIN-COMPLY XGBOOST TRAINING REPORT ===\n")
    
    # STEP A — Load and validate data
    df = pd.read_csv("data/training/training_features.csv")
    X = df.drop(columns=["label"])
    y = df["label"]
    
    print("Dataset:")
    print(f"  Profiles generated: {len(df)}")
    print(f"  Features: {X.shape[1]}")
    print(f"  Classes: {len(y.unique())}\n")
    
    print("Class distribution before SMOTE:")
    counts = y.value_counts()
    total = len(y)
    for cls in sorted(counts.index):
        pct = (counts[cls] / total) * 100
        print(f"  Class {cls}: {counts[cls]} ({pct:.1f}%)")
    print()

    # STEP B — Apply SMOTE with integer rounding
    smote = SMOTE(random_state=42)
    X_smote, y_smote = smote.fit_resample(X, y)
    
    # Rounding rules
    int_cols = [
        "n_violations", "n_warnings", "n_critical_rules_fired", "n_high_rules_fired",
        "consent_violation_count", "retention_violation_count", 
        "encryption_violation_count", "access_violation_count", "policy_violation_count"
    ]
    for col in int_cols:
        X_smote[col] = np.round(X_smote[col]).astype(int)
        X_smote[col] = np.maximum(X_smote[col], 0)
        
    bool_cols = ["breach_rule_fired", "minor_data_rule_fired"]
    for col in bool_cols:
        X_smote[col] = np.clip(np.round(X_smote[col]), 0, 1).astype(int)
        
    print("Class distribution after SMOTE:")
    smote_counts = y_smote.value_counts()
    smote_total = len(y_smote)
    for cls in sorted(smote_counts.index):
        pct = (smote_counts[cls] / smote_total) * 100
        print(f"  Class {cls}: {smote_counts[cls]} ({pct:.1f}%)")
    print()

    # STEP C — 5-Fold Cross-Validation
    print("5-Fold Cross-Validation Results:")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    acc_scores = []
    f1_scores = []
    
    fold = 1
    for train_idx, val_idx in skf.split(X_smote, y_smote):
        X_train_f, X_val_f = X_smote.iloc[train_idx], X_smote.iloc[val_idx]
        y_train_f, y_val_f = y_smote.iloc[train_idx], y_smote.iloc[val_idx]
        
        model = XGBClassifier(
            max_depth=3,
            n_estimators=100,
            learning_rate=0.1,
            reg_lambda=1.0,
            reg_alpha=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric='mlogloss',
            random_state=42,
            use_label_encoder=False
        )
        model.fit(X_train_f, y_train_f)
        preds = model.predict(X_val_f)
        
        acc = accuracy_score(y_val_f, preds)
        f1 = f1_score(y_val_f, preds, average="weighted")
        acc_scores.append(acc)
        f1_scores.append(f1)
        
        print(f"  Fold {fold}: accuracy={acc:.2f}, F1={f1:.2f}")
        fold += 1
        
    mean_acc = np.mean(acc_scores)
    std_acc = np.std(acc_scores)
    mean_f1 = np.mean(f1_scores)
    
    print(f"  Mean accuracy: {mean_acc:.2f} ± {std_acc:.2f}")
    print(f"  Mean F1: {mean_f1:.2f}")
    if std_acc > 0.15:
        print("  WARNING: High variance — model may be overfitting")
    print()

    # STEP D — Train final model on full SMOTE dataset
    final_model = XGBClassifier(
        max_depth=3,
        n_estimators=100,
        learning_rate=0.1,
        reg_lambda=1.0,
        reg_alpha=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric='mlogloss',
        random_state=42,
        use_label_encoder=False
    )
    final_model.fit(X_smote, y_smote)
    
    print("Final Model — Classification Report on full SMOTE dataset (training performance, not test):")
    y_pred_full = final_model.predict(X_smote)
    print(classification_report(y_smote, y_pred_full))

    # STEP E — SHAP Global Feature Importance
    feature_names = X_smote.columns.tolist()
    explainer = shap.TreeExplainer(final_model)
    shap_values = explainer(X_smote)
    
    if isinstance(shap_values.values, list):
        mean_abs_shap = np.mean([np.abs(sv).mean(axis=0) for sv in shap_values.values], axis=0)
    elif len(shap_values.values.shape) == 3:
        mean_abs_shap = np.abs(shap_values.values).mean(axis=(0, 2))
    else:
        mean_abs_shap = np.abs(shap_values.values).mean(axis=0)
    shap_dict = {feat: float(val) for feat, val in zip(feature_names, mean_abs_shap)}
    
    sorted_features = sorted(shap_dict.items(), key=lambda x: x[1], reverse=True)
    top_3 = [x[0] for x in sorted_features[:3]]
    
    print("Top 3 most important features by SHAP:")
    for i, (feat, val) in enumerate(sorted_features[:3], 1):
        print(f"  {i}. {feat} (mean |SHAP| = {val:.2f})")
    print()

    # STEP F — Save artifacts
    Path("src/modeling").mkdir(parents=True, exist_ok=True)
    Path("outputs/explanations").mkdir(parents=True, exist_ok=True)
    
    model_path = "src/modeling/risk_model.pkl"
    joblib.dump(final_model, model_path)
    
    data_path = "data/training/training_data.npy"
    np.save(data_path, X_smote.values)
    
    feat_path = "data/training/feature_names.json"
    with open(feat_path, "w") as f:
        json.dump(feature_names, f)
        
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
        
    shap_path = "outputs/explanations/shap_global.json"
    shap_output = {
        "feature_names": feature_names,
        "mean_abs_shap_values": shap_dict,
        "top_3_features": top_3,
        "model_version": "xgboost_v1",
        "trained_on_samples": len(X_smote)
    }
    with open(shap_path, "w") as f:
        json.dump(shap_output, f, indent=2)
        
    print("Artifacts saved:")
    print(f"  risk_model.pkl: {os.path.getsize(model_path)} bytes")
    print(f"  training_data.npy: {X_smote.shape}")
    print(f"  feature_names.json: {feature_names}")
    print(f"  label_map.json: {label_map}")
    print(f"  shap_global.json: {top_3}")
    print("\n=== END OF TRAINING REPORT ===\n")
    
    # TASK 3 — Sanity Check
    print("--- TASK 3: Sanity Check ---")
    metadata_df = pd.read_csv("data/training/training_metadata.csv")
    
    gen_010_meta = metadata_df[metadata_df['tenant_id'] == 'GEN-010']
    gen_005_meta = metadata_df[metadata_df['tenant_id'] == 'GEN-005']
    
    if not gen_010_meta.empty and not gen_005_meta.empty:
        idx_010 = gen_010_meta.index[0]
        idx_005 = gen_005_meta.index[0]
        
        vec_010 = X.iloc[[idx_010]]
        vec_005 = X.iloc[[idx_005]]
        
        pred_010 = final_model.predict(vec_010)[0]
        prob_010 = final_model.predict_proba(vec_010)[0]
        
        pred_005 = final_model.predict(vec_005)[0]
        prob_005 = final_model.predict_proba(vec_005)[0]
        
        print(f"GEN-010 prediction: {label_map[str(pred_010)]}")
        print(f"GEN-010 probabilities: COMPLIANT={prob_010[0]*100:.1f}% LOW={prob_010[1]*100:.1f}% MEDIUM={prob_010[2]*100:.1f}% HIGH={prob_010[3]*100:.1f}% CRITICAL={prob_010[4]*100:.1f}%")
        
        print(f"GEN-005 prediction: {label_map[str(pred_005)]}")
        print(f"GEN-005 probabilities: COMPLIANT={prob_005[0]*100:.1f}% LOW={prob_005[1]*100:.1f}% MEDIUM={prob_005[2]*100:.1f}% HIGH={prob_005[3]*100:.1f}% CRITICAL={prob_005[4]*100:.1f}%")
        
        if pred_010 not in [3, 4]:
            print("WARNING: GEN-010 should predict HIGH or CRITICAL.")
        if pred_005 not in [0, 1]:
            print("WARNING: GEN-005 should predict COMPLIANT or LOW.")
    else:
        print("WARNING: Could not find GEN-010 or GEN-005 in metadata.")

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
