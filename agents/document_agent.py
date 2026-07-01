"""
agents/document_agent.py
------------------------
Document Agent — validates and normalises raw applicant input into a
structured feature dict consumed by downstream agents.

This is a pure function: dict → dict.  No orchestration logic lives here.
"""

from __future__ import annotations

from typing import Any

# ── required fields and their expected types ──────────────────────────────────
REQUIRED_FIELDS: dict[str, type] = {
    "monthly_income": (int, float),
    "existing_monthly_debt": (int, float),
    "credit_utilization_pct": (int, float),
    "past_defaults": int,
    "employment_years": (int, float),
    "requested_loan_amount": (int, float),
    "txn_volatility_score": (int, float),
    "age": (int, float),
    "kyc_verified": (int, bool),
}

# ── valid ranges for sanity checks ───────────────────────────────────────────
FIELD_RANGES: dict[str, tuple[float, float]] = {
    "monthly_income": (1_000, 10_000_000),
    "existing_monthly_debt": (0, 10_000_000),
    "credit_utilization_pct": (0, 100),
    "past_defaults": (0, 20),
    "employment_years": (0, 50),
    "requested_loan_amount": (1_000, 100_000_000),
    "txn_volatility_score": (0, 100),
    "age": (18, 80),
    "kyc_verified": (0, 1),
}


class DocumentValidationError(ValueError):
    """Raised when the applicant document fails validation."""


def run(raw_input: dict[str, Any]) -> dict[str, Any]:
    """
    Validate, normalise, and enrich a raw applicant dict.

    Parameters
    ----------
    raw_input : dict
        Applicant data as submitted (may contain string values from UI).

    Returns
    -------
    dict with keys:
        - validated_features : dict[str, float|int]  (canonical feature dict)
        - dti_ratio          : float
        - validation_errors  : list[str]             (non-fatal warnings)
        - agent              : str                   ("document_agent")
        - status             : "ok" | "error"
    """
    errors: list[str] = []
    features: dict[str, Any] = {}

    # ── type coercion + presence check ────────────────────────────────────────
    for field, expected_type in REQUIRED_FIELDS.items():
        raw_val = raw_input.get(field)
        if raw_val is None:
            errors.append(f"Missing required field: '{field}'")
            continue
        try:
            if expected_type == int or expected_type == (int, bool):
                features[field] = int(float(str(raw_val)))
            else:
                features[field] = float(str(raw_val))
        except (ValueError, TypeError):
            errors.append(
                f"Cannot parse '{field}' = {raw_val!r} as {expected_type}"
            )

    if errors:
        return {
            "validated_features": features,
            "dti_ratio": None,
            "validation_errors": errors,
            "agent": "document_agent",
            "status": "error",
        }

    # ── range checks ─────────────────────────────────────────────────────────
    for field, (lo, hi) in FIELD_RANGES.items():
        val = features.get(field)
        if val is not None and not (lo <= val <= hi):
            errors.append(
                f"Field '{field}' = {val} is outside expected range [{lo}, {hi}]"
            )

    # ── derived feature: DTI ratio ────────────────────────────────────────────
    monthly_income = features.get("monthly_income", 1)
    if monthly_income <= 0:
        errors.append("monthly_income must be > 0 to compute DTI ratio.")
        dti_ratio = None
    else:
        dti_ratio = round(
            features.get("existing_monthly_debt", 0) / monthly_income, 4
        )
        features["dti_ratio"] = dti_ratio

    # ── normalise kyc_verified to int 0/1 ────────────────────────────────────
    features["kyc_verified"] = int(bool(features.get("kyc_verified", 0)))

    return {
        "validated_features": features,
        "dti_ratio": dti_ratio,
        "validation_errors": errors,
        "agent": "document_agent",
        "status": "ok" if not errors else "warning",
    }
