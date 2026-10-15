"""
creditsense/tests/test_api.py
-----------------------------
Integration and unit tests for the FastAPI REST API layer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure creditsense package root is on path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import app

client = TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def clean_applicant_payload():
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


@pytest.fixture
def aml_applicant_payload():
    return {
        "age": 45,
        "employment_years": 15.0,
        "monthly_income": 120000.0,
        "existing_monthly_debt": 18000.0,
        "credit_utilization_pct": 12.0,
        "past_defaults": 0,
        "requested_loan_amount": 1500000.0,  # > 10x monthly income
        "txn_volatility_score": 92.0,        # > 80
        "kyc_verified": 1,
    }


# ── Health & Metrics Tests ───────────────────────────────────────────────────

def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "services" in data
    assert "X-Request-ID" in response.headers


def test_ready_endpoint():
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["risk_model"] == "ready"


def test_metrics_endpoint():
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    assert "creditsense_api_requests_total" in response.text


# ── Application Endpoints Tests ───────────────────────────────────────────────

def test_create_application_async_default(clean_applicant_payload):
    response = client.post("/api/v1/applications", json=clean_applicant_payload)
    assert response.status_code == 202
    data = response.json()
    assert "application_id" in data
    assert data["status"] in ("PENDING", "PROCESSING", "COMPLETED")


def test_create_application_clean_sync(clean_applicant_payload):
    response = client.post("/api/v1/applications?sync=true", json=clean_applicant_payload)
    assert response.status_code == 202
    data = response.json()

    assert "application_id" in data
    assert data["status"] == "COMPLETED"
    assert data["applicant_data"]["age"] == 34

    decision = data["decision_details"]
    assert decision is not None
    assert decision["decision"] == "APPROVED"
    assert decision["risk_tier"] == "LOW"
    assert decision["default_probability"] < 0.20
    assert decision["interest_rate_pct"] is not None
    assert len(decision["pipeline_trace"]) > 0


def test_create_application_aml_blocking_sync(aml_applicant_payload):
    response = client.post("/api/v1/applications?sync=true", json=aml_applicant_payload)
    assert response.status_code == 202
    data = response.json()

    assert data["status"] == "COMPLETED"
    decision = data["decision_details"]
    assert decision is not None
    assert decision["decision"] == "MANUAL_REVIEW"
    assert "AML_STRUCTURING" in decision["blocking_flags"]
    assert decision["interest_rate_pct"] is None


def test_create_application_validation_error():
    invalid_payload = {
        "age": 15,  # Below minimum age of 18
        "employment_years": -2.0,  # Negative
        "monthly_income": 0,  # Must be > 0
    }
    response = client.post("/api/v1/applications", json=invalid_payload)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in data["error"]


def test_get_application_flow(clean_applicant_payload):
    # 1. Create with sync=true
    post_res = client.post("/api/v1/applications?sync=true", json=clean_applicant_payload)
    assert post_res.status_code == 202
    app_id = post_res.json()["application_id"]

    # 2. Get full application
    get_res = client.get(f"/api/v1/applications/{app_id}")
    assert get_res.status_code == 200
    assert get_res.json()["application_id"] == app_id

    # 3. Get status
    status_res = client.get(f"/api/v1/applications/{app_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "COMPLETED"

    # 4. Get decision
    decision_res = client.get(f"/api/v1/applications/{app_id}/decision")
    assert decision_res.status_code == 200
    assert decision_res.json()["decision_details"]["decision"] == "APPROVED"


def test_get_nonexistent_application():
    response = client.get("/api/v1/applications/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "HTTP_404"


def test_list_applications(clean_applicant_payload):
    # Submit one application
    client.post("/api/v1/applications", json=clean_applicant_payload)

    # List all
    response = client.get("/api/v1/applications")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
