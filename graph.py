"""
graph.py
--------
LangGraph StateGraph wiring the four CreditSense agents with conditional routing.

State: CreditSenseState (TypedDict)
Nodes:
  - document_node    : Document Agent
  - risk_node        : Risk Scoring Agent
  - compliance_node  : Compliance / AML Agent
  - decision_node    : Decision Agent (auto-decision path)
  - manual_review_node : Terminal node for blocked applications

Conditional Edge (after compliance_node):
  - If has_blocking_flag == True  → manual_review_node
  - Else                          → decision_node

Usage:
    from graph import build_graph
    app = build_graph()
    result = app.invoke({"raw_input": {...}})
"""

from __future__ import annotations

import time
from typing import Any, Optional

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from agents import compliance_agent, decision_agent, document_agent, risk_agent
from monitoring.metrics import (
    AGENT_EXECUTION_DURATION_SECONDS,
    RAG_RETRIEVAL_LATENCY_SECONDS,
    RISK_MODEL_LATENCY_SECONDS,
)
from otel.tracer import trace_span


# ── shared state schema ───────────────────────────────────────────────────────

class CreditSenseState(TypedDict, total=False):
    # Raw input from caller
    raw_input: dict[str, Any]

    # Document Agent output
    validated_features: dict[str, Any]
    dti_ratio: Optional[float]
    validation_errors: list[str]
    document_status: str

    # Risk Agent output
    default_probability: Optional[float]
    risk_tier: Optional[str]
    risk_status: str

    # Compliance Agent output
    flags: list[str]
    blocking_flags: list[str]
    has_blocking_flag: bool
    retrieved_clauses: list[dict]
    compliance_verdict: str
    compliance_status: str

    # Decision Agent output
    decision: Optional[str]
    interest_rate_pct: Optional[float]
    explanation: Optional[str]
    applied_clause_ids: list[str]
    explanation_source: Optional[str]
    decision_status: str

    # Observability & Meta
    pipeline_trace: list[str]
    node_latencies: dict[str, float]


# ── node functions ────────────────────────────────────────────────────────────

def document_node(state: CreditSenseState) -> CreditSenseState:
    t0 = time.perf_counter()
    raw = state.get("raw_input", {})
    with trace_span("DocumentAgent.validate", {"applicant.age": raw.get("age")}) as span:
        out = document_agent.run(raw)
        lat = round(time.perf_counter() - t0, 4)
        AGENT_EXECUTION_DURATION_SECONDS.labels(agent_name="document_agent").observe(lat)
        span.set_attribute("agent.status", out["status"])
        span.set_attribute("agent.dti_ratio", out.get("dti_ratio") or 0.0)

    trace = state.get("pipeline_trace", [])
    trace.append("document_agent")
    latencies = state.get("node_latencies", {})
    latencies["document_agent"] = lat

    return {
        **state,
        "validated_features": out["validated_features"],
        "dti_ratio": out["dti_ratio"],
        "validation_errors": out["validation_errors"],
        "document_status": out["status"],
        "pipeline_trace": trace,
        "node_latencies": latencies,
    }


def risk_node(state: CreditSenseState) -> CreditSenseState:
    t0 = time.perf_counter()
    features = state.get("validated_features", {})
    with trace_span("RiskAgent.predict", {"model.type": "GradientBoostingClassifier"}) as span:
        out = risk_agent.run(features)
        lat = round(time.perf_counter() - t0, 4)
        AGENT_EXECUTION_DURATION_SECONDS.labels(agent_name="risk_agent").observe(lat)
        RISK_MODEL_LATENCY_SECONDS.observe(lat)
        span.set_attribute("risk.tier", out.get("risk_tier", "UNKNOWN"))
        span.set_attribute("risk.probability", out.get("default_probability") or 0.0)

    trace = state.get("pipeline_trace", [])
    trace.append("risk_agent")
    latencies = state.get("node_latencies", {})
    latencies["risk_agent"] = lat

    return {
        **state,
        "default_probability": out.get("default_probability"),
        "risk_tier": out.get("risk_tier"),
        "risk_status": out.get("status", "ok"),
        "pipeline_trace": trace,
        "node_latencies": latencies,
    }


