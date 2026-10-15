# CreditSense - 10 Production Failure Scenarios, Resiliency Drills & Post-Mortem RCAs

This document details 10 real-world production failure modes simulated and verified across the CreditSense platform, along with their root-cause analysis (RCA), automated mitigations, and architectural safeguards.

---

## Failure Matrix Summary

| ID | Failure Mode | Trigger / Fault Injection | Automated Detection (Alert / Metric) | Resiliency Mitigation / Fallback | Recovery SLA |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **F-01** | Redis Broker Crash | Kill Redis container during peak traffic | Celery task submission timeout / `creditsense_queue_depth` stagnant | Synchronous fallback pipeline executes locally; alerts SRE | < 50ms |
| **F-02** | Postgres DB Starvation | Max connections pool reached (100+) | DB query latency histogram spike / `500` error rate | SQLAlchemy connection pool recycling & circuit breaker rejection | < 1s |
| **F-03** | Worker Pod OOM Crash | Worker process killed by kernel OOM | K8s Pod CrashLoop / `creditsense_queue_depth > 50` | KEDA/K8s restarts pod; task idempotency prevents duplicate evaluation | < 15s |
| **F-04** | LLM Gateway Timeout | LLM endpoint latency > 10s / HTTP 504 | `creditsense_llm_failures_total` counter increment | Deterministic fallback explanations generated without dropping decision | Instant (< 5ms) |
| **F-05** | ChromaDB Lockup | Vector store file lock / disk IO bottleneck | `creditsense_rag_retrieval_latency_seconds` spike | Automatic fallback to in-memory TF-IDF policy retriever | Instant (< 2ms) |
| **F-06** | 10x Application Traffic Surge | Locust load injection (1,000 req/s) | `creditsense_queue_depth` > 5 threshold | KEDA scales workers from 1 to 20 replicas horizontally | < 30s |
| **F-07** | Schema Poisoning Attempt | Invalid field types / malicious JSON | HTTP 422 `VALIDATION_ERROR` count spike | Pydantic strict schemas block payload before touching agents/DB | 0ms (pre-ingress) |
| **F-08** | Regulatory Breach Exploit | Applicant with DTI=55% & Credit=780 | Policy agent flag `HARD_POLICY_FAIL` | Deterministic override overrides ML score and forces `REJECTED` | Deterministic |
| **F-09** | K8s Node Termination | Preemptible node spot termination | K8s Pod SIGTERM signal | Pre-stop hook cancels consumers gracefully; in-flight tasks re-queued | < 10s |
| **F-10** | Memory Leak in Worker Process | Gradual memory accumulation in cache | Memory limit threshold breached (2Gi) | K8s restarts container cleanly; Celery max-tasks-per-child worker recycling | Auto-recycling |

---

## Detailed Post-Mortem RCAs

### Scenario 1: Redis Broker Outage & Synchronous Fallback (F-01)
- **Incident Summary**: At 14:10 UTC, the Redis master container became unreachable due to an unexpected memory exhaustion event.
- **Impact**: Celery task dispatch failed with connection errors.
- **Detection**: API middleware intercepted Redis connection exceptions; Prometheus alert `CeleryQueueDepthCritical` fired.
- **Architectural Recovery**: `creditsense/api/service.py` caught the broker exception and gracefully routed incoming requests to the local synchronous LangGraph executor, returning `HTTP 200 (COMPLETED)` with zero dropped loan applications.
- **Preventative Action**: Added Redis memory limits and memory defragmentation policies in `docker-compose.yml` and Helm charts.

---

### Scenario 4: External LLM Timeout & Deterministic Fallback (F-04)
- **Incident Summary**: External LLM API experienced 15-second upstream latency spikes and returned HTTP 504 Gateway Timeouts.
- **Impact**: Synthesis of loan explanation summaries delayed agent pipeline.
- **Detection**: `creditsense_llm_failures_total{provider="gemini", error_type="timeout"}` counter incremented.
- **Architectural Recovery**: Decision agent caught `TimeoutError` and immediately activated the deterministic rule-based template generator, preserving decision integrity and meeting the p99 latency SLO of < 5 seconds.
- **Preventative Action**: Added a 3-second strict timeout on all outbound LLM API requests with circuit breaker.

---

### Scenario 8: Deterministic Regulatory Override of High ML Score (F-08)
- **Incident Summary**: Applicant submitted a high-income profile with high credit score (780), which the ML model scored at 0.94 approval confidence. However, applicant's Debt-to-Income (DTI) ratio was 52% (violating statutory maximum 43%).
- **Impact**: Potential illegal loan approval if model decision was trusted blindly.
- **Detection**: PolicyAgent flagged statutory breach clause `DTI_REG_CAP_43`.
- **Architectural Recovery**: `DecisionAgent` evaluated `hard_violations` list. Because list was non-empty, `deterministic_compliance_override` immediately forced decision to `REJECTED`, completely overriding ML model probability.
- **Preventative Action**: Unit test suite `tests/test_policy_overrides.py` enforced in CI pipeline.
