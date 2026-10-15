# CreditSense - 10 Production Architecture & Flow Diagrams

This document contains 10 Mermaid architectural diagrams representing every tier and subsystem of the CreditSense platform.

---

## 1. End-to-End Cloud-Native Architecture

```mermaid
graph TD
    Client["Client / Underwriter UI"] -->|HTTP REST| Ingress["Ingress / API Gateway (FastAPI)"]
    Ingress -->|Record Metrics| Prom["Prometheus (9090)"]
    Prom -->|Visualize| Graf["Grafana Dashboard (3000)"]
    Ingress -->|Export Traces| Jaeger["Jaeger Distributed Tracing (4317)"]
    
    Ingress -->|Enqueue Task (202 Accepted)| Redis[("Redis 7 (Broker & Result Backend)")]
    Ingress -->|Read / Write Status| PG[("PostgreSQL Database (5432)")]
    
    Redis -->|Consume Task| CeleryWorker["Celery Asynchronous Workers"]
    CeleryWorker -->|Execute Pipeline| LangGraph["LangGraph Multi-Agent Engine"]
    
    subgraph "Multi-Agent Underwriting Engine"
        LangGraph --> FA["Financial Agent"]
        LangGraph --> RA["Risk Agent (ML Model)"]
        LangGraph --> ResA["Research Agent"]
        LangGraph --> PolA["Policy Agent (RAG)"]
        LangGraph --> DecA["Decision Agent (Deterministic Override)"]
    end
    
    PolA -->|Vector Search| Chroma[("ChromaDB / TF-IDF Policy Store")]
    DecA -->|Persist Decision & Audit Trail| PG
```

---

## 2. LangGraph Multi-Agent Underwriting Workflow

```mermaid
flowchart TD
    Start([Start Loan Application]) --> FA[Financial Agent: Calculate DTI & Ratios]
    FA --> RA[Risk Agent: XGBoost / GradientBoosting Inference]
    RA --> ResA[Research Agent: Profile & Purpose Analysis]
    ResA --> PolA[Policy Agent: RAG Search Regulatory Clauses]
    PolA --> DecA[Decision Agent: Hard Override Evaluation]
    
    DecA --> CheckHardFail{Hard Violations Present?}
    CheckHardFail -- Yes --> Reject[Force REJECTED Decision - Compliance Override]
    CheckHardFail -- No --> CheckRiskScore{ML Default Probability}
    
    CheckRiskScore -- "Prob <= 0.30" --> Approve[Decision: APPROVED]
    CheckRiskScore -- "0.30 < Prob <= 0.65" --> Review[Decision: MANUAL_REVIEW]
    CheckRiskScore -- "Prob > 0.65" --> RejectModel[Decision: REJECTED]
    
    Reject --> Complete([Generate Explanation & Persist])
    Approve --> Complete
    Review --> Complete
    RejectModel --> Complete
```

---

## 3. Deterministic Compliance Override State Machine

```mermaid
stateDiagram-v2
    [*] --> Ingestion
    Ingestion --> PolicyCheck
    
    state PolicyCheck {
        [*] --> CheckDTI: DTI > 43%?
        CheckDTI --> CheckCredit: Credit < 600?
        CheckCredit --> CheckCitizenship: Valid ID?
    }
    
    PolicyCheck --> HardBreach: Any Hard Rule Failed
    PolicyCheck --> RiskAssessment: All Hard Rules Passed
    
    HardBreach --> ForceReject: Deterministic Override Active
    note right of ForceReject
        ML model score is completely ignored.
        Ensures 100% regulatory compliance.
    end note
    
    RiskAssessment --> MLScoreEvaluation: ML Prob Computed
    MLScoreEvaluation --> Approved: Prob <= 0.30
    MLScoreEvaluation --> ManualReview: 0.30 < Prob <= 0.65
    MLScoreEvaluation --> Rejected: Prob > 0.65
```

---

## 4. Asynchronous Task Processing & Idempotency Flow

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant API as FastAPI Gateway
    participant DB as PostgreSQL
    participant Redis as Redis Broker
    participant Worker as Celery Worker
    participant Graph as LangGraph Engine

    Client->>API: POST /api/v1/applications (Payload)
    API->>DB: Check Idempotency (Existing App ID / Tax ID)
    API->>DB: Insert Application (Status: PENDING)
    API->>Redis: Enqueue celery task (app_id, trace_id)
    API-->>Client: HTTP 202 Accepted (app_id, status=PENDING)
    
    Worker->>Redis: Fetch next task
    Worker->>DB: Fetch application record
    alt Already COMPLETED
        Worker->>Worker: Skip processing (Idempotent Guard)
    else PENDING / PROCESSING
        Worker->>DB: Update Status: PROCESSING
        Worker->>Graph: Run Multi-Agent Underwriting
        Graph-->>Worker: Underwriting Result & Audit Trail
        Worker->>DB: Update Status: COMPLETED & Persist Audit
    end
    
    Client->>API: GET /api/v1/applications/{app_id}
    API->>DB: Query Application Status
    DB-->>API: Status: COMPLETED, Decision: APPROVED
    API-->>Client: HTTP 200 OK (Full Decision & Rationale)