def compliance_node(state: CreditSenseState) -> CreditSenseState:
    t0 = time.perf_counter()
    features = state.get("validated_features", {})
    risk_out = {
        "default_probability": state.get("default_probability"),
        "risk_tier": state.get("risk_tier"),
    }
    with trace_span("ComplianceAgent.evaluate_and_retrieve") as span:
        out = compliance_agent.run(features, risk_out)
        lat = round(time.perf_counter() - t0, 4)
        AGENT_EXECUTION_DURATION_SECONDS.labels(agent_name="compliance_agent").observe(lat)
        RAG_RETRIEVAL_LATENCY_SECONDS.labels(backend="auto").observe(lat)
        span.set_attribute("compliance.verdict", out.get("compliance_verdict", "UNKNOWN"))
        span.set_attribute("compliance.has_blocking_flag", out.get("has_blocking_flag", False))
        span.set_attribute("compliance.flags_count", len(out.get("flags", [])))

    trace = state.get("pipeline_trace", [])
    trace.append("compliance_agent")
    latencies = state.get("node_latencies", {})
    latencies["compliance_agent"] = lat

    return {
        **state,
        "flags": out.get("flags", []),
        "blocking_flags": out.get("blocking_flags", []),
        "has_blocking_flag": out.get("has_blocking_flag", False),
        "retrieved_clauses": out.get("retrieved_clauses", []),
        "compliance_verdict": out.get("compliance_verdict", "ERROR"),
        "compliance_status": out.get("status", "ok"),
        "pipeline_trace": trace,
        "node_latencies": latencies,
    }


def decision_node(state: CreditSenseState) -> CreditSenseState:
    t0 = time.perf_counter()
    features = state.get("validated_features", {})
    risk_out = {
        "default_probability": state.get("default_probability"),
        "risk_tier": state.get("risk_tier"),
    }
    compliance_out = {
        "flags": state.get("flags", []),
        "blocking_flags": state.get("blocking_flags", []),
        "has_blocking_flag": state.get("has_blocking_flag", False),
        "retrieved_clauses": state.get("retrieved_clauses", []),
        "compliance_verdict": state.get("compliance_verdict", "CLEAR"),
    }
    with trace_span("DecisionAgent.synthesize") as span:
        out = decision_agent.run(features, risk_out, compliance_out)
        lat = round(time.perf_counter() - t0, 4)
        AGENT_EXECUTION_DURATION_SECONDS.labels(agent_name="decision_agent").observe(lat)
        span.set_attribute("decision.outcome", out.get("decision", "UNKNOWN"))
        span.set_attribute("decision.explanation_source", out.get("explanation_source", "unknown"))

    trace = state.get("pipeline_trace", [])
    trace.append("decision_agent")
    latencies = state.get("node_latencies", {})
    latencies["decision_agent"] = lat

    return {
        **state,
        "decision": out.get("decision"),
        "interest_rate_pct": out.get("interest_rate_pct"),
        "explanation": out.get("explanation"),
        "applied_clause_ids": out.get("applied_clause_ids", []),
        "explanation_source": out.get("explanation_source"),
        "decision_status": out.get("status", "ok"),
        "pipeline_trace": trace,
        "node_latencies": latencies,
    }


def manual_review_node(state: CreditSenseState) -> CreditSenseState:
    """
    Terminal node for applications with blocking compliance flags.
    Sets decision = MANUAL_REVIEW and writes a standard explanation
    without invoking the Decision Agent's auto-approval logic.
    """
    t0 = time.perf_counter()
    trace = state.get("pipeline_trace", [])
    trace.append("manual_review_node")

    blocking = state.get("blocking_flags", [])
    clauses = state.get("retrieved_clauses", [])
    clause_ids = [c["id"] for c in clauses]
    loan_amount = state.get("validated_features", {}).get("requested_loan_amount", 0)

    explanation = (
        f"This application (loan request ₹{loan_amount:,.0f}) has been escalated "
        f"for mandatory manual review. "
        f"Blocking compliance flags: {', '.join(blocking) or 'N/A'}. "
        f"Applicable policy clauses: {', '.join(clause_ids) or 'N/A'}. "
        "Automatic approval is prohibited. A compliance officer will be in touch "
        "within 3 business days."
    )
    lat = round(time.perf_counter() - t0, 4)
    latencies = state.get("node_latencies", {})
    latencies["manual_review_node"] = lat

    return {
        **state,
        "decision": "MANUAL_REVIEW",
        "interest_rate_pct": None,
        "explanation": explanation,
        "applied_clause_ids": clause_ids,
        "explanation_source": "manual_review_node",
        "decision_status": "ok",
        "pipeline_trace": trace,
        "node_latencies": latencies,
    }


