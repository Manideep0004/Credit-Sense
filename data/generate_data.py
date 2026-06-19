"""
generate_data.py
----------------
Generates a synthetic loan-applicant dataset (~3000 rows) with realistic
features and a derived default label.  The label is constructed from a
weighted combination of risk factors plus Gaussian noise, targeting an
AUC of 0.85-0.95 (realistic, not perfect).

Run:
    python data/generate_data.py
"""

import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(42)

N = 3000
OUTPUT_PATH = Path(__file__).parent / "loan_applicants.csv"


def generate_dataset(n: int = N, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # ── raw features ────────────────────────────────────────────────────────
    age = rng.integers(21, 65, size=n)
    employment_years = np.clip(rng.normal(7, 5, size=n), 0, 40).astype(int)

    # Monthly income: log-normal, range roughly ₹15k – ₹5L
    monthly_income = np.round(rng.lognormal(mean=11.0, sigma=0.6, size=n), -2)
    monthly_income = np.clip(monthly_income, 15_000, 500_000)

    # DTI: existing monthly debt as a fraction of income (0.05 – 0.80)
    dti_ratio = np.clip(rng.beta(2, 5, size=n) * 1.2, 0.05, 0.90)
    existing_monthly_debt = np.round(monthly_income * dti_ratio, 2)

    credit_utilization_pct = np.clip(rng.beta(2, 3, size=n) * 100, 5, 95)

    past_defaults = rng.choice([0, 1, 2, 3], size=n, p=[0.65, 0.20, 0.10, 0.05])

    # Requested loan: 2x – 60x monthly income
    loan_multiplier = np.clip(rng.lognormal(mean=2.5, sigma=0.8, size=n), 2, 60)
    requested_loan_amount = np.round(monthly_income * loan_multiplier, -3)

    # Transaction-volatility score: 0–100 (higher → more erratic cash flows)
    txn_volatility_score = np.clip(rng.normal(40, 20, size=n), 0, 100).round(1)

    # KYC: most applicants pass; a small fraction incomplete
    kyc_verified = rng.choice([1, 0], size=n, p=[0.85, 0.15])

    # ── derive default label ─────────────────────────────────────────────────
    # Risk score (continuous) = weighted sum of normalised bad-indicators
    risk_score = (
        0.35 * dti_ratio                                        # DTI
        + 0.20 * (credit_utilization_pct / 100)                # credit util
        + 0.25 * np.minimum(past_defaults, 3) / 3              # defaults (cap at 3)
        - 0.10 * np.minimum(employment_years, 15) / 15         # tenure (good signal)
        + 0.10 * (txn_volatility_score / 100)                  # volatility
        + rng.normal(0, 0.08, size=n)                          # noise
    )

    # Convert to probability via sigmoid; calibrate midpoint so ~25% default
    prob_default = 1 / (1 + np.exp(-8 * (risk_score - 0.48)))
    default = (rng.random(size=n) < prob_default).astype(int)

    df = pd.DataFrame(
        {
            "age": age,
            "employment_years": employment_years,
            "monthly_income": monthly_income,
            "existing_monthly_debt": existing_monthly_debt,
            "dti_ratio": dti_ratio.round(4),
            "credit_utilization_pct": credit_utilization_pct.round(2),
            "past_defaults": past_defaults,
            "requested_loan_amount": requested_loan_amount,
            "txn_volatility_score": txn_volatility_score,
            "kyc_verified": kyc_verified,
            "default": default,
        }
    )
    return df


if __name__ == "__main__":
    df = generate_dataset()
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Dataset saved → {OUTPUT_PATH}")
    print(f"Shape         : {df.shape}")
    print(f"\nClass balance:")
    vc = df["default"].value_counts()
    print(f"  Non-default (0): {vc[0]} ({vc[0]/len(df)*100:.1f}%)")
    print(f"  Default     (1): {vc[1]} ({vc[1]/len(df)*100:.1f}%)")
    print(f"\nFeature stats:\n{df.describe().T[['mean','std','min','max']].round(2)}")
