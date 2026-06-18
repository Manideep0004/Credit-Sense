# CreditSense 🏦
### Agentic AI Loan Underwriting & Compliance Copilot

> An end-to-end multi-agent pipeline, orchestrated with **LangGraph**, that takes a loan applicant's profile and produces a risk-scored, policy-compliant underwriting decision with a written justification — keeping every decision explainable and policy-traceable.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  CreditSense LangGraph Pipeline              │
│                                                              │
│  raw_input                                                   │
│      │                                                       │
│      ▼                                                       │
│  ┌─────────────────┐                                         │
│  │  Document Agent │  validates, normalises, computes DTI    │
│  └────────┬────────┘                                         │
│           │ validated_features                               │
│           ▼                                                  │
│  ┌─────────────────┐                                         │
│  │  Risk Agent     │  GradientBoosting → prob + risk tier    │
│  └────────┬────────┘                                         │
│           │ default_probability, risk_tier                   │
│           ▼                                                  │
│  ┌─────────────────┐                                         │
│  │ Compliance Agent│  rules + RAG retrieval (ChromaDB/TFIDF) │
│  └────────┬────────┘                                         │
│           │                                                  │
│     ┌─────▼──────────────────────────────┐                   │
│     │   Conditional Edge                 │                   │
│     │   has_blocking_flag?               │                   │
│     └─────┬──────────────────┬───────────┘                   │
│           │ YES              │ NO                            │
│           ▼                  ▼                               │
│  ┌──────────────┐   ┌─────────────────┐                      │
│  │ Manual Review│   │ Decision Agent  │ Groq Llama 3.3 LLM   │
│  │    Node      │   │                 │ (+ template fallback) │
│  └──────┬───────┘   └────────┬────────┘                      │
│         │                   │                                │
│         └──────────┬─────────┘                               │
│                    ▼                                         │
│               FINAL DECISION                                 │
│        APPROVED / REJECTED / MANUAL_REVIEW                   │
└──────────────────────────────────────────────────────────────┘
```

### Agent Roles

| Agent | Role |
|---|---|
| **Document Agent** | Validates & normalises applicant input; computes DTI ratio |
| **Risk Agent** | GradientBoostingClassifier → default probability + risk tier (LOW/MODERATE/HIGH/SEVERE) |
| **Compliance Agent** | Rule-based flags + semantic RAG retrieval from policy corpus |
| **Decision Agent** | Synthesises risk + compliance → APPROVED/REJECTED/MANUAL_REVIEW + LLM explanation |
| **Manual Review Node** | Terminal node for blocked apps — bypasses auto-decision |

### Conditional Routing (Core Agentic Property)

After the Compliance Agent, the graph evaluates `has_blocking_flag`:
- **AML_STRUCTURING** (txn_volatility > 80 AND loan > 10× income)
- **INCOMPLETE_KYC** (kyc_verified = 0)
- **REPEAT_DEFAULTER** (past_defaults > 1)

If **any** blocking flag is present → `manual_review_node` (auto-approval is prohibited, even if ML risk is LOW).

---

## Setup

### Prerequisites
- Python 3.11+
- (Optional) Groq API key — free at [console.groq.com](https://console.groq.com)

### 1. Clone & Install

```bash
git clone https://github.com/your-org/creditsense.git
cd creditsense/creditsense
pip install -r requirements.txt
```

### 2. Set Groq API Key (optional — graceful fallback if absent)

```bash
# Windows
set GROQ_API_KEY=gsk_your_key_here

# Linux/macOS
export GROQ_API_KEY=gsk_your_key_here
```

If `GROQ_API_KEY` is not set, a high-quality templated explanation is used instead.

### 3. Generate Synthetic Data

```bash
python data/generate_data.py
```

Expected output:
```
Dataset saved → data/loan_applicants.csv
Shape         : (3000, 11)
Class balance:
  Non-default (0): 2252 (75.1%)
  Default     (1): 748 (24.9%)
```

### 4. Train the Risk Model

```bash
python train_risk_model.py
```

Expected output:
```
CreditSense — Risk Model Training Complete
  Test AUC : 0.9182
  ...
Model saved → models/risk_model.pkl
```

Target AUC range: **0.85 – 0.95**

### 5. Ingest Policy Corpus

```bash
python ingest_policies.py
```

This embeds 8 lending/KYC/AML policy clauses into ChromaDB (or TF-IDF fallback):
```
[INFO] Using embedding backend: sentence-transformers
[OK] Ingested 8 clauses into ChromaDB.
```

---

## Running

### Streamlit Demo

```bash
streamlit run app.py
```

Open **http://localhost:8501** — configure an applicant in the sidebar, click **Run Underwriting**.

**Demo presets** in the sidebar:
- ✅ **Clean** — qualified applicant, should be APPROVED
- ⚠️ **AML** — good financials but high volatility + large loan → MANUAL_REVIEW
- ❌ **Risk** — high DTI, 3 defaults → MANUAL_REVIEW / REJECTED

### CLI Smoke Test

```bash
python graph.py
```

### Direct Graph Usage (Python)

```python
from graph import build_graph

