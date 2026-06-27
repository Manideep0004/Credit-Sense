"""
verify_pipeline.py
------------------
Runs the full CreditSense LangGraph pipeline on 3 test cases with
verbose, colour-coded step-by-step logs so you can see exactly what
each agent produces.

Run from the creditsense/ directory:
    python verify_pipeline.py

No Streamlit needed — plain terminal output.
"""

import json
import sys
import time
from pathlib import Path

# Force UTF-8 output to avoid Windows pipe encoding crash
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
PURPLE = "\033[95m"
WHITE  = "\033[97m"

def c(color, text): return f"{color}{text}{RESET}"
def header(text):   print(f"\n{BOLD}{BLUE}{'═'*62}{RESET}\n{BOLD}{WHITE}  {text}{RESET}\n{BOLD}{BLUE}{'═'*62}{RESET}")
def section(text):  print(f"\n  {BOLD}{CYAN}▶  {text}{RESET}")
def ok(text):       print(f"  {GREEN}✔  {text}{RESET}")
def warn(text):     print(f"  {YELLOW}⚠  {text}{RESET}")
def err(text):      print(f"  {RED}✘  {text}{RESET}")
def kv(k, v, color=WHITE): print(f"  {DIM}{k:<28}{RESET}{color}{v}{RESET}")


