"""The adjudication rule: asymmetric, deterministic, and unable to clear anything.

ADR-036, from the two challenger reviews. A verdict is a pure function of the
round's readings and the engine's slot views — no clock, no randomness, no
member order — and it can express exactly three actions, none of which binds,
clears, skips or reorders:

``REASK_POSITIVE``
    A red-flag slot the patient answered **absent** in a direct, scripted
    answer, while *any single* draw reads the transcript as present, hedged,
    intermittent, double-negated, qualified or does-not-know. The positive
    question is asked again, verbatim from the slot's own ``ask_tr``; the
    direct answer is not overwritten, the field is CONTESTED and the worst
    case stands for the clinician (medical review §1, §6, §9).

``CONFIRM_BACK``
    A numeric slot whose bound value any draw contradicts — a different
    number, an absent or unsure reading. The slot's own ``confirm_tr`` is
    spoken (D13's scripted confirm-back), and the value stays as bound.

``CANDIDATE_FLAG``
    A red-flag slot with arming narrative evidence the engine will *not* ask
    about: its gate is closed or it is already a gap. The flag is add-only and
    clinician-facing (``LlmCandidateTriage`` caps it at YELLOW_REVIEW), and its
    text is a code, not model prose (medical review §11).

**What is not an action.** A majority reading *absent* clears nothing: there is
no action that could. A narrative reading on a step not yet asked whose gate
is open does nothing to the agenda — the step is asked in its authored place
anyway, and asking it early would be the reorder both reviews removed. The
evidence is recorded (``narrative_refs``) for the note's provenance.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import CandidateFlag
from protocols.triage.context import canonical_scalar

from intake_voice_runtime.clinical_agent.council.orchestrator import (
    MemberOutcome,
    VerificationRound,
)
from intake_voice_runtime.clinical_agent.council.readings import (
    ARMING_READINGS,
    MemberReading,
    Reading,
)
from intake_voice_runtime.clinical_agent.council.scope import VerifierScope
from intake_voice_runtime.clinical_agent.fsm import IntakeEngine

__all__ = [
    "ActionKind",
    "Agreement",
    "ContestedField",
    "SlotView",
    "Verdict",
    "VerifierAction",
    "adjudicate",
    "views_of",
]

#: Readings that contradict a bound number even when they carry none.
_NUMERIC_DOUBT: frozenset[Reading] = frozenset(
    {
        Reading.ABSENT,
        Reading.HEDGED,
        Reading.DOUBLE_NEGATION,
        Reading.QUALIFIED_NEGATIVE,
        Reading.DOES_NOT_KNOW,
    }
)


class ActionKind(enum.StrEnum):
    REASK_POSITIVE = "reask_positive"
    CONFIRM_BACK = "confirm_back"
    CANDIDATE_FLAG = "candidate_flag"


class Agreement(enum.StrEnum):
    """A member's relation to the primary extraction, for the agreement metric."""

    AGREE = "agree"
    DISAGREE = "disagree"
    ABSTAIN = "abstain"


@dataclass(frozen=True, slots=True)
class SlotView:
    """The engine's view of one verifiable slot, read once before convening."""

    ref: str
    state: AnswerState
    value: JsonValue
    revision: int
    gate_open: bool


@dataclass(frozen=True, slots=True)
class VerifierAction:
    kind: ActionKind
    ref: str
    expected_revision: int
    members: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContestedField:
    """A direct answer and the readings that contradict it, both attributed."""

    ref: str
    direct_state: AnswerState
    direct_value: JsonValue
    readings: tuple[tuple[str, Reading, str | None], ...]


@dataclass(frozen=True, slots=True)
class Verdict:
    actions: tuple[VerifierAction, ...]
    contested: tuple[ContestedField, ...]
    narrative_refs: tuple[str, ...]
    agreement: tuple[tuple[str, Agreement], ...]

    @property
    def candidate_flags(self) -> tuple[CandidateFlag, ...]:
        """Add-only, coded, clinician-facing. No model text reaches them."""
        return tuple(
            CandidateFlag(
                text=f"council.narrative_evidence:{action.ref}",
                evidence=f"members:{','.join(action.members)}",
            )
            for action in self.actions
            if action.kind is ActionKind.CANDIDATE_FLAG
        )


