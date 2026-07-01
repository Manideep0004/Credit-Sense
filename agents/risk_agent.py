"""
agents/risk_agent.py
--------------------
Risk Scoring Agent — loads the trained GradientBoosting model and
outputs a default probability + risk tier.

Pure function: dict → dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

# ── model path ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
MODEL_PATH = ROOT / "models" / "risk_model.pkl"

# ── risk tier thresholds ──────────────────────────────────────────────────────
# SEVERE  : prob >= 0.60
# HIGH    : 0.40 <= prob < 0.60
# MODERATE: 0.20 <= prob < 0.40
# LOW     : prob < 0.20

TIER_THRESHOLDS = [
    (0.60, "SEVERE"),
    (0.40, "HIGH"),
    (0.20, "MODERATE"),
    (0.00, "LOW"),
]

# ── cached model ──────────────────────────────────────────────────────────────
_MODEL_CACHE: dict | None = None


def _load_model() -> dict:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Risk model not found at {MODEL_PATH}.\n"
                "Run:  python train_risk_model.py"
            )
        _MODEL_CACHE = joblib.load(MODEL_PATH)
    return _MODEL_CACHE


def _prob_to_tier(prob: float) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if prob >= threshold:
            return tier
    return "LOW"


def run(validated_features: dict[str, Any]) -> dict[str, Any]:
    """
    Score an applicant using the trained risk model.

    Parameters
    ----------
    validated_features : dict
        Output of document_agent.run()['validated_features'].

    Returns
    -------
    dict with keys:
        - default_probability : float   (0.0 – 1.0)
        - risk_tier           : str     ("LOW"|"MODERATE"|"HIGH"|"SEVERE")
        - model_version       : str
        - agent               : str     ("risk_agent")
        - status              : "ok" | "error"
    """
    try:
        artifact = _load_model()
    except FileNotFoundError as e:
        return {
            "default_probability": None,
            "risk_tier": None,
            "agent": "risk_agent",
            "status": "error",
            "error": str(e),
        }

    pipeline = artifact["pipeline"]
    feature_cols = artifact["feature_cols"]

    # Build feature row; fill missing cols with 0
    row = {col: validated_features.get(col, 0) for col in feature_cols}
    X = pd.DataFrame([row])[feature_cols]

    prob = float(pipeline.predict_proba(X)[0, 1])
    tier = _prob_to_tier(prob)

    return {
        "default_probability": round(prob, 4),
        "risk_tier": tier,
        "model_version": "GradientBoostingClassifier-v1",
        "agent": "risk_agent",
        "status": "ok",
    }


# ── allow direct invocation for quick smoke-test ─────────────────────────────
if __name__ == "__main__":
    sample = {
        "age": 35,
        "employment_years": 8,
        "monthly_income": 80_000,
        "existing_monthly_debt": 25_000,
        "dti_ratio": 0.3125,
        "credit_utilization_pct": 35.0,
        "past_defaults": 0,
        "requested_loan_amount": 500_000,
        "txn_volatility_score": 30.0,
        "kyc_verified": 1,
    }
    result = run(sample)
    print(result)
