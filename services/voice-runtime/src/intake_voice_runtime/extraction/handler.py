"""The ``extract_slots`` state handler — the registration INT-083 owed.

docs/evidence/INT-094.md finding 1(i): *"No module under ``services/``
registers an ``extract_slots`` state handler. INT-092 recorded that the
production handler was INT-083's; INT-083 built ``run_extraction`` and
``ExtractionResult.as_engine_call()`` and registered nothing."* Consequence:
a composed session raised ``UnregisteredWorkType`` on its first transcript,
so there was no turn to smoke-test against real adapters.

This module is the body between the two halves that already existed. It is
deliberately thin — four statements of substance — because everything
interesting is already somewhere better:

1. **take** the transcript from the session's vault by the digest the request
   carries (:mod:`intake_voice_runtime.transcript`). No text ever entered the
   queue, so this is where it re-enters the process, already wrapped as
   :class:`~intake_voice_runtime.extraction.boundary.PatientData`.
2. **run** :func:`~intake_voice_runtime.extraction.work.run_extraction` — the
   schema-constrained call, the nonce-fenced data block, the span and the
   eval row, all INT-083's.
3. **apply** the result through ``engine.apply_extraction(**as_engine_call())``
   — INT-081's reconcile-behind, called under the engine lock the queue is
   already holding.
4. **return** an empty :class:`~intake_voice_runtime.clinical_agent.work_queue.StateEffect`.

Four things this handler deliberately does **not** do:

- **It does not call ``mark_asked``.** files/03 §4.5 marks a step when the
  answer arrives; INT-081's ``mark_asked`` marks it when it is spoken. INT-095
  settled it in favour of *spoken* (see
  :class:`~intake_voice_runtime.ports.AskLedger`), and the way the other
  reading is made impossible is that this module has no call to it: the only
  producer of that engine write is the queue's ask-note pump, fed by the
  Talker's speech path. ``tests/voice/adapters/test_residency_contracts.py``
  asserts both halves — this file contains no ``mark_asked``, and exactly one
  module in the tree does.
- **It speaks nothing.** ``StateEffect.speech_tr`` stays ``None``:
  ``ExtractionResult`` has no ``speech_tr`` field precisely so that files/03
  §4.9.6 invariant 30's numeric-pairing rule cannot be broken from here, and
  inventing a Turkish acknowledgement would be patient copy no human signed
  off.
- **It sets no ``triage_update``.** The rules engine is
  ``packages/protocols/triage``, and the queue runs it after this handler
  returns, whenever the Work bound an answer a served red-flag rule reads
  (:mod:`intake_voice_runtime.clinical_agent.live_triage`, INT-521). So
  ``StateEffect.triage_update`` stays ``None`` here and the determination is
  the rules engine's, never this handler's. CLAUDE.md invariant 1 holds in the
  safe direction: an extraction cannot mint a level at all, and
  ``candidate_flags`` — the only triage-shaped material it produces — are
  clinician-facing and reach the note, never routing.
- **It never widens what the model may answer.** The declared slot set is the
  Work's own step plus whatever the engine currently lists as ``awaiting``
  (ask-ahead, files/03 §4.5), because those are exactly the steps
  ``IntakeEngine._bind`` will accept an answer for. A step outside that set
  could not bind, so offering it to the model would be inviting an answer the
  engine is about to drop.

**A closed onset choice binds its decided day** (INT-522). For a date slot
answered by a closed choice the model may answer only an authored choice; the
handler replaces it with the day CD-05 resolves it to against the engine's
``reference_time`` (:class:`~intake_voice_runtime.clinical_agent.anchors.SessionAnchors`)
before the engine sees it, and records the choice beside the day once it has
bound. A session whose closed-choice date has no decided day for every choice
is refused when composed (:class:`~intake_voice_runtime.extraction.errors.AnchorChoicesUnresolved`).

**An asked anchor answered unfit is UNCLEAR at once** (INT-540). For a Work
answering a tense anchor that is asked and unanswered — its question or its
follow-up — a CD-04 hedge (read from the decision, beating any choice the model
guessed) or an answer that bound no authored choice is UNCLEAR whatever
``clarification_needed`` said: the anchor's choice, if any, is withheld, the
rest of the extraction binds as reported, and the anchor gets the
clarification the model did not ask for. The engine holds CD-04's bound for
the anchor, so that is its ``follow_up_tr`` the first time and UNCLEAR — which
CD-05 resolves to the reference day, and which the queue then evaluates — once
the bound is spent. A no-slot-no-flag completion can no longer leave the
anchor silently pending (the INT-522 clinical review's F1).

**The anchor's bound is its cause's, and a gating slot's hedge binds a choice**
(INT-546, INT-519's D18 decisions). CD-04 round 3 gives a hedge on the anchor
no follow-up and an answer that binds no choice one, so the handler hands the
engine the cause's bound with the answer; a hedge resolves on its own Work,
and the choice it leaned to is kept beside the resolution, never bound. Once
the anchor is UNCLEAR it is handed, once, to the CD-08 hook
(:class:`~intake_voice_runtime.clinical_agent.anchors.AnchorUnresolvedHook`).
On a CD-112 mapped slot (``pmh_fh_sh.immunosuppression``,
``pmh_fh_sh.pregnancy_status``) a CD-04 hedge binds the decided choice at once
— never UNCLEAR, never the negative the model may have read into it — and an
answer that binds no choice asks the slot's follow-up, after which the slot
records the decided choice where CD-112 maps it, or UNCLEAR where it does not
(:mod:`intake_voice_runtime.clinical_agent.answer_mappings`).

**A refusal is an outcome, not a crash.** A parser refusal (the model answered
off-schema, or obeyed a planted instruction) leaves the slots unbound and the
question unanswered — the state files/13 §11.1 already knows how to act on. A
*gateway* refusal (an unconfigured lane, a missing recording, an endpoint that
did not answer) propagates, and the queue turns it into a failed
:class:`~intake_voice_runtime.clinical_agent.work_queue.WorkRecord` carrying
the exception's class name and nothing else.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from clinical_schemas.session import AnswerState
from protocols.answer_mappings import MappedAnswer
from protocols.dsl import Slot

from intake_voice_runtime.adapters.pins import ModelPin
from intake_voice_runtime.clinical_agent.anchors import SessionAnchors
from intake_voice_runtime.clinical_agent.answer_mappings import SessionAnswerMappings
from intake_voice_runtime.clinical_agent.fsm import EngineError
from intake_voice_runtime.clinical_agent.work_queue import StateContext, StateEffect
from intake_voice_runtime.extraction.boundary import PatientData
from intake_voice_runtime.extraction.errors import AnchorChoicesUnresolved, CodeSlotUnbound
from intake_voice_runtime.extraction.gateway import ExtractionGateway
from intake_voice_runtime.extraction.result import ExtractionResult, SlotOutcome
from intake_voice_runtime.extraction.schema import closed_choice_dates, unbound_code_slots
from intake_voice_runtime.extraction.work import ExtractionContext, ExtractionOutcome
from intake_voice_runtime.extraction.work import run_extraction as _run_extraction
from intake_voice_runtime.ports import Clock, WorkRequest, work_key
from intake_voice_runtime.transcript import TranscriptSource

__all__ = ["UNPINNED_REVISION", "ExtractSlotsHandler", "VerificationSink"]

#: What goes on a span when the §4.9.1 row's registry entry carries no
#: structured ``model_id@revision``. Deliberately not hash-shaped: an auditor
#: reading a trace must see a gap, not a value they might try to look up
#: (files/HUMAN_BLOCKERS.md Rule 1).
UNPINNED_REVISION: Final = "unpinned"


class VerificationSink(Protocol):
    """Where an answer goes *after* it has been bound (INT-430; ADR-036).

    One synchronous, non-blocking method. The primary extraction above has
    already applied its result — the binding triage reads — so nothing the
    verifier does, or fails to do, can delay or alter it: RED never waits on
    the council.
    """

    def request_verification(self, request: WorkRequest, data: PatientData) -> None: ...


def _session_id_hash(session_id: str) -> str:
    """The span's session identifier — a digest, never the id (INT-175)."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _UnclearAnchor:
    """An asked anchor this Work answered unfit, and its cause's bound (INT-546)."""

    anchor: str
    bound: int


