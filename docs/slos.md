# CreditSense - Service Level Objectives (SLOs) & Error Budget Policy

This document defines the production Service Level Indicators (SLIs), Service Level Objectives (SLOs), error budgets, and multi-window multi-burn-rate alerting strategies for the CreditSense underwriting platform.

---

## 1. Executive Summary & SLO Targets

| Objective Name | SLI Measurement | Target (30-Day Rolling) | Error Budget (30-Day) | Alert Threshold |
| :--- | :--- | :--- | :--- | :--- |
| **API Availability** | Successful HTTP 2xx/3xx/4xx requests / Total requests | **99.50%** | **0.50%** (3.6 hours downtime) | Burn Rate > 14.4x (1h) / > 6x (6h) |
| **Pipeline Latency** | p99 end-to-end multi-agent execution duration | **< 5.0 seconds** | **1.00%** of slow applications | p99 > 5.0s for > 3 minutes |
| **API Latency** | p95 synchronous gateway response time | **< 200 ms** | **5.00%** of requests | p95 > 200ms for > 5 minutes |
| **Policy Strictness** | Zero tolerance for policy breach false approvals | **100.00%** | **0%** | Any non-compliant approval = Sev-1 |

---

## 2. Service Level Indicators (SLIs) & PromQL Definitions

### 2.1 API Availability SLI
- **Definition**: The proportion of non-server-error (non-`5xx`) HTTP responses received by clients.
- **PromQL Equation**:
```promql
100 * (
  1 - (
    sum(rate(creditsense_api_requests_total{status_code=~"5.."}[30d]))
    /
    sum(rate(creditsense_api_requests_total[30d]))
  )
)
```

### 2.2 Pipeline End-to-End Latency SLI
- **Definition**: The 99th percentile time taken by the LangGraph multi-agent pipeline from ingestion to final decision persistence.
- **PromQL Equation**:
```promql
histogram_quantile(
  0.99,
  sum(rate(creditsense_application_processing_duration_seconds_bucket[5m])) by (le)
)
```

### 2.3 Agent Node Latency SLI
- **Definition**: The 95th percentile execution latency for individual agent nodes (`financial_agent`, `risk_agent`, `research_agent`, `policy_agent`, `decision_agent`).
- **PromQL Equation**:
```promql
histogram_quantile(
  0.95,
  sum(rate(creditsense_agent_execution_duration_seconds_bucket[5m])) by (le, agent_name)
)
```

### 2.4 Redis Celery Queue Congestion SLI
- **Definition**: The instantaneous gauge of unconsumed loan applications pending processing.
- **PromQL Equation**:
```promql
creditsense_queue_depth{queue_name="celery"}
```

---

## 3. Multi-Window Multi-Burn-Rate Alerting Strategy

Following Google SRE best practices, CreditSense avoids noisy single-threshold alerts by using multi-window error budget burn rate calculations:

```
Burn Rate = (% Error Budget Consumed / Time Elapsed) / (% Allowed Budget / Total Time Window)
```

| Alert Level | Burn Rate | Short Window | Long Window | Budget Consumed | Action / Routing |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Page (Sev-1)** | **14.4x** | 2 min (1h trend) | 1 hour | 2% in 1 hour | Immediate On-Call Page |
| **Warning (Sev-2)** | **6.0x** | 15 min (6h trend) | 6 hours | 5% in 6 hours | Slack / SRE Escalation |
| **Ticket (Sev-3)** | **1.0x** | 1 hour (3d trend) | 3 days | 10% in 3 days | Jira / Next Sprint Ticket |

---

## 4. Error Budget Policy & Enforcement

1. **Error Budget Depletion > 50% in a month**:
   - Feature freeze on risky changes (e.g. prompt template updates, new model checkpoints).
   - Priority shifts to stability, test coverage, and infrastructure resilience.
2. **Error Budget Depletion = 100%**:
   - All deployments blocked except Sev-1 hotfixes and compliance patches.
   - Post-mortem mandatory within 48 hours.