# ── conditional routing ───────────────────────────────────────────────────────

def _route_after_compliance(state: CreditSenseState) -> str:
    """
    Core conditional edge:
      - Blocking flag present → manual_review (cannot be auto-approved)
      - Otherwise             → decision (auto-decision path)

    This is the critical 'agentic override' that ensures AML / KYC / repeat-
    defaulter flags always escalate regardless of the ML model's risk tier.
    """
    if state.get("has_blocking_flag", False):
        return "manual_review"
    return "decision"


# ── graph builder ─────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Build and compile the CreditSense LangGraph state machine."""
    graph = StateGraph(CreditSenseState)

    # Register nodes
    graph.add_node("document", document_node)
    graph.add_node("risk", risk_node)
    graph.add_node("compliance", compliance_node)
    graph.add_node("decision", decision_node)
    graph.add_node("manual_review", manual_review_node)

    # Entry point
    graph.set_entry_point("document")

    # Linear edges: document → risk → compliance
    graph.add_edge("document", "risk")
    graph.add_edge("risk", "compliance")

    # Conditional edge: compliance → {decision | manual_review}
    graph.add_conditional_edges(
        "compliance",
        _route_after_compliance,
        {
            "decision": "decision",
            "manual_review": "manual_review",
        },
    )

    # Terminal edges
    graph.add_edge("decision", END)
    graph.add_edge("manual_review", END)

    return graph.compile()


# ── CLI smoke test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    app = build_graph()

    # -- Test 1: Clean approval candidate
    clean_applicant = {
        "age": 32,
        "employment_years": 7,
        "monthly_income": 90_000,
        "existing_monthly_debt": 20_000,
        "credit_utilization_pct": 28.0,
        "past_defaults": 0,
        "requested_loan_amount": 400_000,
        "txn_volatility_score": 25.0,
        "kyc_verified": 1,
    }
    print("=" * 60)
    print("TEST 1: Clean Applicant")
    r1 = app.invoke({"raw_input": clean_applicant, "pipeline_trace": []})
    print(f"  Decision  : {r1['decision']}")
    print(f"  Risk Tier : {r1['risk_tier']}  (prob={r1['default_probability']:.1%})")
    print(f"  Flags     : {r1['flags']}")
    print(f"  Trace     : {r1['pipeline_trace']}")

    # -- Test 2: AML flagged (low ML risk but high volatility + big loan)
    aml_applicant = {
        "age": 45,
        "employment_years": 12,
        "monthly_income": 100_000,
        "existing_monthly_debt": 20_000,
        "credit_utilization_pct": 15.0,
        "past_defaults": 0,
        "requested_loan_amount": 1_500_000,  # > 10x income
        "txn_volatility_score": 92.0,        # > 80 → AML flag
        "kyc_verified": 1,
    }
    print("\n" + "=" * 60)
    print("TEST 2: AML-flagged Applicant (low ML risk, but must → MANUAL_REVIEW)")
    r2 = app.invoke({"raw_input": aml_applicant, "pipeline_trace": []})
    print(f"  Decision  : {r2['decision']}")
    print(f"  Risk Tier : {r2['risk_tier']}  (prob={r2['default_probability']:.1%})")
    print(f"  Flags     : {r2['flags']}")
    print(f"  Blocking  : {r2['blocking_flags']}")
    print(f"  Trace     : {r2['pipeline_trace']}")
