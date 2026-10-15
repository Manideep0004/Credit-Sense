"""
agents/compliance_agent.py
--------------------------
Compliance / AML Agent — applies rule-based compliance flags AND performs
RAG retrieval of relevant policy clauses from ChromaDB (or TF-IDF fallback).

Pure function: (validated_features, risk_output) → dict.

Rule-based flags:
  - INCOMPLETE_KYC     : kyc_verified == 0
  - REPEAT_DEFAULTER   : past_defaults > 1
  - HIGH_DTI           : dti_ratio > 0.55
  - AML_STRUCTURING    : txn_volatility_score > 80 AND
                         requested_loan_amount > 10 × monthly_income

The retrieval query is built from NATURAL LANGUAGE descriptions of the flags
raised (not raw flag codes) so semantic retrieval actually matches policy text.

Blocking flags (trigger MANUAL_REVIEW regardless of risk score):
  INCOMPLETE_KYC, REPEAT_DEFAULTER, AML_STRUCTURING
"""

from __future__ import annotations

import json
import math
import pickle
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).parent.parent
VECTORSTORE_DIR = ROOT / "vectorstore"
METADATA_PATH = VECTORSTORE_DIR / "store_metadata.json"

# ── flag constants ────────────────────────────────────────────────────────────
FLAG_INCOMPLETE_KYC = "INCOMPLETE_KYC"
FLAG_REPEAT_DEFAULTER = "REPEAT_DEFAULTER"
FLAG_HIGH_DTI = "HIGH_DTI"
FLAG_AML_STRUCTURING = "AML_STRUCTURING"

BLOCKING_FLAGS = {FLAG_INCOMPLETE_KYC, FLAG_REPEAT_DEFAULTER, FLAG_AML_STRUCTURING}

# Natural-language descriptions for each flag (used as retrieval queries)
FLAG_DESCRIPTIONS = {
    FLAG_INCOMPLETE_KYC: (
        "The applicant has not completed KYC verification. "
        "Identity documents are missing or unverified."
    ),
    FLAG_REPEAT_DEFAULTER: (
        "The applicant has more than one prior loan default history. "
        "They are classified as a repeat defaulter with multiple loan defaults."
    ),
    FLAG_HIGH_DTI: (
        "The applicant's debt-to-income ratio exceeds the maximum threshold of 0.55. "
        "Total monthly debt obligations are too high relative to monthly income."
    ),
    FLAG_AML_STRUCTURING: (
        "The applicant shows high transaction volatility and requests an unusually large "
        "loan amount relative to income. This may indicate AML structuring or suspicious "
        "financial activity requiring AML compliance review."
    ),
}


from rag.vectorstore import get_retriever


# ── rule engine ───────────────────────────────────────────────────────────────

def _apply_rules(features: dict[str, Any]) -> list[str]:
    """Return list of flag codes raised for this applicant."""
    flags: list[str] = []

    if not bool(features.get("kyc_verified", 1)):
        flags.append(FLAG_INCOMPLETE_KYC)

    if int(features.get("past_defaults", 0)) > 1:
        flags.append(FLAG_REPEAT_DEFAULTER)

    dti = features.get("dti_ratio", 0.0)
    if dti is not None and dti > 0.55:
        flags.append(FLAG_HIGH_DTI)

    txn_vol = float(features.get("txn_volatility_score", 0))
    monthly_income = float(features.get("monthly_income", 1))
    loan_amount = float(features.get("requested_loan_amount", 0))
    if txn_vol > 80 and loan_amount > 10 * monthly_income:
        flags.append(FLAG_AML_STRUCTURING)

    return flags


# ── main agent function ───────────────────────────────────────────────────────

def run(
    validated_features: dict[str, Any],
    risk_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Apply compliance rules and retrieve relevant policy clauses.

    Parameters
    ----------
    validated_features : dict
        Feature dict from document_agent.
    risk_output : dict, optional
        Output from risk_agent (not used in rule logic, passed through for context).

    Returns
    -------
    dict with keys:
        - flags              : list[str]   (rule flags raised)
        - blocking_flags     : list[str]   (subset that block auto-approval)
        - has_blocking_flag  : bool
        - retrieved_clauses  : list[dict]  (relevant policy clauses per flag)
        - compliance_verdict : str         ("CLEAR" | "FLAG" | "BLOCK")
        - agent              : str         ("compliance_agent")
        - status             : "ok" | "error"
    """
    try:
        retriever = get_retriever()
    except Exception as e:
        return {
            "flags": [],
            "blocking_flags": [],
            "has_blocking_flag": False,
            "retrieved_clauses": [],
            "compliance_verdict": "ERROR",
            "agent": "compliance_agent",
            "status": "error",
            "error": str(e),
        }

    flags = _apply_rules(validated_features)
    blocking = [f for f in flags if f in BLOCKING_FLAGS]

    # RAG retrieval: one query per raised flag using natural-language description
    all_retrieved: list[dict] = []
    seen_ids: set[str] = set()

    for flag in flags:
        query = FLAG_DESCRIPTIONS.get(flag, flag)
        clauses = retriever.retrieve(query, top_k=2)
        for clause in clauses:
            if clause["id"] not in seen_ids:
                clause["triggered_by_flag"] = flag
                all_retrieved.append(clause)
                seen_ids.add(clause["id"])

    # Also retrieve a general risk clause if SEVERE
    if risk_output and risk_output.get("risk_tier") in ("SEVERE", "HIGH"):
        query = "high risk loan application default probability escalation"
        for clause in retriever.retrieve(query, top_k=1):
            if clause["id"] not in seen_ids:
                clause["triggered_by_flag"] = "HIGH_RISK_TIER"
                all_retrieved.append(clause)
                seen_ids.add(clause["id"])

    if blocking:
        verdict = "BLOCK"
    elif flags:
        verdict = "FLAG"
    else:
        verdict = "CLEAR"

    return {
        "flags": flags,
        "blocking_flags": blocking,
        "has_blocking_flag": bool(blocking),
        "retrieved_clauses": all_retrieved,
        "compliance_verdict": verdict,
        "agent": "compliance_agent",
        "status": "ok",
    }
