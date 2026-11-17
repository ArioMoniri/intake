"""Every proposal is an event, and every field says where its value came from.

Two products, kept apart because they have different readers:

**The event log** (:class:`VerifierEvent`) is the AI/ML review's *"every
proposal is logged as an event"*. It is PHI-free by construction: each field
is a sequence number, a closed enumeration or an id. A reading is logged as
``(member, slot, reading)`` — never the quote, never the number — so the log
can go anywhere an operational log goes (CLAUDE.md invariant 6).

**The field records** (:class:`FieldRecord`) are what the clinician's note
renders: one record per slot with its provenance — direct, narrative,
document, contested, or *Sorulmadı* — and the attributed values. They carry
clinical values and are never logged. They carry **no confidence**: the type
has no field for one (medical review §11), and a negative appears only as a
direct answer (``ASKED_ABSENT``), never from narrative.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import CandidateFlag, LlmCandidateTriage

from intake_voice_runtime.clinical_agent.council.adjudicate import ContestedField, Verdict
from intake_voice_runtime.clinical_agent.council.orchestrator import (
    MemberOutcome,
    VerificationRound,
)
from intake_voice_runtime.clinical_agent.council.readings import Reading
from intake_voice_runtime.clinical_agent.council.scope import VerifierScope
from intake_voice_runtime.clinical_agent.fsm import IntakeEngine

__all__ = [
    "AttributedValue",
    "EventKind",
    "FieldRecord",
    "Provenance",
    "VerifierEvent",
    "VerifierLedger",
]

_ASKED_STATES = frozenset(
    {
        AnswerState.ASKED_PRESENT,
        AnswerState.ASKED_ABSENT,
        AnswerState.UNCLEAR,
        AnswerState.DECLINED,
    }
)


class Provenance(enum.StrEnum):
    """Where a field's value came from (medical review §11)."""

    DIRECT = "direct"
    NARRATIVE = "narrative"
    DOCUMENT = "document"
    CONTESTED = "contested"
    NOT_ASKED = "sorulmadi"


class EventKind(enum.StrEnum):
    READING = "reading"
    DRAW_WITHOUT_READING = "draw_without_reading"
    ACTION = "action"
    REFUSED_TEXT_ONLY = "refused_text_only"
    REFUSED_BUDGET = "refused_budget"
    SHED_SATURATED = "shed_saturated"
    EVICTED = "evicted"
    LATE_ADDENDUM = "late_addendum"
    TRIAGE_RERUN = "triage_rerun"


@dataclass(frozen=True, slots=True)
class VerifierEvent:
    """One event. Ids and closed codes only."""

    seq: int
    kind: EventKind
    ref: str | None = None
    member_id: str | None = None
    reading: Reading | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class AttributedValue:
    provenance: Provenance
    value: JsonValue
    member_id: str | None = None


@dataclass(frozen=True, slots=True)
class FieldRecord:
    """What the note renders for one slot. There is no confidence field."""

    ref: str
    provenance: Provenance
    state: AnswerState
    values: tuple[AttributedValue, ...]


@dataclass
class VerifierLedger:
    """One session's verifier history: events, open contests, narrative evidence."""

    events: list[VerifierEvent] = field(default_factory=list)
    _contested: dict[str, tuple[ContestedField, int]] = field(default_factory=dict, repr=False)
    _narrative: set[str] = field(default_factory=set, repr=False)
    _flags: list[CandidateFlag] = field(default_factory=list, repr=False)

    def log(
        self,
        kind: EventKind,
        *,
        ref: str | None = None,
        member_id: str | None = None,
        reading: Reading | None = None,
        code: str | None = None,
    ) -> None:
        self.events.append(
            VerifierEvent(
                seq=len(self.events),
                kind=kind,
                ref=ref,
                member_id=member_id,
                reading=reading,
                code=code,
            )
        )

    def log_round(self, round_: VerificationRound) -> None:
        for result in round_.results:
            if result.outcome is not MemberOutcome.OK or not result.readings:
                self.log(
                    EventKind.DRAW_WITHOUT_READING,
                    member_id=result.member_id,
                    code=result.outcome.value,
                )
                continue
            for reading in result.readings:
                self.log(
                    EventKind.READING,
                    ref=reading.ref,
                    member_id=result.member_id,
                    reading=reading.reading,
                )

    def record_verdict(self, verdict: Verdict, *, stale: frozenset[str]) -> None:
        """Open a contest for each contested field whose verdict was not stale."""
        for contested in verdict.contested:
            if contested.ref in stale:
                continue
            action = next(a for a in verdict.actions if a.ref == contested.ref)
            self._contested[contested.ref] = (contested, action.expected_revision)
        self._narrative.update(verdict.narrative_refs)

    def add_candidate_flags(self, flags: tuple[CandidateFlag, ...]) -> None:
        """Add-only: a flag is never withdrawn, replaced or downgraded here."""
        for flag in flags:
            if flag not in self._flags:
                self._flags.append(flag)

    def llm_candidates(self) -> LlmCandidateTriage | None:
        """The session's flags as the one triage shape an LLM may produce.

        ``LlmCandidateTriage`` can spell exactly ``YELLOW_REVIEW`` (CLAUDE.md
        invariant 1); ``None`` when nothing was flagged, never an empty level.
        """
        if not self._flags:
            return None
        return LlmCandidateTriage(candidate_flags=tuple(self._flags))

    def open_contests(self, engine: IntakeEngine) -> tuple[ContestedField, ...]:
        """Contests the patient has not yet settled with a fresh direct answer."""
        return tuple(
            contested
            for ref, (contested, revision) in sorted(self._contested.items())
            if engine.slot_revision(ref) == revision
        )

    def field_records(self, engine: IntakeEngine, scope: VerifierScope) -> tuple[FieldRecord, ...]:
        """One record per slot of the pack, in ref order."""
        contests = {contested.ref: contested for contested in self.open_contests(engine)}
        records: list[FieldRecord] = []
        for ref in sorted({*scope.refs, *scope.excluded}):
            state = engine.state_of(ref)
            contest = contests.get(ref)
            if contest is not None:
                values = (
                    AttributedValue(Provenance.DIRECT, contest.direct_value),
                    *(
                        AttributedValue(Provenance.NARRATIVE, number, member_id)
                        for member_id, _, number in contest.readings
                    ),
                )
                records.append(FieldRecord(ref, Provenance.CONTESTED, state, values))
            elif state in _ASKED_STATES:
                direct = (AttributedValue(Provenance.DIRECT, engine.value_of(ref)),)
                records.append(FieldRecord(ref, Provenance.DIRECT, state, direct))
            elif ref in self._narrative:
                records.append(FieldRecord(ref, Provenance.NARRATIVE, state, ()))
            else:
                records.append(FieldRecord(ref, Provenance.NOT_ASKED, state, ()))
        return tuple(records)
