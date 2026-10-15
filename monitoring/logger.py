"""
creditsense/monitoring/logger.py
--------------------------------
Structured JSON logger with OpenTelemetry trace context and correlation IDs.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Custom JSON Formatter injecting correlation IDs and OTel trace context."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        # Attach request_id if present
        if hasattr(record, "request_id"):
            log_obj["request_id"] = record.request_id

        # Attach OpenTelemetry trace and span IDs if available
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span and span.get_span_context().is_valid:
                ctx = span.get_span_context()
                log_obj["trace_id"] = trace.format_trace_id(ctx.trace_id)
                log_obj["span_id"] = trace.format_span_id(ctx.span_id)
        except Exception:
            pass

        # Attach exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def configure_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Configure root logger with either JSON format or readable console format."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if json_format or os.environ.get("LOG_FORMAT", "").lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured under the creditsense namespace."""
    return logging.getLogger(f"creditsense.{name}")
