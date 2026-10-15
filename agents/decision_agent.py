"""
agents/decision_agent.py
------------------------
Decision Agent — synthesises risk tier + compliance verdict into a final
decision with a natural-language explanation citing specific policy clause IDs.

Uses Groq API (Llama 3.1/3.3 70B) to generate explanations.
Falls back to a templated generator if GROQ_API_KEY is not set.

Pure function: (validated_features, risk_output, compliance_output) → dict.
"""

from __future__ import annotations

import os
from typing import Any

# ── interest rate schedule (approximate, by risk tier) ───────────────────────
INTEREST_RATE_SCHEDULE = {
    "LOW": 10.5,
    "MODERATE": 13.0,
    "HIGH": 16.5,
    "SEVERE": None,  # Not approved at auto level
}

# ── decision logic ────────────────────────────────────────────────────────────

def _determine_base_decision(
    risk_tier: str,
    compliance_verdict: str,
    has_blocking_flag: bool,
) -> str:
    """
    Routing logic (mirrors graph.py conditional edge):
      - Any blocking compliance flag → MANUAL_REVIEW
      - SEVERE risk tier            → MANUAL_REVIEW
      - HIGH risk tier              → MANUAL_REVIEW
      - Compliance FLAG (non-block) + MODERATE → MANUAL_REVIEW
      - Otherwise LOW/MODERATE + CLEAR/FLAG(non-block) → APPROVED / REJECTED
    """
    if has_blocking_flag:
        return "MANUAL_REVIEW"
    if risk_tier == "SEVERE":
        return "MANUAL_REVIEW"
    if risk_tier == "HIGH":
        return "MANUAL_REVIEW"
    if compliance_verdict == "FLAG" and risk_tier == "MODERATE":
        return "MANUAL_REVIEW"
    if risk_tier in ("LOW", "MODERATE") and compliance_verdict in ("CLEAR", "FLAG"):
        return "APPROVED"
    return "REJECTED"


# ── LLM explanation generation ────────────────────────────────────────────────

def _build_prompt(
    features: dict[str, Any],
    risk: dict[str, Any],
    compliance: dict[str, Any],
    decision: str,
    interest_rate: float | None,
) -> str:
    clause_ids = [c["id"] for c in compliance.get("retrieved_clauses", [])]
    flags_str = ", ".join(compliance.get("flags", [])) or "None"
    clauses_str = ", ".join(clause_ids) or "N/A"
    rate_str = f"{interest_rate}% p.a." if interest_rate else "N/A (not applicable)"

    return f"""You are a senior loan underwriting analyst at an NBFC.
Write a concise, professional loan decision explanation (3-5 sentences) for the following case.
Cite specific policy clause IDs where relevant.

Applicant Profile:
- Age: {features.get('age')} years
- Employment: {features.get('employment_years')} years
- Monthly Income: ₹{features.get('monthly_income'):,.0f}
- Existing Monthly Debt: ₹{features.get('existing_monthly_debt'):,.0f}
- DTI Ratio: {features.get('dti_ratio', 0):.2%}
- Credit Utilization: {features.get('credit_utilization_pct')}%
- Past Defaults: {features.get('past_defaults')}
- Requested Loan: ₹{features.get('requested_loan_amount'):,.0f}
- Transaction Volatility Score: {features.get('txn_volatility_score')}
- KYC Verified: {'Yes' if features.get('kyc_verified') else 'No'}

Risk Assessment:
- Default Probability: {risk.get('default_probability', 0):.1%}
- Risk Tier: {risk.get('risk_tier')}

Compliance:
- Flags Raised: {flags_str}
- Blocking Flags: {', '.join(compliance.get('blocking_flags', [])) or 'None'}
- Relevant Policy Clauses: {clauses_str}

Decision: {decision}
Interest Rate Offered: {rate_str}

Write the explanation now (professional, citing clause IDs like DTI-1.1, AML-3.1, etc.):"""


def _groq_explain(prompt: str) -> str:
    """Call Groq API to generate explanation. Returns explanation string."""
    from groq import Groq  # type: ignore

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY environment variable not set.")

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=400,
    )
    return response.choices[0].message.content.strip()


