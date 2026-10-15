"""
creditsense/monitoring/metrics.py
---------------------------------
Comprehensive Prometheus metric instruments for CreditSense SLI/SLO monitoring,
underwriting throughput, per-agent latency breakdowns, RAG retrieval, and Celery worker metrics.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ── Application Underwriting Metrics ──────────────────────────────────────────

APPLICATIONS_RECEIVED_TOTAL = Counter(
    "creditsense_applications_received_total",
    "Total number of loan applications received by the platform",
)

APPLICATIONS_PROCESSED_TOTAL = Counter(
    "creditsense_applications_processed_total",
    "Total applications completed by the underwriting engine",
    ["decision", "risk_tier"],
)

APPLICATIONS_APPROVED_TOTAL = Counter(
    "creditsense_applications_approved_total",
    "Total applications approved by the platform",
)

APPLICATIONS_REJECTED_TOTAL = Counter(
    "creditsense_applications_rejected_total",
    "Total applications rejected by the platform",
)

APPLICATIONS_MANUAL_REVIEW_TOTAL = Counter(
    "creditsense_applications_manual_review_total",
    "Total applications escalated for mandatory manual underwriting review",
)

APPLICATION_PROCESSING_DURATION_SECONDS = Histogram(
    "creditsense_application_processing_duration_seconds",
    "Total end-to-end multi-agent underwriting execution time in seconds",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0),
)


# ── Per-Agent Latency & Execution Breakdown ───────────────────────────────────

AGENT_EXECUTION_DURATION_SECONDS = Histogram(
    "creditsense_agent_execution_duration_seconds",
    "Execution duration for individual underwriting agent nodes in seconds",
    ["agent_name"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

RISK_MODEL_LATENCY_SECONDS = Histogram(
    "creditsense_risk_model_latency_seconds",
    "Inference latency of the GradientBoosting risk prediction model in seconds",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)

RAG_RETRIEVAL_LATENCY_SECONDS = Histogram(
    "creditsense_rag_retrieval_latency_seconds",
    "Latency of policy clause semantic search in vector store in seconds",
    ["backend"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

LLM_REQUEST_LATENCY_SECONDS = Histogram(
    "creditsense_llm_request_latency_seconds",
    "Latency of LLM explanation generation requests in seconds",
    ["provider", "model"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0),
)

LLM_FAILURES_TOTAL = Counter(
    "creditsense_llm_failures_total",
    "Total count of failed LLM API requests triggering template fallback",
    ["provider", "error_type"],
)


# ── API Gateway Metrics ───────────────────────────────────────────────────────

API_REQUESTS_TOTAL = Counter(
    "creditsense_api_requests_total",
    "Total count of HTTP requests received across API endpoints",
    ["method", "endpoint", "status_code"],
)

API_REQUEST_DURATION_SECONDS = Histogram(
    "creditsense_api_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


# ── Database & Persistence Metrics ────────────────────────────────────────────

DATABASE_QUERY_LATENCY_SECONDS = Histogram(
    "creditsense_database_query_latency_seconds",
    "SQLAlchemy database transaction and query execution latency in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)


# ── Celery Worker & Queue Metrics ─────────────────────────────────────────────

CELERY_TASKS_TOTAL = Counter(
    "creditsense_celery_tasks_total",
    "Total count of background Celery tasks processed",
    ["task_name", "status"],
)

CELERY_TASK_FAILURES_TOTAL = Counter(
    "creditsense_celery_task_failures_total",
    "Total count of permanent Celery task failures",
    ["task_name"],
)

QUEUE_DEPTH = Gauge(
    "creditsense_queue_depth",
    "Current number of pending tasks in Redis task queue",
    ["queue_name"],
)

WORKER_ACTIVE_TASKS = Gauge(
    "creditsense_worker_active_tasks",
    "Number of active concurrent tasks currently being processed by workers",
    ["worker_name"],
)


def get_metrics_exposition() -> bytes:
    """Export all registered Prometheus metric instruments as UTF-8 bytes."""
    return generate_latest()


def get_metrics_response() -> bytes:
    """Convenience alias for get_metrics_exposition."""
    return generate_latest()


def record_application_metric(decision: str, risk_tier: str, duration: float) -> None:
    """Record application outcome and processing duration."""
    APPLICATIONS_PROCESSED_TOTAL.labels(decision=decision, risk_tier=risk_tier).inc()
    if decision.upper() == "APPROVED":
        APPLICATIONS_APPROVED_TOTAL.inc()
    elif decision.upper() == "REJECTED":
        APPLICATIONS_REJECTED_TOTAL.inc()
    else:
        APPLICATIONS_MANUAL_REVIEW_TOTAL.inc()
    APPLICATION_PROCESSING_DURATION_SECONDS.observe(duration)


def record_agent_latency(agent_name: str, duration: float) -> None:
    """Record execution duration of a specific agent node."""
    AGENT_EXECUTION_DURATION_SECONDS.labels(agent_name=agent_name).observe(duration)


def record_rag_latency(backend: str, duration: float) -> None:
    """Record RAG policy retrieval latency."""
    RAG_RETRIEVAL_LATENCY_SECONDS.labels(backend=backend).observe(duration)


def record_model_inference_latency(model_name: str, duration: float) -> None:
    """Record ML model inference latency."""
    RISK_MODEL_LATENCY_SECONDS.observe(duration)


def record_api_request(endpoint: str, method: str, status_code: int, duration: float) -> None:
    """Record HTTP API request metrics."""
    API_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=str(status_code)).inc()
    API_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)


def set_queue_depth(depth: int, queue_name: str = "celery") -> None:
    """Update current Redis queue depth gauge."""
    QUEUE_DEPTH.labels(queue_name=queue_name).set(depth)
