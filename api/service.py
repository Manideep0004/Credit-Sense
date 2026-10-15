"""
creditsense/api/service.py
--------------------------
Application Service Layer — coordinates application domain operations,
underwriting orchestration, and database persistence through ApplicationRepository.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from api.schemas import (
    ApplicantInput,
    ApplicationResponse,
    ApplicationStatus,
    ApplicationStatusResponse,
    AuditEventResponse,
    DecisionDetails,
    DecisionOutcome,
    DecisionResponse,
    PolicyClause,
    RiskTier,
)
from database.models import Application
from database.repository import ApplicationRepository
from database.session import SessionLocal, init_db
from graph import build_graph

logger = logging.getLogger("creditsense.api.service")


class ApplicationNotFoundError(Exception):
    """Raised when an application ID does not exist."""


def _map_model_to_response(app_model: Application) -> ApplicationResponse:
    """Map SQLAlchemy Application entity with loaded relations to Pydantic schema."""
    applicant = app_model.applicant
    applicant_data = ApplicantInput(
        age=applicant.age,
        employment_years=applicant.employment_years,
        monthly_income=applicant.monthly_income,
        existing_monthly_debt=applicant.existing_monthly_debt,
        credit_utilization_pct=applicant.credit_utilization_pct,
        past_defaults=applicant.past_defaults,
        requested_loan_amount=applicant.requested_loan_amount,
        txn_volatility_score=applicant.txn_volatility_score,
        kyc_verified=applicant.kyc_verified,
    )

    decision_details = None
    if app_model.decision and app_model.risk_assessment and app_model.compliance_check:
        dec = app_model.decision
        risk = app_model.risk_assessment
        comp = app_model.compliance_check
        doc = app_model.document

        raw_clauses = json.loads(comp.retrieved_clauses_json or "[]")
        retrieved_clauses = [
            PolicyClause(
                id=c.get("id", ""),
                title=c.get("title", ""),
                text=c.get("text", ""),
                triggered_by_flag=c.get("triggered_by_flag"),
            )
            for c in raw_clauses
        ]

        decision_details = DecisionDetails(
            decision=DecisionOutcome(dec.decision),
            risk_tier=RiskTier(risk.risk_tier),
            default_probability=risk.default_probability,
            dti_ratio=doc.dti_ratio if doc else None,
            flags=json.loads(comp.flags_json or "[]"),
            blocking_flags=json.loads(comp.blocking_flags_json or "[]"),
            applied_clause_ids=json.loads(dec.applied_clause_ids_json or "[]"),
            retrieved_clauses=retrieved_clauses,
            interest_rate_pct=dec.interest_rate_pct,
            explanation=dec.explanation,
            explanation_source=dec.explanation_source,
            pipeline_trace=json.loads(dec.pipeline_trace_json or "[]"),
        )

    return ApplicationResponse(
        application_id=app_model.id,
        status=ApplicationStatus(app_model.status),
        created_at=app_model.created_at,
        updated_at=app_model.updated_at,
        applicant_data=applicant_data,
        decision_details=decision_details,
        error_message=app_model.error_message,
    )


class UnderwritingService:
    """
    Coordinates credit application lifecycle, persistence, and underwriting execution.
    """

    def __init__(self, db: Optional[Session] = None) -> None:
        init_db()  # Ensure tables exist
        self._db = db
        self._graph = build_graph()

    def _get_repo(self, db_session: Optional[Session] = None) -> tuple[ApplicationRepository, Session, bool]:
        """Return repository and session, noting whether session should be closed."""
        if db_session is not None:
            return ApplicationRepository(db_session), db_session, False
        if self._db is not None:
            return ApplicationRepository(self._db), self._db, False
        sess = SessionLocal()
        return ApplicationRepository(sess), sess, True

    def create_and_enqueue_application(
        self,
        applicant: ApplicantInput,
        db_session: Optional[Session] = None,
        sync: bool = False,
    ) -> ApplicationResponse:
        """
        Create application in database, enqueue asynchronous Celery processing job, and return 202 Accepted.
        If sync=True or Celery is unavailable, executes immediately.
        """
        repo, sess, should_close = self._get_repo(db_session)
        raw_payload = applicant.model_dump()

        try:
            # 1. Create application & applicant record in DB (status=PENDING)
            app_model = repo.create_application(raw_payload)
            app_id = app_model.id
            app_model.status = "PENDING"
            sess.commit()
            sess.refresh(app_model)
            logger.info("Application %s created in state PENDING", app_id)

            if sync:
                # Synchronous execution mode requested
                return self.create_and_process_application(applicant, db_session=sess)

            # 2. Asynchronous Celery dispatch
            try:
                from workers.tasks import process_underwriting_application
                task = process_underwriting_application.apply_async(args=[app_id], retry=False)
                logger.info("Enqueued Celery task %s for application %s", task.id, app_id)
                return _map_model_to_response(app_model)
            except Exception as celery_err:
                logger.warning("Celery queue dispatch failed (%s). Executing pipeline directly.", celery_err)
                # Fallback to direct execution for zero-friction local development without Redis
                return self.create_and_process_application(applicant, db_session=sess)

        finally:
            if should_close:
                sess.close()

    def create_and_process_application(
        self,
        applicant: ApplicantInput,
        db_session: Optional[Session] = None,
    ) -> ApplicationResponse:
        """
        Create a new credit application record, execute the underwriting graph synchronously, and persist result.
        """
        repo, sess, should_close = self._get_repo(db_session)
        raw_payload = applicant.model_dump()

        try:
            # 1. Create application & applicant record in DB
            app_model = repo.create_application(raw_payload)
            app_id = app_model.id
            logger.info("Created application %s in database. Executing underwriting pipeline.", app_id)

            # 2. Invoke multi-agent LangGraph workflow
            try:
                pipeline_out = self._graph.invoke({"raw_input": raw_payload, "pipeline_trace": []})
                updated_app = repo.record_underwriting_result(app_id, pipeline_out)
                logger.info("Application %s successfully processed. Decision: %s", app_id, pipeline_out.get("decision"))
                return _map_model_to_response(updated_app)
            except Exception as pipeline_exc:
                logger.exception("Underwriting pipeline failure for app %s: %s", app_id, pipeline_exc)
                failed_app = repo.record_underwriting_failure(app_id, str(pipeline_exc))
                return _map_model_to_response(failed_app)

        finally:
            if should_close:
                sess.close()

    def get_application(
        self,
        application_id: str,
        db_session: Optional[Session] = None,
    ) -> ApplicationResponse:
        """Fetch full application with normalized details by ID."""
        repo, sess, should_close = self._get_repo(db_session)
        try:
            app_model = repo.get_application_by_id(application_id)
            if not app_model:
                raise ApplicationNotFoundError(f"Application '{application_id}' not found.")
            return _map_model_to_response(app_model)
        finally:
            if should_close:
                sess.close()

    def get_status(
        self,
        application_id: str,
        db_session: Optional[Session] = None,
    ) -> ApplicationStatusResponse:
        """Fetch lightweight status summary by ID."""
        repo, sess, should_close = self._get_repo(db_session)
        try:
            app_model = repo.get_application_by_id(application_id)
            if not app_model:
                raise ApplicationNotFoundError(f"Application '{application_id}' not found.")
            return ApplicationStatusResponse(
                application_id=app_model.id,
                status=ApplicationStatus(app_model.status),
                updated_at=app_model.updated_at,
                error_message=app_model.error_message,
            )
        finally:
            if should_close:
                sess.close()

    def get_decision(
        self,
        application_id: str,
        db_session: Optional[Session] = None,
    ) -> DecisionResponse:
        """Fetch decision details by ID."""
        repo, sess, should_close = self._get_repo(db_session)
        try:
            app_model = repo.get_application_by_id(application_id)
            if not app_model:
                raise ApplicationNotFoundError(f"Application '{application_id}' not found.")
            full_res = _map_model_to_response(app_model)
            return DecisionResponse(
                application_id=full_res.application_id,
                status=full_res.status,
                decision_details=full_res.decision_details,
                error_message=full_res.error_message,
            )
        finally:
            if should_close:
                sess.close()

    def list_applications(
        self,
        limit: int = 50,
        offset: int = 0,
        db_session: Optional[Session] = None,
    ) -> List[ApplicationResponse]:
        """List stored applications with pagination."""
        repo, sess, should_close = self._get_repo(db_session)
        try:
            apps = repo.list_applications(limit=limit, offset=offset)
            return [_map_model_to_response(a) for a in apps]
        finally:
            if should_close:
                sess.close()

    def get_audit_trail(
        self,
        application_id: str,
        db_session: Optional[Session] = None,
    ) -> List[AuditEventResponse]:
        """Fetch chronological audit trail for an application."""
        repo, sess, should_close = self._get_repo(db_session)
        try:
            app_model = repo.get_application_by_id(application_id)
            if not app_model:
                raise ApplicationNotFoundError(f"Application '{application_id}' not found.")
            events = repo.get_audit_trail(application_id)
            return [
                AuditEventResponse(
                    id=e.id,
                    application_id=e.application_id,
                    event_type=e.event_type,
                    actor=e.actor,
                    payload=json.loads(e.payload_json or "{}"),
                    created_at=e.created_at,
                )
                for e in events
            ]
        finally:
            if should_close:
                sess.close()


# Global singleton instance for the service layer
_service_instance: Optional[UnderwritingService] = None


def get_underwriting_service() -> UnderwritingService:
    global _service_instance
    if _service_instance is None:
        _service_instance = UnderwritingService()
    return _service_instance