```

---

## 5. RAG Dual-Engine Hybrid Retrieval Architecture

```mermaid
graph TD
    Query["Incoming Policy Query (e.g. 'DTI limit and bankruptcy rules')"] --> Router{"Embedding Model Available?"}
    
    Router -- Yes --> ChromaDB["ChromaDB Vector Store (all-MiniLM-L6-v2)"]
    Router -- No / Fallback --> TFIDF["TF-IDF Fast In-Memory Retriever"]
    
    ChromaDB --> TopK["Top-K Semantic Matches"]
    TFIDF --> TopK
    
    TopK --> Filter["Metadata Filter (document, section, policy_type, version)"]
    Filter --> PolicyContext["Policy Context Injection into Agent Prompt"]
```

---

## 6. Distributed Tracing & Trace Context Propagation

```mermaid
flowchart LR
    subgraph "HTTP Layer"
        HTTPReq["HTTP POST /applications"] --> TraceGen["Generate trace_id & span_id"]
    end
    
    subgraph "Message Queue"
        TraceGen -->|Inject into Celery Headers| RedisQueue["Redis Message Queue"]
    end
    
    subgraph "Worker Execution"
        RedisQueue -->|Extract trace_id| WorkerSpan["Celery Worker Root Span"]
        WorkerSpan --> AgentSpan1["Span: FinancialAgent.execute"]
        AgentSpan1 --> AgentSpan2["Span: RiskAgent.inference"]
        AgentSpan2 --> AgentSpan3["Span: PolicyAgent.rag_search"]
        AgentSpan3 --> AgentSpan4["Span: DecisionAgent.evaluate"]
    end
    
    subgraph "Jaeger / OTel"
        TraceGen -.->|OTLP gRPC 4317| Jaeger["Jaeger Distributed Tracing"]
        WorkerSpan -.->|OTLP gRPC 4317| Jaeger
    end
```

---

## 7. Observability & Multi-Window Burn-Rate Alerting

```mermaid
graph TD
    AppMetrics["FastAPI & Worker Metrics"] -->|Scrape /metrics (15s)| Prometheus["Prometheus Server"]
    
    Prometheus -->|Evaluate Alert Rules| Engine{"Alert Evaluation"}
    
    Engine -->|Burn Rate > 14.4x (1h)| PageAlert["Sev-1 Page: High Error Budget Burn"]
    Engine -->|Burn Rate > 6.0x (6h)| WarnAlert["Sev-2 Warning: Moderate Burn"]
    Engine -->|Queue Depth > 50| QueueAlert["Sev-2 Warning: Redis Queue Spike"]
    Engine -->|p99 Latency > 5s| LatencyAlert["Sev-2 Warning: Pipeline Latency SLO Breach"]
    
    Prometheus -->|Data Source| Grafana["Grafana Dashboards"]
```

---

## 8. Kubernetes Pod Topology & Network Policy

```mermaid
graph TD
    subgraph "Kubernetes Namespace: creditsense"
        subgraph "Ingress & Edge"
            APIPod1["creditsense-api (Replica 1)"]
            APIPod2["creditsense-api (Replica 2)"]
        end
        
        subgraph "Data Services (Private)"
            PG["creditsense-postgres (StatefulSet)"]
            Redis["creditsense-redis (Deployment)"]
        end
        
        subgraph "Worker Pool (Autoscaled)"
            Worker1["creditsense-worker-1"]
            Worker2["creditsense-worker-2"]
            WorkerN["creditsense-worker-N"]
        end
    end
    
    APIPod1 -->|Read / Write| PG
    APIPod2 -->|Read / Write| PG
    APIPod1 -->|Enqueue| Redis
    APIPod2 -->|Enqueue| Redis
    
    Worker1 -->|Consume| Redis
    Worker2 -->|Consume| Redis
    WorkerN -->|Consume| Redis
    
    Worker1 -->|Update| PG
    Worker2 -->|Update| PG
    WorkerN -->|Update| PG
```

---

## 9. KEDA Event-Driven Autoscaling Architecture

```mermaid
sequenceDiagram
    participant Traffic as Application Influx
    participant Redis as Redis Queue (celery)
    participant KEDA as KEDA Operator
    participant HPA as K8s Horizontal Pod Autoscaler
    participant Workers as Celery Worker Pods

    Traffic->>Redis: Surge in submissions (50+ pending tasks)
    KEDA->>Redis: Poll list length (every 10s)
    Redis-->>KEDA: Queue Depth = 60 (target = 5 per worker)
    KEDA->>HPA: Scale target replicas to 12
    HPA->>Workers: Spin up 12 worker replicas
    Workers->>Redis: Concurrently process 12 tasks in parallel
    Redis-->>Workers: Queue depth drops to 0
    KEDA->>HPA: Cool down timer expires (30s)
    HPA->>Workers: Scale down gracefully to 1 replica
```

---

## 10. Disaster Recovery & Failover Sequence

```mermaid
sequenceDiagram
    autonumber
    actor SRE as On-Call SRE
    participant Cluster as DR Kubernetes Cluster
    participant S3 as Backup Storage (S3 / Local Dump)
    participant DB as Postgres DR Instance
    participant App as API & Worker Pods

    Note over SRE,App: Primary Database Corruption Incident
    SRE->>Cluster: kubectl apply -k k8s/
    Cluster->>DB: Provision Clean PostgreSQL Instance
    SRE->>S3: Download latest verified daily snapshot + WAL archives
    SRE->>DB: pg_restore verified database dump
    SRE->>App: alembic upgrade head
    App->>DB: Run schema migrations & verify tables
    App->>App: Trigger verify_pipeline.py smoke test
    App-->>SRE: Pipeline Status: HEALTHY (RTO < 15 min, RPO < 5 min)
```
