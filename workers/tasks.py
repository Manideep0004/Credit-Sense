"""
creditsense/workers/tasks.py
----------------------------
Asynchronous Celery tasks for executing multi-agent credit underwriting workflows.
Includes exponential backoff retries, idempotency checks, timeout protection, and audit logging.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from celery.exceptions import SoftTimeLimitExceeded

from database.models import AuditEvent
from database.repository import ApplicationRepository
from database.session import SessionLocal
from graph import build_graph
from workers.celery_app import celery_app

logger = logging.getLogger("creditsense.workers.tasks")

# Cache graph instance inside worker process
_GRAPH_INSTANCE = None


def _get_worker_graph():
    global _GRAPH_INSTANCE
    if _GRAPH_INSTANCE is None:
        _GRAPH_INSTANCE = build_graph()
    return _GRAPH_INSTANCE


@celery_app.task(
    bind=True,
    name="workers.tasks.process_underwriting_application",
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_underwriting_application(self, application_id: str) -> Dict[str, Any]:
    """
    Asynchronous task executing the end-to-end multi-agent underwriting pipeline.

    Idempotency:
    - If the application status is already COMPLETED, returns existing decision to avoid duplicate computation.

    Resilience:
    - Automatically retries up to 3 times with exponential backoff on transient errors.
    - Captures SoftTimeLimitExceeded and persists a failure record.
    """
    logger.info("Celery worker starting underwriting task for application: %s (attempt %d/%d)",
                application_id, self.request.retries + 1, self.max_retries + 1)

    db = SessionLocal()
    repo = ApplicationRepository(db)

    try:
        app_model = repo.get_application_by_id(application_id)
        if not app_model:
            logger.error("Application %s not found in database. Aborting task.", application_id)
            return {"status": "error", "message": f"Application {application_id} not found"}

        # ── Idempotency Check ────────────────────────────────────────────────
        if app_model.status == "COMPLETED":
            logger.info("Application %s already in COMPLETED state. Skipping duplicate execution (Idempotent).", application_id)
            return {
                "status": "already_completed",
                "application_id": application_id,
                "decision": app_model.decision.decision if app_model.decision else "UNKNOWN",
            }

        # Update status to PROCESSING and log audit event
        app_model.status = "PROCESSING"
        audit = AuditEvent(
            application_id=application_id,
            event_type="UNDERWRITING_TASK_STARTED",
            actor=f"celery_worker_{self.request.hostname or 'default'}",
            payload_json=json.dumps({"task_id": self.request.id, "attempt": self.request.retries + 1}),
        )
        db.add(audit)
        db.commit()

        # Build raw applicant dictionary for the agent graph
        applicant = app_model.applicant
        raw_payload = {
            "age": applicant.age,
            "employment_years": applicant.employment_years,
            "monthly_income": applicant.monthly_income,
            "existing_monthly_debt": applicant.existing_monthly_debt,
            "credit_utilization_pct": applicant.credit_utilization_pct,
            "past_defaults": applicant.past_defaults,
            "requested_loan_amount": applicant.requested_loan_amount,
            "txn_volatility_score": applicant.txn_volatility_score,
            "kyc_verified": applicant.kyc_verified,
        }

        # Execute LangGraph Multi-Agent Pipeline
        graph = _get_worker_graph()
        pipeline_output = graph.invoke({"raw_input": raw_payload, "pipeline_trace": []})

        # Atomically record results across normalized tables
        repo.record_underwriting_result(application_id, pipeline_output)
        logger.info("Celery task completed successfully for application %s. Decision: %s",
                    application_id, pipeline_output.get("decision"))

        return {
            "status": "success",
            "application_id": application_id,
            "decision": pipeline_output.get("decision"),
            "risk_tier": pipeline_output.get("risk_tier"),
            "default_probability": pipeline_output.get("default_probability"),
        }

    except SoftTimeLimitExceeded:
        err_msg = f"Task exceeded 45s execution limit for application {application_id}"
        logger.error(err_msg)
        repo.record_underwriting_failure(application_id, err_msg)
        return {"status": "timeout", "error": err_msg}

    except Exception as exc:
        logger.warning("Error processing application %s: %s", application_id, exc)

        # If retries remain, Celery autoretry_for handles the retry and backoff
        if self.request.retries >= self.max_retries:
            logger.error("Max retries (%d) exhausted for application %s. Recording permanent failure.",
                         self.max_retries, application_id)
            repo.record_underwriting_failure(application_id, f"Processing failed after {self.max_retries} retries: {exc}")

        raise exc

    finally:
        db.close()
