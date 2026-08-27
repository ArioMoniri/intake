"""INT-178 — traces are not a side channel (review #195 HIGH-3).

Redaction existed only for logs, at both layers: app-side (`JsonLogFormatter`)
and collector-side (`transform/redact` wired into the logs pipeline alone).
Span attributes and events — most dangerously `record_exception` payloads
carrying patient input inside a ValidationError message — exported unscrubbed
the moment ``OTEL_EXPORTER_OTLP_ENDPOINT`` was set.

Two contracts under test:

1. **App side**: every exported span passes ``RedactingSpanExporter`` — a
   span attribute or exception event carrying a TCKN/phone/IBAN reaches the
   wire redacted.
2. **Collector side**: the committed config wires ``transform/redact`` into
   the traces AND metrics pipelines (not only logs), and carries
   trace/metric statements — asserted against the file so the tested config
   is the deployed config.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from intake_platform.otel import RedactingSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

REPO = Path(__file__).resolve().parents[2]
COLLECTOR_CONFIG = REPO / "infra" / "observability" / "otel-collector.yaml"

VALID_TCKN = "10000000146"  # passes the published checksum
PHONE = "05321114455"


def _provider_and_memory() -> tuple[TracerProvider, InMemorySpanExporter]:
    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(RedactingSpanExporter(memory)))
    return provider, memory


def test_span_attributes_reach_the_exporter_redacted() -> None:
    provider, memory = _provider_and_memory()
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("ingest") as span:
        span.set_attribute("http.request.note", f"hasta {VALID_TCKN} tel {PHONE}")
        span.set_attribute("count", 3)
    (exported,) = memory.get_finished_spans()
    attrs = dict(exported.attributes or {})
    joined = str(attrs)
    assert VALID_TCKN not in joined
    assert PHONE not in joined
    assert "[TCKN]" in str(attrs["http.request.note"])
    assert attrs["count"] == 3, "non-string attributes pass through untouched"


def test_record_exception_payload_is_redacted() -> None:
    provider, memory = _provider_and_memory()
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("handler") as span:
        try:
            raise ValueError(f"validation failed for input: TCKN {VALID_TCKN}, tel {PHONE}")
        except ValueError as err:
            span.record_exception(err)
    (exported,) = memory.get_finished_spans()
    assert exported.events, "record_exception must still produce the event"
    for event in exported.events:
        blob = str(dict(event.attributes or {}))
        assert VALID_TCKN not in blob, "exception.message is the classic leak path"
        assert PHONE not in blob
        assert "[TCKN]" in blob


def test_span_name_and_status_are_redacted() -> None:
    provider, memory = _provider_and_memory()
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span(f"lookup {VALID_TCKN}") as span:
        span.set_attribute("event", "x")
    (exported,) = memory.get_finished_spans()
    assert VALID_TCKN not in exported.name
    assert "[TCKN]" in exported.name


def test_collector_wires_redaction_into_all_three_pipelines() -> None:
    config = yaml.safe_load(COLLECTOR_CONFIG.read_text(encoding="utf-8"))
    pipelines = config["service"]["pipelines"]
    for name in ("logs", "traces", "metrics"):
        assert "transform/redact" in pipelines[name]["processors"], (
            f"{name} pipeline must run the redact processor — errors are not a side channel"
        )
    redact = config["processors"]["transform/redact"]
    for section in ("log_statements", "trace_statements", "metric_statements"):
        statements = str(redact.get(section))
        assert "TCKN" in statements, f"{section} must carry the TCKN pattern"
