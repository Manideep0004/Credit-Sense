"""
creditsense/database/models.py
------------------------------
SQLAlchemy 2.0 relational models and schema definitions with indexing rationale.

INDEXING RATIONALE:
- applications.id: Primary key lookup index for O(1) retrieval of application by ID.
- applications.status: Filter index for worker queues and status aggregations (e.g. counting pending jobs).
- applications.created_at: Range index for time-windowed SLI/SLO and analytics queries.
- applications.applicant_id: Foreign key index for fast joins between applications and applicants.
- risk_assessments.risk_tier: Aggregation index for tracking risk distribution and model monitoring.
- compliance_checks.compliance_verdict / has_blocking_flag: Filter index for compliance audits and AML filtering.
- decisions.decision: Aggregation index for computing approval/rejection rates.
- audit_events.application_id & created_at: Composite/single indexes for chronological audit trail reconstructions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Applicant(Base):
    """Stores synthetic applicant profile and baseline financial attributes."""

    __tablename__ = "applicants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    employment_years: Mapped[float] = mapped_column(Float, nullable=False)
    monthly_income: Mapped[float] = mapped_column(Float, nullable=False)
    existing_monthly_debt: Mapped[float] = mapped_column(Float, nullable=False)
    credit_utilization_pct: Mapped[float] = mapped_column(Float, nullable=False)
    past_defaults: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_loan_amount: Mapped[float] = mapped_column(Float, nullable=False)
    txn_volatility_score: Mapped[float] = mapped_column(Float, nullable=False)
    kyc_verified: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    applications: Mapped[List["Application"]] = relationship("Application", back_populates="applicant", cascade="all, delete-orphan")


class Application(Base):
    """Central loan application lifecycle state record."""

    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    applicant_id: Mapped[str] = mapped_column(String(36), ForeignKey("applicants.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    applicant: Mapped["Applicant"] = relationship("Applicant", back_populates="applications")
    document: Mapped[Optional["Document"]] = relationship("Document", back_populates="application", uselist=False, cascade="all, delete-orphan")
    risk_assessment: Mapped[Optional["RiskAssessment"]] = relationship("RiskAssessment", back_populates="application", uselist=False, cascade="all, delete-orphan")
    compliance_check: Mapped[Optional["ComplianceCheck"]] = relationship("ComplianceCheck", back_populates="application", uselist=False, cascade="all, delete-orphan")
    decision: Mapped[Optional["Decision"]] = relationship("Decision", back_populates="application", uselist=False, cascade="all, delete-orphan")
    audit_events: Mapped[List["AuditEvent"]] = relationship("AuditEvent", back_populates="application", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_applications_status_created_at", "status", "created_at"),
    )


class Document(Base):
    """Normalized document and feature extraction outcome."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    dti_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    validation_errors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped["Application"] = relationship("Application", back_populates="document")


class RiskAssessment(Base):
    """Machine learning risk model prediction output."""

    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    default_probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped["Application"] = relationship("Application", back_populates="risk_assessment")


class ComplianceCheck(Base):
    """Policy rules and RAG regulatory clause retrieval result."""

    __tablename__ = "compliance_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    compliance_verdict: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    has_blocking_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    flags_json: Mapped[str] = mapped_column(Text, default="[]")
    blocking_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    retrieved_clauses_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped["Application"] = relationship("Application", back_populates="compliance_check")


class Decision(Base):
    """Final synthesized underwriting decision with explanation and clause citations."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    interest_rate_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_source: Mapped[str] = mapped_column(String(50), nullable=False)
    applied_clause_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    pipeline_trace_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped["Application"] = relationship("Application", back_populates="decision")


class AuditEvent(Base):
    """Immutable audit trail log for regulatory traceability and system events."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    application_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(50), nullable=False, default="system")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    application: Mapped[Optional["Application"]] = relationship("Application", back_populates="audit_events")

    __table_args__ = (
        Index("ix_audit_events_app_created", "application_id", "created_at"),
    )