def _template_explain(
    features: dict[str, Any],
    risk: dict[str, Any],
    compliance: dict[str, Any],
    decision: str,
    interest_rate: float | None,
) -> str:
    """
    Templated fallback explanation generator.
    NOTE: This is where the LLM call (Groq/Llama) plugs in for production.
          Set GROQ_API_KEY to enable AI-generated explanations.
    """
    clause_ids = [c["id"] for c in compliance.get("retrieved_clauses", [])]
    flags = compliance.get("flags", [])
    tier = risk.get("risk_tier", "UNKNOWN")
    prob = risk.get("default_probability", 0) or 0

    parts: list[str] = []

    if decision == "APPROVED":
        parts.append(
            f"After reviewing the application, we are pleased to approve the loan request "
            f"of ₹{features.get('requested_loan_amount', 0):,.0f} at an interest rate of "
            f"{interest_rate}% p.a."
        )
        parts.append(
            f"The applicant's risk profile is classified as {tier} "
            f"(estimated default probability: {prob:.1%}), which is within acceptable limits."
        )
        if clause_ids:
            parts.append(
                f"The application has been evaluated in accordance with policy clauses: "
                f"{', '.join(clause_ids)}."
            )
        if features.get("employment_years", 0) >= 5:
            parts.append(
                "Stable employment history of "
                f"{features.get('employment_years')} years is a positive factor."
            )

    elif decision == "REJECTED":
        parts.append(
            f"After careful review, the loan request of "
            f"₹{features.get('requested_loan_amount', 0):,.0f} has been declined."
        )
        parts.append(
            f"The applicant's risk profile is {tier} with an estimated default "
            f"probability of {prob:.1%}, which exceeds our risk appetite."
        )
        if flags:
            parts.append(
                f"Compliance flags raised: {', '.join(flags)}. "
                f"Relevant policy clauses: {', '.join(clause_ids) or 'N/A'}."
            )
        parts.append(
            "We encourage the applicant to improve their credit profile and reapply "
            "after addressing the flagged concerns."
        )

    else:  # MANUAL_REVIEW
        blocking = compliance.get("blocking_flags", [])
        parts.append(
            f"The loan application of ₹{features.get('requested_loan_amount', 0):,.0f} "
            f"has been escalated for manual review by a senior underwriter."
        )
        if blocking:
            parts.append(
                f"Blocking compliance flags were raised: {', '.join(blocking)}. "
                "Automatic approval is prohibited per policy."
            )
        if clause_ids:
            parts.append(
                f"Applicable policy clauses requiring manual review: {', '.join(clause_ids)}."
            )
        parts.append(
            "A compliance officer will contact the applicant within 3 business days "
            "to resolve outstanding requirements."
        )

    return " ".join(parts)


# ── main agent function ───────────────────────────────────────────────────────

def run(
    validated_features: dict[str, Any],
    risk_output: dict[str, Any],
    compliance_output: dict[str, Any],
) -> dict[str, Any]:
    """
    Synthesise a final lending decision with explanation.

    Parameters
    ----------
    validated_features : dict   from document_agent
    risk_output        : dict   from risk_agent
    compliance_output  : dict   from compliance_agent

    Returns
    -------
    dict with keys:
        - decision           : str   ("APPROVED"|"REJECTED"|"MANUAL_REVIEW")
        - interest_rate_pct  : float | None
        - explanation        : str
        - applied_clause_ids : list[str]
        - explanation_source : str   ("groq_llm" | "template_fallback")
        - agent              : str   ("decision_agent")
        - status             : "ok" | "error"
    """
    risk_tier = risk_output.get("risk_tier", "SEVERE")
    compliance_verdict = compliance_output.get("compliance_verdict", "BLOCK")
    has_blocking_flag = compliance_output.get("has_blocking_flag", False)

    decision = _determine_base_decision(risk_tier, compliance_verdict, has_blocking_flag)
    
    # ── Deterministic Policy Guard ───────────────────────────────────────────
    # Compliance blocking flags (AML, KYC, repeat defaults) strictly override ML risk
    if has_blocking_flag and decision != "MANUAL_REVIEW":
        decision = "MANUAL_REVIEW"
    
    interest_rate = INTEREST_RATE_SCHEDULE.get(risk_tier) if decision == "APPROVED" else None
    applied_clause_ids = [c["id"] for c in compliance_output.get("retrieved_clauses", [])]

    # Try LLM explanation, fall back to template
    explanation_source = "template_fallback"
    try:
        prompt = _build_prompt(
            validated_features, risk_output, compliance_output, decision, interest_rate
        )
        explanation = _groq_explain(prompt)
        explanation_source = "groq_llm"
    except Exception:
        # NOTE: LLM call failed or GROQ_API_KEY not set.
        #       Template explanation used. Set GROQ_API_KEY for AI explanations.
        explanation = _template_explain(
            validated_features, risk_output, compliance_output, decision, interest_rate
        )

    return {
        "decision": decision,
        "interest_rate_pct": interest_rate,
        "explanation": explanation,
        "applied_clause_ids": applied_clause_ids,
        "explanation_source": explanation_source,
        "agent": "decision_agent",
        "status": "ok",
    }
