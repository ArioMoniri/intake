"""``extract_slots`` — one Backend Work, end to end, and what it hands back.

files/03 §4.3 lists ``extract_slots(step_id, transcript)`` first among Layer B's
Work types. This module is that Work's body: wrap the transcript, build the
schema-constrained call, ask the gateway, validate the answer, and produce
three artefacts with sharply different audiences.

- :class:`ExtractionResult` — the clinical answer. Slot updates, candidate
  flags, and the flags that record what did not bind. It goes to the engine
  through ``as_engine_call()``, which is exactly
  ``IntakeEngine.apply_extraction``'s parameter set.
- :class:`intake_platform.observability.spans.LlmSpan` — the operator's view.
  Ids, enums and counts, and no carrier for content at all (INT-175, HB-L6).
- :class:`intake_platform.observability.experiment.ExperimentRecord` — the eval
  row. Structural results only, gated by ``make langfuse-experiment``.

**Enqueueing, delivery and idempotency are not here.** files/03 §4.3's FIFO
queue, the one-Work-in-flight rule and the ``{inline, speech_tr, priority}``
result envelope are INT-092's, and this module deliberately produces no
``speech_tr``: a numeric slot value that could be spoken from here would need
the ``inline`` pairing of files/03 §4.9.6 invariant 30, and the safest way to
hold that invariant is to have nothing to speak with.

**The latency is measured, not believed.** ``now_ms`` is injected the way
``intake_voice_runtime.ports.Clock`` is, so a recorded run's numbers come from
the harness rather than from whatever the machine felt like doing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from intake_platform.observability.experiment import ExperimentRecord
from intake_platform.observability.spans import LlmSpan, SpanKind, SpanOutcome
from protocols.dsl import Slot

from intake_voice_runtime.extraction.boundary import wrap_patient_data
from intake_voice_runtime.extraction.errors import ExtractionRefused
from intake_voice_runtime.extraction.gateway import ExtractionCall, ExtractionGateway
from intake_voice_runtime.extraction.parse import parse_extraction
from intake_voice_runtime.extraction.result import ExtractionResult
from intake_voice_runtime.extraction.schema import (
    EXTRACTION_SCHEMA_ID,
    PROMPT_VERSION,
    build_instructions,
    slot_output_schema,
)

__all__ = [
    "CANDIDATE_FLAG_LEVEL",
    "NO_CANDIDATE_LEVEL",
    "ExtractionContext",
    "ExtractionOutcome",
    "run_extraction",
]

#: The two values ``llm_triage_level`` can take on an extraction row, and both
#: are members of ``experiment.PERMITTED_LLM_TRIAGE_LEVELS``. There is no third
#: branch in this module: the result type cannot express a triage level, so
#: there is nothing else to write here (CLAUDE.md invariant 1).
CANDIDATE_FLAG_LEVEL: Final = "candidate_flag"
NO_CANDIDATE_LEVEL: Final = "none"


@dataclass(frozen=True)
class ExtractionContext:
    """The ids one extraction is attributed by. Every field is id-shaped, and
    ``LlmSpan`` re-validates each of them at construction and again at
    emission — this type carries no free text at all."""

    work_id: str
    session_id_hash: str
    tenant_id: str
    protocol_hash: str
    model_id: str
    model_revision: str
    case_id: str


@dataclass(frozen=True, repr=False)
class ExtractionOutcome:
    """One Work's three artefacts, plus the refusal when there was one."""

    result: ExtractionResult | None
    span: LlmSpan
    record: ExperimentRecord
    refusal: str | None = None

    def __repr__(self) -> str:
        return (
            f"ExtractionOutcome(case_id={self.record.case_id!r}, "
            f"outcome={self.span.outcome.value!r}, "
            f"bound={0 if self.result is None else len(self.result.slot_updates)}, "
            f"refused={self.refusal is not None})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def run_extraction(
    context: ExtractionContext,
    *,
    step_id: str,
    slots: Mapping[str, Slot],
    valuesets: Mapping[str, tuple[str, ...]],
    transcript: str,
    gateway: ExtractionGateway,
    now_ms: Callable[[], float],
    required_slots_total: int | None = None,
) -> ExtractionOutcome:
    """Run one ``extract_slots`` Work against ``gateway``.

    A refusal from the *parser* is an outcome, not an exception: a model that
    answered off-schema is the normal failure this Work exists to survive, and
    the caller needs the span and the eval row for it. A refusal from the
    *gateway* — an unconfigured lane, a missing recording, an endpoint that did
    not answer — propagates, because that is an operator's problem and not a
    measurement of the model.
    """
    data = wrap_patient_data(transcript)
    json_schema = slot_output_schema(slots, valuesets)
    call = ExtractionCall(
        instructions=build_instructions(json_schema), data=data, json_schema=json_schema
    )

    started = now_ms()
    completion = gateway.complete(call)
    latency_ms = max(0, int(round(now_ms() - started)))

    result: ExtractionResult | None = None
    refusal: str | None = None
    try:
        result = parse_extraction(
            raw=completion.text, slots=slots, valuesets=valuesets, step_id=step_id
        )
    except ExtractionRefused as err:
        refusal = str(err)

    obliged = (
        required_slots_total
        if required_slots_total is not None
        else sum(1 for slot in slots.values() if slot.required)
    )
    required_refs = {ref for ref, slot in slots.items() if slot.required}
    filled = 0 if result is None else len(result.bound_refs() & required_refs)
    if filled > obliged:
        raise ValueError(
            "more required slots bound than the step obliged — the obligation count "
            "and the declarations disagree, and a clamped ratio would hide it"
        )

    candidate_count = 0 if result is None else len(result.candidate_flags)
    span = LlmSpan(
        work_id=context.work_id,
        session_id_hash=context.session_id_hash,
        tenant_id=context.tenant_id,
        prompt_version=PROMPT_VERSION,
        protocol_hash=context.protocol_hash,
        model_id=context.model_id,
        model_revision=context.model_revision,
        kind=SpanKind.EXTRACTION,
        outcome=SpanOutcome.OK if result is not None else SpanOutcome.SCHEMA_INVALID,
        latency_ms=latency_ms,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        input_chars=len(transcript),
        output_chars=len(completion.text),
        candidate_flag_count=candidate_count,
        schema_id=EXTRACTION_SCHEMA_ID,
    )
    record = ExperimentRecord(
        case_id=context.case_id,
        kind=SpanKind.EXTRACTION,
        outcome=span.outcome,
        schema_valid=result is not None,
        required_slots_filled=filled,
        required_slots_total=obliged,
        llm_triage_level=CANDIDATE_FLAG_LEVEL if candidate_count else NO_CANDIDATE_LEVEL,
        # Extraction produces no patient-facing sentence — there is nothing for
        # PolicyGuard to judge, and invariant 2 has no surface here. The field
        # is INT-175's, shared with the note and summary kinds, and it becomes
        # a real measurement on those.
        policyguard_pass=True,
        latency_ms=latency_ms,
    )
    return ExtractionOutcome(result=result, span=span, record=record, refusal=refusal)
