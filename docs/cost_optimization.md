# CreditSense - Cloud Cost Optimization & FinOps Architecture

This guide analyzes the infrastructure cost structure of CreditSense, explaining how it runs at **$0 local cost** while detailing production FinOps cost optimization strategies on AWS.

---

## 1. Zero-Cost ($0) Local Development Stack

All dependencies and tiers in CreditSense are designed to execute locally with **zero paid SaaS subscriptions**:

| Component | Cloud Paid Equivalent | $0 Local Alternative Used |
| :--- | :--- | :--- |
| **Relational Database** | AWS Aurora PostgreSQL ($150+/mo) | Local PostgreSQL Container / SQLite Fallback ($0) |
| **Task Queue / Broker** | AWS SQS / Managed Redis ($50+/mo) | Local Redis 7 Alpine Container ($0) |
| **Vector Store (RAG)** | Pinecone / Weaviate Cloud ($70+/mo) | In-Memory TF-IDF / ChromaDB Local ($0) |
| **Observability & Metrics**| Datadog / New Relic ($100+/mo) | Prometheus + Grafana OSS ($0) |
| **Distributed Tracing** | Honeycomb / Dynatrace ($80+/mo) | Jaeger All-In-One OSS ($0) |
| **Compute Orchestration** | Managed AWS EKS ($73+/mo) | Kind / Minikube / Docker Compose ($0) |

**Total Local Development Cost: $0.00 / month.**

---

## 2. Production AWS FinOps & Cost Optimization Strategies

When deploying CreditSense to AWS, total monthly spend is minimized using cloud-native FinOps architectural decisions:

### 1. AWS Graviton (ARM64) Instances
- Utilizing `t4g.small` and `c7g.large` EC2/EKS instances delivers **up to 40% better price-performance** compared to x86 instances.

### 2. KEDA-Driven Scale-to-Zero & Spot Instances
- Asynchronous Celery worker pods run on **Amazon EC2 Spot Instances** (up to 70-90% discount compared to On-Demand).
- KEDA dynamically scales worker pods down during off-peak hours (e.g. night batches) and scales up horizontally during peak loan origination hours.

### 3. Serverless LLM Inference vs Self-Hosted Fallback
- Lightweight feature processing and deterministic policy validation occur on CPU in < 5ms without invoking expensive GPU instances.
- External LLM calls are cached and only triggered for complex multi-page synthesis.

---

## 3. Estimated AWS Monthly Bill Comparison

| Infrastructure Component | Unoptimized (On-Demand x86) | FinOps Optimized (Graviton + Spot + KEDA) | Savings |
| :--- | :--- | :--- | :--- |
| **EKS Control Plane** | $73.00 | $73.00 | 0% |
| **Worker Nodes (API + Workers)**| $145.00 (m5.large On-Demand) | $36.00 (t4g/c7g Spot + KEDA auto) | **75%** |
| **PostgreSQL Database** | $92.00 (db.m5.large Multi-AZ) | $28.00 (db.t4g.small gp3) | **69%** |
| **Redis Broker** | $45.00 (cache.m5.large) | $12.00 (cache.t4g.micro) | **73%** |
| **Observability (Datadog vs OSS)**| $180.00 (SaaS agent billing) | $15.00 (Self-hosted Prom/Grafana) | **91%** |
| **Total Monthly Spend** | **~$535.00 / mo** | **~$164.00 / mo** | **~69% Savings** |
