"""The Langfuse wiring for Extraction Work (INT-083, on INT-175's boundary).

INT-175 built the emission boundary — a closed field set of ids, enums and
counts, with no carrier for content at all
(:mod:`intake_platform.observability.spans`). This module is the *extraction*
side of it: it assembles the one span kind INT-175 reserved
(``SpanKind.EXTRACTION``) from the structural facts of one Work, and it adds
the one check INT-175's shape rule cannot make.

**That check matters and is easy to miss.** ``refuse_unless_ref_shaped``
admits any value made of ``[A-Za-z0-9._:/@-]`` with no spaces. A TC Kimlik
number is eleven digits with no spaces, and an 05xx mobile number likewise:
both are *id-shaped*, so the shape rule alone would let one through in
``tenant_id`` or ``session_id_hash`` if a caller ever put one there. So every
string value is run through :func:`intake_platform.redaction.redact_text`
first, and any value the redactor would change is refused — the field is
named, the value never is (invariant 6).

**No live Langfuse instance is reached from here, and none is needed.** The
sink is a Protocol (:class:`~intake_platform.observability.spans.SpanSink`);
production wires :class:`~intake_platform.observability.spans.OtelSpanSink`
over OTLP to the self-hosted ``/api/public/otel`` endpoint, whose tier lives
in its own compose file behind its own profile and is not booted in CI
(HB-I1/HB-I2). This module imports no HTTP client and reads no configuration,
which a contract test asserts.

**"Scores" are structural, and are not accuracy claims.**
:func:`extraction_record` produces exactly the row
``intake_platform.observability.experiment.ExperimentRecord`` loads — schema
validity, required-slot fill, the ``llm_triage_level`` that invariant 1 gates
on, and a latency — over a corpus that is named where it is reported
(invariant 20).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from intake_platform.llm.errors import IdentifierInTraceError
from intake_platform.llm.slot_schema import SlotSchema
from intake_platform.observability.spans import (
    LLM_SPAN_FIELDS,
    LlmSpan,
    SpanKind,
    SpanOutcome,
    SpanSink,
    emit_llm_span,
)
from intake_platform.redaction import redact_text

if TYPE_CHECKING:  # pragma: no cover - import cycle only exists for the checker
    from intake_platform.llm.extraction import ExtractionRun

__all__ = [
    "PERMITTED_RECORD_LEVELS",
    "emit_extraction_span",
    "extraction_record",
    "extraction_span",
]

#: Mirrors ``experiment.PERMITTED_LLM_TRIAGE_LEVELS``. Anything else in a
#: recorded run means the extractor reached a level, which invariant 1 forbids
#: and which the committed gate fails on outright.
PERMITTED_RECORD_LEVELS = ("none", "candidate_flag")


def extraction_span(
    *,
    work_id: str,
    session_id_hash: str,
    tenant_id: str,
    prompt_version: str,
    protocol_hash: str,
    model_id: str,
    model_revision: str,
    schema_id: str,
    outcome: SpanOutcome,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
    input_chars: int,
    output_chars: int,
    candidate_flag_count: int,
) -> LlmSpan:
    """Assemble the extraction span. Every argument is an id, an enum or a count."""
    return LlmSpan(
        work_id=work_id,
        session_id_hash=session_id_hash,
        tenant_id=tenant_id,
        prompt_version=prompt_version,
        protocol_hash=protocol_hash,
        model_id=model_id,
        model_revision=model_revision,
        kind=SpanKind.EXTRACTION,
        outcome=outcome,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_chars=input_chars,
        output_chars=output_chars,
        candidate_flag_count=candidate_flag_count,
        schema_id=schema_id,
    )


def emit_extraction_span(span: LlmSpan, sink: SpanSink) -> dict[str, str | int]:
    """Refuse any identifier-shaped value, then emit through INT-175's boundary."""
    for field_name in LLM_SPAN_FIELDS:
        value = getattr(span, field_name)
        if isinstance(value, str) and redact_text(value) != value:
            raise IdentifierInTraceError(
                f"field {field_name!r} matches an identifier pattern (TCKN, TR mobile "
                "or IBAN). Those are id-SHAPED, so the span's ref-shape rule would "
                "admit one; nothing identifying reaches the trace store (CLAUDE.md "
                "invariant 6, KVKK-9, HB-L6). The value is deliberately not echoed."
            )
    return emit_llm_span(span, sink)


def _no_patient_facing_text(run: ExtractionRun) -> bool:
    """Whether this Work produced anything a patient could hear. It cannot.

    ``ExtractionOutput`` has no speech field: slot values go to the
    "Anlattıklarınız" rail and candidate flags go to a clinician. Text that
    *is* spoken is composed one layer out and passes the Talker's PolicyGuard
    (CLAUDE.md invariant 2), which owns that verdict — this column records the
    structural fact rather than borrowing a classifier's opinion.
    """
    return run.output is None or not hasattr(run.output, "speech_tr")


def extraction_record(*, case_id: str, run: ExtractionRun, schema: SlotSchema) -> dict[str, Any]:
    """One structural row for the recorded-experiment gate (INT-175).

    Raises when the schema declares no required slot: the gate divides by the
    required-slot total, and a corpus case that asks for nothing measures
    nothing.
    """
    required = schema.required_refs
    if not required:
        raise ValueError(
            f"case {case_id!r} runs a schema with no required slot; the slot-fill score "
            "would divide by zero and the case would measure nothing"
        )
    filled = sum(1 for ref in required if ref in run.output.slot_updates) if run.output else 0
    flags = len(run.output.candidate_flags) if run.output else 0
    return {
        "case_id": case_id,
        "kind": SpanKind.EXTRACTION.value,
        "outcome": run.outcome.value,
        "schema_valid": run.output is not None,
        "required_slots_filled": filled,
        "required_slots_total": len(required),
        "llm_triage_level": "candidate_flag" if flags else "none",
        "policyguard_pass": _no_patient_facing_text(run),
        "latency_ms": run.completion.latency_ms if run.completion else 0,
    }
