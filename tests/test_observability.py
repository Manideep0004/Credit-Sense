import json
import logging
import sys
from pathlib import Path

# Ensure package root is on path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from monitoring.metrics import (
        record_application_metric,
        record_agent_latency,
        record_rag_latency,
        record_model_inference_latency,
        record_api_request,
        set_queue_depth,
        get_metrics_response,
    )
    from monitoring.logger import JSONFormatter, get_logger
    from otel.tracer import get_tracer, trace_span
except ImportError:
    from creditsense.monitoring.metrics import (
        record_application_metric,
        record_agent_latency,
        record_rag_latency,
        record_model_inference_latency,
        record_api_request,
        set_queue_depth,
        get_metrics_response,
    )
    from creditsense.monitoring.logger import JSONFormatter, get_logger
    from creditsense.otel.tracer import get_tracer, trace_span


def test_metrics_recording():
    record_application_metric("APPROVED", "risk_tier_low", 1.25)
    record_agent_latency("financial_agent", 0.35)
    record_rag_latency("tfidf", 0.05)
    record_model_inference_latency("xgboost_v1", 0.02)
    record_api_request("/api/v1/applications", "POST", 202, 0.15)
    set_queue_depth(5)

    metrics_text = get_metrics_response()
    assert b"creditsense_applications_total" in metrics_text
    assert b"creditsense_agent_duration_seconds" in metrics_text
    assert b"creditsense_rag_search_duration_seconds" in metrics_text
    assert b"creditsense_queue_depth" in metrics_text


def test_json_logging_format():
    logger = get_logger("test_logger")
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Application received",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert parsed["message"] == "Application received"
    assert parsed["level"] == "INFO"
    assert "timestamp" in parsed


def test_otel_tracer():
    tracer = get_tracer("test_service")
    assert tracer is not None
    with trace_span("test_operation", {"loan_id": "L12345"}) as span:
        assert span is not None
