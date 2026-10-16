"""Layer B's Work queue: FIFO, one state Work in flight, serialised writes.

files/03 §4.3 states the shape: *"One persistent agent context per session
(``intake:<session_id>:backend``), fed a **FIFO Work queue**; only **one Work
in flight per session**; all writes to ``SessionState`` serialised (queue lock
+ engine lock — qwen-audio-agent's "double guard")."*

**The double guard is two locks, and which one is which is the whole point.**

- ``_queue_lock`` guards the bookkeeping — the deques, the record table, the
  in-flight tokens — and is held for a few statements at a time. ``submit``
  takes only this one.
- ``_engine_lock`` is held across a state handler's whole execution, which is
  where :class:`~intake_voice_runtime.clinical_agent.fsm.IntakeEngine` is
  written.

Collapsing them into one lock would make ``submit`` block for the duration of
Backend Work, which breaks CLAUDE.md invariant 9's second clause — *the Talker
never awaits Backend Work* — **in the queue** rather than in the Talker.
``tests/voice/test_work_queue.py::TestSerializedSessionState`` holds a handler
open on one thread and submits on another to prove the two locks are not one.

**Under contention nothing is dropped and nothing is reordered.** A second
``run_pending`` — from another thread, or re-entered from inside a handler —
finds the lane's in-flight token taken (or the engine lock held) and **returns
having run nothing**, leaving the item at the head of its FIFO. A queue that
silently dropped or reordered clinical Work would be worse than one that
refuses, so it refuses.

**"One Work in flight" means one *slot-writing* Work.** files/12 §7.4 splits
the queue after files/03 was written: a ``state`` lane that *"holds the engine
lock and is strictly FIFO"*, and a ``background`` lane that is concurrent and
*"structurally cannot write slots: it receives ``ReadOnlyContext``, which has
no mutator"*. That split exists to remove the head-of-line case where a RED
sat behind a ``parse_document`` (files/12 §7.3), so honouring files/03's
sentence literally would reintroduce the defect files/12 fixed. What the
sentence protects — *"no lost or reordered slot updates"* (files/03 §4.6
invariant 5) — is protected exactly, because the state lane is single
in-flight and the background lane is handed nothing it could write with.

**No handler can ask for a priority.** Neither :class:`StateEffect` nor
:class:`BackgroundEffect` has a ``priority`` field, so ``preempt`` is not
something a handler may request: the queue *derives* it, and only from a
:class:`~clinical_schemas.triage.RulesTriageResult` at ``RED``.
:class:`BackgroundEffect` has no ``triage_update`` field at all, so the lane
that runs concurrently cannot reach the branch. A derived preempt is then put
through :func:`~intake_voice_runtime.talker.preemption.authorise_preempt`; a
RED naming a rule outside the session's pinned pack **fails the Work** rather
than being downgraded, because speaking a RED as routine is the worse error.

**The rules engine runs here, after the Work, never inside a handler**
(INT-521). A queue handed a
:class:`~intake_voice_runtime.clinical_agent.live_triage.SessionTriage`
compares the answers the served rules read before and after each state-lane
Work; when the Work bound or changed one, it asks the rules engine for a
determination and passes it on as that Work's ``triage_update``. So every
answer that can change a red-flag rule is evaluated, by whichever handler it
was bound. Three ways a RED could be lost are closed:

- a handler that returns its own determination is checked against the rules
  engine whenever the session serves rules; where the two disagree, the
  engine's stands and the disagreement pages
  (``triage_live_evaluation_failures_total{kind="conflict"}``);
- an evaluation that raises fails the Work, pages
  (``{kind="fault"}``, an ids-only error log), and leaves the evaluation
  owed, so the next state-lane Work evaluates whether or not it binds a read
  slot;
- a RED already raised for this session is not raised again by a later
  re-evaluation, so a RED that leaves the intake running does not re-notify
  the clinic on every answer.

The moment the determination was in hand travels on a ``preempt`` result as
``evaluated_at_ms``, because files/02 §8.2 measures the RED budgets from rule
evaluation and the Talker must not stamp a RED on arrival.

**A RED does not wait for the Talker's next turn** (INT-531). Once a RED has
settled (and sealed the queue, where its register stops the intake) the queue
posts it through :class:`~intake_voice_runtime.talker.red_push.RedPush` — one
member, not awaitable — to the session's mailbox, which wakes the Talker's
own between-turn loop. Nothing here calls into the Talker or waits on it. The
post is the fast route, not the only one: the RED stays in the results for
the turn's drain, and a post that raises is logged by id and costs the RED
nothing.

**The queue is PHI-free by construction** (CLAUDE.md invariant 6).
:class:`~intake_voice_runtime.ports.WorkRequest` carries ``input_hash``, not
the transcript, so there is no patient text in a record, a log line or a
metric label to redact. The consequence is a boundary INT-083 owns: extraction
needs the text, and the route by which it gets it is that issue's
data-boundary decision (CLAUDE.md invariant 14), not a field on this record.
INT-095 settled that route and **kept the property**: the transcript travels
in :mod:`intake_voice_runtime.transcript`, a per-session in-memory vault keyed
by the same digest ``input_hash`` already carries, so nothing on this record,
in this module's logs or in its metric labels changed.

There are **no production handlers registered here** — registration is the
composition root's job (:mod:`intake_voice_runtime.composition`), because a
handler needs a gateway, a transcript source and a model pin, and a queue that
built its own would be a queue that chose a model. Submitting a Work type with
no handler still raises :class:`UnregisteredWorkType` at ``submit``: the gate
fails closed for ``parse_document``, whose background handler is INT-121.

**The ask ledger is the one Layer-B write Layer A may ask for.**
:meth:`BackendAgent.note_asked` is the
:class:`~intake_voice_runtime.ports.AskLedger` half of files/03 §4.5's *"ask
ahead, reconcile behind"*: the Talker records the step it spoke, the note is
queued under the cheap ``_queue_lock``, and :meth:`BackendAgent.run_pending`
applies it through ``IntakeEngine.mark_asked`` **under the engine lock, before
either lane runs** — so an answer's extraction can never overtake the mark for
the question it answers. A note for a step the frontier is no longer offering
is refused and recorded in :attr:`BackendAgent.refused_asks` rather than
forced: the frontier is the protocol's decision about what is askable, and a
step outside it has no open gate.
"""

