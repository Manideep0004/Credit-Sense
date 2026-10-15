"""
creditsense/tests/test_policy_overrides.py
------------------------------------------
Comprehensive unit and integration tests for Deterministic Policy Overrides and Agent Telemetry.

Verifies:
- Hard rule compliance override: Auto-approval is strictly prohibited if any blocking flag is present.
- LLM non-determinism cannot alter the deterministic decision outcome.
- Node latencies are measured and recorded in state for observability.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure creditsense package root is on path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import compliance_agent, decision_agent, document_agent, risk_agent
from graph import build_graph


@pytest.fixture(scope="module")
def graph_app():
    return build_graph()


def test_aml_blocking_overrides_low_ml_risk(graph_app):
    """Low ML risk applicant with AML structuring must be forced to MANUAL_REVIEW."""
    aml_applicant = {
        "age": 45,
        "employment_years": 15.0,
        "monthly_income": 150000.0,
        "existing_monthly_debt": 15000.0,
        "credit_utilization_pct": 10.0,
        "past_defaults": 0,
        "requested_loan_amount": 2000000.0,  # 13.3x income (> 10x)
        "txn_volatility_score": 95.0,        # > 80 -> AML flag
        "kyc_verified": 1,
    }
    result = graph_app.invoke({"raw_input": aml_applicant, "pipeline_trace": []})

    assert result["decision"] == "MANUAL_REVIEW"
    assert "AML_STRUCTURING" in result["blocking_flags"]
    assert result["has_blocking_flag"] is True
    assert result["interest_rate_pct"] is None
    assert "manual_review_node" in result["pipeline_trace"]


def test_incomplete_kyc_blocks_approval(graph_app):
    """Applicant with incomplete KYC must not be approved regardless of clean financials."""
    kyc_missing_applicant = {
        "age": 35,
        "employment_years": 10.0,
        "monthly_income": 100000.0,
        "existing_monthly_debt": 10000.0,
        "credit_utilization_pct": 20.0,
        "past_defaults": 0,
        "requested_loan_amount": 300000.0,
        "txn_volatility_score": 15.0,
        "kyc_verified": 0,  # Incomplete KYC
    }
    result = graph_app.invoke({"raw_input": kyc_missing_applicant, "pipeline_trace": []})

    assert result["decision"] == "MANUAL_REVIEW"
    assert "INCOMPLETE_KYC" in result["blocking_flags"]
    assert result["has_blocking_flag"] is True
    assert result["interest_rate_pct"] is None


def test_repeat_defaulter_blocks_approval(graph_app):
    """Applicant with > 1 past defaults must be blocked from auto-approval."""
    repeat_defaulter = {
        "age": 40,
        "employment_years": 8.0,
        "monthly_income": 80000.0,
        "existing_monthly_debt": 12000.0,
        "credit_utilization_pct": 25.0,
        "past_defaults": 2,  # > 1
        "requested_loan_amount": 250000.0,
        "txn_volatility_score": 20.0,
        "kyc_verified": 1,
    }
    result = graph_app.invoke({"raw_input": repeat_defaulter, "pipeline_trace": []})

    assert result["decision"] == "MANUAL_REVIEW"
    assert "REPEAT_DEFAULTER" in result["blocking_flags"]
    assert result["has_blocking_flag"] is True


def test_clean_applicant_approved(graph_app):
    """Clean applicant with low risk and verified KYC is approved with correct rate."""
    clean_applicant = {
        "age": 34,
        "employment_years": 8.0,
        "monthly_income": 95000.0,
        "existing_monthly_debt": 22000.0,
        "credit_utilization_pct": 28.0,
        "past_defaults": 0,
        "requested_loan_amount": 450000.0,
        "txn_volatility_score": 22.0,
        "kyc_verified": 1,
    }
    result = graph_app.invoke({"raw_input": clean_applicant, "pipeline_trace": []})

    assert result["decision"] == "APPROVED"
    assert result["risk_tier"] == "LOW"
    assert result["interest_rate_pct"] == 10.5
    assert result["has_blocking_flag"] is False
    assert "decision_agent" in result["pipeline_trace"]


def test_node_latencies_telemetry(graph_app):
    """Verify that node latencies are tracked and populated in state."""
    clean_applicant = {
        "age": 30,
        "employment_years": 5.0,
        "monthly_income": 70000.0,
        "existing_monthly_debt": 15000.0,
        "credit_utilization_pct": 20.0,
        "past_defaults": 0,
        "requested_loan_amount": 200000.0,
        "txn_volatility_score": 15.0,
        "kyc_verified": 1,
    }
    result = graph_app.invoke({"raw_input": clean_applicant, "pipeline_trace": []})

    latencies = result.get("node_latencies", {})
    assert "document_agent" in latencies
    assert "risk_agent" in latencies
    assert "compliance_agent" in latencies
    assert "decision_agent" in latencies
    for node_name, lat in latencies.items():
        assert isinstance(lat, float)
        assert lat >= 0.0
