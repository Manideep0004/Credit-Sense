"""
train_risk_model.py
-------------------
Trains a GradientBoostingClassifier on the synthetic loan-applicant dataset,
evaluates it (AUC + classification report), and saves the model artifact.

Run:
    python train_risk_model.py
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data" / "loan_applicants.csv"
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "risk_model.pkl"

FEATURE_COLS = [
    "age",
    "employment_years",
    "monthly_income",
    "existing_monthly_debt",
    "dti_ratio",
    "credit_utilization_pct",
    "past_defaults",
    "requested_loan_amount",
    "txn_volatility_score",
    "kyc_verified",
]
TARGET_COL = "default"


def train_and_save(data_path: Path = DATA_PATH, model_path: Path = MODEL_PATH) -> dict:
    """Train model, print metrics, persist to disk. Returns eval metrics."""
    if not data_path.exists():
        print(f"[ERROR] Dataset not found at {data_path}.")
        print("        Run:  python data/generate_data.py")
        sys.exit(1)

    df = pd.read_csv(data_path)
    X = df[FEATURE_COLS]
    y = df[TARGET_COL]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                GradientBoostingClassifier(
                    n_estimators=300,
                    learning_rate=0.05,
                    max_depth=5,
                    subsample=0.8,
                    min_samples_leaf=20,
                    random_state=42,
                ),
            ),
        ]
    )

    pipeline.fit(X_train, y_train)

    y_prob = pipeline.predict_proba(X_test)[:, 1]
    y_pred = pipeline.predict(X_test)
    auc = roc_auc_score(y_test, y_prob)

    print("=" * 55)
    print("CreditSense — Risk Model Training Complete")
    print("=" * 55)
    print(f"  Test AUC : {auc:.4f}")
    print(f"\nClassification Report (threshold = 0.5):\n")
    print(classification_report(y_test, y_pred, target_names=["Non-Default", "Default"]))

    # Feature importances
    clf = pipeline.named_steps["clf"]
    importance_df = pd.DataFrame(
        {"feature": FEATURE_COLS, "importance": clf.feature_importances_}
    ).sort_values("importance", ascending=False)
    print("Feature Importances:")
    for _, row in importance_df.iterrows():
        bar = "█" * int(row["importance"] * 50)
        print(f"  {row['feature']:30s} {row['importance']:.4f}  {bar}")

    # Persist
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"pipeline": pipeline, "feature_cols": FEATURE_COLS},
        model_path,
    )
    print(f"\nModel saved → {model_path}")

    return {"auc": auc, "model_path": str(model_path)}


if __name__ == "__main__":
    train_and_save()