from __future__ import annotations

import enum
import logging
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from threading import Lock
from typing import Final

from clinical_schemas.common import FrozenModel
from clinical_schemas.triage import CandidateFlag, RulesTriageResult, TriageLevel
from intake_platform.safety_inbox.metrics import CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL
from pydantic import Field, ValidationError

from intake_voice_runtime.clinical_agent.fsm import EngineError, IntakeEngine
from intake_voice_runtime.clinical_agent.live_triage import BoundReads, SessionTriage
from intake_voice_runtime.metrics import (
    TRIAGE_LIVE_EVALUATION_FAILURES_TOTAL,
    WORK_FAILED_TOTAL,
    WORK_LATENCY_MS,
    WORK_QUEUE_DEPTH,
)
from intake_voice_runtime.ports import (
    Clock,
    EngineSnapshot,
    QueueSealed,
    SystemClock,
    WorkRequest,
    WorkState,
    WorkTicket,
    WorkType,
    work_key,
)
from intake_voice_runtime.talker.activity import ACTIVITY_OF, ActivityLabel
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    InlinePayload,
    PreemptRefused,
    Presentation,
    Priority,
    authorise_preempt,
)
from intake_voice_runtime.talker.red_path import REGISTER_DELIVERY, ClinicNotifier, RedNotification
from intake_voice_runtime.talker.red_push import RedPush

__all__ = [
    "LANE_OF",
    "BackendAgent",
    "BackgroundEffect",
    "BackgroundHandler",
    "EffectClass",
    "QueueSealed",
    "ReadOnlyContext",
    "StateContext",
    "StateEffect",
    "StateHandler",
    "UnregisteredWorkType",
    "WorkLane",
    "WorkRecord",
]

logger = logging.getLogger("intake_voice_runtime.clinical_agent.work_queue")


class WorkLane(enum.StrEnum):
    """files/12 §7.4's two lanes."""

    STATE = "state"
    BACKGROUND = "background"


#: Which lane each Work type runs in. Declared, never inferred: a lane chosen
#: at runtime would be a guess about whether the Work may write slots.
LANE_OF: Final[Mapping[WorkType, WorkLane]] = {
    WorkType.EXTRACT_SLOTS: WorkLane.STATE,
    WorkType.PLAN_FOLLOW_UPS: WorkLane.STATE,
    WorkType.PARSE_DOCUMENT: WorkLane.BACKGROUND,
    WorkType.RETRIEVE_RECORDS: WorkLane.BACKGROUND,
}


class UnregisteredWorkType(LookupError):
    """No handler for this Work type. Refused at submit, never queued."""


