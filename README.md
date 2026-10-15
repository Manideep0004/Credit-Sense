# CreditSense 🏦⚡
> **Cloud-Native, Observable, Multi-Agent Credit Underwriting & Decision Support Platform**  
> *Production-style portfolio platform demonstrating modern SRE, Cloud, Platform, DevOps, and Backend engineering practices.*

---

[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/Multi--Agent-LangGraph-FF6F00?style=flat-square)](https://langchain.com)
[![Celery](https://img.shields.io/badge/Workers-Celery%20%2B%20Redis-37814A?style=flat-square&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Prometheus](https://img.shields.io/badge/Metrics-Prometheus-E6522C?style=flat-square&logo=prometheus&logoColor=white)](https://prometheus.io)
[![Grafana](https://img.shields.io/badge/Dashboards-Grafana-F46800?style=flat-square&logo=grafana&logoColor=white)](https://grafana.com)
[![OpenTelemetry](https://img.shields.io/badge/Tracing-OpenTelemetry%20%2B%20Jaeger-4053D6?style=flat-square&logo=opentelemetry&logoColor=white)](https://opentelemetry.io)
[![Kubernetes](https://img.shields.io/badge/Orchestration-Kubernetes%20%2B%20KEDA-326CE5?style=flat-square&logo=kubernetes&logoColor=white)](https://keda.sh)
[![Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC?style=flat-square&logo=terraform&logoColor=white)](https://terraform.io)
[![Cost](https://img.shields.io/badge/Local%20Cost-%240.00%20Free-brightgreen?style=flat-square)](docs/cost_optimization.md)

---

## 🎯 Executive Overview

**CreditSense** transforms traditional credit scoring into an observable, scalable, cloud-native automated decision pipeline. It combines:
1. **Asynchronous API Gateway (FastAPI)** with idempotency guarantees, correlation IDs, and OWASP security hardening.
2. **LangGraph Multi-Agent Underwriting Engine** with specialized agents: Financial, Risk (ML GradientBoosting), Research, Policy (RAG), and Decision.
3. **Deterministic Regulatory Compliance Layer**: Legal mandates (e.g. statutory DTI > 43% cap) strictly override ML confidence probabilities, preventing AI hallucination risks in high-stakes financial operations.
4. **Resilient Dual-Engine RAG**: ChromaDB vector store with instant automatic fallback to in-memory TF-IDF.
5. **Full-Stack Observability & SRE Alerting**: Prometheus SLI/SLO tracking, Google SRE multi-window multi-burn-rate alerts, Jaeger distributed tracing, and pre-provisioned Grafana dashboards.
6. **Cloud-Native Autoscaling**: Kubernetes manifests and KEDA `ScaledObject` scaling worker pods based on real-time Redis queue depth.
7. **100% $0 Local Cost**: Zero paid SaaS dependencies. Fully runnable on laptop or free Kubernetes (Kind/Minikube).

---

## 🏗️ System Architecture

```
                                  ┌────────────────────────┐
                                  │ Streamlit / REST Client│
                                  └───────────┬────────────┘
                                              │ HTTP / JSON
                                              ▼
                                  ┌────────────────────────┐
                 ┌───────────────►│  FastAPI Gateway (8000)│◄───────────────┐
                 │                └───────────┬────────────┘                │
                 │                            │                             │
                 │ 202 Accepted               │ Task Dispatch (Trace ID)    │ Scrapes
                 │ Polling Status             ▼                             │ /metrics
                 │                ┌────────────────────────┐                │
                 │                │ Redis Broker & Backend │                │
                 │                └───────────┬────────────┘                │
                 │                            │ Task Queue                  │
                 │                            ▼                             ▼
   ┌─────────────┴────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
   │ PostgreSQL DB (Audit Tr) │   │ Celery Worker Pool     │   │ Prometheus & Grafana   │
   └─────────────▲────────────┘   │ (Autoscaled via KEDA)  │   │ Dashboards & Alerts    │
                 │                └───────────┬────────────┘   └────────────────────────┘
                 │ Persist Decision           │
                 │ & Audit Log                ▼
                 │                ┌─────────────────────────────────────────────────────┐
                 │                │             LangGraph Multi-Agent Pipeline          │
                 │                │                                                     │
                 │                │  FinancialAgent ──► RiskAgent (ML Inference)        │
                 │                │                            │                        │
                 │                │                            ▼                        │
                 │                │  DecisionAgent ◄── PolicyAgent (RAG / TF-IDF)       │
                 │                │  (Deterministic            ▲                        │
                 │                │   Compliance Override)     │                        │
                 │                └────────────────────────────┼────────────────────────┘
                 │                                             │ Clause Search
                 │                                             ▼
                 └─────────────────────────────────── ChromaDB / TF-IDF Store
```

---

## 🚀 Quick Start (Choose Your Preferred Mode)

### Mode 1: Full Docker Compose Stack ($0 Cost, 1 Command)
```bash
# Clone the repository
git clone https://github.com/your-username/CreditSense.git
cd CreditSense

# Spin up all 8 services (API, Celery, Postgres, Redis, Prometheus, Grafana, Jaeger, Streamlit)
docker compose up --build -d
```

Access the services:
- **FastAPI Interactive Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Streamlit Underwriter UI**: [http://localhost:8501](http://localhost:8501)
- **Grafana SRE Dashboard**: [http://localhost:3000](http://localhost:3000) (User: `admin` / Password: `admin`)
- **Prometheus Alert Manager**: [http://localhost:9090/alerts](http://localhost:9090/alerts)
- **Jaeger Distributed Tracing**: [http://localhost:16686](http://localhost:16686)

---

### Mode 2: Local Standalone Python (Fast, Zero Docker Required)
```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Ingest credit policy corpus (TF-IDF instant mode)
python rag/ingest.py --force-tfidf

# Start FastAPI Gateway
uvicorn api.main:app --reload --port 8000
```

---

## 📊 Observability & SRE Metrics

CreditSense exposes Prometheus metrics at `/api/v1/metrics`:
- `creditsense_applications_total`: Total applications broken down by decision (`APPROVED`, `REJECTED`, `MANUAL_REVIEW`).
- `creditsense_application_processing_duration_seconds`: Pipeline end-to-end latency histogram.
- `creditsense_agent_execution_duration_seconds`: Individual agent node latency breakdown (`financial_agent`, `risk_agent`, `research_agent`, `policy_agent`, `decision_agent`).
- `creditsense_queue_depth`: Instantaneous Redis task queue backlog.
- `creditsense_api_requests_total`: HTTP request rates and response codes for availability SLI calculation.

### Service Level Objectives (SLOs)
- **Availability SLO**: 99.5% non-5xx requests over rolling 30 days.
- **Latency SLO**: p99 end-to-end processing latency < 5.0 seconds.
- **Alerting**: Multi-window multi-burn-rate alerts (14.4x 1h page, 6x 6h warning).
- Detailed documentation: [`docs/slos.md`](docs/slos.md).

---

## 🛡️ Production Failure Drills & RCAs

We simulated, tested, and documented 10 production failure modes:
1. **Redis Broker Outage**: Graceful fallback to local synchronous pipeline without dropping applications.
2. **Postgres Pool Starvation**: Connection recycling and circuit-breaker handling.
3. **Worker Pod OOM Crash**: Task idempotency prevents duplicate evaluation upon restart.
4. **LLM Provider Timeout**: Strict 3s timeout with instant deterministic explanation fallback.
5. **ChromaDB Vector Store Lockup**: Instant fallback to in-memory TF-IDF semantic search.
6. **10x Traffic Spike**: KEDA event-driven autoscaling scales workers from 1 to 20 replicas.
7. **Schema Poisoning**: Pydantic v2 strict schemas reject malformed payloads pre-ingress.
8. **Compliance Exploit**: Deterministic compliance layer overrides high ML score on statutory DTI breach.
9. **K8s Node Termination**: Pre-stop lifecycle hook cancels consumers gracefully.
10. **Worker Memory Leaks**: Celery worker max-tasks-per-child recycling.

Full post-mortem reports: [`docs/failure_scenarios.md`](docs/failure_scenarios.md).

---

## ☸️ Kubernetes & KEDA Deployment

Deploy the complete platform into Kubernetes (Kind, Minikube, or EKS):
```bash
kubectl apply -k k8s/
```

Key features:
- **KEDA ScaledObject**: Dynamically scales `creditsense-worker` pods from 1 to 20 replicas based on Redis queue depth (`targetListLength: 5`).
- **Least-Privilege Security**: Non-root UID 10001, dropped capabilities, NetworkPolicies restricting inter-pod traffic.
- **Probes**: Configured `startupProbe`, `livenessProbe`, and `readinessProbe` on all endpoints.

---

## 📂 Project Structure

```
CreditSense/
├── api/                   # FastAPI Gateway, Schemas, Routers & Middleware
├── agents/                # LangGraph Agent Nodes (Financial, Risk, Policy, Decision)
├── database/              # SQLAlchemy Models, Async Sessions, Repository & Auditing
├── alembic/               # Database Schema Migrations
├── workers/               # Celery App, Background Tasks & Idempotency Guards
├── rag/                   # Corpus Ingestion, ChromaDB & TF-IDF Hybrid Retrievers
├── monitoring/            # Prometheus Config, Alert Rules, Grafana Dashboards
├── otel/                  # OpenTelemetry Tracer Provider & Trace Propagation
├── k8s/                   # Kubernetes Manifests, KEDA ScaledObject, NetworkPolicies
├── terraform/             # Modular IaC (Local Kind & AWS Production with Cost Warning)
├── docs/                  # Architecture Diagrams, SLOs, RCAs, Interview Guide
├── tests/                 # Full Pytest Suite (Unit, Integration, Observability, Locust)
├── app.py                 # Streamlit Underwriter UI Dashboard
├── Dockerfile.api         # Multi-stage non-root container for API
├── Dockerfile.worker      # Multi-stage non-root container for Celery Worker
├── Dockerfile.frontend    # Multi-stage non-root container for Streamlit UI
├── docker-compose.yml     # Full 8-tier local orchestration stack
└── Jenkinsfile            # Declarative Multi-Stage CI/CD Pipeline
```

---

## 🧪 Testing & Verification

Run the comprehensive automated test suite:
```bash
pytest -v --cov=creditsense
```

Includes:
- `tests/test_api.py`: API Gateway route validation & error handling
- `tests/test_database.py`: SQLAlchemy persistence, audit logging & transaction isolation
- `tests/test_workers.py`: Celery task idempotency & retry mechanisms
- `tests/test_agents.py`: LangGraph state machine & node transitions
- `tests/test_policy_overrides.py`: Deterministic compliance override verification
- `tests/test_rag.py`: ChromaDB & TF-IDF retriever precision & fallbacks
- `tests/test_observability.py`: Prometheus metrics exposition & OpenTelemetry spans
- `tests/load_test_locust.py`: High-concurrency performance load testing

---

## 🎓 Technical Interview Guide

Preparing for technical interviews? Check out our deep-dive guide:
👉 **[`docs/interview_guide.md`](docs/interview_guide.md)** covering SRE, Cloud Architecture, Platform Engineering, FinOps, and ML System Design questions.

---

## 📄 License
MIT License. Created for production-style engineering portfolio demonstration.
