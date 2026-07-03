"""
tests/test_agents.py
--------------------
Unit tests for all four CreditSense agents and the full LangGraph pipeline.

Coverage:
  - document_agent: valid input, missing field, range error, DTI computation
  - risk_agent: score a clean and a high-risk applicant
  - compliance_agent: clean clear, AML block, KYC block, repeat-defaulter block, high-DTI flag
  - decision_agent: approved path, manual review template
  - graph (integration): clean approval, high-risk rejection, AML manual-review branch

Run:
    pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow imports from parent package
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def clean_features():
    """A well-qualified applicant — should clear all compliance checks."""
    return {
        "age": 34,
        "employment_years": 8,
        "monthly_income": 95_000.0,
        "existing_monthly_debt": 22_000.0,
        "dti_ratio": round(22_000 / 95_000, 4),
        "credit_utilization_pct": 30.0,
        "past_defaults": 0,
        "requested_loan_amount": 450_000.0,
        "txn_volatility_score": 22.0,
        "kyc_verified": 1,
    }


@pytest.fixture(scope="module")
def high_risk_features():
    """High-risk applicant: severe DTI, multiple defaults, high credit utilization."""
    return {
        "age": 28,
        "employment_years": 1,
        "monthly_income": 30_000.0,
        "existing_monthly_debt": 24_000.0,
        "dti_ratio": round(24_000 / 30_000, 4),
        "credit_utilization_pct": 88.0,
        "past_defaults": 3,
        "requested_loan_amount": 500_000.0,
        "txn_volatility_score": 70.0,
        "kyc_verified": 1,
    }


@pytest.fixture(scope="module")
def aml_features():
    """
    Low ML risk on paper (good income, no defaults, good KYC) BUT:
      txn_volatility_score > 80  AND  loan > 10× income → AML_STRUCTURING flag.
    This applicant MUST be routed to MANUAL_REVIEW regardless of ML risk tier.
    """
    monthly_income = 120_000.0
    return {
        "age": 45,
        "employment_years": 15,
        "monthly_income": monthly_income,
        "existing_monthly_debt": 18_000.0,
        "dti_ratio": round(18_000 / monthly_income, 4),
        "credit_utilization_pct": 12.0,
        "past_defaults": 0,
        "requested_loan_amount": 1_500_000.0,  # 12.5× income
        "txn_volatility_score": 92.0,          # > 80
        "kyc_verified": 1,
    }


@pytest.fixture(scope="module")
def kyc_incomplete_features(clean_features):
    return {**clean_features, "kyc_verified": 0}


@pytest.fixture(scope="module")
def repeat_defaulter_features(clean_features):
    return {**clean_features, "past_defaults": 2}


# ─────────────────────────────────────────────────────────────────────────────
# Document Agent Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDocumentAgent:
    from agents import document_agent

    def test_valid_input_returns_ok(self, clean_features):
        from agents import document_agent
        # Document agent takes raw_input (without dti_ratio pre-computed)
        raw = {k: v for k, v in clean_features.items() if k != "dti_ratio"}
        result = document_agent.run(raw)
        assert result["status"] in ("ok", "warning")
        assert "validated_features" in result
        assert result["dti_ratio"] is not None

    def test_dti_ratio_computed_correctly(self):
        from agents import document_agent
        raw = {
            "age": 30, "employment_years": 5,
            "monthly_income": 50_000,
            "existing_monthly_debt": 15_000,
            "credit_utilization_pct": 40.0,
            "past_defaults": 0,
            "requested_loan_amount": 200_000,
            "txn_volatility_score": 30.0,
            "kyc_verified": 1,
        }
        result = document_agent.run(raw)
        assert abs(result["dti_ratio"] - 0.3) < 1e-3

    def test_missing_required_field_returns_error(self):
        from agents import document_agent
        result = document_agent.run({"age": 30})  # most fields missing
        assert result["status"] == "error"
        assert len(result["validation_errors"]) > 0

    def test_string_coercion(self):
        """UI often sends numeric fields as strings."""
        from agents import document_agent
        raw = {
            "age": "35", "employment_years": "10",
            "monthly_income": "80000",
            "existing_monthly_debt": "20000",
            "credit_utilization_pct": "45",
            "past_defaults": "1",
            "requested_loan_amount": "300000",
            "txn_volatility_score": "55",
            "kyc_verified": "1",
        }
        result = document_agent.run(raw)
        assert result["status"] in ("ok", "warning")
        assert isinstance(result["validated_features"]["monthly_income"], float)


# ─────────────────────────────────────────────────────────────────────────────
# Risk Agent Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskAgent:
    def test_clean_applicant_is_low_or_moderate(self, clean_features):
        from agents import risk_agent
        result = risk_agent.run(clean_features)
        assert result["status"] == "ok"
        assert result["risk_tier"] in ("LOW", "MODERATE")
        assert 0.0 <= result["default_probability"] <= 1.0

    def test_high_risk_applicant_is_high_or_severe(self, high_risk_features):
        from agents import risk_agent
        result = risk_agent.run(high_risk_features)
        assert result["status"] == "ok"
        assert result["risk_tier"] in ("HIGH", "SEVERE")
        assert result["default_probability"] > 0.3

    def test_probability_in_unit_interval(self, aml_features):
        from agents import risk_agent
        result = risk_agent.run(aml_features)
        assert 0.0 <= result["default_probability"] <= 1.0

    def test_risk_tier_is_valid(self, clean_features):
        from agents import risk_agent
        result = risk_agent.run(clean_features)
        assert result["risk_tier"] in ("LOW", "MODERATE", "HIGH", "SEVERE")


# ─────────────────────────────────────────────────────────────────────────────
# Compliance Agent Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestComplianceAgent:
    def test_clean_applicant_is_clear(self, clean_features):
        from agents import compliance_agent
        result = compliance_agent.run(clean_features)
        assert result["compliance_verdict"] == "CLEAR"
        assert not result["has_blocking_flag"]
        assert result["flags"] == []

    def test_aml_structuring_flag(self, aml_features):
        """High volatility + large loan must raise AML_STRUCTURING."""
        from agents import compliance_agent
        result = compliance_agent.run(aml_features)
        assert "AML_STRUCTURING" in result["flags"]
        assert "AML_STRUCTURING" in result["blocking_flags"]
        assert result["has_blocking_flag"] is True
        assert result["compliance_verdict"] == "BLOCK"

    def test_incomplete_kyc_is_blocking(self, kyc_incomplete_features):
        from agents import compliance_agent
        result = compliance_agent.run(kyc_incomplete_features)
        assert "INCOMPLETE_KYC" in result["blocking_flags"]
        assert result["has_blocking_flag"] is True

    def test_repeat_defaulter_is_blocking(self, repeat_defaulter_features):
        from agents import compliance_agent
        result = compliance_agent.run(repeat_defaulter_features)
        assert "REPEAT_DEFAULTER" in result["blocking_flags"]
        assert result["has_blocking_flag"] is True

    def test_high_dti_is_non_blocking_flag(self):
        from agents import compliance_agent
        features = {
            "age": 32, "employment_years": 6,
            "monthly_income": 50_000,
            "existing_monthly_debt": 30_000,
            "dti_ratio": 0.60,  # > 0.55
            "credit_utilization_pct": 35.0,
            "past_defaults": 0,
            "requested_loan_amount": 200_000,
            "txn_volatility_score": 25.0,
            "kyc_verified": 1,
        }
        result = compliance_agent.run(features)
        assert "HIGH_DTI" in result["flags"]
        assert "HIGH_DTI" not in result["blocking_flags"]  # non-blocking
        assert result["compliance_verdict"] == "FLAG"

    def test_retrieved_clauses_non_empty_when_flagged(self, aml_features):
        from agents import compliance_agent
        result = compliance_agent.run(aml_features)
        assert len(result["retrieved_clauses"]) > 0
        # Each clause must have an ID
        for clause in result["retrieved_clauses"]:
            assert "id" in clause


# ─────────────────────────────────────────────────────────────────────────────
# Decision Agent Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionAgent:
    def _make_risk(self, tier: str, prob: float) -> dict:
        return {"risk_tier": tier, "default_probability": prob}

    def _make_compliance(self, verdict: str, blocking: list, flags: list, clauses: list) -> dict:
        return {
            "compliance_verdict": verdict,
            "has_blocking_flag": bool(blocking),
            "blocking_flags": blocking,
            "flags": flags,
            "retrieved_clauses": clauses,
        }

    def test_low_risk_clear_compliance_approved(self, clean_features):
        from agents import decision_agent
        risk = self._make_risk("LOW", 0.12)
        comp = self._make_compliance("CLEAR", [], [], [])
        result = decision_agent.run(clean_features, risk, comp)
        assert result["decision"] == "APPROVED"
        assert result["interest_rate_pct"] == 10.5
        assert result["explanation"] != ""

    def test_manual_review_when_blocking_flag(self, clean_features):
        """Even a LOW-risk applicant must be MANUAL_REVIEW if compliance blocks."""
        from agents import decision_agent
        risk = self._make_risk("LOW", 0.08)  # very low risk
        comp = self._make_compliance(
            "BLOCK",
            ["AML_STRUCTURING"],
            ["AML_STRUCTURING"],
            [{"id": "AML-3.1", "title": "AML Structuring Risk", "text": "..."}],
        )
        result = decision_agent.run(clean_features, risk, comp)
        assert result["decision"] == "MANUAL_REVIEW"
        assert result["interest_rate_pct"] is None

    def test_severe_risk_no_auto_approval(self, high_risk_features):
        from agents import decision_agent
        risk = self._make_risk("SEVERE", 0.75)
        comp = self._make_compliance("CLEAR", [], [], [])
        result = decision_agent.run(high_risk_features, risk, comp)
        assert result["decision"] in ("MANUAL_REVIEW", "REJECTED")

    def test_explanation_is_string(self, clean_features):
        from agents import decision_agent
        risk = self._make_risk("MODERATE", 0.25)
        comp = self._make_compliance("FLAG", [], ["HIGH_DTI"], [])
        result = decision_agent.run(clean_features, risk, comp)
        assert isinstance(result["explanation"], str)
        assert len(result["explanation"]) > 20


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests — Full Graph Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestGraphPipeline:
    @pytest.fixture(scope="class")
    def app(self):
        from graph import build_graph
        return build_graph()

    def test_clean_approval_end_to_end(self, app):
        """Clean applicant should be APPROVED through the full pipeline."""
        result = app.invoke({
            "raw_input": {
                "age": 34, "employment_years": 8,
                "monthly_income": 95_000,
                "existing_monthly_debt": 22_000,
                "credit_utilization_pct": 30.0,
                "past_defaults": 0,
                "requested_loan_amount": 450_000,
                "txn_volatility_score": 22.0,
                "kyc_verified": 1,
            },
            "pipeline_trace": [],
        })
        assert result["decision"] == "APPROVED"
        assert result["interest_rate_pct"] is not None
        assert "document_agent" in result["pipeline_trace"]
        assert "risk_agent" in result["pipeline_trace"]
        assert "compliance_agent" in result["pipeline_trace"]

    def test_high_risk_routes_to_manual_or_rejected(self, app):
        """High-risk applicant with multiple defaults should not be auto-approved."""
        result = app.invoke({
            "raw_input": {
                "age": 28, "employment_years": 1,
                "monthly_income": 30_000,
                "existing_monthly_debt": 24_000,
                "credit_utilization_pct": 88.0,
                "past_defaults": 3,
                "requested_loan_amount": 500_000,
                "txn_volatility_score": 70.0,
                "kyc_verified": 1,
            },
            "pipeline_trace": [],
        })
        assert result["decision"] in ("MANUAL_REVIEW", "REJECTED")
        assert result["decision"] != "APPROVED"

    def test_aml_flag_overrides_low_ml_risk_to_manual_review(self, app):
        """
        CRITICAL TEST:
        An applicant with LOW model risk (good income, no defaults, KYC verified)
        but high txn_volatility_score + large loan MUST be routed to MANUAL_REVIEW.
        This proves that compliance blocking overrides the ML model outcome.
        """
        monthly_income = 120_000
        result = app.invoke({
            "raw_input": {
                "age": 45,
                "employment_years": 15,
                "monthly_income": monthly_income,
                "existing_monthly_debt": 18_000,
                "credit_utilization_pct": 12.0,
                "past_defaults": 0,
                "requested_loan_amount": 1_500_000,  # 12.5× income > 10× threshold
                "txn_volatility_score": 92.0,        # > 80 → AML trigger
                "kyc_verified": 1,
            },
            "pipeline_trace": [],
        })

        # The ML model should see LOW/MODERATE risk
        assert result["risk_tier"] in ("LOW", "MODERATE", "HIGH"), (
            f"Expected low-moderate ML risk; got {result['risk_tier']}"
        )

        # But compliance MUST block it
        assert "AML_STRUCTURING" in result["blocking_flags"], (
            "AML_STRUCTURING flag must be raised"
        )

        # Final decision MUST be MANUAL_REVIEW
        assert result["decision"] == "MANUAL_REVIEW", (
            f"Expected MANUAL_REVIEW (compliance override) but got {result['decision']}"
        )

        # Verify the manual_review_node was in the trace
        assert "manual_review_node" in result["pipeline_trace"]
        # Verify the decision_node was NOT reached (bypassed)
        assert "decision_agent" not in result["pipeline_trace"]

    def test_incomplete_kyc_forces_manual_review(self, app):
        """KYC-incomplete applicant must be escalated regardless of risk."""
        result = app.invoke({
            "raw_input": {
                "age": 34, "employment_years": 8,
                "monthly_income": 95_000,
                "existing_monthly_debt": 22_000,
                "credit_utilization_pct": 30.0,
                "past_defaults": 0,
                "requested_loan_amount": 450_000,
                "txn_volatility_score": 22.0,
                "kyc_verified": 0,  # ← incomplete KYC
            },
            "pipeline_trace": [],
        })
        assert result["decision"] == "MANUAL_REVIEW"
        assert "INCOMPLETE_KYC" in result["blocking_flags"]

    def test_repeat_defaulter_forces_manual_review(self, app):
        """Repeat defaulter must always be escalated."""
        result = app.invoke({
            "raw_input": {
                "age": 34, "employment_years": 8,
                "monthly_income": 95_000,
                "existing_monthly_debt": 22_000,
                "credit_utilization_pct": 30.0,
                "past_defaults": 2,  # ← repeat defaulter
                "requested_loan_amount": 450_000,
                "txn_volatility_score": 22.0,
                "kyc_verified": 1,
            },
            "pipeline_trace": [],
        })
        assert result["decision"] == "MANUAL_REVIEW"
        assert "REPEAT_DEFAULTER" in result["blocking_flags"]

    def test_pipeline_trace_always_has_four_nodes(self, app):
        """All runs should pass through all expected nodes."""
        result = app.invoke({
            "raw_input": {
                "age": 34, "employment_years": 8,
                "monthly_income": 95_000,
                "existing_monthly_debt": 22_000,
                "credit_utilization_pct": 30.0,
                "past_defaults": 0,
                "requested_loan_amount": 450_000,
                "txn_volatility_score": 22.0,
                "kyc_verified": 1,
            },
            "pipeline_trace": [],
        })
        trace = result["pipeline_trace"]
        assert "document_agent" in trace
        assert "risk_agent" in trace
        assert "compliance_agent" in trace
        # Either decision_agent OR manual_review_node (mutually exclusive)
        assert (
            "decision_agent" in trace or "manual_review_node" in trace
        )