class EffectClass(enum.StrEnum):
    """The delivery classes a *handler* may declare.

    :class:`~intake_voice_runtime.talker.delivery.DeliveryClass` also has
    ``RED`` and ``TRIAGE_YELLOW``; neither appears here, because those two are
    determinations rather than presentation choices and the queue derives them
    from the rules-engine result. A handler cannot elect itself into the
    protected classes.
    """

    CLINICAL_INFO = "clinical_info"
    ROUTINE = "routine"


class StateEffect(FrozenModel):
    """What a state-lane handler returns. No ``priority``, by design."""

    inline: InlinePayload | None = Field(default=None)
    speech_tr: str | None = Field(default=None)
    speech_numerics: tuple[str, ...] = Field(
        default=(), description="Slot keys the speech states; each needs an inline render."
    )
    triage_update: RulesTriageResult | None = Field(
        default=None,
        description="A determination from packages/protocols/triage, passed through "
        "verbatim — the queue computes no level (CLAUDE.md invariant 1).",
    )
    effect_class: EffectClass = Field(default=EffectClass.ROUTINE)


class BackgroundEffect(FrozenModel):
    """What a background-lane handler returns.

    files/12 §7.4: *"its effect type ``BackgroundEffect`` cannot express a slot
    write"*. It has no ``triage_update`` field either, so the concurrent lane
    cannot reach the RED branch that derives ``preempt``. LLM material leaves
    it as ``candidate_flags`` — clinician-facing text, never a level.
    """

    inline: InlinePayload | None = Field(default=None)
    speech_tr: str | None = Field(default=None)
    speech_numerics: tuple[str, ...] = Field(default=())
    candidate_flags: tuple[CandidateFlag, ...] = Field(default=())
    effect_class: EffectClass = Field(default=EffectClass.ROUTINE)


@dataclass(frozen=True, slots=True)
class StateContext:
    """What a state handler is handed: the request, and the engine itself.

    Constructed only inside the engine lock, so a handler that writes is
    writing under the serialisation this module exists to provide.
    """

    request: WorkRequest
    engine: IntakeEngine


@dataclass(frozen=True, slots=True)
class ReadOnlyContext:
    """What a background handler is handed. There is no engine and no mutator.

    ``is_cancelled`` is the cooperative token of files/12 §7.1 — the only
    cancellation channel running background work has.
    """

    request: WorkRequest
    snapshot: EngineSnapshot
    is_cancelled: Callable[[], bool]


StateHandler = Callable[[StateContext], StateEffect]
BackgroundHandler = Callable[[ReadOnlyContext], BackgroundEffect]


@dataclass
class WorkRecord:
    """A delivery receipt, not a mirror of internal reasoning (files/03 §4.3).

    Every field is an id, a closed enumeration, a clock reading or an error
    class name. There is no field a transcript could occupy.
    """

    request: WorkRequest
    state: WorkState
    enqueued_ms: float
    started_ms: float | None = None
    finished_ms: float | None = None
    error: str | None = None


