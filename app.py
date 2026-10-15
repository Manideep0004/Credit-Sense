"""
app.py
------
CreditSense — Streamlit demo UI

Features:
  - Side panel for applicant data entry
  - "Run Underwriting" button triggers the full LangGraph pipeline
  - Agent-by-agent trace panel (collapsible) shows each agent's raw output
  - Final decision banner: APPROVED (green) / REJECTED (red) / MANUAL_REVIEW (amber)
  - Explanation text + applicable clause IDs
  - Disclaimer banner

Run:
    streamlit run app.py
"""

import sys
from pathlib import Path

import os
import httpx
import streamlit as st

# Allow imports from creditsense package root
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

API_BASE_URL = os.environ.get(
    "CREDITSENSE_API_URL",
    os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8000"),
)

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CreditSense — AI Loan Underwriting Copilot",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Main bg */
.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    min-height: 100vh;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.04) !important;
    border-right: 1px solid rgba(255,255,255,0.08);
}

/* Decision banners */
.decision-approved {
    background: linear-gradient(135deg, #11998e, #38ef7d);
    color: #fff;
    padding: 1.5rem 2rem;
    border-radius: 16px;
    font-size: 1.6rem;
    font-weight: 700;
    text-align: center;
    letter-spacing: 0.5px;
    box-shadow: 0 8px 32px rgba(56,239,125,0.25);
    animation: fadeIn 0.5s ease;
}
.decision-rejected {
    background: linear-gradient(135deg, #c0392b, #e74c3c);
    color: #fff;
    padding: 1.5rem 2rem;
    border-radius: 16px;
    font-size: 1.6rem;
    font-weight: 700;
    text-align: center;
    box-shadow: 0 8px 32px rgba(231,76,60,0.25);
    animation: fadeIn 0.5s ease;
}
.decision-manual {
    background: linear-gradient(135deg, #f39c12, #f1c40f);
    color: #1a1a2e;
    padding: 1.5rem 2rem;
    border-radius: 16px;
    font-size: 1.6rem;
    font-weight: 700;
    text-align: center;
    box-shadow: 0 8px 32px rgba(241,196,15,0.25);
    animation: fadeIn 0.5s ease;
}

/* Agent cards */
.agent-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.75rem;
    backdrop-filter: blur(10px);
}
.agent-card h4 {
    color: #a78bfa;
    margin: 0 0 0.4rem 0;
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Risk tier badges */
.tier-low    { background: #11998e; color: #fff; }
.tier-mod    { background: #f39c12; color: #fff; }
.tier-high   { background: #e74c3c; color: #fff; }
.tier-severe { background: #8e44ad; color: #fff; }
.tier-badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
}

/* Flag chips */
.flag-blocking { background: #e74c3c; color: #fff; padding: 3px 10px; border-radius: 12px; font-size: 0.78rem; margin-right: 4px; }
.flag-normal   { background: #f39c12; color: #fff; padding: 3px 10px; border-radius: 12px; font-size: 0.78rem; margin-right: 4px; }

.clause-badge { background: rgba(167,139,250,0.2); color: #a78bfa; border: 1px solid #a78bfa; padding: 2px 8px; border-radius: 8px; font-size: 0.78rem; margin-right: 4px; }

/* Section header */
.section-header {
    color: #e2e8f0;
    font-size: 1.1rem;
    font-weight: 600;
    margin: 1.2rem 0 0.5rem;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding-bottom: 0.4rem;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
""",
    unsafe_allow_html=True,
)


# ── helper: load graph (cached) ───────────────────────────────────────────────

@st.cache_resource(show_spinner="Loading underwriting pipeline…")
def get_graph():
    from graph import build_graph
    return build_graph()


# ── sidebar: applicant input form ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🏦 CreditSense")
    st.markdown("*AI Loan Underwriting Copilot*")
    st.divider()

    st.markdown("### 👤 Applicant Profile")

    age = st.slider("Age", 18, 70, 34, key="age")
    employment_years = st.slider("Employment Years", 0, 40, 8, key="emp")
    kyc_verified = st.selectbox("KYC Verified", [1, 0], format_func=lambda x: "✅ Yes" if x else "❌ No", key="kyc")

    st.markdown("### 💰 Financials")
    monthly_income = st.number_input("Monthly Income (₹)", min_value=10_000, max_value=1_000_000, value=90_000, step=5_000, key="income")
    existing_monthly_debt = st.number_input("Existing Monthly Debt (₹)", min_value=0, max_value=500_000, value=18_000, step=1_000, key="debt")
    credit_utilization_pct = st.slider("Credit Utilization (%)", 0, 100, 28, key="cutil")
    requested_loan_amount = st.number_input("Requested Loan Amount (₹)", min_value=10_000, max_value=10_000_000, value=400_000, step=10_000, key="loan")

    st.markdown("### 📊 Risk Indicators")
    past_defaults = st.selectbox("Past Defaults", [0, 1, 2, 3], key="defaults")
    txn_volatility_score = st.slider("Transaction Volatility Score (0-100)", 0, 100, 25, key="txnvol")

    st.divider()

    # Quick-load presets for demo
    st.markdown("#### ⚡ Demo Presets")
    col1, col2, col3 = st.columns(3)
    if col1.button("✅ Clean", use_container_width=True):
        st.session_state["age"] = 34
        st.session_state["emp"] = 8
        st.session_state["kyc"] = 1
        st.session_state["income"] = 95000
        st.session_state["debt"] = 22000
        st.session_state["cutil"] = 30
        st.session_state["loan"] = 450000
        st.session_state["defaults"] = 0
        st.session_state["txnvol"] = 22
        st.rerun()

    if col2.button("⚠️ AML", use_container_width=True):
        st.session_state["age"] = 45
        st.session_state["emp"] = 15
        st.session_state["kyc"] = 1
        st.session_state["income"] = 120000
        st.session_state["debt"] = 18000
        st.session_state["cutil"] = 12
        st.session_state["loan"] = 1500000
        st.session_state["defaults"] = 0
        st.session_state["txnvol"] = 92
        st.rerun()

    if col3.button("❌ Risk", use_container_width=True):
        st.session_state["age"] = 28
        st.session_state["emp"] = 1
        st.session_state["kyc"] = 1
        st.session_state["income"] = 30000
        st.session_state["debt"] = 24000
        st.session_state["cutil"] = 88
        st.session_state["loan"] = 500000
        st.session_state["defaults"] = 3
        st.session_state["txnvol"] = 70
        st.rerun()

    backend_mode = st.radio(
        "Execution Gateway",
        ["FastAPI REST API", "Direct In-Process"],
        index=0,
        help="FastAPI routes requests through the REST gateway. Direct runs the LangGraph engine in-process."
    )

    run_btn = st.button("🚀 Run Underwriting", type="primary", use_container_width=True)


# ── main panel ────────────────────────────────────────────────────────────────

st.markdown("# 🏦 CreditSense")
st.markdown("**Agentic AI Loan Underwriting & Compliance Copilot**")
st.markdown(
    "_Powered by LangGraph · GradientBoosting · ChromaDB / TF-IDF RAG · Groq Llama 3.3 · FastAPI Gateway_"
)
st.divider()

if not run_btn:
    st.markdown(
        """
        <div style='text-align:center;padding:3rem 0;color:rgba(255,255,255,0.5)'>
            <div style='font-size:4rem'>🏦</div>
            <div style='font-size:1.2rem;margin-top:1rem'>Configure applicant details in the sidebar and click <b>Run Underwriting</b></div>
            <div style='font-size:0.9rem;margin-top:0.5rem'>Use the demo presets for instant examples</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ── build and invoke pipeline ─────────────────────────────────────────────────

raw_input = {
    "age": int(age),
    "employment_years": float(employment_years),
    "monthly_income": float(monthly_income),
    "existing_monthly_debt": float(existing_monthly_debt),
    "credit_utilization_pct": float(credit_utilization_pct),
    "past_defaults": int(past_defaults),
    "requested_loan_amount": float(requested_loan_amount),
    "txn_volatility_score": float(txn_volatility_score),
    "kyc_verified": int(kyc_verified),
}

result = {}
with st.spinner("Running multi-agent underwriting pipeline…"):
    if backend_mode == "FastAPI REST API":
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(f"{API_BASE_URL}/api/v1/applications", json=raw_input)
                if resp.status_code in (200, 201):
                    app_data = resp.json()
                    details = app_data.get("decision_details", {}) or {}
                    result = {
                        "decision": details.get("decision"),
                        "risk_tier": details.get("risk_tier"),
                        "default_probability": details.get("default_probability"),
                        "dti_ratio": details.get("dti_ratio"),
                        "flags": details.get("flags", []),
                        "blocking_flags": details.get("blocking_flags", []),
                        "retrieved_clauses": details.get("retrieved_clauses", []),
                        "applied_clause_ids": details.get("applied_clause_ids", []),
                        "explanation": details.get("explanation", ""),
                        "interest_rate_pct": details.get("interest_rate_pct"),
                        "explanation_source": details.get("explanation_source"),
                        "pipeline_trace": details.get("pipeline_trace", []),
                        "validated_features": app_data.get("applicant_data"),
                        "gateway_used": f"FastAPI ({app_data.get('application_id', '')[:8]}...)",
                    }
                else:
                    st.warning(f"FastAPI gateway returned HTTP {resp.status_code}. Falling back to direct in-process engine.")
                    app = get_graph()
                    result = app.invoke({"raw_input": raw_input, "pipeline_trace": []})
        except Exception as e:
            st.info(f"FastAPI gateway unavailable at {API_BASE_URL} ({e}). Executing via direct in-process engine.")
            app = get_graph()
            result = app.invoke({"raw_input": raw_input, "pipeline_trace": []})
    else:
        try:
            app = get_graph()
            result = app.invoke({"raw_input": raw_input, "pipeline_trace": []})
        except Exception as e:
            st.error(f"Pipeline error: {e}")
            st.stop()

decision = result.get("decision", "ERROR")
risk_tier = result.get("risk_tier", "N/A")
prob = result.get("default_probability") or 0.0
flags = result.get("flags", [])
blocking_flags = result.get("blocking_flags", [])
clauses = result.get("retrieved_clauses", [])
explanation = result.get("explanation", "")
interest_rate = result.get("interest_rate_pct")
trace = result.get("pipeline_trace", [])

# ── decision banner ───────────────────────────────────────────────────────────

css_cls = {
    "APPROVED": "decision-approved",
    "REJECTED": "decision-rejected",
    "MANUAL_REVIEW": "decision-manual",
}.get(decision, "decision-manual")

icon = {"APPROVED": "✅", "REJECTED": "❌", "MANUAL_REVIEW": "🔍"}.get(decision, "❓")
label = {"APPROVED": "LOAN APPROVED", "REJECTED": "LOAN REJECTED", "MANUAL_REVIEW": "ESCALATED FOR MANUAL REVIEW"}.get(decision, decision)
rate_str = f"  ·  {interest_rate}% p.a." if interest_rate else ""

st.markdown(
    f'<div class="{css_cls}">{icon} {label}{rate_str}</div>',
    unsafe_allow_html=True,
)

st.markdown("---")

# ── two-column layout ─────────────────────────────────────────────────────────

col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown('<p class="section-header">📝 Decision Explanation</p>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="agent-card">
            <p style="color:#e2e8f0;line-height:1.7;font-size:0.96rem">{explanation}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if clauses:
        st.markdown('<p class="section-header">📋 Applied Policy Clauses</p>', unsafe_allow_html=True)
        for c in clauses:
            with st.expander(f"[{c['id']}] {c.get('title', '')}", expanded=False):
                st.markdown(c.get("text", ""))
                flag_src = c.get("triggered_by_flag", "")
                if flag_src:
                    st.caption(f"Triggered by: `{flag_src}`")

with col_right:
    st.markdown('<p class="section-header">🎯 Risk Assessment</p>', unsafe_allow_html=True)

    tier_cls = {
        "LOW": "tier-low",
        "MODERATE": "tier-mod",
        "HIGH": "tier-high",
        "SEVERE": "tier-severe",
    }.get(risk_tier, "tier-mod")

    st.markdown(
        f"""
        <div class="agent-card">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <div style="color:#94a3b8;font-size:0.8rem">RISK TIER</div>
                    <span class="tier-badge {tier_cls}">{risk_tier}</span>
                </div>
                <div style="text-align:right">
                    <div style="color:#94a3b8;font-size:0.8rem">DEFAULT PROBABILITY</div>
                    <div style="font-size:1.6rem;font-weight:700;color:#e2e8f0">{prob:.1%}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<p class="section-header">🚦 Compliance Flags</p>', unsafe_allow_html=True)
    if flags:
        flag_html = ""
        for f in flags:
            css = "flag-blocking" if f in blocking_flags else "flag-normal"
            flag_html += f'<span class="{css}">{f}</span> '
        st.markdown(f'<div class="agent-card">{flag_html}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="agent-card" style="color:#22c55e">✅ No compliance flags raised</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<p class="section-header">💳 Applicant Summary</p>', unsafe_allow_html=True)
    features = result.get("validated_features", raw_input)
    dti = result.get("dti_ratio") or features.get("dti_ratio", 0)
    st.markdown(
        f"""
        <div class="agent-card">
            <table style="width:100%;font-size:0.85rem;color:#e2e8f0;border-collapse:collapse">
                <tr><td style="padding:4px 0;color:#94a3b8">Monthly Income</td><td style="text-align:right">₹{features.get('monthly_income',0):,.0f}</td></tr>
                <tr><td style="padding:4px 0;color:#94a3b8">Existing Debt</td><td style="text-align:right">₹{features.get('existing_monthly_debt',0):,.0f}</td></tr>
                <tr><td style="padding:4px 0;color:#94a3b8">DTI Ratio</td><td style="text-align:right">{dti:.2%}</td></tr>
                <tr><td style="padding:4px 0;color:#94a3b8">Credit Utilization</td><td style="text-align:right">{features.get('credit_utilization_pct',0):.1f}%</td></tr>
                <tr><td style="padding:4px 0;color:#94a3b8">Past Defaults</td><td style="text-align:right">{features.get('past_defaults',0)}</td></tr>
                <tr><td style="padding:4px 0;color:#94a3b8">Requested Loan</td><td style="text-align:right">₹{features.get('requested_loan_amount',0):,.0f}</td></tr>
                <tr><td style="padding:4px 0;color:#94a3b8">Txn Volatility</td><td style="text-align:right">{features.get('txn_volatility_score',0):.1f}/100</td></tr>
                <tr><td style="padding:4px 0;color:#94a3b8">KYC</td><td style="text-align:right">{'✅ Verified' if features.get('kyc_verified') else '❌ Incomplete'}</td></tr>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── agent trace ───────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown('<p class="section-header">🔍 Agent Execution Trace</p>', unsafe_allow_html=True)

trace_cols = st.columns(len(trace))
for i, node_name in enumerate(trace):
    color = "#a78bfa" if "agent" in node_name or "node" in node_name else "#64748b"
    trace_cols[i].markdown(
        f"""
        <div style="text-align:center;padding:0.6rem;background:rgba(167,139,250,0.1);
             border:1px solid rgba(167,139,250,0.3);border-radius:10px;">
            <div style="font-size:0.75rem;color:{color};font-weight:600">{node_name.replace('_',' ').upper()}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with st.expander("🔬 Raw Agent Outputs (Debug)", expanded=False):
    import json
    st.json({
        "document_agent": {
            "validated_features": result.get("validated_features"),
            "dti_ratio": result.get("dti_ratio"),
            "validation_errors": result.get("validation_errors"),
        },
        "risk_agent": {
            "default_probability": result.get("default_probability"),
            "risk_tier": result.get("risk_tier"),
        },
        "compliance_agent": {
            "flags": flags,
            "blocking_flags": blocking_flags,
            "compliance_verdict": result.get("compliance_verdict"),
            "retrieved_clauses": [{"id": c["id"], "title": c.get("title")} for c in clauses],
        },
        "decision_agent": {
            "decision": decision,
            "interest_rate_pct": interest_rate,
            "applied_clause_ids": result.get("applied_clause_ids"),
            "explanation_source": result.get("explanation_source"),
        },
        "pipeline_trace": trace,
    })

# ── footer disclaimer ─────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "⚠️ **Disclaimer:** CreditSense is a research prototype. "
    "Decisions are generated by AI models and are for demonstration purposes only. "
    "No real credit decisions should be made based on this system without human oversight. "
    "Always comply with applicable banking regulations, RBI guidelines, and PMLA obligations."
)
