"""
creditsense/database/repository.py
----------------------------------
Application repository layer encapsulating CRUD operations, transactions, and audit logging.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from database.models import (
    Applicant,
    Application,
    AuditEvent,
    ComplianceCheck,
    Decision,
    Document,
    RiskAssessment,
)


class ApplicationRepository:
    """Repository handling persistence for CreditSense domain entities and audit events."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_application(self, applicant_data: dict[str, Any]) -> Application:
        """Create an applicant record, initialize application state, and record audit log."""
        applicant = Applicant(
            id=str(uuid4()),
            age=applicant_data["age"],
            employment_years=applicant_data["employment_years"],
            monthly_income=applicant_data["monthly_income"],
            existing_monthly_debt=applicant_data["existing_monthly_debt"],
            credit_utilization_pct=applicant_data["credit_utilization_pct"],
            past_defaults=applicant_data["past_defaults"],
            requested_loan_amount=applicant_data["requested_loan_amount"],
            txn_volatility_score=applicant_data["txn_volatility_score"],
            kyc_verified=applicant_data["kyc_verified"],
        )
        self.db.add(applicant)
        self.db.flush()

        app_id = str(uuid4())
        application = Application(
            id=app_id,
            applicant_id=applicant.id,
            status="PROCESSING",
        )
        self.db.add(application)

        audit = AuditEvent(
            id=str(uuid4()),
            application_id=app_id,
            event_type="APPLICATION_SUBMITTED",
            actor="api_gateway",
            payload_json=json.dumps(applicant_data),
        )
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(application)
        return application

    def record_underwriting_result(
        self,
        application_id: str,
        pipeline_output: dict[str, Any],
    ) -> Application:
        """Atomically persist multi-agent underwriting results across normalized tables."""
        application = self.get_application_by_id(application_id)
        if not application:
            raise ValueError(f"Application {application_id} not found.")

        # 1. Document features
        doc = Document(
            id=str(uuid4()),
            application_id=application_id,
            validation_status=pipeline_output.get("document_status", "ok"),
            dti_ratio=pipeline_output.get("dti_ratio"),
            validation_errors_json=json.dumps(pipeline_output.get("validation_errors", [])),
        )
        self.db.add(doc)

        # 2. Risk assessment
        risk = RiskAssessment(
            id=str(uuid4()),
            application_id=application_id,
            default_probability=float(pipeline_output.get("default_probability") or 0.0),
            risk_tier=pipeline_output.get("risk_tier", "MODERATE"),
            model_version="GradientBoostingClassifier-v1",
            status=pipeline_output.get("risk_status", "ok"),
        )
        self.db.add(risk)

        # 3. Compliance check
        compliance = ComplianceCheck(
            id=str(uuid4()),
            application_id=application_id,
            compliance_verdict=pipeline_output.get("compliance_verdict", "CLEAR"),
            has_blocking_flag=bool(pipeline_output.get("has_blocking_flag", False)),
            flags_json=json.dumps(pipeline_output.get("flags", [])),
            blocking_flags_json=json.dumps(pipeline_output.get("blocking_flags", [])),
            retrieved_clauses_json=json.dumps(pipeline_output.get("retrieved_clauses", [])),
        )
        self.db.add(compliance)

        # 4. Final Decision
        dec = Decision(
            id=str(uuid4()),
            application_id=application_id,
            decision=pipeline_output.get("decision", "MANUAL_REVIEW"),
            interest_rate_pct=pipeline_output.get("interest_rate_pct"),
            explanation=pipeline_output.get("explanation", ""),
            explanation_source=pipeline_output.get("explanation_source", "template_fallback"),
            applied_clause_ids_json=json.dumps(pipeline_output.get("applied_clause_ids", [])),
            pipeline_trace_json=json.dumps(pipeline_output.get("pipeline_trace", [])),
        )
        self.db.add(dec)

        # 5. Update Application Status
        application.status = "COMPLETED"

        # 6. Audit Trail Event
        audit = AuditEvent(
            id=str(uuid4()),
            application_id=application_id,
            event_type="DECISION_RECORDED",
            actor="underwriting_engine",
            payload_json=json.dumps({
                "decision": dec.decision,
                "risk_tier": risk.risk_tier,
                "default_probability": risk.default_probability,
                "compliance_verdict": compliance.compliance_verdict,
            }),
        )
        self.db.add(audit)

        self.db.commit()
        self.db.refresh(application)
        return application

    def record_underwriting_failure(
        self,
        application_id: str,
        error_message: str,
    ) -> Application:
        """Mark application as FAILED and record failure audit log."""
        application = self.get_application_by_id(application_id)
        if not application:
            raise ValueError(f"Application {application_id} not found.")

        application.status = "FAILED"
        application.error_message = error_message

        audit = AuditEvent(
            id=str(uuid4()),
            application_id=application_id,
            event_type="APPLICATION_FAILED",
            actor="underwriting_engine",
            payload_json=json.dumps({"error": error_message}),
        )
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(application)
        return application

    def get_application_by_id(self, application_id: str) -> Optional[Application]:
        """Fetch full application with all relationships joined in a single query."""
        stmt = (
            select(Application)
            .options(
                joinedload(Application.applicant),
                joinedload(Application.document),
                joinedload(Application.risk_assessment),
                joinedload(Application.compliance_check),
                joinedload(Application.decision),
                joinedload(Application.audit_events),
            )
            .where(Application.id == application_id)
        )
        return self.db.scalars(stmt).unique().first()

    def list_applications(self, limit: int = 50, offset: int = 0) -> List[Application]:
        """Retrieve paginated list of applications with applicant and decision preloaded."""
        stmt = (
            select(Application)
            .options(
                joinedload(Application.applicant),
                joinedload(Application.decision),
                joinedload(Application.risk_assessment),
            )
            .order_by(desc(Application.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).unique().all())

    def get_audit_trail(self, application_id: str) -> List[AuditEvent]:
        """Fetch chronological audit events for a given application."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.application_id == application_id)
            .order_by(AuditEvent.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())