@dataclass
class BackendAgent:
    """One session's Clinical Backend Agent — the ``WorkSubmitter`` Layer A sees."""

    session_id: str
    engine: IntakeEngine
    rule_ids: frozenset[str] = frozenset()
    clock: Clock = field(default_factory=SystemClock)
    #: INT-406, invariant 49: the clinician route, told of every rules-engine
    #: RED at the moment it settles — before Layer A drains it, so a session
    #: that ends on the answer that fired the RED still reaches the clinic.
    #: ``None`` is the unit-level default only; both composition roots require
    #: one (``intake_voice_runtime.composition``).
    clinic: ClinicNotifier | None = None
    #: INT-521: the session's served red-flag rules, evaluated after every
    #: state-lane Work that binds a slot one of them reads. ``None`` where the
    #: pinned protocol serves no rule; composition binds one wherever it does.
    triage: SessionTriage | None = None
    #: INT-531: where a settled RED is posted for the Talker's between-turn
    #: watch. ``None`` where no RED path is bound; the turn's drain still
    #: delivers it then.
    red_push: RedPush | None = None
    _queue_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _engine_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _state_handlers: dict[WorkType, StateHandler] = field(default_factory=dict, init=False)
    _background_handlers: dict[WorkType, BackgroundHandler] = field(
        default_factory=dict, init=False
    )
    _queues: dict[WorkLane, deque[str]] = field(default_factory=dict, init=False, repr=False)
    _running: dict[WorkLane, str | None] = field(default_factory=dict, init=False, repr=False)
    _records: dict[str, WorkRecord] = field(default_factory=dict, init=False, repr=False)
    _claimed_ms: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _ready: list[BackendResult] = field(default_factory=list, init=False, repr=False)
    _cancelling: set[str] = field(default_factory=set, init=False, repr=False)
    _asked: deque[str] = field(default_factory=deque, init=False, repr=False)
    _refused_asks: list[str] = field(default_factory=list, init=False, repr=False)
    _sealed: bool = field(default=False, init=False)
    #: INT-521: an evaluation faulted and is still owed; the next state Work
    #: evaluates whether or not it binds a read slot.
    _evaluation_owed: bool = field(default=False, init=False, repr=False)
    #: INT-521: the REDs this session already raised, by what they determine.
    _raised_reds: set[tuple[str, frozenset[str], str, str]] = field(
        default_factory=set, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self._queues = {lane: deque() for lane in WorkLane}
        self._running = dict.fromkeys(WorkLane, None)

    # --- registration --------------------------------------------------------

    def register_state(self, work_type: WorkType, handler: StateHandler) -> None:
        """Bind a state-lane handler. A background type is refused."""
        if LANE_OF[work_type] is not WorkLane.STATE:
            raise ValueError(
                f"{work_type.value!r} runs in the background lane; a state handler "
                "would be handed the engine and could write slots (files/12 §7.4)"
            )
        self._state_handlers[work_type] = handler

    def register_background(self, work_type: WorkType, handler: BackgroundHandler) -> None:
        """Bind a background-lane handler. A state type is refused."""
        if LANE_OF[work_type] is not WorkLane.BACKGROUND:
            raise ValueError(
                f"{work_type.value!r} runs in the state lane and must hold the engine "
                "lock; a background handler never takes it (files/12 §7.4)"
            )
        self._background_handlers[work_type] = handler

    # --- reads ---------------------------------------------------------------

    @property
    def engine_lock(self) -> Lock:
        """The lock a state handler runs under. Exposed so a test can hold it."""
        return self._engine_lock

    @property
    def sealed(self) -> bool:
        """True once a rules-engine RED closed the queue (files/12 §7.1)."""
        return self._sealed

    @property
    def state_handlers(self) -> Mapping[WorkType, StateHandler]:
        """What is bound in the state lane — the registration, readable.

        Exposed so a composition root's wiring is assertable from outside
        rather than by reaching into a private dict; the mapping is a copy, so
        reading it cannot register anything.
        """
        return dict(self._state_handlers)

    @property
    def refused_asks(self) -> tuple[str, ...]:
        """Ask notes the engine refused, in order (files/13 §9.2).

        Step ids are protocol identifiers, never patient text, so this is
        readable and loggable under CLAUDE.md invariant 6. A non-empty tuple
        means Layer A spoke a step the frontier was no longer offering — a
        real defect, kept visible rather than swallowed.
        """
        with self._queue_lock:
            return tuple(self._refused_asks)

    @property
    def in_flight(self) -> tuple[str, ...]:
        """The Work ids running right now — at most one per lane."""
        with self._queue_lock:
            return tuple(work_id for work_id in self._running.values() if work_id is not None)

    @property
    def activity(self) -> tuple[ActivityLabel, ...]:
        """What the rail may say this session is doing (files/03 §4.6 inv. 10).

        Derived from the Work types that are queued or running — never from a
        handler, which is what stops a prompt or a chain of reasoning reaching
        the client through this channel. Each label appears once however many
        Works of that type are outstanding: the rail shows *what* is happening,
        not *how much*, and a count would leak queue depth to the patient.
        """
        with self._queue_lock:
            outstanding = [
                self._records[work_id].request.work_type
                for lane, queue in self._queues.items()
                for work_id in (*queue, *((self._running[lane],) if self._running[lane] else ()))
            ]
        seen: list[ActivityLabel] = []
        for work_type in outstanding:
            label = ACTIVITY_OF[work_type]
            if label not in seen:
                seen.append(label)
        return tuple(seen)

    def depth(self, lane: WorkLane) -> int:
        """Queued (not running) items in one lane."""
        with self._queue_lock:
            return len(self._queues[lane])

    def record(self, work_id: str) -> WorkRecord:
        """The receipt for one Work."""
        with self._queue_lock:
            record = self._records.get(work_id)
        if record is None:
            raise LookupError(f"no such work: {work_id!r}")
        return record

    # --- the WorkSubmitter port ------------------------------------------------

    def submit(self, request: WorkRequest) -> WorkTicket:
        """Enqueue and return at once. Runs nothing; waits on nothing."""
        if request.session_id != self.session_id:
            raise ValueError(
                f"work for another session reached this queue: {request.session_id!r} "
                f"!= {self.session_id!r} — one Backend context per session (files/03 §4.3)"
            )
        lane = LANE_OF[request.work_type]
        handlers: Mapping[WorkType, object] = (
            self._state_handlers if lane is WorkLane.STATE else self._background_handlers
        )
        if request.work_type not in handlers:
            raise UnregisteredWorkType(
                f"no handler registered for {request.work_type.value!r}; refusing to "
                "queue Work that could never run (fail closed)"
            )
        work_id = work_key(request)
        with self._queue_lock:
            if self._sealed:
                raise QueueSealed(
                    "the queue was sealed by a rules-engine RED; no further Work is "
                    "admitted for this session (files/12 §7.1)"
                )
            existing = self._records.get(work_id)
            if existing is not None:
                return WorkTicket(work_id=work_id, state=existing.state)
            self._records[work_id] = WorkRecord(
                request=request, state=WorkState.QUEUED, enqueued_ms=self.clock.now_ms()
            )
            self._queues[lane].append(work_id)
            self._publish_depth()
        logger.debug(
            "work queued", extra={"work_id": work_id, "work_type": request.work_type.value}
        )
        return WorkTicket(work_id=work_id, state=WorkState.QUEUED)

    # --- the AskLedger port ----------------------------------------------------

    def note_asked(self, step_id: str) -> None:
        """Record that Layer A spoke ``step_id``. Returns at once; runs nothing.

        Takes only ``_queue_lock`` — a few statements — never the engine lock,
        which a state handler holds for the whole of an LLM call. The mark
        itself is applied by :meth:`run_pending` (CLAUDE.md invariant 9).
        """
        with self._queue_lock:
            self._asked.append(step_id)

    def cancel(self, work_id: str, reason: str) -> WorkTicket:
        """files/12 §7.1: dequeue if queued; never abort a committing write.

        ``reason`` is accepted because the tool signature carries it and is
        deliberately not recorded: it is free patient-supplied text and the
        record is PHI-free (CLAUDE.md invariant 6).
        """
        with self._queue_lock:
            record = self._records.get(work_id)
            if record is None:
                raise LookupError(f"no such work: {work_id!r}")
            if record.state is WorkState.QUEUED:
                self._queues[LANE_OF[record.request.work_type]].remove(work_id)
                record.state = WorkState.CANCELLED
                record.finished_ms = self.clock.now_ms()
                self._publish_depth()
            elif record.state is WorkState.RUNNING:
                # The write, if it has happened, stands. Only the speech is
                # suppressed, and only where the result is not a RED.
                self._cancelling.add(work_id)
            return WorkTicket(work_id=work_id, state=record.state)

    def drain_results(self) -> tuple[BackendResult, ...]:
        """Whatever is finished. Never blocks; each result appears exactly once."""
        with self._queue_lock:
            drained = tuple(self._ready)
            self._ready.clear()
        return drained

    # --- the pump ---------------------------------------------------------------

    def run_pending(self) -> int:
        """Advance each lane by at most one Work. Returns how many ran.

        Called by the Backend worker loop, never from the Talker's turn — no
        expression on the speech path reaches this method.

        Ask notes are applied **first**, so the mark for a question always
        lands before the extraction of its answer runs: files/13 §9.3 binds
        nothing to a step that is not ``ASKED_PENDING``, and the other order
        would drop every answer.
        """
        self._apply_asked_notes()
        return sum(self._run_lane(lane) for lane in (WorkLane.STATE, WorkLane.BACKGROUND))

    def _apply_asked_notes(self) -> None:
        """Drain the ask notes under the engine lock, in order.

        A non-blocking acquire: when a state handler holds the engine the
        notes keep their place and are applied on the next pass, which is the
        same refusal-rather-than-interleave rule ``_run_lane`` uses.
        """
        with self._queue_lock:
            if not self._asked:
                return
        if not self._engine_lock.acquire(blocking=False):
            return
        try:
            while True:
                with self._queue_lock:
                    if not self._asked:
                        return
                    step_id = self._asked.popleft()
                try:
                    self.engine.mark_asked(step_id)
                except EngineError:
                    with self._queue_lock:
                        self._refused_asks.append(step_id)
                    logger.warning(
                        "ask note refused",
                        extra={"session_id": self.session_id, "step_id": step_id},
                    )
        finally:
            self._engine_lock.release()

    def _run_lane(self, lane: WorkLane) -> int:
        work_id = self._claim(lane)
        if work_id is None:
            return 0
        if lane is WorkLane.BACKGROUND:
            self._execute_background(work_id)
            return 1
        if not self._engine_lock.acquire(blocking=False):
            # Another writer holds the engine. Refuse rather than interleave,
            # and put the item back at the head so FIFO order is untouched.
            self._unclaim(lane, work_id)
            return 0
        try:
            self._execute_state(work_id)
        finally:
            self._engine_lock.release()
        return 1

    def _claim(self, lane: WorkLane) -> str | None:
        with self._queue_lock:
            if self._running[lane] is not None or not self._queues[lane]:
                return None
            work_id = self._queues[lane].popleft()
            record = self._records[work_id]
            record.state = WorkState.RUNNING
            record.started_ms = self.clock.now_ms()
            self._claimed_ms[work_id] = record.started_ms
            self._running[lane] = work_id
            self._publish_depth()
            return work_id

    def _unclaim(self, lane: WorkLane, work_id: str) -> None:
        with self._queue_lock:
            record = self._records[work_id]
            record.state = WorkState.QUEUED
            record.started_ms = None
            del self._claimed_ms[work_id]
            self._queues[lane].appendleft(work_id)
            self._running[lane] = None
            self._publish_depth()

    # --- execution ----------------------------------------------------------------

    def _execute_state(self, work_id: str) -> None:
        record = self._records[work_id]
        handler = self._state_handlers[record.request.work_type]
        try:
            before = self.triage.bound(self.engine) if self.triage is not None else ()
        except Exception as err:  # the evaluation cannot be prepared: fail closed, loudly
            self._evaluation_failed(work_id, err)
            return
        try:
            effect = handler(StateContext(request=record.request, engine=self.engine))
        except Exception as err:  # a handler fault is a receipt, not a crashed pump
            self._finish_failed(WorkLane.STATE, work_id, err)
            return
        try:
            triage_update = self._determination(effect, before, work_id)
        except Exception as err:  # the answer is bound and unevaluated: fail closed, loudly
            self._evaluation_failed(work_id, err)
            return
        self._finish(
            WorkLane.STATE,
            work_id,
            inline=effect.inline,
            speech_tr=effect.speech_tr,
            speech_numerics=effect.speech_numerics,
            triage_update=triage_update,
            candidate_flags=(),
            effect_class=effect.effect_class,
            determined_at_ms=self.clock.now_ms(),
        )

    def _determination(
        self, effect: StateEffect, before: BoundReads, work_id: str
    ) -> RulesTriageResult | None:
        """The Work's ``triage_update`` (INT-521).

        With no served rules, a handler's own determination passes through.
        Otherwise the rules engine runs — under the engine lock, over exactly
        the state the Work left — when the Work bound or changed an answer a
        served rule reads, when an earlier evaluation is still owed, or when
        the handler returned a determination of its own. The engine's stands;
        a handler's that disagrees with it is refused and pages. A RED this
        session already raised is not raised again.
        """
        triage = self.triage
        if triage is None:
            return effect.triage_update
        changed = self._evaluation_owed or triage.bound(self.engine) != before
        if not changed and effect.triage_update is None:
            return None
        determined = triage.evaluate(self.engine, work_id=work_id)
        self._evaluation_owed = False
        handed = effect.triage_update
        if handed is not None and _determines(handed) != _determines(determined):
            TRIAGE_LIVE_EVALUATION_FAILURES_TOTAL.labels(kind="conflict").inc()
            logger.error(
                "triage determination conflict",
                extra={"session_id": self.session_id, "work_id": work_id},
            )
        if determined.level is TriageLevel.RED and _determines(determined) in self._raised_reds:
            return None
        return determined

    def _evaluation_failed(self, work_id: str, err: Exception) -> None:
        """The rules engine could not evaluate this Work: fail closed, loudly.

        The Work fails, the evaluation stays owed so the next state Work runs
        it again whatever it binds, and the fault pages with ids only
        (invariant 6): an answer may be bound that a RED depends on.
        """
        self._evaluation_owed = True
        TRIAGE_LIVE_EVALUATION_FAILURES_TOTAL.labels(kind="fault").inc()
        logger.error(
            "triage evaluation failed",
            extra={
                "session_id": self.session_id,
                "work_id": work_id,
                "error": type(err).__name__,
            },
        )
        self._finish_failed(WorkLane.STATE, work_id, err)

    def _execute_background(self, work_id: str) -> None:
        record = self._records[work_id]
        handler = self._background_handlers[record.request.work_type]
        context = ReadOnlyContext(
            request=record.request,
            snapshot=self.engine.snapshot,
            is_cancelled=lambda: work_id in self._cancelling,
        )
        try:
            effect = handler(context)
        except Exception as err:
            self._finish_failed(WorkLane.BACKGROUND, work_id, err)
            return
        self._finish(
            WorkLane.BACKGROUND,
            work_id,
            inline=effect.inline,
            speech_tr=effect.speech_tr,
            speech_numerics=effect.speech_numerics,
            triage_update=None,
            candidate_flags=effect.candidate_flags,
            effect_class=effect.effect_class,
            determined_at_ms=self.clock.now_ms(),
        )

    def _finish(
        self,
        lane: WorkLane,
        work_id: str,
        *,
        inline: InlinePayload | None,
        speech_tr: str | None,
        speech_numerics: tuple[str, ...],
        triage_update: RulesTriageResult | None,
        candidate_flags: tuple[CandidateFlag, ...],
        effect_class: EffectClass,
        determined_at_ms: float,
    ) -> None:
        delivery_class, priority = _delivery_of(triage_update, effect_class)
        suppressed = priority is Priority.NORMAL and work_id in self._cancelling
        try:
            presentation = Presentation(
                inline=inline,
                speech_tr=None if suppressed else speech_tr,
                speech_numerics=() if suppressed else speech_numerics,
                triage_update=triage_update,
                candidate_flags=candidate_flags,
            )
        except ValidationError as err:
            # CLAUDE.md invariant 22 refused the pair; the Work fails rather
            # than speaking a number the rail never rendered.
            self._finish_failed(lane, work_id, err)
            return
        result = BackendResult(
            work_id=work_id,
            state=WorkState.COMPLETED,
            delivery_class=delivery_class,
            presentation=presentation,
            priority=priority,
            evaluated_at_ms=determined_at_ms if priority is Priority.PREEMPT else None,
        )
        if priority is Priority.PREEMPT:
            try:
                authorise_preempt(result, rule_ids=self.rule_ids)
            except PreemptRefused as err:
                self._finish_failed(lane, work_id, err)
                return
            self._notify_clinic(result)
            if isinstance(triage_update, RulesTriageResult):
                self._raised_reds.add(_determines(triage_update))
        self._settle(lane, work_id, WorkState.COMPLETED, result, error=None)
        if priority is Priority.PREEMPT:
            if _stops_intake(triage_update):
                self._seal()
            self._push_red(result)

    def _push_red(self, result: BackendResult) -> None:
        """INT-531: post a settled, authorised RED for the Talker's watch.

        After the settle (so the turn's drain has it too) and after the seal
        (so the Talker never hears of a stopping RED while the queue still
        admits Work). The port's one member returns at once. A post that
        raises is logged by id and error class (invariant 6) and costs the RED
        nothing: it is settled, and the next turn's drain delivers it.
        """
        if self.red_push is None:
            return
        try:
            self.red_push.push(result)
        except Exception as err:  # the post must never cost the RED
            logger.error(
                "red push failed",
                extra={
                    "session_id": self.session_id,
                    "work_id": result.work_id,
                    "error": type(err).__name__,
                },
            )

    def _notify_clinic(self, result: BackendResult) -> None:
        """Invariant 49: hand an authorised RED to the clinician route.

        Runs after :func:`authorise_preempt`, so only a rules-engine RED from
        the pinned pack reaches it (invariant 1), and before the result
        settles, so the route hears of the RED no later than Layer A can. The
        port has no awaitable member; a route that raises is logged by work
        id and never costs the RED its delivery — the result settles and the
        queue seals either way.
        """
        if self.clinic is None:
            return
        try:
            triage = result.presentation.triage_update
            stamp = result.evaluated_at_ms
            if not isinstance(triage, RulesTriageResult) or (
                triage.register is None or triage.location is None or stamp is None
            ):
                # unreachable past authorise_preempt and _finish's stamp; counted,
                # never raised here
                raise TypeError(
                    "an authorised RED carries a rules result with both axes and the "
                    "moment it was determined"
                )
            self.clinic.notify(
                RedNotification(
                    work_id=result.work_id,
                    rule_ids=tuple(fire.id for fire in triage.rules),
                    register=triage.register,
                    location=triage.location,
                    evaluated_at_ms=stamp,
                    patient_facing=REGISTER_DELIVERY[triage.register].triggers_device,
                )
            )
        except Exception:  # the route must never cost the RED; the failure pages
            CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL.inc()
            logger.error(
                "red clinic route failed",
                extra={"session_id": self.session_id, "work_id": result.work_id},
            )

    def _finish_failed(self, lane: WorkLane, work_id: str, err: Exception) -> None:
        record = self._records[work_id]
        WORK_FAILED_TOTAL.labels(type=record.request.work_type.value).inc()
        result = BackendResult(
            work_id=work_id,
            state=WorkState.FAILED,
            delivery_class=DeliveryClass.ROUTINE,
            presentation=Presentation(),
            priority=Priority.NORMAL,
        )
        self._settle(lane, work_id, WorkState.FAILED, result, error=type(err).__name__)

    def _settle(
        self,
        lane: WorkLane,
        work_id: str,
        state: WorkState,
        result: BackendResult,
        *,
        error: str | None,
    ) -> None:
        with self._queue_lock:
            record = self._records[work_id]
            record.state = state
            record.error = error
            record.finished_ms = self.clock.now_ms()
            # ``_settle`` is only ever reached through ``_claim``, so the pop
            # cannot miss; a KeyError here would mean a Work finished that was
            # never claimed, which is a bug worth raising rather than skipping.
            WORK_LATENCY_MS.labels(type=record.request.work_type.value).observe(
                record.finished_ms - self._claimed_ms.pop(work_id)
            )
            self._ready.append(result)
            self._running[lane] = None
            self._cancelling.discard(work_id)
            self._publish_depth()
        logger.debug(
            "work settled",
            extra={
                "work_id": work_id,
                "work_type": record.request.work_type.value,
                "state": state.value,
            },
        )

    def _seal(self) -> None:
        """files/12 §7.1: on RED, cancel everything queued and admit no more.

        Only a RED whose register stops the intake seals (INT-521). A
        ``DEFERRED_CLINICIAN`` RED leaves the patient surface unchanged and the
        session running (files/02 §5.3; files/03 §15b), so sealing behind it
        would refuse every later answer the intake still asks for.

        The allowed set files/12 names — ``{note_finalize, clinic_notify,
        audit_flush}`` — has no member in :class:`WorkType` on this branch, so
        the seal admits nothing at all. When those Work types exist they are
        added here, not worked around.
        """
        with self._queue_lock:
            self._sealed = True
            for lane, queue in self._queues.items():
                while queue:
                    cancelled = queue.popleft()
                    record = self._records[cancelled]
                    record.state = WorkState.CANCELLED
                    record.finished_ms = self.clock.now_ms()
                del lane
            self._publish_depth()

    def _publish_depth(self) -> None:
        """Called under ``_queue_lock``. Labels are ``WorkType`` values only."""
        counts = dict.fromkeys(WorkType, 0)
        for queue in self._queues.values():
            for work_id in queue:
                counts[self._records[work_id].request.work_type] += 1
        for work_type, count in counts.items():
            WORK_QUEUE_DEPTH.labels(type=work_type.value).set(count)


def _determines(triage: RulesTriageResult) -> tuple[str, frozenset[str], str, str]:
    """What a determination decides: its level, the rules that fired, and for a
    RED its register and location. Evidence text is not part of it."""
    register = triage.register.value if triage.register is not None else ""
    location = triage.location.value if triage.location is not None else ""
    return (triage.level.value, frozenset(fire.id for fire in triage.rules), register, location)


def _stops_intake(triage: RulesTriageResult | None) -> bool:
    """Does this RED's register stop the intake (files/02 §5.3)?"""
    register = triage.register if triage is not None else None
    return register is not None and REGISTER_DELIVERY[register].stops_intake


def _delivery_of(
    triage: RulesTriageResult | None, effect_class: EffectClass
) -> tuple[DeliveryClass, Priority]:
    """Derive the delivery class and priority. Handlers do not choose either.

    files/03 §4.3: ``priority: "preempt"`` is accepted *"only when
    ``triage_update.level == "RED"``"*, and only a ``RulesTriageResult`` can
    spell ``RED`` (CLAUDE.md invariant 1). Everything else is ``normal``.
    """
    if triage is not None and triage.level is TriageLevel.RED:
        return DeliveryClass.RED, Priority.PREEMPT
    if triage is not None and triage.level is TriageLevel.YELLOW:
        return DeliveryClass.TRIAGE_YELLOW, Priority.NORMAL
    if effect_class is EffectClass.CLINICAL_INFO:
        return DeliveryClass.CLINICAL_INFO, Priority.NORMAL
    return DeliveryClass.ROUTINE, Priority.NORMAL
