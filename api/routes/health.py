"""
creditsense/api/routes/health.py
--------------------------------
Health and readiness check endpoints for orchestrators (Docker, Kubernetes, load balancers).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from api.schemas import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["Health & Observability"])

ROOT = Path(__file__).parent.parent.parent
MODEL_PATH = ROOT / "models" / "risk_model.pkl"
VECTORSTORE_DIR = ROOT / "vectorstore"


@router.get("/healthz", include_in_schema=False)
@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Liveness Probe",
    description="Returns HTTP 200 if the CreditSense API server process is alive.",
)
def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc),
        services={
            "api": "healthy",
        },
    )


@router.get("/readyz", include_in_schema=False)
@router.get(
    "/ready",
    summary="Service Readiness Probe",
    description="Returns HTTP 200 if the service has loaded ML model artifacts and RAG vector store.",
)
def get_ready() -> JSONResponse:
    checks: dict[str, str] = {}
    is_ready = True

    # 1. Check ML Model artifact presence
    if MODEL_PATH.exists():
        checks["risk_model"] = "ready"
    else:
        checks["risk_model"] = "not_found"
        is_ready = False

    # 2. Check Vector store directory presence
    if VECTORSTORE_DIR.exists() and (
        (VECTORSTORE_DIR / "chroma.sqlite3").exists()
        or (VECTORSTORE_DIR / "store_metadata.json").exists()
        or (VECTORSTORE_DIR / "tfidf_store.pkl").exists()
    ):
        checks["vectorstore"] = "ready"
    else:
        checks["vectorstore"] = "not_found"
        is_ready = False

    checks["status"] = "ready" if is_ready else "degraded"

    http_status = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=http_status,
        content={
            "status": checks["status"],
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        },
    )
