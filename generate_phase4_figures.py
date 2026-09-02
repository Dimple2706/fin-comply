"""
Phase 4, Step 7: produce every figure and table for the paper's Evaluation
section, from the already-trained model and the two fixed datasets
(225-profile family training set, 90-profile unseen-persona holdout).

Reconstructs the exact same 80/20 split train_risk_model.py used
(random_state=42, stratified) so results are reproducible, then adds what
wasn't saved during training: full confusion matrices, per-fold CV scores
for a stability chart, a naive penalty-threshold baseline for comparison,
and a real SHAP beeswarm plot (not just aggregate importance).
"""
import json
import pickle
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shap

from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import (
    f1_score, matthews_corrcoef, confusion_matrix, classification_report
)
from imblearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier

OUT_DIR = "outputs/phase4_figures"
import os
os.makedirs(OUT_DIR, exist_ok=True)

FEATURE_NAMES = json.load(open("data/training/feature_names.json"))
LABEL_MAP = {int(k): v for k, v in json.load(open("src/modeling/label_map.json")).items()}
TARGET_NAMES = [LABEL_MAP[i] for i in range(5)]

with open("src/modeling/risk_model.pkl", "rb") as f:
    trained_model = pickle.load(f)

# ── Load the two fixed datasets ────────────────────────────────────────────
train_df = pd.read_csv("data/training/train_features_family.csv")
X_all = train_df[FEATURE_NAMES]
y_all = train_df["label"].values

holdout_X = pd.read_csv("data/training/holdout_features_unique.csv")[FEATURE_NAMES]
holdout_meta = pd.read_csv("data/training/holdout_metadata_unique.csv")
y_holdout = pd.read_csv("data/training/holdout_features_unique.csv")["label"].values

# ── Naive baseline: the exposure-threshold label logic we replaced ────────
def naive_exposure_label(total_crore):
    if total_crore == 0: return 0
    elif total_crore <= 300: return 1
    elif total_crore <= 750: return 2
    elif total_crore <= 1500: return 3
    else: return 4

naive_holdout_pred = holdout_meta["total_penalty_exposure"].apply(naive_exposure_label).values

# ═══════════════════════════════════════════════════════════════════════════
# 1. Reconstruct the exact sealed 20% split (same random_state as training)
# ═══════════════════════════════════════════════════════════════════════════
X_train, X_test, y_train, y_test = train_test_split(
    X_all, y_all, test_size=0.20, stratify=y_all, random_state=42
)

def make_pipeline():
    # Must exactly match train_risk_model.py's XGBClassifier params, or
    # results silently diverge from what was actually trained/reported.
    return Pipeline([
        ("smote", SMOTE(random_state=42)),
        ("xgb", XGBClassifier(
            max_depth=3, n_estimators=100, learning_rate=0.1,
            reg_lambda=1.0, reg_alpha=0.1, subsample=0.8, colsample_bytree=0.8,
            eval_metric="mlogloss", random_state=42
        )),
    ])

pipeline = make_pipeline()
pipeline.fit(X_train, y_train)
y_pred_sealed = pipeline.predict(X_test)

sealed_f1 = f1_score(y_test, y_pred_sealed, average="macro")
sealed_mcc = matthews_corrcoef(y_test, y_pred_sealed)
sealed_cm = confusion_matrix(y_test, y_pred_sealed, labels=list(range(5)))
print(f"Sealed holdout (reconstructed) -- Macro F1: {sealed_f1:.4f}  MCC: {sealed_mcc:.4f}")

# ═══════════════════════════════════════════════════════════════════════════
# 2. 5-fold CV with per-fold scores (for the stability chart)
# ═══════════════════════════════════════════════════════════════════════════
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
fold_f1, fold_mcc = [], []
for fold_i, (tr_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
    fold_pipeline = make_pipeline()
    Xf_tr, Xf_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    yf_tr, yf_val = y_train[tr_idx], y_train[val_idx]
    fold_pipeline.fit(Xf_tr, yf_tr)
    yf_pred = fold_pipeline.predict(Xf_val)
    fold_f1.append(f1_score(yf_val, yf_pred, average="macro"))
    fold_mcc.append(matthews_corrcoef(yf_val, yf_pred))
    print(f"  fold {fold_i+1}: Macro F1={fold_f1[-1]:.4f}  MCC={fold_mcc[-1]:.4f}")

# ═══════════════════════════════════════════════════════════════════════════
# 3. Unseen-persona holdout (already-trained model, full model on all 225)
# ═══════════════════════════════════════════════════════════════════════════
y_pred_ood = trained_model.predict(holdout_X)
ood_f1 = f1_score(y_holdout, y_pred_ood, average="macro")
ood_mcc = matthews_corrcoef(y_holdout, y_pred_ood)
ood_cm = confusion_matrix(y_holdout, y_pred_ood, labels=list(range(5)))

naive_ood_f1 = f1_score(y_holdout, naive_holdout_pred, average="macro")
naive_ood_mcc = matthews_corrcoef(y_holdout, naive_holdout_pred)

print(f"\nOOD holdout -- XGBoost Macro F1: {ood_f1:.4f}  MCC: {ood_mcc:.4f}")
print(f"OOD holdout -- Naive baseline Macro F1: {naive_ood_f1:.4f}  MCC: {naive_ood_mcc:.4f}")

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 1: Confusion matrices (sealed holdout + OOD holdout, side by side)
# ═══════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
for ax, cm, title in [
    (axes[0], sealed_cm, f"Sealed 20% Holdout (same-distribution)\nMacro F1={sealed_f1:.3f}, MCC={sealed_mcc:.3f}"),
    (axes[1], ood_cm, f"Unseen-Persona Holdout (out-of-distribution)\nMacro F1={ood_f1:.3f}, MCC={ood_mcc:.3f}"),
]:
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(5)); ax.set_xticklabels(TARGET_NAMES, rotation=45, ha="right")
    ax.set_yticks(range(5)); ax.set_yticklabels(TARGET_NAMES)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    ax.set_title(title, fontsize=10)
    for i in range(5):
        for j in range(5):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black")
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/confusion_matrices.png", dpi=150)
plt.close()
print(f"[OK] {OUT_DIR}/confusion_matrices.png")

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 2: Comparison bar chart -- CV / sealed / OOD, XGBoost vs naive
# ═══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(8, 5))
groups = ["5-fold CV\n(train set)", "Sealed 20%\nholdout", "Unseen-persona\nholdout (OOD)"]
xgb_f1_vals = [np.mean(fold_f1), sealed_f1, ood_f1]
naive_f1_vals = [None, None, naive_ood_f1]  # naive baseline only meaningful/computed for OOD here