def run_case(app, label: str, raw_input: dict, expected_decision: str):
    """Run one test case and print per-agent logs."""
    header(label)

    t0 = time.perf_counter()
    state = app.invoke({"raw_input": raw_input, "pipeline_trace": []})
    elapsed = time.perf_counter() - t0

    trace = state.get("pipeline_trace", [])

    # ── AGENT 1: Document Agent ───────────────────────────────────────────────
    section("AGENT 1 — Document Agent")
    feats = state.get("validated_features", {})
    errs  = state.get("validation_errors", [])
    dstat = state.get("document_status", "?")
    kv("Status",             dstat, GREEN if dstat == "ok" else YELLOW)
    kv("Monthly Income",     f"₹{feats.get('monthly_income', 0):,.0f}")
    kv("Existing Debt",      f"₹{feats.get('existing_monthly_debt', 0):,.0f}")
    kv("DTI Ratio",          f"{feats.get('dti_ratio', 0):.4f}  {'⚠ HIGH' if feats.get('dti_ratio', 0) > 0.55 else '✔ OK'}", YELLOW if feats.get('dti_ratio', 0) > 0.55 else GREEN)
    kv("Credit Utilization", f"{feats.get('credit_utilization_pct', 0):.1f}%")
    kv("Past Defaults",      str(feats.get("past_defaults", 0)), RED if feats.get("past_defaults", 0) > 1 else GREEN)
    kv("KYC Verified",       "YES ✔" if feats.get("kyc_verified") else "NO ✘", GREEN if feats.get("kyc_verified") else RED)
    kv("Txn Volatility",     f"{feats.get('txn_volatility_score', 0):.1f}/100")
    kv("Loan Requested",     f"₹{feats.get('requested_loan_amount', 0):,.0f}")
    kv("Loan/Income Ratio",  f"{feats.get('requested_loan_amount', 0) / max(feats.get('monthly_income', 1), 1):.1f}×")
    if errs:
        for e in errs: warn(f"Validation: {e}")

    # ── AGENT 2: Risk Agent ───────────────────────────────────────────────────
    section("AGENT 2 — Risk Scoring Agent  (GradientBoosting ML Model)")
    prob = state.get("default_probability") or 0.0
    tier = state.get("risk_tier", "UNKNOWN")
    tier_color = {
        "LOW": GREEN, "MODERATE": YELLOW,
        "HIGH": RED, "SEVERE": PURPLE,
    }.get(tier, WHITE)
    kv("Default Probability", f"{prob:.2%}", tier_color)
    kv("Risk Tier",           tier, tier_color)
    kv("Model",               state.get("risk_status", "?"))

    # ── AGENT 3: Compliance Agent ─────────────────────────────────────────────
    section("AGENT 3 — Compliance / AML Agent  (Rules + RAG Retrieval)")
    flags    = state.get("flags", [])
    blocking = state.get("blocking_flags", [])
    verdict  = state.get("compliance_verdict", "?")
    clauses  = state.get("retrieved_clauses", [])

    verdict_color = {"CLEAR": GREEN, "FLAG": YELLOW, "BLOCK": RED}.get(verdict, WHITE)
    kv("Compliance Verdict", verdict, verdict_color)

    if flags:
        kv("Flags Raised", "")
        for f in flags:
            is_block = f in blocking
            flag_color = RED if is_block else YELLOW
            print(f"  {flag_color}    {'[BLOCKING]' if is_block else '[WARNING] '} {f}{RESET}")
    else:
        ok("No compliance flags raised — CLEAR")

    if clauses:
        kv("Retrieved Policy Clauses", "")
        for cl in clauses:
            print(f"  {PURPLE}    [{cl['id']}]{RESET}  {DIM}{cl.get('title', '')}  ← triggered by {cl.get('triggered_by_flag','?')}{RESET}")
    else:
        kv("Retrieved Clauses", "none")

    # ── AGENT 4 / Manual Review Node ─────────────────────────────────────────
    routed_to = "manual_review_node" if "manual_review_node" in trace else "decision_agent"
    section(f"AGENT 4 — {'Manual Review Node  (BLOCKING FLAG OVERRIDE)' if routed_to == 'manual_review_node' else 'Decision Agent  (auto-decision path)'}")

    decision      = state.get("decision", "?")
    interest_rate = state.get("interest_rate_pct")
    explanation   = state.get("explanation", "")
    exp_source    = state.get("explanation_source", "?")
    clause_ids    = state.get("applied_clause_ids", [])

    dec_color = {
        "APPROVED": GREEN,
        "REJECTED": RED,
        "MANUAL_REVIEW": YELLOW,
    }.get(decision, WHITE)

    kv("Decision",            decision, f"{BOLD}{dec_color}")
    kv("Interest Rate",       f"{interest_rate}% p.a." if interest_rate else "N/A")
    kv("Applied Clauses",     ", ".join(clause_ids) or "none")
    kv("Explanation Source",  exp_source)
    print(f"\n  {DIM}Explanation:{RESET}")
    # Word-wrap at 70 chars
    words = explanation.split()
    line, lines = [], []
    for w in words:
        line.append(w)
        if sum(len(x) for x in line) + len(line) > 68:
            lines.append(" ".join(line[:-1]))
            line = [w]
    lines.append(" ".join(line))
    for ln in lines:
        print(f"    {WHITE}{ln}{RESET}")

    # ── Pipeline Trace ────────────────────────────────────────────────────────
    section("Pipeline Execution Trace")
    for i, node in enumerate(trace):
        arrow = "→ " if i < len(trace) - 1 else "⊙ "
        print(f"    {CYAN}{arrow}{node}{RESET}", end="  ")
    print()
    kv("Total Time", f"{elapsed*1000:.0f} ms")

    # ── Assertion ─────────────────────────────────────────────────────────────
    section("Assertion Check")
    if decision == expected_decision:
        ok(f"PASS — got '{decision}' as expected")
    else:
        err(f"FAIL — expected '{expected_decision}' but got '{decision}'")

    return state