@dataclass(frozen=True)
class _MappedSlot:
    """An asked CD-112 slot this Work answered: the choice to bind, or ``None``
    to ask its follow-up (INT-546)."""

    slot: str
    answer: MappedAnswer | None


@dataclass
class ExtractSlotsHandler:
    """One session's ``extract_slots`` handler, bound to its collaborators.

    A callable object rather than a closure so the wiring is inspectable: a
    reviewer can see which gateway, which vault and which pin this handler
    would use without reading the composition root's local variables.
    """

    transcripts: TranscriptSource
    gateway: ExtractionGateway
    slots: Mapping[str, Slot]
    pin: ModelPin
    clock: Clock
    tenant_id: str
    valuesets: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: INT-430. ``None`` — the state of every session composed today — means no
    #: verifier runs; the primary extraction is unchanged either way.
    verifier: VerificationSink | None = None
    #: INT-522. CD-05's resolution of each closed-choice date (the onset
    #: anchor); required wherever the slots declare one, so such a choice
    #: always binds a day.
    anchors: SessionAnchors | None = None
    #: INT-546. CD-112's per-slot mappings: a hedge on a gating slot binds the
    #: authored choice, never UNCLEAR. ``None`` where no mapped slot is declared.
    mappings: SessionAnswerMappings | None = None
    outcomes: list[ExtractionOutcome] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        """Refuse a handler that could never bind one of its code slots (INT-518).

        A code slot binds only to a member of its value set. Handed no members,
        every Work that declares it is refused, and because the slot then stays
        awaiting, every later Work declares it too: before INT-518 a session
        bound nothing after its first question. Composition is where that is
        refused, naming each slot and set, before a patient is asked anything.
        """
        unbound = unbound_code_slots(self.slots, self.valuesets)
        if unbound:
            named = ", ".join(f"{ref} ({valueset})" for ref, valueset in unbound)
            raise CodeSlotUnbound(
                f"code slot(s) with no committed value set: {named}. Extraction binds a "
                "code slot only to a member, so these could never be answered; commit "
                "each set in packages/protocols/base/valuesets.yaml (INT-518)"
            )
        unresolved = self._unresolved_dates()
        if unresolved:
            raise AnchorChoicesUnresolved(
                "date slot(s) answered by closed choices with no decided day for every "
                f"choice: {', '.join(unresolved)}. Such a choice could never bind, so the "
                "anchor would read Unknown for the whole session; the resolution is a "
                "clinical decision (CD-05, INT-522), never a default"
            )

    def _unresolved_dates(self) -> list[str]:
        """Each closed-choice date whose choices are not exactly a decided table's."""
        anchors = self.anchors
        return [
            ref
            for ref, choices in closed_choice_dates(self.slots).items()
            if anchors is None or ref not in anchors.refs or anchors.table.choice_texts != choices
        ]

    def __call__(self, context: StateContext) -> StateEffect:
        request = context.request
        data = self.transcripts.take(request.input_hash)
        declared = self._declared_slots(context)
        outcome = _run_extraction(
            ExtractionContext(
                work_id=work_key(request),
                session_id_hash=_session_id_hash(request.session_id),
                tenant_id=self.tenant_id,
                protocol_hash=request.protocol_hash,
                model_id=self.pin.model_id or self.pin.component,
                model_revision=self.pin.revision or UNPINNED_REVISION,
                case_id=f"{request.step_id}@{request.engine_version}",
            ),
            step_id=request.step_id,
            slots=declared,
            valuesets=self.valuesets,
            transcript=data.text,
            gateway=self.gateway,
            now_ms=self.clock.now_ms,
        )
        self.outcomes.append(outcome)
        engine = context.engine
        unclear = self._unclear_anchor(context, outcome.result, data.text)
        mapped = self._mapped_answer(context, outcome.result, data.text)
        clarified = False
        if outcome.result is not None:
            call = outcome.result.as_engine_call()
            updates = dict(call["slot_updates"])
            if unclear is not None:
                updates.pop(unclear.anchor, None)
            if mapped is not None and mapped.answer is not None:
                updates[mapped.slot] = mapped.answer.choice
                call["clarification_needed"] = False
            call["slot_updates"] = updates
            clarified = bool(call["clarification_needed"])
            if clarified and unclear is not None:
                # the model's own flag, held to the anchor's bound for its cause
                engine.clarify(request.step_id, bound=unclear.bound)
            else:
                self._apply(context, call)
        elif mapped is not None and mapped.answer is not None:
            engine.apply_extraction(request.step_id, {mapped.slot: mapped.answer.choice})
        if unclear is not None and not clarified:
            self._clarify(context, unclear.anchor, unclear.bound)
        if mapped is not None:
            self._settle_mapped(context, mapped, clarified)
        if unclear is not None and self.anchors is not None:
            self.anchors.settle(engine, unclear.anchor)
        if self.verifier is not None:
            self.verifier.request_verification(request, data)
        return StateEffect()

    @staticmethod
    def _asked_origin(context: StateContext) -> str | None:
        """The step this Work answers, if it is asked and unanswered; else ``None``."""
        engine = context.engine
        try:
            origin = engine.origin_of(context.request.step_id)
        except EngineError:
            return None
        return origin if engine.state_of(origin) is AnswerState.ASKED_PENDING else None

    def _unclear_anchor(
        self, context: StateContext, result: ExtractionResult | None, text: str
    ) -> _UnclearAnchor | None:
        """The asked tense anchor this Work answered unfit, or ``None`` (INT-540).

        Only a Work answering an anchor that is asked and unanswered — its own
        question or its follow-up. A CD-04 hedge is UNCLEAR even under a
        choice the model guessed (kept as the hedged choice, never bound);
        with none, any answer that bound no authored choice is (a narrative,
        a refused value or document, a completion with no slot and no flag).
        The bound it carries is CD-04's for its cause (INT-546).
        """
        anchors = self.anchors
        origin = self._asked_origin(context)
        if anchors is None or origin is None or origin not in anchors.refs:
            return None
        choice = None
        if result is not None and result.outcome_of(origin) is SlotOutcome.BOUND:
            choice = result.as_engine_call()["slot_updates"][origin]
        cause = anchors.unclear_cause(origin, text, choice)
        if cause is None:
            return None
        return _UnclearAnchor(origin, anchors.follow_up_bound(cause))

    def _mapped_answer(
        self, context: StateContext, result: ExtractionResult | None, text: str
    ) -> _MappedSlot | None:
        """What this Work's answer to an asked CD-112 mapped slot records (INT-546).

        A hedge records the mapped choice at once, over any choice the model
        guessed. A choice the model bound is the patient's answer, and ``None``
        is returned. An answer that bound none asks the slot's follow-up while
        any is left (``answer`` is ``None``); once spent it records the mapped
        choice where CD-112 decides one, and is left to the engine's UNCLEAR
        where it does not.
        """
        mappings = self.mappings
        origin = self._asked_origin(context)
        if mappings is None or origin is None or origin not in mappings.refs:
            return None
        hedged = mappings.hedge(origin, text)
        if hedged is not None:
            return _MappedSlot(origin, hedged)
        if result is not None and result.outcome_of(origin) is SlotOutcome.BOUND:
            return None
        if context.engine.clarifications_left(origin) > 0:
            return _MappedSlot(origin, None)
        return _MappedSlot(origin, mappings.unresolved(origin))

    def _settle_mapped(self, context: StateContext, mapped: _MappedSlot, clarified: bool) -> None:
        """Ask the follow-up the model did not ask for, or record what was bound."""
        engine = context.engine
        if mapped.answer is None:
            if not clarified:
                self._clarify(context, mapped.slot, None)
            return
        if (
            self.mappings is not None
            and engine.state_of(mapped.slot) is AnswerState.ASKED_PRESENT
            and engine.value_of(mapped.slot) == mapped.answer.choice
        ):
            self.mappings.note(mapped.answer)

    @staticmethod
    def _clarify(context: StateContext, origin: str, bound: int | None) -> None:
        """Ask the slot's follow-up — or, its bound spent, record UNCLEAR.

        The engine holds the slot's ceiling; ``bound`` is the tighter one for
        this answer's cause, if any (INT-546). This is the
        ``clarification_needed`` the model did not set. It answers the
        follow-up being answered when that is still queued, else the slot; a
        slot the extraction just invalidated is dropped by the engine.
        """
        engine = context.engine
        step = context.request.step_id
        engine.clarify(step if step in engine.follow_ups else origin, bound=bound)

    def _apply(self, context: StateContext, call: dict[str, Any]) -> None:
        """Bind the extraction, each anchor's choice replaced by its CD-05 day."""
        engine = context.engine
        if self.anchors is None:
            engine.apply_extraction(**call)
            return
        updates, resolutions = self.anchors.resolve_choices(
            call["slot_updates"], engine.reference_time
        )
        revisions = {r.anchor: engine.slot_revision(r.anchor) for r in resolutions}
        engine.apply_extraction(**{**call, "slot_updates": updates})
        self.anchors.note_bound(resolutions, engine, revisions)

    def _declared_slots(self, context: StateContext) -> Mapping[str, Slot]:
        """The Work's own step plus every step the engine is awaiting.

        ``awaiting`` is the ask-ahead set (files/03 §4.5): the questions that
        have been spoken and not yet reconciled. Those are the only refs
        ``IntakeEngine._bind`` will accept, so they are the only refs worth
        declaring.
        """
        refs = {context.request.step_id, *context.engine.snapshot.awaiting}
        # An empty intersection means the Work names a step this pack does not
        # declare. ``slot_output_schema`` refuses an empty schema, and that is
        # the right answer: nobody could validate an answer to it.
        return {ref: self.slots[ref] for ref in sorted(refs) if ref in self.slots}
