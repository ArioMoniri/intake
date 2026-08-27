"""Shared OTel setup + JSON logging with the no-PHI posture (INT-011).

Every service calls :func:`setup_otel` once and installs
:class:`JsonLogFormatter` on its handlers. What this module guarantees:

- **Propagated ids** — ``trace_id``/``span_id`` (from the active span),
  ``session_id_hash`` (the raw session id is hashed at bind time and never
  stored), ``tenant_id``, ``protocol_hash``, ``prompt_version``.
- **JSON logs** whose message text passes :func:`redact_text` and whose extra
  attributes are restricted to a closed allow-list — an attribute not on the
  list never reaches a log line ("names allow-list": free-text names have no
  allow-listed key to travel in; NER-based scrubbing is INT-015).
- **Local-only by default** — no exporter is wired unless
  ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (CI is vendor-free; the egress
  posture forbids default network sinks). The collector config lives at
  infra/observability/otel-collector.yaml with the same redaction patterns.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
from contextvars import ContextVar
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from intake_platform.redaction import redact_text

__all__ = [
    "ALLOWED_LOG_ATTRIBUTES",
    "JsonLogFormatter",
    "bind_log_context",
    "clear_log_context",
    "setup_otel",
]

ALLOWED_LOG_ATTRIBUTES = frozenset(
    {"session_id_hash", "tenant_id", "protocol_hash", "prompt_version", "event", "duration_ms"}
)

_EMPTY_CONTEXT: dict[str, str] = {}
_log_context: ContextVar[dict[str, str]] = ContextVar("intake_log_context", default=_EMPTY_CONTEXT)


def bind_log_context(
    *,
    session_id: str | None = None,
    tenant_id: str | None = None,
    protocol_hash: str | None = None,
    prompt_version: str | None = None,
) -> None:
    """Bind per-session ids for log propagation. The session id is hashed here,
    at the boundary — the raw value is never retained by this module."""
    ctx = dict(_log_context.get())
    if session_id is not None:
        ctx["session_id_hash"] = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
    if tenant_id is not None:
        ctx["tenant_id"] = tenant_id
    if protocol_hash is not None:
        ctx["protocol_hash"] = protocol_hash
    if prompt_version is not None:
        ctx["prompt_version"] = prompt_version
    _log_context.set(ctx)


def clear_log_context() -> None:
    _log_context.set({})


class JsonLogFormatter(logging.Formatter):
    """JSON lines: redacted message + allow-listed attributes + trace ids."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.UTC
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        out.update(_log_context.get())
        for key in ALLOWED_LOG_ATTRIBUTES:
            value = record.__dict__.get(key)
            if value is not None and key not in out:
                out[key] = redact_text(value) if isinstance(value, str) else value
        span = trace.get_current_span()
        span_ctx = span.get_span_context()
        if span_ctx.is_valid:
            out["trace_id"] = format(span_ctx.trace_id, "032x")
            out["span_id"] = format(span_ctx.span_id, "016x")
        if record.exc_info:
            out["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(out, ensure_ascii=False)


def setup_otel(service_name: str) -> TracerProvider:
    """Create (and globally install) the tracer provider for a service.

    An OTLP exporter is attached only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is
    set *and* the exporter package is installed — never by default.
    """
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        except ImportError:
            logging.getLogger(__name__).warning(
                "OTEL_EXPORTER_OTLP_ENDPOINT set but no OTLP exporter installed; spans stay local"
            )
    trace.set_tracer_provider(provider)
    return provider