def main():
    print(f"\n{BOLD}{PURPLE}{'='*62}")
    print(f"  CreditSense — Pipeline Verification & Agent Log Viewer")
    print(f"{'█'*62}{RESET}")
    print(f"  {DIM}Loading graph and model...{RESET}")

    try:
        from graph import build_graph
        app = build_graph()
        ok("Graph compiled successfully")
    except Exception as e:
        err(f"Graph build failed: {e}")
        sys.exit(1)

    results = []

    # ══════════════════════════════════════════════════════════════════════════
    # TEST CASE 1: Clean applicant → APPROVED
    # ══════════════════════════════════════════════════════════════════════════
    s1 = run_case(
        app,
        label="TEST 1 — Clean Applicant  (expected: APPROVED)",
        raw_input={
            "age": 34,
            "employment_years": 8,
            "monthly_income": 95_000,
            "existing_monthly_debt": 22_000,
            "credit_utilization_pct": 30.0,
            "past_defaults": 0,
            "requested_loan_amount": 450_000,
            "txn_volatility_score": 22.0,
            "kyc_verified": 1,
        },
        expected_decision="APPROVED",
    )
    results.append(("Clean Applicant", s1.get("decision"), "APPROVED"))

    # ══════════════════════════════════════════════════════════════════════════
    # TEST CASE 2: AML structuring risk → MANUAL_REVIEW
    # (Low ML risk, but txn_volatility > 80 AND loan > 10× income)
    # ══════════════════════════════════════════════════════════════════════════
    s2 = run_case(
        app,
        label="TEST 2 — AML Structuring Risk  (expected: MANUAL_REVIEW)\n"
              "         ↳ ML risk is LOW but compliance BLOCKS auto-approval",
        raw_input={
            "age": 45,
            "employment_years": 15,
            "monthly_income": 120_000,
            "existing_monthly_debt": 18_000,
            "credit_utilization_pct": 12.0,
            "past_defaults": 0,
            "requested_loan_amount": 1_500_000,   # 12.5× income → AML trigger
            "txn_volatility_score": 92.0,          # > 80 → AML trigger
            "kyc_verified": 1,
        },
        expected_decision="MANUAL_REVIEW",
    )
    results.append(("AML Override", s2.get("decision"), "MANUAL_REVIEW"))

    # ══════════════════════════════════════════════════════════════════════════
    # TEST CASE 3: High-risk applicant (repeat defaulter + high DTI)
    # ══════════════════════════════════════════════════════════════════════════
    s3 = run_case(
        app,
        label="TEST 3 — High-Risk Repeat Defaulter  (expected: MANUAL_REVIEW)",
        raw_input={
            "age": 28,
            "employment_years": 1,
            "monthly_income": 30_000,
            "existing_monthly_debt": 24_000,
            "credit_utilization_pct": 88.0,
            "past_defaults": 3,
            "requested_loan_amount": 500_000,
            "txn_volatility_score": 70.0,
            "kyc_verified": 1,
        },
        expected_decision="MANUAL_REVIEW",
    )
    results.append(("Repeat Defaulter", s3.get("decision"), "MANUAL_REVIEW"))

    # ══════════════════════════════════════════════════════════════════════════
    # TEST CASE 4: Incomplete KYC → MANUAL_REVIEW
    # ══════════════════════════════════════════════════════════════════════════
    s4 = run_case(
        app,
        label="TEST 4 — Incomplete KYC  (expected: MANUAL_REVIEW)\n"
              "         ↳ Good financials but KYC not verified",
        raw_input={
            "age": 34,
            "employment_years": 8,
            "monthly_income": 95_000,
            "existing_monthly_debt": 22_000,
            "credit_utilization_pct": 30.0,
            "past_defaults": 0,
            "requested_loan_amount": 450_000,
            "txn_volatility_score": 22.0,
            "kyc_verified": 0,               # ← KYC incomplete
        },
        expected_decision="MANUAL_REVIEW",
    )
    results.append(("Incomplete KYC", s4.get("decision"), "MANUAL_REVIEW"))

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{BOLD}{BLUE}{'═'*62}{RESET}")
    print(f"{BOLD}{WHITE}  VERIFICATION SUMMARY{RESET}")
    print(f"{BOLD}{BLUE}{'═'*62}{RESET}\n")

    all_pass = True
    for name, got, expected in results:
        passed = got == expected
        all_pass = all_pass and passed
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  [{status}]  {name:<25} got={BOLD}{got}{RESET}  expected={expected}")

    print()
    if all_pass:
        print(f"  {BOLD}{GREEN}✔  ALL {len(results)} TEST CASES PASSED — Pipeline is working correctly!{RESET}")
    else:
        print(f"  {BOLD}{RED}✘  Some tests failed — check output above.{RESET}")
    print()


if __name__ == "__main__":
    main()
