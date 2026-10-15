"""
creditsense/api/main.py
-----------------------
FastAPI Application Entry Point.
Configures OpenAPI documentation, middleware (correlation IDs, CORS, Prometheus metrics),
exception handlers, and route controllers.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from uuid import uuid4

# Ensure creditsense root is on sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import applications, health, metrics
from api.routes.metrics import API_REQUEST_DURATION_SECONDS, API_REQUESTS_TOTAL

# Configure structured root logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("creditsense.api")

app = FastAPI(
    title="CreditSense Underwriting API",
    description=(
        "Production-style, cloud-native REST API for the CreditSense "
        "multi-agent loan underwriting and compliance decision engine."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Correlation ID & Metrics Middleware ───────────────────────────────────────
@app.middleware("http")
async def request_lifecycle_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id

    start_time = time.perf_counter()
    status_code = 500
    response: Response | None = None

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        logger.exception("Unhandled error processing request %s: %s", request_id, exc)
        raise exc
    finally:
        duration = time.perf_counter() - start_time
        if response is not None:
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration:.4f}s"
            # OWASP Hardening Security Headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Record metrics (strip dynamic UUIDs from path for low cardinality)
        endpoint = request.url.path
        if endpoint.startswith("/api/v1/applications/") and len(endpoint.split("/")) > 4:
            endpoint = "/api/v1/applications/{id}" + endpoint[endpoint.rfind("/"):]
        elif endpoint.startswith("/api/v1/applications/"):
            endpoint = "/api/v1/applications/{id}"

        API_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=str(status_code),
        ).inc()

        API_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)


# ── Structured Exception Handlers ─────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", "unknown")
    logger.warning("Validation failed for request %s: %s", req_id, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Input validation failed. Check request payload against schema requirements.",
                "details": exc.errors(),
                "request_id": req_id,
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    req_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
                "request_id": req_id,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Internal server error for request %s: %s", req_id, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred while processing the request.",
                "request_id": req_id,
            }
        },
    )


# ── Register Routers ──────────────────────────────────────────────────────────
app.include_router(applications.router)
app.include_router(health.router)
app.include_router(metrics.router)


@app.get("/", include_in_schema=False)
def root_redirect():
    return {
        "service": "CreditSense API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "metrics": "/api/v1/metrics",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