x = np.arange(len(groups))
width = 0.35
ax.bar(x - width/2, xgb_f1_vals, width, label="XGBoost", color="#2E6E7C")
ax.bar(x[-1] + width/2, naive_ood_f1, width, label="Naive exposure-threshold baseline", color="#B4423D")
ax.set_ylabel("Macro F1")
ax.set_xticks(x); ax.set_xticklabels(groups)
ax.set_ylim(0, 1.05)
ax.legend()
ax.set_title("Macro F1 across evaluation regimes")
for i, v in enumerate(xgb_f1_vals):
    ax.text(i - width/2, v + 0.02, f"{v:.2f}", ha="center", fontsize=9)
ax.text(len(groups)-1 + width/2, naive_ood_f1 + 0.02, f"{naive_ood_f1:.2f}", ha="center", fontsize=9)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/comparison_bar_chart.png", dpi=150)
plt.close()
print(f"[OK] {OUT_DIR}/comparison_bar_chart.png")

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 3: CV fold stability chart
# ═══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(7, 5))
folds = list(range(1, 6))
ax.errorbar(folds, fold_f1, fmt="o-", color="#2E6E7C", label="Macro F1", capsize=4)
ax.errorbar(folds, fold_mcc, fmt="s--", color="#96721C", label="MCC", capsize=4)
ax.set_xlabel("CV Fold"); ax.set_ylabel("Score")
ax.set_xticks(folds)
ax.set_ylim(0, 1.05)
ax.set_title(f"5-Fold CV Stability (mean F1={np.mean(fold_f1):.3f} +/- {np.std(fold_f1):.3f})")
ax.legend()
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/cv_stability.png", dpi=150)
plt.close()
print(f"[OK] {OUT_DIR}/cv_stability.png")

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 4: SHAP beeswarm summary plot (on the OOD holdout -- real, unseen data)
# ═══════════════════════════════════════════════════════════════════════════
xgb_step = trained_model.named_steps["xgb"] if hasattr(trained_model, "named_steps") else trained_model
explainer = shap.TreeExplainer(xgb_step)
shap_values = explainer.shap_values(holdout_X)

# shap_values for multi-class XGBoost: list of arrays (one per class) or a 3D array
plt.figure(figsize=(9, 6))
if isinstance(shap_values, list):
    # Average |SHAP| across classes for a single summary view
    mean_abs = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    shap.summary_plot(mean_abs, holdout_X, feature_names=FEATURE_NAMES, show=False)
else:
    shap.summary_plot(shap_values, holdout_X, feature_names=FEATURE_NAMES, show=False)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/shap_beeswarm.png", dpi=150)
plt.close()
print(f"[OK] {OUT_DIR}/shap_beeswarm.png")

# ═══════════════════════════════════════════════════════════════════════════
# Save all numeric results
# ═══════════════════════════════════════════════════════════════════════════
results = {
    "cv": {"fold_macro_f1": fold_f1, "fold_mcc": fold_mcc,
           "mean_macro_f1": float(np.mean(fold_f1)), "std_macro_f1": float(np.std(fold_f1)),
           "mean_mcc": float(np.mean(fold_mcc))},
    "sealed_holdout": {"macro_f1": float(sealed_f1), "mcc": float(sealed_mcc),
                        "confusion_matrix": sealed_cm.tolist(), "n": int(len(y_test))},
    "ood_holdout_xgboost": {"macro_f1": float(ood_f1), "mcc": float(ood_mcc),
                             "confusion_matrix": ood_cm.tolist(), "n": int(len(y_holdout))},
    "ood_holdout_naive_baseline": {"macro_f1": float(naive_ood_f1), "mcc": float(naive_ood_mcc)},
}
with open(f"{OUT_DIR}/phase4_results_summary.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"[OK] {OUT_DIR}/phase4_results_summary.json")
print("\nDONE.")