def views_of(engine: IntakeEngine, scope: VerifierScope) -> dict[str, SlotView]:
    """Read every verifiable slot's view. Called under the engine lock."""
    return {
        ref: SlotView(
            ref=ref,
            state=engine.state_of(ref),
            value=engine.value_of(ref),
            revision=engine.slot_revision(ref),
            gate_open=engine.gate_open(ref),
        )
        for ref in scope.ordered
    }


def _as_decimal(value: JsonValue) -> Decimal | None:
    scalar = canonical_scalar(value)
    return scalar if isinstance(scalar, Decimal) and not isinstance(scalar, bool) else None


def _contradicts_number(reading: MemberReading, bound: Decimal | None) -> bool:
    if reading.reading in _NUMERIC_DOUBT:
        return True
    if reading.number is None:
        return False
    if bound is None:
        return True  # a number we cannot compare is confirmed, never trusted
    try:
        return Decimal(reading.number) != bound
    except InvalidOperation:
        return True


def adjudicate(
    round_: VerificationRound, views: Mapping[str, SlotView], scope: VerifierScope
) -> Verdict:
    """The verdict. Pure: the same round and views give the same verdict."""
    actions: list[VerifierAction] = []
    contested: list[ContestedField] = []
    narrative: list[str] = []
    by_ref: dict[str, list[tuple[str, MemberReading]]] = {}
    for member_id, reading in round_.readings:
        by_ref.setdefault(reading.ref, []).append((member_id, reading))
    for ref in scope.ordered:
        view = views.get(ref)
        readings = by_ref.get(ref, [])
        if view is None or not readings:
            continue
        info = scope.refs[ref]
        triggered: tuple[str, ...] = ()
        kind: ActionKind | None = None
        if info.red_flag:
            triggered = _members(m for m, r in readings if r.reading in ARMING_READINGS)
            if triggered and view.state is AnswerState.ASKED_ABSENT:
                kind = ActionKind.REASK_POSITIVE
            elif triggered and view.state is AnswerState.NOT_ASKED and view.gate_open:
                narrative.append(ref)
            elif triggered and view.state in (
                AnswerState.NOT_ASKED,
                AnswerState.UNCLEAR,
                AnswerState.DECLINED,
            ):
                kind = ActionKind.CANDIDATE_FLAG
        if kind is None and info.numeric and view.state is AnswerState.ASKED_PRESENT:
            bound = _as_decimal(view.value)
            triggered = _members(m for m, r in readings if _contradicts_number(r, bound))
            if triggered:
                kind = ActionKind.CONFIRM_BACK
        if kind is None:
            continue
        actions.append(
            VerifierAction(kind=kind, ref=ref, expected_revision=view.revision, members=triggered)
        )
        if kind is not ActionKind.CANDIDATE_FLAG:
            contested.append(
                ContestedField(
                    ref=ref,
                    direct_state=view.state,
                    direct_value=view.value,
                    readings=tuple(
                        sorted((m, r.reading, r.number) for m, r in readings if m in set(triggered))
                    ),
                )
            )
    return Verdict(
        actions=tuple(actions),
        contested=tuple(contested),
        narrative_refs=tuple(narrative),
        agreement=_agreement(round_, actions),
    )


def _members(ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(ids)))


def _agreement(
    round_: VerificationRound, actions: list[VerifierAction]
) -> tuple[tuple[str, Agreement], ...]:
    disagreeing = {member for action in actions for member in action.members}
    answered: dict[str, bool] = {}
    for result in round_.results:
        answered[result.member_id] = answered.get(result.member_id, False) or (
            result.outcome is MemberOutcome.OK
        )
    rows: list[tuple[str, Agreement]] = []
    for member_id in sorted(answered):
        if not answered[member_id]:
            rows.append((member_id, Agreement.ABSTAIN))
        elif member_id in disagreeing:
            rows.append((member_id, Agreement.DISAGREE))
        else:
            rows.append((member_id, Agreement.AGREE))
    return tuple(rows)
