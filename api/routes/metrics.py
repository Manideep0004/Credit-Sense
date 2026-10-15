"""
creditsense/api/routes/metrics.py
---------------------------------
Prometheus metrics exposition endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST

from monitoring.metrics import (
    API_REQUEST_DURATION_SECONDS,
    API_REQUESTS_TOTAL,
    APPLICATION_PROCESSING_DURATION_SECONDS,
    APPLICATIONS_PROCESSED_TOTAL,
    APPLICATIONS_RECEIVED_TOTAL,
    get_metrics_exposition,
)

router = APIRouter(tags=["Health & Observability"])


@router.get("/metrics", include_in_schema=False)
@router.get(
    "/api/v1/metrics",
    summary="Prometheus Metrics Exposition",
    description="Returns application and system runtime metrics in Prometheus text exposition format.",
)
def get_metrics() -> Response:
    """Expose Prometheus metrics for scraping."""
    return Response(content=get_metrics_exposition(), media_type=CONTENT_TYPE_LATEST)
