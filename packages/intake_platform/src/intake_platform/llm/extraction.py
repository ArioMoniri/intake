"""Extraction Work: what the model said, checked before anyone believes it.

files/03 §4.3 lists ``extract_slots(step_id, transcript)`` as the first Work
type on the per-session FIFO; INT-081 built the engine that consumes its
output. This module is the piece between them, and its whole job is to be
sceptical.

**Invariant 1 lives here as a refusal, not a clamp.** A completion that
carries a key naming a level or a delivery priority is rejected outright
(:class:`~intake_platform.llm.errors.TriageAssertionRefused`) — the offending
key is *not* stripped and the rest used, because a model that answered
outside its schema answered a different question and the remainder is not
evidence of anything. What survives is
:class:`~clinical_schemas.triage.LlmCandidateTriage`, whose ``level`` is the
literal ``"YELLOW_REVIEW"`` and which the ``BackendResult`` validator can
never carry as ``preempt`` (files/03 §4.3; ADR-004).
:class:`ExtractionOutput` has no field a level could occupy, so the ceiling is
type-level rather than a check somebody could forget.

**A code with no valueset does not bind.** No valueset member list exists
anywhere in this repository, so a code slot's value cannot be validated
against one. It is reported in :attr:`ExtractionOutput.unbound` and kept out
of ``slot_updates``: build the mechanism, wire the gate, make it fail closed,
leave the content empty. Inventing the member list would be inventing
clinical content.

**Nothing here raises on a bad model.** :meth:`ExtractionWork.run` turns a
schema violation into a completed Work with ``outcome=schema_invalid`` and a
trace span, because one malformed completion must not take down the session
queue (files/03 §4.3 "retries are bounded so one malformed result cannot
block later ones"). It *does* raise when the caller is misconfigured — a
dev-tier gateway without de-identification, or an unpinned model — since
those are build errors, not runtime events.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from clinical_schemas.triage import CandidateFlag, LlmCandidateTriage

from intake_platform.deid import Deidentifier
from intake_platform.llm.boundary import build_extraction_prompt
from intake_platform.llm.errors import (
    DeidentificationRequired,
    DelimiterCollisionError,
    SchemaViolation,
    TriageAssertionRefused,
)
from intake_platform.llm.gateway import GatewayTier, LlmCompletion, LlmGateway
from intake_platform.llm.slot_schema import (
    MAX_FREE_TEXT_CHARS,
    SlotSchema,
    SlotSpec,
    SlotValueType,
)
from intake_platform.llm.trace import emit_extraction_span, extraction_span
from intake_platform.llm.units import render_quantity
from intake_platform.observability.spans import LlmSpan, SpanOutcome, SpanSink

__all__ = [
    "INJECTION_SIGNAL_REFUSALS",
    "LEVEL_SHAPED_KEYS",
    "SlotValue",
    "TOP_LEVEL_KEYS",
    "ExtractionOutput",
    "ExtractionRun",
    "ExtractionWork",
    "is_injection_signal",
    "parse_extraction",
]

#: What a validated slot value can be. Deliberately **not**
#: ``clinical_schemas.common.JsonValue``: that alias admits ``float``, and no
#: float crosses a representation boundary for a clinical magnitude (CLAUDE.md
#: invariant 22). A ``decimal``/``quantity`` slot therefore lands here as an
#: exact :class:`~decimal.Decimal`.
#:
#: ⚠ **Handoff note for the caller.** ``protocols.triage.context.canonical_scalar``
#: canonicalises ``bool``, ``int``, ``float`` and ``str``; a ``Decimal`` handed
#: to it today falls through and reads **Unknown**, so a decimal slot passed
#: straight into ``IntakeEngine.apply_extraction`` would be invisible to a gate
#: that references it. That is a one-line fix in a package this issue does not
#: own; docs/evidence/INT-083.md records it as an open integration defect
#: rather than papering over it with a float here.
type SlotValue = bool | int | str | Decimal

#: The only four keys a completion may carry.
TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {"slot_updates", "candidate_flags", "clarification_needed", "confidence"}
)

#: Unknown keys are refused whatever they are called; these names get the
#: *specific* refusal so the failure reads as "the model tried to triage"
#: rather than "the model added a key". The list may grow, never shrink.
LEVEL_SHAPED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "triage",
        "triage_update",
        "level",
        "severity",
        "priority",
        "preempt",
        "red_flags",
        "disposition",
        "ek4",
    }
)


@dataclass(frozen=True)
class ExtractionOutput:
    """A validated completion. There is no field here a level could occupy."""

    slot_updates: Mapping[str, SlotValue]
    candidate_flags: tuple[CandidateFlag, ...]
    clarification_needed: bool
    confidence: Decimal
    unbound: tuple[str, ...]

    def candidate_triage(self) -> LlmCandidateTriage | None:
        """The most this output can ever amount to: ``YELLOW_REVIEW``."""
        if not self.candidate_flags:
            return None
        return LlmCandidateTriage(candidate_flags=self.candidate_flags)

    def inline_numerics(self) -> dict[str, str]:
        """Every numeric slot value, rendered the one permitted way.

        CLAUDE.md invariant 22 / files/03 §4.6 invariant 30: no numeric slot
        value is spoken without a matching ``inline`` render on the same
        ``work_id``. This is the render; the pairing is enforced by the
        ``Presentation`` validator in the voice runtime, where both halves
        are fields of one object.

        Booleans are excluded explicitly — ``True`` is an ``int`` in Python,
        and "1" on a dose card is exactly the kind of number this invariant
        exists to stop.
        """
        rendered: dict[str, str] = {}
        for ref, value in self.slot_updates.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, int | Decimal):
                rendered[ref] = render_quantity(value)
        return rendered


def _refuse(message: str) -> SchemaViolation:
    return SchemaViolation(message)


def _check_top_level(document: Mapping[str, Any]) -> None:
    unknown = sorted(set(document) - TOP_LEVEL_KEYS)
    if unknown:
        offending = sorted(key for key in unknown if key.casefold() in LEVEL_SHAPED_KEYS)
        if offending:
            raise TriageAssertionRefused(
                f"completion carries key(s) {offending}, which name a triage level or a "
                "delivery priority. RED and YELLOW come from packages/protocols/triage "
                "alone and an extraction may reach candidate_flags at most (CLAUDE.md "
                "invariant 1; ADR-004). The completion is refused whole, not stripped."
            )
        raise _refuse(
            f"completion carries key(s) {unknown} the slot schema does not declare; the "
            "key set is closed so an answer to a different question is refused rather "
            "than partially used"
        )
    missing = sorted(TOP_LEVEL_KEYS - set(document))
    if missing:
        raise _refuse(f"completion is missing required key(s) {missing}")


def _coerce_slot_value(spec: SlotSpec, value: Any, members: frozenset[str] | None) -> SlotValue:
    match spec.value_type:
        case SlotValueType.BOOLEAN:
            if not isinstance(value, bool):
                raise _refuse(f"slot {spec.ref!r} takes a JSON boolean")
            return value
        case SlotValueType.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                raise _refuse(f"slot {spec.ref!r} takes a JSON integer")
            return value
        case SlotValueType.STRING:
            if not isinstance(value, str) or not value or len(value) > MAX_FREE_TEXT_CHARS:
                raise _refuse(f"slot {spec.ref!r} takes a non-empty string within bounds")
            return value
        case SlotValueType.DATE | SlotValueType.DURATION:
            if not isinstance(value, str) or not value:
                raise _refuse(f"slot {spec.ref!r} takes a non-empty ISO-8601 string")
            return value
        case SlotValueType.CODE:
            if not isinstance(value, str) or not value:
                raise _refuse(f"slot {spec.ref!r} takes a code string")
            if members is not None and value not in members:
                raise _refuse(f"slot {spec.ref!r} takes a code from its valueset")
            return value
        case _:
            # decimal and quantity: the magnitude, as an exact decimal string
            if not isinstance(value, str):
                raise _refuse(
                    f"slot {spec.ref!r} takes its magnitude as a decimal STRING — no "
                    "float crosses this boundary (CLAUDE.md invariant 22)"
                )
            try:
                return Decimal(value)
            except InvalidOperation:
                raise _refuse(f"slot {spec.ref!r} is not an exact decimal") from None


def _members_of(schema: SlotSchema, spec: SlotSpec) -> frozenset[str] | None:
    properties = schema.json_schema["properties"]["slot_updates"]["properties"]
    enum_members = properties[spec.ref].get("enum")
    return frozenset(enum_members) if enum_members is not None else None


def _parse_slot_updates(
    raw: Any, schema: SlotSchema
) -> tuple[dict[str, SlotValue], tuple[str, ...]]:
    if not isinstance(raw, dict):
        raise _refuse("'slot_updates' must be a JSON object")
    unknown = sorted(set(raw) - set(schema.refs))
    if unknown:
        raise _refuse(f"'slot_updates' names slot(s) {unknown} the step's schema does not declare")
    bound: dict[str, SlotValue] = {}
    unbound: list[str] = []
    for ref, value in raw.items():
        spec = schema.spec_for(ref)
        if spec is None:  # pragma: no cover - the unknown check above covers it
            raise _refuse(f"slot {ref!r} is not on this schema")
        if ref in schema.unbound_valueset_refs:
            # nothing can validate this code, so nothing binds it
            unbound.append(ref)
            continue
        bound[ref] = _coerce_slot_value(spec, value, _members_of(schema, spec))
    return bound, tuple(sorted(unbound))


def _parse_candidate_flags(raw: Any) -> tuple[CandidateFlag, ...]:
    if not isinstance(raw, list):
        raise _refuse("'candidate_flags' must be a JSON array")
    flags: list[CandidateFlag] = []
    for item in raw:
        if not isinstance(item, dict) or sorted(item) != ["evidence", "text"]:
            raise _refuse(
                "each candidate flag carries exactly {text, evidence}; a flag with no "
                "evidence is an assertion, and an extraction may not assert"
            )
        text, evidence = item["text"], item["evidence"]
        if not isinstance(text, str) or not text or not isinstance(evidence, str) or not evidence:
            raise _refuse("a candidate flag's text and evidence are non-empty strings")
        flags.append(CandidateFlag(text=text, evidence=evidence))
    return tuple(flags)


def parse_extraction(raw: str | Mapping[str, Any], schema: SlotSchema) -> ExtractionOutput:
    """Validate one completion against ``schema``, or refuse it whole."""
    if isinstance(raw, str):
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise _refuse(f"completion is not JSON ({exc.msg})") from None
    else:
        document = dict(raw)
    if not isinstance(document, dict):
        raise _refuse("completion is not a JSON object")

    _check_top_level(document)
    slot_updates, unbound = _parse_slot_updates(document["slot_updates"], schema)
    flags = _parse_candidate_flags(document["candidate_flags"])

    clarification = document["clarification_needed"]
    if not isinstance(clarification, bool):
        raise _refuse("'clarification_needed' must be a JSON boolean")

    confidence_raw = document["confidence"]
    if not isinstance(confidence_raw, str):
        raise _refuse("'confidence' is an exact decimal string, never a float")
    try:
        confidence = Decimal(confidence_raw)
    except InvalidOperation:
        raise _refuse("'confidence' is not an exact decimal") from None
    if not Decimal(0) <= confidence <= Decimal(1):
        raise _refuse("'confidence' is outside [0, 1]")

    return ExtractionOutput(
        slot_updates=slot_updates,
        candidate_flags=flags,
        clarification_needed=clarification,
        confidence=confidence,
        unbound=unbound,
    )


#: The refusals that are worth a ``security.injection_suspected`` signal
#: (files/10 §5; docs/security/threat-model.md row ``llm-boundary``). Both mean
#: something tried to act outside the data boundary: a fenced block that
#: already carried the fence marker, or a completion that answered with a level
#: instead of with slots.
INJECTION_SIGNAL_REFUSALS: Final = (TriageAssertionRefused, DelimiterCollisionError)


def is_injection_signal(error: BaseException) -> bool:
    """Whether ``error`` is worth raising the suspicion signal.

    A **suspicion**, never a determination: a model can add a stray key
    without anybody having attacked it, and the signal is there to be counted
    and looked at, not to accuse. Emitting the ``SecurityV1`` event itself
    belongs to the service that owns the SIEM writer, not to this boundary —
    this function is the classification, so that two callers cannot disagree
    about what counts.
    """
    return isinstance(error, INJECTION_SIGNAL_REFUSALS)


@dataclass(frozen=True)
class ExtractionRun:
    """The delivery receipt for one Extraction Work (files/03 §4.3)."""

    outcome: SpanOutcome
    span: LlmSpan
    span_payload: Mapping[str, str | int]
    schema_id: str
    output: ExtractionOutput | None = None
    completion: LlmCompletion | None = None
    refusal: str | None = None
    injection_suspected: bool = False


@dataclass(frozen=True)
class ExtractionWork:
    """Runs one extraction: fence, call, validate, trace.

    ``deidentifier`` is required only for a ``dev``-tier gateway, which is the
    mock/dev path of invariant 19 and the only tier on which a transcript
    would leave our own infrastructure. On the PHI path the model is
    self-hosted in-country (00_STATE D11), so the transcript is not
    de-identified before it is read — de-identifying it there would corrupt
    the clinical content the extraction exists to read, and there is no third
    party to protect it from. Nothing derived from it reaches the trace store
    either way: :mod:`intake_platform.llm.trace` has no content carrier.
    """

    gateway: LlmGateway
    sink: SpanSink
    deidentifier: Deidentifier | None = None

    def run(
        self,
        *,
        work_id: str,
        session_id_hash: str,
        tenant_id: str,
        transcript_tr: str,
        schema: SlotSchema,
        protocol_hash: str,
        nonce: str | None = None,
    ) -> ExtractionRun:
        text = self._material(transcript_tr)
        prompt = build_extraction_prompt(schema=schema, transcript_tr=text, nonce=nonce)

        completion = self.gateway.complete(prompt, schema)

        output: ExtractionOutput | None = None
        refusal: str | None = None
        suspected = False
        outcome = SpanOutcome.OK
        try:
            output = parse_extraction(completion.text, schema)
        except SchemaViolation as err:
            outcome = SpanOutcome.SCHEMA_INVALID
            refusal = str(err)
            suspected = is_injection_signal(err)

        span = extraction_span(
            work_id=work_id,
            session_id_hash=session_id_hash,
            tenant_id=tenant_id,
            prompt_version=prompt.prompt_version,
            protocol_hash=protocol_hash,
            model_id=completion.model_id,
            model_revision=completion.model_revision,
            schema_id=schema.schema_id,
            outcome=outcome,
            latency_ms=completion.latency_ms,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            input_chars=sum(len(block.text) for block in prompt.blocks),
            output_chars=len(completion.text),
            candidate_flag_count=len(output.candidate_flags) if output else 0,
        )
        payload = emit_extraction_span(span, self.sink)
        return ExtractionRun(
            outcome=outcome,
            span=span,
            span_payload=payload,
            schema_id=schema.schema_id,
            output=output,
            completion=completion,
            refusal=refusal,
            injection_suspected=suspected,
        )

    def _material(self, transcript_tr: str) -> str:
        if self.gateway.tier is not GatewayTier.DEV:
            return transcript_tr
        if self.deidentifier is None:
            raise DeidentificationRequired(
                "a dev/mock-tier gateway is the only tier on which a transcript leaves "
                "our own infrastructure, so it requires INT-015's "
                "Deidentifier.deidentify_for_egress — which itself fails closed without "
                "the names/addresses NER tier. Refusing (invariant 19, KVKK-9)."
            )
        return self.deidentifier.deidentify_for_egress(transcript_tr)
