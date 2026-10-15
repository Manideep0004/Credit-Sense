"""
creditsense/api/schemas.py
--------------------------
Pydantic schemas for request validation, domain modeling, and API responses.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ApplicationStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DecisionOutcome(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class RiskTier(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


# ── Request Schemas ───────────────────────────────────────────────────────────

class ApplicantInput(BaseModel):
    """Raw applicant financial and profile inputs for credit underwriting."""

    age: int = Field(..., ge=18, le=80, description="Applicant age in years (18-80)", example=34)
    employment_years: float = Field(..., ge=0, le=50, description="Employment tenure in years (0-50)", example=8.0)
    monthly_income: float = Field(..., gt=0, le=10_000_000, description="Gross monthly income in INR", example=95000.0)
    existing_monthly_debt: float = Field(..., ge=0, le=10_000_000, description="Existing monthly debt obligations in INR", example=22000.0)
    credit_utilization_pct: float = Field(..., ge=0.0, le=100.0, description="Credit card/revolving credit utilization percentage (0-100)", example=28.0)
    past_defaults: int = Field(..., ge=0, le=20, description="Number of past loan defaults recorded", example=0)
    requested_loan_amount: float = Field(..., gt=0, le=100_000_000, description="Requested principal loan amount in INR", example=450000.0)
    txn_volatility_score: float = Field(..., ge=0.0, le=100.0, description="Bank transaction volatility score (0-100)", example=22.0)
    kyc_verified: int = Field(..., ge=0, le=1, description="KYC verification status: 1 = Verified, 0 = Incomplete", example=1)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "age": 34,
                "employment_years": 8.0,
                "monthly_income": 95000.0,
                "existing_monthly_debt": 22000.0,
                "credit_utilization_pct": 28.0,
                "past_defaults": 0,
                "requested_loan_amount": 450000.0,
                "txn_volatility_score": 22.0,
                "kyc_verified": 1,
            }
        }
    )


# ── Response Sub-schemas ──────────────────────────────────────────────────────

class PolicyClause(BaseModel):
    id: str
    title: str
    text: str
    triggered_by_flag: Optional[str] = None


class DecisionDetails(BaseModel):
    decision: DecisionOutcome
    risk_tier: RiskTier
    default_probability: float = Field(..., ge=0.0, le=1.0)
    dti_ratio: Optional[float] = None
    flags: list[str] = Field(default_factory=list)
    blocking_flags: list[str] = Field(default_factory=list)
    applied_clause_ids: list[str] = Field(default_factory=list)
    retrieved_clauses: list[PolicyClause] = Field(default_factory=list)
    interest_rate_pct: Optional[float] = None
    explanation: str
    explanation_source: str
    pipeline_trace: list[str] = Field(default_factory=list)


# ── Top-level API Responses ───────────────────────────────────────────────────

class ApplicationResponse(BaseModel):
    """Complete application resource representation."""

    application_id: str = Field(..., description="Unique application identifier")
    status: ApplicationStatus = Field(..., description="Current processing lifecycle status")
    created_at: datetime
    updated_at: datetime
    applicant_data: ApplicantInput
    decision_details: Optional[DecisionDetails] = None
    error_message: Optional[str] = None


class ApplicationStatusResponse(BaseModel):
    """Lightweight polling status response."""

    application_id: str
    status: ApplicationStatus
    updated_at: datetime
    error_message: Optional[str] = None


class DecisionResponse(BaseModel):
    """Detailed decision outcome response."""

    application_id: str
    status: ApplicationStatus
    decision_details: Optional[DecisionDetails] = None
    error_message: Optional[str] = None


class AuditEventResponse(BaseModel):
    """Audit log entry for an application lifecycle event."""

    id: str
    application_id: Optional[str] = None
    event_type: str
    actor: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    services: dict[str, str] = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
