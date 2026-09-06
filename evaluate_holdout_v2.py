"""
OOD holdout v2 evaluation -- scores the retrained model against the
470-tenant covering-array holdout (see generate_ood_testset.py /
build_holdout_v2_features.py), structurally decorrelated from training's
tier-first fixed-recipe generator, replacing the old 90-tenant holdout
(evaluate_holdout.py) where 65/90 tenants were built by the same mechanical
process as training data.
"""
import json
import pickle
import pandas as pd
from sklearn.metrics import (
    classification_report, matthews_corrcoef, confusion_matrix, f1_score
)

FEATURE_NAMES = json.load(open("data/training/feature_names.json"))
LABEL_MAP = {int(k): v for k, v in json.load(open("src/modeling/label_map.json")).items()}
TARGET_NAMES = [LABEL_MAP[i] for i in range(5)]

with open("src/modeling/risk_model.pkl", "rb") as f:
    model = pickle.load(f)

X = pd.read_csv("data/training/holdout_features_v2.csv")
meta = pd.read_csv("data/training/holdout_metadata_v2.csv")

y_true = X["label"].values
X_features = X[FEATURE_NAMES]

y_pred = model.predict(X_features)

macro_f1 = f1_score(y_true, y_pred, average="macro")
mcc = matthews_corrcoef(y_true, y_pred)

print("=" * 60)
print("OOD HOLDOUT v2 EVALUATION (470 covering-array-generated tenants)")
print("=" * 60)
print(f"Macro F1 : {macro_f1:.4f}")
print(f"MCC      : {mcc:.4f}")
print()
print("Classification Report:")
print(classification_report(y_true, y_pred, labels=list(range(5)), target_names=TARGET_NAMES, zero_division=0))
print("Confusion Matrix (rows=true, cols=predicted, order COMPLIANT/LOW/MEDIUM/HIGH/CRITICAL):")
print(confusion_matrix(y_true, y_pred, labels=list(range(5))))

meta = meta.reset_index(drop=True)
mismatches = meta[y_true != y_pred].copy()
mismatches["true_label"] = [LABEL_MAP[v] for v in y_true[y_true != y_pred]]
mismatches["predicted_label"] = [LABEL_MAP[v] for v in y_pred[y_true != y_pred]]
print()
print(f"Misclassified: {len(mismatches)} / {len(meta)}")
if len(mismatches):
    print(mismatches[["tenant_id", "profile_name", "true_label", "predicted_label"]].to_string(index=False))

results = {
    "n_holdout": int(len(meta)),
    "macro_f1": round(float(macro_f1), 4),
    "mcc": round(float(mcc), 4),
    "n_misclassified": int(len(mismatches)),
    "misclassified": mismatches[["tenant_id", "profile_name", "true_label", "predicted_label"]].to_dict("records") if len(mismatches) else [],
}
with open("data/training/holdout_v2_results.json", "w") as f:
    json.dump(results, f, indent=2)
print()
print("[OK] Saved data/training/holdout_v2_results.json")