app = build_graph()
result = app.invoke({
    "raw_input": {
        "age": 34,
        "employment_years": 8,
        "monthly_income": 90_000,
        "existing_monthly_debt": 20_000,
        "credit_utilization_pct": 30.0,
        "past_defaults": 0,
        "requested_loan_amount": 400_000,
        "txn_volatility_score": 25.0,
        "kyc_verified": 1,
    },
    "pipeline_trace": [],
})
print(result["decision"])         # APPROVED
print(result["risk_tier"])        # LOW or MODERATE
print(result["explanation"])      # natural-language justification
```

---

## Running Tests

```bash
cd creditsense
pytest tests/ -v
```

### Test Coverage

| Test Class | Tests |
|---|---|
| `TestDocumentAgent` | Valid input, DTI computation, missing fields, string coercion |
| `TestRiskAgent` | Clean (LOW/MOD), high-risk (HIGH/SEVERE), probability bounds |
| `TestComplianceAgent` | Clear, AML block, KYC block, repeat-defaulter block, non-blocking HIGH_DTI |
| `TestDecisionAgent` | Approved path, blocking override, severe risk, explanation type |
| `TestGraphPipeline` | E2E approval, high-risk non-approval, **AML override proves compliance > ML**, KYC, repeat-defaulter, trace completeness |

**Key acceptance test:**
```
test_aml_flag_overrides_low_ml_risk_to_manual_review
```
Proves that an applicant with LOW ML risk (15% default probability, no defaults, KYC verified) is **still routed to MANUAL_REVIEW** when AML_STRUCTURING is flagged.

---

## Policy Corpus

| Clause ID | Category | Summary |
|---|---|---|
| DTI-1.1 | Credit Risk | Max DTI ≤ 0.55; 0.45–0.55 needs senior sign-off |
| DTI-1.2 | Credit Risk | First-time borrower: max loan = 12× monthly income |
| DEFAULT-2.1 | Credit History | Repeat defaulter (>1) → mandatory manual review |
| DEFAULT-2.2 | Credit History | Single default OK with mitigating factors |
| AML-3.1 | AML / CFT | Structuring risk: volatility >80 + loan >10× income |
| KYC-4.1 | KYC / Identity | KYC mandatory; incomplete = hard block |
| KYC-4.2 | KYC / Identity | PEP & sanctions screening required |
| RISK-5.1 | Risk Tiering | SEVERE (>60%) → manual; HIGH (40–60%) → senior approval |

---

## Scalability & Production Roadmap

### 1. Real Bureau Data
- Swap synthetic `generate_data.py` for API calls to **CIBIL / Experian / CRIF** bureaus.
- Add a bureau adapter layer in `agents/document_agent.py` that normalises bureau XML/JSON responses to the same feature dict.
- Re-train the risk model on real bureau data periodically (monthly refit cadence).

### 2. Production-Grade Embeddings
- The TF-IDF retriever in `ingest_policies.py` is a clearly marked stand-in.
- Replace `_tfidf_backend()` with `all-MiniLM-L6-v2` (already supported) or a fine-tuned domain model (e.g., `FinBERT`).
- For scale, move from ChromaDB local to **Pinecone** / **Weaviate** / **pgvector**.

### 3. Batch & Async Execution
- Wrap `build_graph().invoke()` in an async function using `langgraph`'s async graph interface (`ainvoke`).
- Deploy as a **FastAPI** service with background task queuing (Celery + Redis) for concurrent loan applications.
- Add a rate-limiter and per-applicant idempotency key to prevent double-submission.

### 4. Cloud Deployment
```
┌─────────────┐    ┌──────────────────┐    ┌──────────────┐
│  Streamlit  │───▶│  FastAPI Backend  │───▶│  LangGraph   │
│   (GCP      │    │  (Cloud Run /     │    │  Workers     │
│   Cloud Run)│    │   App Engine)     │    │  (Celery)    │
└─────────────┘    └──────────────────┘    └──────┬───────┘
                                                   │
                          ┌────────────────────────┤
                          │                        │
                   ┌──────▼──────┐        ┌────────▼────────┐
                   │  ChromaDB   │        │  Risk Model     │
                   │ (Pinecone/  │        │  (Vertex AI /   │
                   │  Weaviate)  │        │  SageMaker)     │
                   └─────────────┘        └─────────────────┘
```
- **Model registry**: MLflow or Vertex AI Model Registry for versioned risk model artifacts.
- **Audit trail**: All decisions written to BigQuery / PostgreSQL with full feature snapshot for regulatory audit.
- **Secrets**: Google Secret Manager / AWS Secrets Manager for `GROQ_API_KEY` and bureau API credentials.

### 5. Monitoring & Compliance
- Model drift detection: track rolling AUC monthly; trigger retraining alert at AUC < 0.80.
- Decision fairness audit: periodic demographic parity check across age/employment tenure buckets.
- Full audit log (input features, risk score, compliance flags, clause IDs, final decision) stored immutably for regulatory inspection.

---

## Project Structure

```
creditsense/
├── data/
│   ├── generate_data.py       # synthetic dataset generator
│   ├── policy_corpus.py       # 8 hardcoded lending/AML/KYC clauses
│   └── loan_applicants.csv    # generated dataset (git-ignored)
├── models/
│   └── risk_model.pkl         # trained GBM artifact (git-ignored)
├── vectorstore/               # ChromaDB persistence + TF-IDF store
├── agents/
│   ├── document_agent.py      # validation + normalisation + DTI
│   ├── risk_agent.py          # ML scoring → prob + tier
│   ├── compliance_agent.py    # rules + RAG retrieval
│   └── decision_agent.py      # synthesis + LLM explanation
├── graph.py                   # LangGraph StateGraph
├── ingest_policies.py         # embed corpus into ChromaDB / TF-IDF
├── train_risk_model.py        # GBM training + evaluation
├── app.py                     # Streamlit UI
├── tests/
│   └── test_agents.py         # pytest suite
├── requirements.txt
└── README.md
```

---

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

CreditSense is a research prototype. No real credit decisions should be made based solely on this system without qualified human underwriter oversight and compliance with applicable banking regulations (RBI Master Direction on KYC, PMLA 2002, etc.).
