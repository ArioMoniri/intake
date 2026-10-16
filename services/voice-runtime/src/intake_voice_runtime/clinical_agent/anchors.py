"""CD-05 at runtime: a closed onset choice binds its day, and the record keeps both (INT-522).

``chest_pain.onset_at`` — the tense anchor of ``rf.chest_pain_cardiac_features``
(KIRMIZI_K2) and its SARI sibling — is a ``date`` slot the patient answers with
one of four closed choices. Before INT-522 the extraction schema offered the
model a ``format: date`` field with no reference date and told it not to
infer one, so a spoken choice bound nothing, the anchor read Unknown and the
rule could not fire from a conversation (GitHub #888).

:class:`SessionAnchors` is one session's binding of
:class:`protocols.anchor_choices.AnchorChoiceTable` (CD-05, read through the
clinical-decisions register):

- **The model picks the choice; the runtime computes the day.** The handler
  hands :meth:`SessionAnchors.resolve_choices` the extraction's updates; each
  anchor's value — an authored choice, the only thing the schema let the model
  answer — is replaced by the day CD-05 resolves it to, against the session's
  ``reference_time``: the engine's, stamped once at composition (files/13
  §9.2), the very time the tense windows compare against. No clock is read
  here, and no day ever comes from the model (invariant 14: speech is data).
- **An answer that never fits a choice resolves to the reference day.** The
  engine records UNCLEAR once its bounded clarification is spent (files/13
  §11.1); CD-05 ``unresolved_answer`` resolves that to the more acute reading,
  and :meth:`SessionAnchors.unclear_readings` is how the rules engine's context
  reads it. Only CD-05's own anchors resolve this way: any other UNCLEAR slot
  reads Unknown (files/12 §1.1). A hedged answer that is still being clarified
  binds nothing and reads Unknown, so the rule's Unknown branch holds.
- **The record** (:attr:`SessionAnchors.record`) keeps, per anchor, the
  patient's choice beside the resolved day and the basis — CD-05's decided
  band, the twelve-to-seventy-two-hour band's ``while_draft_resolution``, or
  the unresolved answer — so a reader can always tell a resolution that is
  still draft from a decided one.

**An unfit answer is UNCLEAR at once, and the anchor cannot outlive the
session** (INT-540, the INT-522 review's F1 and F2). CD-04 decides that a
hedged answer — its table, read here as
:class:`protocols.answer_states.AnswerStateTable` — is UNCLEAR, reads Unknown
and triggers the slot's ``follow_up_tr`` once. :meth:`SessionAnchors.unclear_cause`
is how the extraction handler asks, for an asked anchor, whether this answer
is such a one: a CD-04 hedge (which beats a choice the model guessed), or no
authored choice recorded at all — a narrative, a refused value, a completion
with no slot and no flag (CD-04: an unmatched hedge is UNCLEAR; CD-05: an
answer fitting no choice). :meth:`SessionAnchors.follow_up_bounds` hands the
engine CD-04's number for each anchor, so the follow-up is asked that many
times and then the engine records UNCLEAR, which CD-05 resolves. When the
session closes with an anchor still asked and unanswered, the close records
it UNCLEAR too (:mod:`intake_voice_runtime.clinical_agent.session_close`).
:attr:`SessionAnchors.unclear` keeps each such reading and its cause — ids and
CD-04 qualifiers, never the patient's words.

**The bound is per cause, and the close reaches every anchor** (INT-546,
applying INT-519's CD-04 round 3 and CD-05 round 3):

- :meth:`SessionAnchors.follow_up_bound` is CD-04's
  ``tense_anchor_follow_up_tr_asks`` for the cause — none for a hedge, one for
  an answer that binds no choice — and :meth:`SessionAnchors.follow_up_bounds`
  hands the engine the larger as the anchor's ceiling. A hedge therefore
  resolves on the Work that read it.
- A hedge beside an authored choice keeps that choice on the reading
  (``hedged_choice``) and on the record, never bound (CD-04 round 3 item 8).
- The record of an unresolved anchor carries CD-05's label for its cause.
- An anchor never asked when the session closes, while its gate —
  ``chest_pain.present == true`` — is open, is read once as CD-05's
  ``never_asked_at_close`` day (:meth:`SessionAnchors.close_never_asked`); the
  slot stays NOT_ASKED and nothing binds.
- Every anchor left unresolved — its cause's bound spent, ``session_closed``,
  or ``never_asked_at_close`` — is handed once to
  :class:`AnchorUnresolvedHook`, where the CD-08 ``chest_pain_arms_unresolved``
  clinic-inbox item plugs in (INT-547 builds the item). The trigger is kept on
  :attr:`SessionAnchors.unresolved_triggers` whether or not a hook is wired.

Nothing here produces a triage level (invariant 1): it dates an anchor; the
rules engine alone decides whether the date and the gate fire a rule.
"""

