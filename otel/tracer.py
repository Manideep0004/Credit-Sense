"""
creditsense/otel/tracer.py
--------------------------
OpenTelemetry Distributed Tracing Provider, Context Propagation & Span Decorators.
Enables end-to-end tracing from HTTP Request -> Celery Queue -> Multi-Agent Pipeline -> Database.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger("creditsense.otel.tracer")

_IS_TRACER_INITIALIZED = False


def init_tracer(service_name: str = "creditsense-service") -> trace.Tracer:
    """Initialize OpenTelemetry TracerProvider with OTLP or fallback console exporter."""
    global _IS_TRACER_INITIALIZED
    if _IS_TRACER_INITIALIZED:
        return trace.get_tracer(service_name)

    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": os.environ.get("ENVIRONMENT", "local-dev"),
    })

    provider = TracerProvider(resource=resource)
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("Configured OTLP gRPC trace exporter to %s", otlp_endpoint)
        except Exception as exc:
            logger.warning("Failed to initialize OTLP exporter (%s). Using fallback provider.", exc)
    else:
        # Development mode: use lightweight provider without network overhead
        logger.debug("OTEL_EXPORTER_OTLP_ENDPOINT not set; running with in-process trace provider.")

    trace.set_tracer_provider(provider)
    _IS_TRACER_INITIALIZED = True
    return trace.get_tracer(service_name)


def get_tracer(service_name: str = "creditsense") -> trace.Tracer:
    """Return the global tracer instance."""
    return trace.get_tracer(service_name)


@contextmanager
def trace_span(
    span_name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Generator[trace.Span, None, None]:
    """
    Context manager for creating an instrumented OpenTelemetry span.

    Usage:
        with trace_span("RiskAgent.predict", {"model.version": "v1"}) as span:
            prob = model.predict(X)
            span.set_attribute("risk.probability", prob)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(span_name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, v)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise exc


def inject_trace_context(headers: Dict[str, Any]) -> Dict[str, Any]:
    """Inject current distributed trace context into headers (e.g. for Celery tasks)."""
    inject(headers)
    return headers


def extract_trace_context(headers: Dict[str, Any]) -> Any:
    """Extract distributed trace context from headers to continue trace in worker."""
    return extract(headers)
