"""INT-175 — the LLM-trace emission boundary (CLAUDE.md inv. 6/14; files/08
§0b F1, §3, §7; files/10 §9 row observability-pipeline).

Langfuse exists to store prompts and completions verbatim, and here the
extraction prompt **is** the patient's transcript — files/08 §6 calls it "a
transcript store with its own login page", and files/HUMAN_BLOCKERS.md
**HB-L6** records Langfuse spans as one of four unmanaged staff read paths
into patient content, on which counsel has not ruled.

So this module is the boundary, and it is deny-by-default in the only shape
that survives that reading: **there is no carrier for content.**

- Not a redactor. :func:`intake_platform.redaction.redact_text` catches
  identifiers — TCKN, phone, IBAN — and says so in its own docstring; a
  Turkish symptom sentence carries none of those patterns and would pass
  straight through. Scrubbing is the wrong control for narrative.
- Not a default-off flag. :class:`LlmSpan` has a closed field set of ids,
  enums and counts; every string field must be **id-shaped**, so a sentence —
  spaces, Turkish diacritics — cannot be constructed into one at all.
- Not the instance's own ``__dict__``. :func:`emit_llm_span` serialises from
  ``LLM_SPAN_FIELDS``, so a subclass or an ``object.__setattr__`` cannot add
  an attribute that reaches the payload, and it **re-validates** every value
  first, because ``frozen=True`` is a typo-catcher and not a boundary.

**The content-carrying mode is absent, not disabled.** files/08 §3 speaks of
a "raw-content project ... break-glass only"; that project has no
representation here. There is no branch to take, no environment variable to
read (the module imports neither ``os`` nor the flag provider — a test
asserts it) and no feature flag to flip. Building one means adding a type and
deleting the tests that assert it does not exist: a reviewed change, not an
operator's mistake. When HB-L6 is answered, that is the work.

What does travel is what an operator actually needs to debug an extraction
without reading a patient: which prompt version, which model revision, which
schema, how long it took, how many tokens and characters went in and out, and
whether the result was accepted. A character count is a measurement of a
string, not the string.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from opentelemetry.trace import Tracer
from prometheus_client import Counter

__all__ = [
    "DENIED_FIELD_TOKENS",
    "LLM_SPAN_FIELDS",
    "LlmSpan",
    "OtelSpanSink",
    "SpanFieldRefused",
    "SpanKind",
    "SpanOutcome",
    "SpanSink",
    "emit_llm_span",
    "refuse_unless_ref_shaped",
]

#: Ids, refs, dotted names and hex digests only — the same shape the audit
#: chain enforces on its own fields (:mod:`intake_platform.audit`). Anything
#: with a space or a non-ASCII character — which is to say, anything a person
#: said — has no field it can legally occupy.
_REF_SHAPE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}")

#: Substrings that name a content carrier rather than an identifier. The
#: closed field set below is the wall; this list is the readability guard that
#: makes a future field named ``completion`` obvious in review. It may grow,
#: never shrink (the same rule as PHI_RISK_LABEL_NAMES, inv. 6).
DENIED_FIELD_TOKENS: Final[tuple[str, ...]] = (
    "answer",
    "body",
    "completion",
    "content",
    "message",
    "narrative",
    "raw",
    "snippet",
    "text",
    "transcript",
    "utterance",
    "verbatim",
)

SPANS_EMITTED_TOTAL: Final = Counter(
    "llm_trace_spans_emitted_total",
    "LLM trace spans emitted to the self-hosted trace store, by kind and outcome (INT-175).",
    ["kind", "outcome"],
)

FIELDS_REFUSED_TOTAL: Final = Counter(
    "llm_trace_fields_refused_total",
    "Span fields refused at the emission boundary because the value was not id-shaped "
    "(INT-175; HB-L6). The refused value is never recorded — only which field it targeted.",
    ["field"],
)


class SpanKind(StrEnum):
    """Which LLM call produced the span. A closed set: a new kind is a code
    change with a test, not a string an operator can invent at runtime."""

    EXTRACTION = "extraction"
    NOTE_DRAFT = "note_draft"
    SUMMARY = "summary"
    INSTRUMENT_SCORE = "instrument_score"
    #: INT-430 / ADR-036: one draw of the council verifier.
    VERIFICATION = "verification"


class SpanOutcome(StrEnum):
    """How the call ended. ``policy_blocked`` is PolicyGuard (inv. 2);
    ``schema_invalid`` is the slot-schema validator rejecting the output."""

    OK = "ok"
    SCHEMA_INVALID = "schema_invalid"
    POLICY_BLOCKED = "policy_blocked"
    TIMEOUT = "timeout"
    ERROR = "error"


class SpanFieldRefused(ValueError):
    """A field was handed something that is not an identifier.

    The message names the field and **never** echoes the value: the value is
    the very thing that must not reach a log, and an exception message reaches
    a log (invariant 6, and the same rule :mod:`intake_platform.audit` states).
    """


def refuse_unless_ref_shaped(field_name: str, value: str) -> str:
    """Return ``value`` when it is id-shaped; raise :class:`SpanFieldRefused`
    otherwise, counting the refusal by field name."""
    if not isinstance(value, str) or not _REF_SHAPE.fullmatch(value):
        FIELDS_REFUSED_TOTAL.labels(field=field_name).inc()
        raise SpanFieldRefused(
            f"field {field_name!r} must be id-shaped ([A-Za-z0-9._:/@-], <=128 chars, "
            "no spaces, ASCII): free text is how patient content reaches a trace store "
            "(CLAUDE.md invariant 6, HB-L6). The refused value is deliberately not "
            "echoed here, for the same reason."
        )
    return value


def _refuse_unless_counted(field_name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        FIELDS_REFUSED_TOTAL.labels(field=field_name).inc()
        raise SpanFieldRefused(f"field {field_name!r} must be a non-negative integer count")
    return value


@dataclass(frozen=True)
class LlmSpan:
    """The only shape that reaches the trace store.

    The field set is closed on purpose: a span that accepts arbitrary keys
    accumulates transcripts the first time someone attaches a payload "for
    debugging". Every field below is an id, an enum or a count.
    """

    work_id: str
    session_id_hash: str
    tenant_id: str
    prompt_version: str
    protocol_hash: str
    model_id: str
    model_revision: str
    kind: SpanKind
    outcome: SpanOutcome
    latency_ms: int
    input_tokens: int
    output_tokens: int
    input_chars: int
    output_chars: int
    candidate_flag_count: int
    schema_id: str

    def __post_init__(self) -> None:
        _validate(self)


#: The closed field set, in emission order. :func:`emit_llm_span` iterates
#: THIS tuple rather than the instance, so nothing a subclass or an
#: ``object.__setattr__`` bolts on can reach a payload.
LLM_SPAN_FIELDS: Final[tuple[str, ...]] = (
    "work_id",
    "session_id_hash",
    "tenant_id",
    "prompt_version",
    "protocol_hash",
    "model_id",
    "model_revision",
    "kind",
    "outcome",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "input_chars",
    "output_chars",
    "candidate_flag_count",
    "schema_id",
)

_STRING_FIELDS: Final[tuple[str, ...]] = (
    "work_id",
    "session_id_hash",
    "tenant_id",
    "prompt_version",
    "protocol_hash",
    "model_id",
    "model_revision",
    "schema_id",
)

_COUNT_FIELDS: Final[tuple[str, ...]] = (
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "input_chars",
    "output_chars",
    "candidate_flag_count",
)


def _validate(span: LlmSpan) -> None:
    """Every rule, applied at construction AND again at emission."""
    for field_name in _STRING_FIELDS:
        refuse_unless_ref_shaped(field_name, getattr(span, field_name))
    for field_name in _COUNT_FIELDS:
        _refuse_unless_counted(field_name, getattr(span, field_name))
    if not isinstance(span.kind, SpanKind):
        FIELDS_REFUSED_TOTAL.labels(field="kind").inc()
        raise SpanFieldRefused("field 'kind' must be a SpanKind member")
    if not isinstance(span.outcome, SpanOutcome):
        FIELDS_REFUSED_TOTAL.labels(field="outcome").inc()
        raise SpanFieldRefused("field 'outcome' must be a SpanOutcome member")


class SpanSink(Protocol):
    """Where an emitted span goes. The transport is a seam so the boundary can
    be proven without a running trace store — and so the boundary, not the
    transport, is the thing under test."""

    def emit(self, name: str, attributes: Mapping[str, str | int]) -> None: ...


class OtelSpanSink:
    """The production sink: one OTel span per LLM call, exported over OTLP to
    the self-hosted Langfuse endpoint (``/api/public/otel``).

    It carries no redaction of its own and needs none — everything it is given
    has already passed :func:`_validate`. The shared setup wraps the exporter
    in :class:`intake_platform.otel.RedactingSpanExporter` regardless, so the
    identifier patterns get a second pass on the wire.
    """

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def emit(self, name: str, attributes: Mapping[str, str | int]) -> None:
        with self._tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                span.set_attribute(key, value)


def emit_llm_span(span: LlmSpan, sink: SpanSink) -> dict[str, str | int]:
    """Serialise ``span`` through the closed field set and hand it to ``sink``.

    Returns the payload that was emitted, so a caller (and a test) can assert
    on exactly what left the process. Raises :class:`SpanFieldRefused` — and
    emits nothing — if any value fails re-validation.
    """
    if not isinstance(span, LlmSpan):
        raise TypeError(
            "emit_llm_span takes an LlmSpan and nothing else: a mapping would let an "
            "arbitrary key through, which is the whole failure mode (HB-L6)"
        )
    _validate(span)
    payload: dict[str, str | int] = {}
    for field_name in LLM_SPAN_FIELDS:
        value = getattr(span, field_name)
        payload[field_name] = value.value if isinstance(value, StrEnum) else value
    sink.emit(f"llm.{span.kind.value}", payload)
    SPANS_EMITTED_TOTAL.labels(kind=span.kind.value, outcome=span.outcome.value).inc()
    return payload
