"""
creditsense/api/routes/applications.py
--------------------------------------
Application resource endpoints for submitting applicants, polling status, and fetching decisions.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.schemas import (
    ApplicantInput,
    ApplicationResponse,
    ApplicationStatusResponse,
    AuditEventResponse,
    DecisionResponse,
    ErrorResponse,
)
from api.service import ApplicationNotFoundError, UnderwritingService, get_underwriting_service
from database.session import get_db

router = APIRouter(prefix="/api/v1/applications", tags=["Applications"])


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Loan Application (Async)",
    description="Submit applicant data. Returns HTTP 202 Accepted with a job/application ID while Celery processes underwriting asynchronously in the background.",
    responses={
        202: {"description": "Application accepted for asynchronous underwriting", "model": ApplicationResponse},
        422: {"description": "Validation error in applicant payload", "model": ErrorResponse},
    },
)
def create_application(
    payload: ApplicantInput,
    sync: bool = False,
    db: Session = Depends(get_db),
    service: UnderwritingService = Depends(get_underwriting_service),
) -> ApplicationResponse:
    return service.create_and_enqueue_application(payload, db_session=db, sync=sync)


@router.get(
    "",
    response_model=List[ApplicationResponse],
    summary="List Applications",
    description="Retrieve all submitted applications.",
)
def list_applications(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    service: UnderwritingService = Depends(get_underwriting_service),
) -> List[ApplicationResponse]:
    return service.list_applications(limit=limit, offset=offset, db_session=db)


@router.get(
    "/{application_id}",
    response_model=ApplicationResponse,
    summary="Get Application Details",
    description="Retrieve full application resource, applicant profile, and underwriting decision details.",
    responses={
        200: {"description": "Application found", "model": ApplicationResponse},
        404: {"description": "Application not found", "model": ErrorResponse},
    },
)
def get_application(
    application_id: str,
    db: Session = Depends(get_db),
    service: UnderwritingService = Depends(get_underwriting_service),
) -> ApplicationResponse:
    try:
        return service.get_application(application_id, db_session=db)
    except ApplicationNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{application_id}/status",
    response_model=ApplicationStatusResponse,
    summary="Get Application Status",
    description="Lightweight status endpoint for polling application lifecycle state.",
    responses={
        200: {"description": "Status retrieved", "model": ApplicationStatusResponse},
        404: {"description": "Application not found", "model": ErrorResponse},
    },
)
def get_application_status(
    application_id: str,
    db: Session = Depends(get_db),
    service: UnderwritingService = Depends(get_underwriting_service),
) -> ApplicationStatusResponse:
    try:
        return service.get_status(application_id, db_session=db)
    except ApplicationNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{application_id}/decision",
    response_model=DecisionResponse,
    summary="Get Application Decision",
    description="Retrieve the risk scoring, policy compliance checks, and final underwriting decision.",
    responses={
        200: {"description": "Decision retrieved", "model": DecisionResponse},
        404: {"description": "Application not found", "model": ErrorResponse},
    },
)
def get_application_decision(
    application_id: str,
    db: Session = Depends(get_db),
    service: UnderwritingService = Depends(get_underwriting_service),
) -> DecisionResponse:
    try:
        return service.get_decision(application_id, db_session=db)
    except ApplicationNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get(
    "/{application_id}/audit",
    response_model=List[AuditEventResponse],
    summary="Get Application Audit Trail",
    description="Retrieve the chronological immutable audit events for this credit application.",
    responses={
        200: {"description": "Audit trail retrieved", "model": List[AuditEventResponse]},
        404: {"description": "Application not found", "model": ErrorResponse},
    },
)
def get_application_audit_trail(
    application_id: str,
    db: Session = Depends(get_db),
    service: UnderwritingService = Depends(get_underwriting_service),
) -> List[AuditEventResponse]:
    try:
        return service.get_audit_trail(application_id, db_session=db)
    except ApplicationNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