from __future__ import annotations

import enum
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from protocols.anchor_choices import AnchorChoiceError, AnchorChoiceTable, AnchorResolution
from protocols.answer_states import AnswerStateError, AnswerStateTable, HedgeState, InboxItemRef

from intake_voice_runtime.clinical_agent.fsm import IntakeEngine

__all__ = [
    "AnchorUnresolved",
    "AnchorUnresolvedHook",
    "SessionAnchors",
    "UnclearAnswer",
    "UnclearCause",
]


class UnclearCause(enum.StrEnum):
    """Why an asked anchor was read UNCLEAR (INT-540)."""

    #: A CD-04 table entry read UNCLEAR on the anchor.
    HEDGE = "hedge"
    #: No authored choice was recorded: CD-04's unmatched hedge, CD-05's
    #: answer fitting no choice.
    NO_CHOICE = "no_choice"
    #: The session closed with the anchor asked and unanswered.
    SESSION_CLOSED = "session_closed"


@dataclass(frozen=True, repr=False)
class UnclearAnswer:
    """One UNCLEAR reading of an asked anchor, in the order it was read."""

    anchor: str
    cause: UnclearCause
    #: The CD-04 entry's qualifier, for a hedge; otherwise ``None``.
    qualifier: str | None
    decision_id: str
    #: The authored choice a hedge leaned to — kept, never bound (INT-546).
    hedged_choice: str | None = None

    def __repr__(self) -> str:
        return (
            f"UnclearAnswer(anchor={self.anchor!r}, cause={self.cause.value!r}, "
            f"decision_id={self.decision_id!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class AnchorUnresolved:
    """One anchor left unresolved, as the CD-08 clinic-inbox item needs it (INT-546).

    Ids and labels only (invariant 6): the anchor's step id, CD-05's label for
    why it is unresolved, the item kind and the decisions behind it, as the
    decisions name them (CD-04 ``unresolved_after_follow_up``, CD-05
    ``never_asked_at_close.inbox_item``).
    """

    anchor: str
    label: str
    kind: str
    decision_ids: tuple[str, ...]


class AnchorUnresolvedHook(Protocol):
    """Where an unresolved anchor's CD-08 ``chest_pain_arms_unresolved`` item is raised.

    The item itself — its inbox entry, audit row and once-per-session id — is
    INT-547's; this hook is the one place it plugs in. It is called on the
    Backend lane under the engine lock and must not block (invariant 9).
    """

    def anchor_unresolved(self, trigger: AnchorUnresolved) -> None: ...


@dataclass
class SessionAnchors:
    """One session's CD-05 and CD-04 tables, and the record of each anchor."""

    table: AnchorChoiceTable
    #: CD-04 (INT-540): which answers are UNCLEAR, and the follow-up bounds.
    answer_states: AnswerStateTable
    #: INT-546: where an unresolved anchor's CD-08 item is raised, if wired.
    hook: AnchorUnresolvedHook | None = None
    #: ``{anchor step id: its latest resolution}`` — the choice beside the day.
    record: dict[str, AnchorResolution] = field(default_factory=dict, init=False)
    #: Every UNCLEAR reading of an anchor, in order (INT-540).
    unclear: list[UnclearAnswer] = field(default_factory=list, init=False)
    #: Every unresolved anchor handed to the hook, in order, once each (INT-546).
    unresolved_triggers: list[AnchorUnresolved] = field(default_factory=list, init=False)
    #: Anchors the close found never asked with their gate open (CD-05 item 10).
    never_asked: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        """A tense anchor is a date: CD-04 may read it UNCLEAR, never present."""
        named = sorted(self.answer_states.present_qualified_slots & self.refs)
        if named:
            raise AnswerStateError(
                f"{self.answer_states.decision_id} gives a present-qualified reading to "
                f"the tense anchor(s) {', '.join(named)}, which a date cannot carry"
            )

    @property
    def refs(self) -> frozenset[str]:
        """The step ids CD-05 resolves: its active anchors."""
        return self.table.anchors

    def follow_up_bound(self, cause: UnclearCause) -> int:
        """CD-04 round 3: the follow-up asks an anchor gets for this cause."""
        return self.answer_states.tense_anchor_follow_up_tr_asks[cause.value]

    def follow_up_bounds(self, steps: Collection[str]) -> dict[str, int]:
        """The engine's ceiling for each anchor among ``steps``: the larger cause bound."""
        asks = max(self.answer_states.tense_anchor_follow_up_tr_asks.values())
        return {ref: asks for ref in sorted(self.refs.intersection(steps))}

    def unclear_cause(
        self, anchor: str, text: str, choice: JsonValue | None
    ) -> UnclearCause | None:
        """Why this answer to the asked ``anchor`` is UNCLEAR, or ``None``.

        ``choice`` is the authored choice the extraction bound, or ``None``. A
        CD-04 hedge is UNCLEAR whatever the model chose, and the choice it
        leaned to is kept as ``hedged_choice``; with no hedge, an answer that
        bound no choice is UNCLEAR too. The reading is recorded.
        """
        reading = self.answer_states.read(anchor, text)
        if reading is not None and reading.state is HedgeState.UNCLEAR:
            leaned = choice if isinstance(choice, str) else None
            self.unclear.append(
                UnclearAnswer(
                    anchor, UnclearCause.HEDGE, reading.qualifier, reading.decision_id, leaned
                )
            )
            return UnclearCause.HEDGE
        if choice is not None:
            return None
        self.note_unclear(anchor, UnclearCause.NO_CHOICE)
        return UnclearCause.NO_CHOICE

    def note_unclear(self, anchor: str, cause: UnclearCause) -> None:
        """Record an UNCLEAR reading CD-05 decides the resolution of."""
        self.unclear.append(UnclearAnswer(anchor, cause, None, self.table.decision_id))

    def settle(self, engine: IntakeEngine, anchor: str) -> None:
        """Hand the anchor to the hook once the engine holds it UNCLEAR.

        CD-04 ``anchor_trigger``: the item is raised when the cause's bound is
        spent — at once for a hedge — and for an anchor the close records
        UNCLEAR. An anchor still being clarified raises nothing yet.
        """
        if engine.state_of(anchor) is not AnswerState.UNCLEAR:
            return
        cause = self._last_cause(anchor)
        if cause is not None:
            self._raise(
                anchor,
                self.table.unresolved_labels[cause.value],
                self.answer_states.unresolved_inbox,
                self.answer_states.decision_id,
            )

    def close_never_asked(self, engine: IntakeEngine, anchor: str) -> None:
        """CD-05 ``never_asked_at_close``: read the never-asked anchor once at close.

        Only an anchor NOT_ASKED whose gate is open — ``chest_pain.present ==
        true``, the condition CD-05 names — is read; nothing is bound and the
        slot stays NOT_ASKED. The rules engine evaluates the close with the
        reading (:meth:`never_asked_readings`), and the item is raised.
        """
        if engine.state_of(anchor) is not AnswerState.NOT_ASKED or not engine.gate_open(anchor):
            return
        self.never_asked.add(anchor)
        resolution = self.table.resolve_never_asked(anchor, engine.reference_time)
        self.record[anchor] = resolution
        self._raise(
            anchor,
            resolution.label or resolution.basis.value,
            self.table.never_asked_inbox,
            self.table.decision_id,
        )

    def resolve_choices(
        self, updates: Mapping[str, JsonValue], reference_time: datetime
    ) -> tuple[dict[str, JsonValue], tuple[AnchorResolution, ...]]:
        """The updates with each anchor's choice replaced by its CD-05 day.

        A value that is not an authored choice raises
        :class:`protocols.anchor_choices.AnchorChoiceError`: the parser admits
        only the slot's choices and composition checked they are CD-05's, so
        reaching it is a defect, and the Work fails rather than binding a guess.
        """
        translated = dict(updates)
        resolutions: list[AnchorResolution] = []
        for ref in sorted(self.refs & translated.keys()):
            choice = translated[ref]
            if not isinstance(choice, str):
                raise AnchorChoiceError(
                    f"{ref}: an anchor's answer is a choice, not a {type(choice).__name__}"
                )
            resolution = self.table.resolve(ref, choice, reference_time)
            translated[ref] = resolution.resolved_on
            resolutions.append(resolution)
        return translated, tuple(resolutions)

    def note_bound(
        self,
        resolutions: tuple[AnchorResolution, ...],
        engine: IntakeEngine,
        revisions: Mapping[str, int],
    ) -> None:
        """Record each resolution the engine actually bound.

        ``revisions`` is each anchor's slot revision before the extraction was
        applied: an anchor the engine did not move (an answer to a question
        nobody asked, say) did not bind, and its choice is not recorded.
        """
        for resolution in resolutions:
            anchor = resolution.anchor
            if (
                engine.slot_revision(anchor) != revisions.get(anchor)
                and engine.state_of(anchor) is AnswerState.ASKED_PRESENT
                and engine.value_of(anchor) == resolution.resolved_on
            ):
                self.record[anchor] = resolution

    def unclear_readings(
        self, engine: IntakeEngine, refs: Collection[str]
    ) -> dict[str, AnchorResolution]:
        """CD-05's resolution for each of ``refs`` the engine holds UNCLEAR.

        Pure: it records nothing (the queue reads it before and after every
        Work). :meth:`note` records the ones an evaluation used. The resolution
        carries the label of the cause that left the anchor UNCLEAR and, for a
        hedge, the choice it leaned to (INT-546).
        """
        readings: dict[str, AnchorResolution] = {}
        for ref in sorted(self.refs.intersection(refs)):
            if engine.state_of(ref) is not AnswerState.UNCLEAR:
                continue
            last = self._last_reading(ref)
            readings[ref] = self.table.resolve_unresolved(
                ref,
                engine.reference_time,
                cause=None if last is None else last.cause.value,
                hedged_choice=None if last is None else last.hedged_choice,
            )
        return readings

    def never_asked_readings(
        self, engine: IntakeEngine, refs: Collection[str]
    ) -> dict[str, AnchorResolution]:
        """CD-05 ``never_asked_at_close`` for each of ``refs`` the close read (pure).

        Only while the anchor is still NOT_ASKED: nothing was bound, and the
        reading is the rules engine's alone.
        """
        return {
            ref: self.table.resolve_never_asked(ref, engine.reference_time)
            for ref in sorted(self.never_asked.intersection(refs))
            if engine.state_of(ref) is AnswerState.NOT_ASKED
        }

    def note(self, resolution: AnchorResolution) -> None:
        """Record one resolution an evaluation read."""
        self.record[resolution.anchor] = resolution

    def _last_reading(self, anchor: str) -> UnclearAnswer | None:
        for reading in reversed(self.unclear):
            if reading.anchor == anchor:
                return reading
        return None

    def _last_cause(self, anchor: str) -> UnclearCause | None:
        last = self._last_reading(anchor)
        return None if last is None else last.cause

    def _raise(self, anchor: str, label: str, item: InboxItemRef, source: str) -> None:
        """Hand one unresolved anchor to the hook — once per anchor."""
        if any(trigger.anchor == anchor for trigger in self.unresolved_triggers):
            return
        trigger = AnchorUnresolved(
            anchor=anchor, label=label, kind=item.kind, decision_ids=(source, item.decision_ref)
        )
        self.unresolved_triggers.append(trigger)
        if self.hook is not None:
            self.hook.anchor_unresolved(trigger)
