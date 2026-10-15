"""
creditsense/tests/test_workers.py
---------------------------------
Unit and integration tests for Celery task workers, asynchronous underwriting, and idempotency.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
from database.session import SessionLocal, get_db
from workers.celery_app import celery_app
from workers.tasks import process_underwriting_application


@pytest.fixture
def clean_applicant_dict():
    return {
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


def test_celery_app_configuration():
    """Verify Celery task queue configurations, serializers, and timeouts."""
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_soft_time_limit == 45
    assert celery_app.conf.task_time_limit == 60
    assert celery_app.conf.task_default_queue == "underwriting_queue"


def test_worker_task_execution(clean_applicant_dict):
    """Test direct execution of process_underwriting_application Celery task."""
    db = SessionLocal()
    repo = ApplicationRepository(db)

    # 1. Create PENDING application
    app_entity = repo.create_application(clean_applicant_dict)
    app_entity.status = "PENDING"
    db.commit()
    app_id = app_entity.id

    # 2. Execute task directly (synchronous worker simulation)
    # Mock celery task self context
    mock_self = MagicMock()
    mock_self.request.retries = 0
    mock_self.max_retries = 3
    mock_self.request.id = "mock-task-123"
    mock_self.request.hostname = "test-worker-1"

    result = process_underwriting_application(mock_self, app_id)
    assert result["status"] == "success"
    assert result["application_id"] == app_id
    assert result["decision"] == "APPROVED"

    # 3. Verify database state
    updated_app = repo.get_application_by_id(app_id)
    assert updated_app.status == "COMPLETED"
    assert updated_app.decision is not None
    assert updated_app.decision.decision == "APPROVED"
    assert updated_app.risk_assessment.risk_tier == "LOW"

    # 4. Verify task start audit event
    audit_trail = repo.get_audit_trail(app_id)
    event_types = [e.event_type for e in audit_trail]
    assert "UNDERWRITING_TASK_STARTED" in event_types
    assert "DECISION_RECORDED" in event_types

    db.close()


def test_worker_task_idempotency(clean_applicant_dict):
    """Verify Celery task skips re-execution if application is already COMPLETED."""
    db = SessionLocal()
    repo = ApplicationRepository(db)

    # 1. Create application and process once
    app_entity = repo.create_application(clean_applicant_dict)
    app_id = app_entity.id

    mock_self = MagicMock()
    mock_self.request.retries = 0
    mock_self.max_retries = 3
    mock_self.request.id = "mock-task-idempotent-1"
    mock_self.request.hostname = "test-worker-1"

    res1 = process_underwriting_application(mock_self, app_id)
    assert res1["status"] == "success"

    # 2. Call again on same completed application
    res2 = process_underwriting_application(mock_self, app_id)
    assert res2["status"] == "already_completed"
    assert res2["decision"] == "APPROVED"

    db.close()


def test_api_async_endpoint_returns_202(clean_applicant_dict):
    """Verify POST /api/v1/applications returns 202 Accepted in async mode."""
    client = TestClient(app)
    response = client.post("/api/v1/applications", json=clean_applicant_dict)
    assert response.status_code == 202
    data = response.json()
    assert "application_id" in data
    assert data["status"] in ("PENDING", "PROCESSING", "COMPLETED")
