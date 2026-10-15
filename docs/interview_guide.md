# CreditSense - Technical Engineering Interview Guide

This guide prepares you to present, defend, and deep-dive into the architectural decisions of CreditSense across **SRE, Cloud, Platform, DevOps, Backend, and AI/ML** engineering interviews.

---

## 1. System Architecture & High-Level Design

### Q1: Can you give an executive overview of CreditSense?
> **Answer**:  
> "CreditSense is a cloud-native, observable, multi-agent credit underwriting platform. It receives loan applications via a hardened FastAPI gateway, enqueues work asynchronously into Redis/Celery, and executes a LangGraph deterministic-first multi-agent underwriting pipeline.  
> The pipeline combines ML default risk scoring (GradientBoosting), hybrid RAG regulatory compliance retrieval (ChromaDB/TF-IDF), and a strict **deterministic compliance override layer** that ensures legal and credit policy constraints strictly override statistical ML scores.  
> The entire stack is instrumented with Prometheus SLI/SLO metrics, OpenTelemetry distributed tracing, Grafana dashboards, and is deployable via Kubernetes with KEDA event-driven autoscaling, while remaining 100% cost-free for local development."

---

## 2. Site Reliability Engineering (SRE) & Observability

### Q2: How did you design your SLIs, SLOs, and alerting rules?
> **Answer**:  
> "I followed Google SRE principles:
> 1. **Availability SLO**: 99.5% successful HTTP requests over rolling 30 days (`status_code < 500`).
> 2. **Pipeline Latency SLO**: p99 execution duration < 5.0 seconds.
> 3. **Multi-Window Multi-Burn-Rate Alerts**: Instead of noisy single-threshold spikes, we calculate error budget burn rates over multiple lookback windows (e.g. 14.4x burn rate over 1 hour pages on-call, 6x burn rate over 6 hours creates a Sev-2 warning). This eliminates false alarms during brief micro-spikes while catching catastrophic outages within 2 minutes."

### Q3: How do you trace a loan application through asynchronous queues and agents?
> **Answer**:  
> "We implement OpenTelemetry distributed tracing with custom context propagation. When an HTTP request enters FastAPI, a unique `trace_id` is created and injected into the response headers (`X-Request-ID`). When enqueuing a Celery task, the OTel trace context is injected into task kwargs/headers. The background worker extracts the trace context and binds subsequent LangGraph agent execution spans (`FinancialAgent`, `RiskAgent`, `PolicyAgent`, `DecisionAgent`) under the same trace. In Jaeger, an engineer can visualize the complete trace across process and network boundaries."

---

## 3. Cloud & Platform Engineering (Kubernetes, KEDA & Terraform)

### Q4: Why use KEDA instead of standard Kubernetes Horizontal Pod Autoscaler (HPA)?
> **Answer**:  
> "Standard Kubernetes HPA scales solely on CPU or memory metrics. In an asynchronous worker architecture, queue depth (the number of pending loan applications waiting in Redis) is the true indicator of load. A worker waiting for I/O might consume low CPU while a massive backlog builds up.  
> KEDA queries the Redis queue length directly every 10 seconds. When queue length exceeds 5 items per worker, KEDA immediately scales the worker pool up to 20 replicas, and scales back down when the queue drains."

### Q5: How is your Terraform code structured and how did you address cloud costs?
> **Answer**:  
> "The Terraform repository is organized into reusable modules (`vpc`, `rds`, `elasticache`) with distinct environment roots: `environments/local` (which targets Kind/Minikube with Helm releases for $0 local cost) and `environments/aws` (which targets production AWS). The AWS root includes clear cost warning banners and is optimized for FinOps using AWS Graviton ARM64 instances, spot worker pools, and single-AZ development configurations to reduce costs by nearly 70%."

---

## 4. Backend Engineering & Data Integrity

### Q6: How do you guarantee idempotency and prevent double-processing?
> **Answer**:  
> "Idempotency is enforced at both the API and worker layers:
> 1. At API submission, applications check for existing active tax IDs or client-supplied idempotency keys in PostgreSQL.
> 2. In Celery workers, before executing the LangGraph pipeline, the task acquires an application row lock and checks `application.status`. If the application is already `COMPLETED`, the task exits immediately without re-running the ML model or altering audit trails."

---

## 5. AI/ML & Regulatory Compliance

### Q7: Why did you implement a 'Deterministic Compliance Override' and not let the AI make the final decision?
> **Answer**:  
> "In consumer lending and fintech, lending regulations (such as statutory Debt-to-Income caps under Dodd-Frank, FCRA, and ECOA guidelines) are legal mandates with zero tolerance. Statistical ML models or LLMs are probabilistic and can hallucinate or approve high-risk applicants due to outlier features.  
> In CreditSense, the Policy Agent evaluates non-negotiable rules. If a hard policy breach is detected (e.g. DTI > 43%), the `DecisionAgent` overrides the ML probability with an absolute `REJECTED` decision. This prevents AI hallucination risks in high-stakes financial compliance."

### Q8: What happens if ChromaDB or the external LLM provider fails?
> **Answer**:  
> "We engineered strict graceful fallbacks:
> 1. If ChromaDB or embedding weights are unavailable, the RAG subsystem immediately falls back to our in-memory TF-IDF vectorizer (`TfidfRetriever`), executing semantic search in < 2ms without dropping the request.
> 2. If the LLM provider times out (> 3s) or throws an API error, the decision agent falls back to a deterministic explanation template, guaranteeing zero dropped loan applications and preserving our p99 latency SLO."
