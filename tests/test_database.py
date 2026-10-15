"""
creditsense/tests/test_database.py
----------------------------------
Unit and integration tests for SQLAlchemy relational database models, repository operations, and audit logging.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure creditsense package root is on path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import app
from database.models import Base
from database.repository import ApplicationRepository
from database.session import get_db

from sqlalchemy.pool import StaticPool

# Use an isolated in-memory SQLite database for unit testing
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client_with_db(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def sample_applicant_dict():
    return {
        "age": 32,
        "employment_years": 6.0,
        "monthly_income": 85000.0,
        "existing_monthly_debt": 20000.0,
        "credit_utilization_pct": 25.0,
        "past_defaults": 0,
        "requested_loan_amount": 350000.0,
        "txn_volatility_score": 18.0,
        "kyc_verified": 1,
    }


def test_repository_create_and_get(db_session, sample_applicant_dict):
    repo = ApplicationRepository(db_session)

    # 1. Create
    app_entity = repo.create_application(sample_applicant_dict)
    assert app_entity.id is not None
    assert app_entity.status == "PROCESSING"
    assert app_entity.applicant.monthly_income == 85000.0

    # 2. Check initial audit event
    audit_trail = repo.get_audit_trail(app_entity.id)
    assert len(audit_trail) == 1
    assert audit_trail[0].event_type == "APPLICATION_SUBMITTED"

    # 3. Record decision
    pipeline_output = {
        "document_status": "ok",
        "dti_ratio": 0.2353,
        "validation_errors": [],
        "default_probability": 0.08,
        "risk_tier": "LOW",
        "risk_status": "ok",
        "flags": [],
        "blocking_flags": [],
        "has_blocking_flag": False,
        "retrieved_clauses": [{"id": "DTI-1.1", "title": "DTI Threshold", "text": "...", "triggered_by_flag": None}],
        "compliance_verdict": "CLEAR",
        "decision": "APPROVED",
        "interest_rate_pct": 10.5,
        "explanation": "Application meets all underwriting standards.",
        "explanation_source": "template_fallback",
        "applied_clause_ids": ["DTI-1.1"],
        "pipeline_trace": ["document_agent", "risk_agent", "compliance_agent", "decision_agent"],
    }

    updated_app = repo.record_underwriting_result(app_entity.id, pipeline_output)
    assert updated_app.status == "COMPLETED"
    assert updated_app.decision.decision == "APPROVED"
    assert updated_app.risk_assessment.risk_tier == "LOW"
    assert updated_app.compliance_check.compliance_verdict == "CLEAR"

    # 4. Verify audit trail growth
    audit_trail_2 = repo.get_audit_trail(app_entity.id)
    assert len(audit_trail_2) == 2
    assert audit_trail_2[1].event_type == "DECISION_RECORDED"


def test_repository_failure_recording(db_session, sample_applicant_dict):
    repo = ApplicationRepository(db_session)
    app_entity = repo.create_application(sample_applicant_dict)

    failed_app = repo.record_underwriting_failure(app_entity.id, "Mock pipeline timeout error")
    assert failed_app.status == "FAILED"
    assert failed_app.error_message == "Mock pipeline timeout error"

    trail = repo.get_audit_trail(app_entity.id)
    assert len(trail) == 2
    assert trail[1].event_type == "APPLICATION_FAILED"


def test_api_audit_trail_endpoint(client_with_db, sample_applicant_dict):
    # 1. Create via API
    res = client_with_db.post("/api/v1/applications?sync=true", json=sample_applicant_dict)
    assert res.status_code == 202
    app_id = res.json()["application_id"]

    # 2. Fetch audit trail via API
    audit_res = client_with_db.get(f"/api/v1/applications/{app_id}/audit")
    assert audit_res.status_code == 200
    events = audit_res.json()
    assert len(events) >= 2
    event_types = [e["event_type"] for e in events]
    assert "APPLICATION_SUBMITTED" in event_types
    assert "DECISION_RECORDED" in event_types
