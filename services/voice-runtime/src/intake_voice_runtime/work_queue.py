"""Layer B's FIFO Work queue — one Work in flight, serialised writes (INT-092).

files/03 §4.3 is the whole specification in one sentence: *"One persistent
agent context per session (``intake:<session_id>:backend``), fed a **FIFO Work
queue**; only **one Work in flight per session**; all writes to
``SessionState`` serialised (queue lock + engine lock — qwen-audio-agent's
'double guard')."*

Four properties are structural here rather than remembered:

- **The Talker cannot await this.** ``submit``, ``cancel`` and
  ``drain_results`` are ordinary functions — the whole
  :class:`~intake_voice_runtime.ports.WorkSubmitter` port is synchronous, so
  ADR-009's *"never awaits Backend Work"* has no expression to violate. The
  pump (:meth:`WorkQueue.run_pending`) belongs to Layer B's own task and is
  not on the port.
- **One Work in flight.** The pump holds ``_queue_lock`` for the whole drain,
  so two racing pumps produce one runner, not two. The engine write
  additionally takes ``_engine_lock`` — the second half of the double guard,
  kept as a separate lock because the engine is writable from more than the
  pump's own call site.
- **Duplicates are impossible by identity.** ``work_id`` is content-addressed
  (files/12 §7.5), so a re-submitted transcript — after a restart, a retry, or
  two racing callers — resolves to a record that already exists. It is not
  enqueued twice, not run twice, and not emitted twice.
- **A result that cannot be represented is refused, not repaired.** The
  ``BackendResult`` is built and authorised *before* any engine write, so a
  spoken number with no ``inline`` render (CLAUDE.md invariant 22) or a
  ``preempt`` that is not a rules-engine RED from the session's pinned pack
  (invariant 9) fails the whole Work. Nothing is silently corrected, because a
  correction is a clinical decision.

**What this module deliberately does not contain.**

- **Handlers.** The extraction LLM is files/03 §4.9.1 row 9 behind ADR-006's
  gateway (INT-095); the document parser is INT-12x. The queue takes its
  handlers by injection, so there is no stand-in on a serving path and the
  mocks live in tests (CLAUDE.md invariant 17).
- **The state/background lane split of files/12 §7.4.** That split needs six
  work types (``confirm_proposed_fact``, ``reconcile_meds``, ``note_finalize``,
  ``retrieve_records``, ``draft_note_delta``, ``score_wellbeing_segment``) and
  a ``ProposedFact`` type, none of which exist on this branch — a half-built
  lane would be worse than none. What survives of §7.4 here is its load-bearing
  safety property, enforced directly: a ``parse_document`` result may not carry
  slot updates, because a document's facts reach the record through a confirm
  step and never through a write from the work that read the document. The
  consequence of the missing split is recorded in docs/evidence/INT-092.md: a
  document parse still occupies the single in-flight slot.
- **The RED preemption path.** Only its authorisation gate is called here
  (:func:`~intake_voice_runtime.talker.preemption.authorise_preempt`) and its
  queue effect (:meth:`WorkQueue.seal_for_red`). The flush → cancel →
  pre-positioned-clip sequence over the data channel is INT-093, and files/03
  §4.6 invariant 4 requires it to touch no media transport.
- **A metric.** Every emitted metric must exist in
  ``observability/metrics_catalog.yaml`` (CLAUDE.md invariant 13) and no
  queue-depth or work-duration row is catalogued yet, so this module emits
  none rather than emitting one the catalogue does not know.
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Final, Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.triage import CandidateFlag, TriageResult
from pydantic import Field, ValidationError

from intake_voice_runtime.ports import (
    Clock,
    EngineSnapshot,
    WorkRequest,
    WorkState,
    WorkTicket,
    WorkType,
    work_key,
)
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    InlinePayload,
    PreemptRefused,
    Presentation,
    Priority,
    authorise_preempt,
)

__all__ = [
    "ACTIVITY_LABELS_TR",
    "RED_SEALED_WORK_TYPES",
    "QueueSealedError",
    "ReadOnlyContext",
    "SessionStateWriter",
    "WorkFailure",
    "WorkHandler",
    "WorkOutcome",
    "WorkQueue",
    "WorkRecord",
]


#: The fixed activity-label table of files/03 §4.6 invariant 10.
#:
#: files/03 §4.3 states two labels verbatim — ``"belge okunuyor"`` and
#: ``"not güncelleniyor"`` — and only the first names a work type that exists
#: here. The other two work types have **no** label, because a label is
#: patient-facing Turkish copy and no human has supplied one; an unset label
#: renders nothing rather than an invented sentence (CLAUDE.md: never invent a
#: value to unblock yourself). The ask is in docs/evidence/INT-092.md.
ACTIVITY_LABELS_TR: Final[Mapping[WorkType, str]] = {WorkType.PARSE_DOCUMENT: "belge okunuyor"}

#: files/12 §7.1: *"On RED the queue is sealed to ``{note_finalize,
#: clinic_notify, audit_flush}``"*. None of those three is a member of
#: :class:`~intake_voice_runtime.ports.WorkType` on this branch, so the
#: allow-list is empty and a sealed queue refuses every submission. That is
#: the fail-closed state, not an omission: the seal admits exactly the work
#: the blueprint names, and the blueprint names nothing that exists yet.
RED_SEALED_WORK_TYPES: Final[frozenset[WorkType]] = frozenset()

#: files/03 §4.3 lists the terminal states a Work may reach through the pump.
_TERMINAL_STATES: Final[frozenset[WorkState]] = frozenset(
    {
        WorkState.COMPLETED,
        WorkState.COMPLETED_SUPPRESSED,
        WorkState.FAILED,
        WorkState.CANCELLED,
    }
)


class QueueSealedError(RuntimeError):
    """The queue is sealed on RED and this work type is not admitted."""


class WorkFailure(enum.StrEnum):
    """Why a Work failed — a closed set, because the reason reaches the client.

    files/03 §4.6 invariant 10: *"no session ids, prompts, or reasoning reach
    the client"*. A handler's exception message can contain a transcript
    fragment, so it is never carried: the class of failure is, the detail is
    not (CLAUDE.md invariant 6).
    """

    NO_HANDLER = "no_handler"
    HANDLER_ERROR = "handler_error"
    RESULT_REFUSED = "result_refused"
    PREEMPT_REFUSED = "preempt_refused"
    RESTART = "restart"


class ReadOnlyContext(FrozenModel):
    """What a handler is given: the engine's published snapshot, and no mutator.

    Handlers never write ``SessionState``. They return a :class:`WorkOutcome`
    and the queue applies it under the engine lock, which is how *"all writes
    to ``SessionState`` serialised"* is a property of the queue rather than a
    convention every handler has to honour.
    """

    work_id: str = Field(min_length=1)
    snapshot: EngineSnapshot


class WorkOutcome(FrozenModel):
    """What a handler produces — the parts of files/03 §4.3's result shape.

    The queue assembles the ``Presentation`` from these fields rather than
    accepting a built one, so invariant 22's guard (*"no numeric slot value is
    spoken without a matching ``inline`` render on the same ``work_id``"*)
    fires **inside the queue**, where the refusal can fail the Work, instead of
    inside the handler, where it would surface as an ordinary crash.
    """

    delivery_class: DeliveryClass = Field(
        description="How this result is delivered (files/12 §6). No default: how "
        "long a result may wait before it interrupts a patient is a clinical "
        "decision, so the handler states it."
    )
    slot_updates: dict[str, JsonValue] = Field(
        default_factory=dict, description="Reconcile-behind writes (files/03 §5)."
    )
    clarification_needed: bool = Field(default=False)
    inline: InlinePayload | None = Field(
        default=None, description="Goes to the data channel immediately (files/03 §4.3)."
    )
    speech_tr: str | None = Field(
        default=None, description="Spoken at a safe insertion window, never before."
    )
    speech_numerics: tuple[str, ...] = Field(
        default=(), description="Slot keys whose numeric values the speech states."
    )
    triage_update: TriageResult | None = Field(default=None)
    candidate_flags: tuple[CandidateFlag, ...] = Field(default=())
    priority: Priority = Field(default=Priority.NORMAL)


#: A Work handler: read-only context in, declarative outcome out.
WorkHandler = Callable[[ReadOnlyContext, WorkRequest], Awaitable[WorkOutcome]]


class WorkRecord(FrozenModel):
    """The delivery receipt of files/03 §4.3 — *"not a mirror of internal
    reasoning"*.

    Public fields only: the request's ids, the timestamps, the generic activity
    label, the delivery state and a closed failure class. There is deliberately
    **no** ``session_id`` field (files/03 §4.6 invariant 10) and no transcript,
    prompt or model output anywhere in it (CLAUDE.md invariant 6).
    """

    work_id: str = Field(min_length=1)
    work_type: WorkType
    step_id: str = Field(min_length=1)
    state: WorkState
    queued_at_ms: float = Field(ge=0.0)
    started_at_ms: float | None = Field(default=None)
    finished_at_ms: float | None = Field(default=None)
    activity_label_tr: str | None = Field(default=None)
    failure: WorkFailure | None = Field(default=None)
    delivered: bool = Field(default=False)


@runtime_checkable
class SessionStateWriter(Protocol):
    """The engine, as the queue needs it — ``IntakeEngine`` satisfies it.

    Structural rather than nominal so the queue never imports
    ``clinical_agent``: Layer B's FSM is INT-081's surface and the queue is
    the thing that serialises access to it, not a thing that knows its shape.
    """

    @property
    def snapshot(self) -> EngineSnapshot: ...

    def apply_extraction(
        self,
        step_id: str,
        slot_updates: Mapping[str, JsonValue],
        clarification_needed: bool = False,
    ) -> None: ...


class _Refused(Exception):
    """Internal: a result the queue will not represent. Carries no detail."""

    def __init__(self, failure: WorkFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure


@dataclass
class WorkQueue:
    """One session's Backend Work queue: FIFO, one in flight, idempotent.

    Satisfies :class:`~intake_voice_runtime.ports.WorkSubmitter`, so a
    ``TalkerSession`` takes it in place of a double with no change on Layer A.
    """

    session_id: str
    engine: SessionStateWriter
    clock: Clock
    handlers: Mapping[WorkType, WorkHandler]
    rule_ids: frozenset[str] = frozenset()

    _fifo: list[str] = field(default_factory=list, init=False)
    _requests: dict[str, WorkRequest] = field(default_factory=dict, init=False)
    _records: dict[str, WorkRecord] = field(default_factory=dict, init=False)
    _ready: list[BackendResult] = field(default_factory=list, init=False)
    _suppressed: set[str] = field(default_factory=set, init=False)
    _in_flight: list[str] = field(default_factory=list, init=False)
    _sealed: bool = field(default=False, init=False)
    _queue_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _engine_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    # --- the port the Talker holds (no member here is awaitable) -----------------------

    def submit(self, request: WorkRequest) -> WorkTicket:
        """Enqueue one Work and return its ticket immediately (ADR-009).

        Idempotent on the content-addressed ``work_id`` (files/12 §7.5): a
        request whose id is already known returns that record's current
        ticket and is neither enqueued nor run a second time.
        """
        if request.session_id != self.session_id:
            raise ValueError(
                f"this queue serves one session and the request names another "
                f"(work_type={request.work_type.value}) — a per-session FIFO that "
                "accepted foreign work would serialise nothing (files/03 §4.3)"
            )
        work_id = work_key(request)
        known = self._records.get(work_id)
        if known is not None:
            return WorkTicket(work_id=work_id, state=known.state)
        if self._sealed and request.work_type not in RED_SEALED_WORK_TYPES:
            raise QueueSealedError(
                f"the queue is sealed on RED and admits only "
                f"{sorted(t.value for t in RED_SEALED_WORK_TYPES) or 'nothing'} "
                "(files/12 §7.1)"
            )
        self._records[work_id] = WorkRecord(
            work_id=work_id,
            work_type=request.work_type,
            step_id=request.step_id,
            state=WorkState.QUEUED,
            queued_at_ms=self.clock.now_ms(),
            activity_label_tr=ACTIVITY_LABELS_TR.get(request.work_type),
        )
        self._requests[work_id] = request
        self._fifo.append(work_id)
        return WorkTicket(work_id=work_id, state=WorkState.QUEUED)

    def cancel(self, work_id: str, reason: str) -> WorkTicket:
        """Cancel a Work (files/12 §7.1). ``reason`` is the caller's, not stored.

        A **queued** item is dequeued synchronously and becomes ``CANCELLED``.
        A **running** item is never aborted mid-write: it finishes, its write
        stands, and its result is suppressed rather than deleted — so a patient
        retraction is a supersession. The reason is not written to the record,
        which carries a closed vocabulary only (CLAUDE.md invariant 6).
        """
        record = self._records.get(work_id)
        if record is None:
            raise LookupError(f"no such work: {work_id!r}")
        if record.state is WorkState.QUEUED:
            self._fifo.remove(work_id)
            self._transition(work_id, state=WorkState.CANCELLED)
        elif record.state is WorkState.RUNNING:
            self._suppressed.add(work_id)
        return WorkTicket(work_id=work_id, state=self._records[work_id].state)

    def drain_results(self) -> tuple[BackendResult, ...]:
        """Whatever is ready. Never blocks; never returns a result twice."""
        drained = tuple(self._ready)
        self._ready.clear()
        for result in drained:
            self._transition(result.work_id, delivered=True)
        return drained

    # --- reads ----------------------------------------------------------------------------

    @property
    def pending_work_ids(self) -> tuple[str, ...]:
        """Queued and not yet started, in FIFO order."""
        return tuple(self._fifo)

    @property
    def in_flight_work_ids(self) -> tuple[str, ...]:
        """At most one, always — the acceptance's own words, as a read."""
        return tuple(self._in_flight)

    @property
    def sealed(self) -> bool:
        return self._sealed

    def record(self, work_id: str) -> WorkRecord:
        """The public delivery receipt for one Work."""
        record = self._records.get(work_id)
        if record is None:
            raise LookupError(f"no such work: {work_id!r}")
        return record

    def records(self) -> tuple[WorkRecord, ...]:
        """Every receipt, in submission order."""
        return tuple(self._records.values())

    def retained_frames(self) -> int:
        """How many audio buffers this queue still references — zero.

        Counted rather than asserted, so a future field that *did* retain
        audio would be caught (CLAUDE.md invariant 3).
        """
        return sum(1 for value in vars(self).values() if isinstance(value, bytes | bytearray))

    # --- the pump (Layer B's own task, never the Talker's) ---------------------------------

    async def run_pending(self) -> int:
        """Drain the queue in FIFO order, one Work at a time.

        The lock is held for the whole drain, so concurrent pumps do not
        produce concurrent Work: the second caller waits and then finds an
        empty queue. Returns how many Works this call ran.

        Every id in ``_fifo`` is ``QUEUED``: :meth:`submit` is the only place
        that appends, and :meth:`cancel`, :meth:`seal_for_red` and
        :meth:`fail_active_work_on_restart` — the only transitions out of
        ``QUEUED`` — each remove the id in the same statement. So the pump
        needs no re-check, and there is no branch here that cannot be reached.
        """
        ran = 0
        async with self._queue_lock:
            while self._fifo:
                await self._run_one(self._fifo.pop(0))
                ran += 1
        return ran

    async def _run_one(self, work_id: str) -> None:
        request = self._requests[work_id]
        self._in_flight.append(work_id)
        self._transition(work_id, state=WorkState.RUNNING, started_at_ms=self.clock.now_ms())
        try:
            try:
                outcome, result = await self._produce(work_id, request)
            except _Refused as refused:
                self._transition(
                    work_id,
                    state=WorkState.FAILED,
                    finished_at_ms=self.clock.now_ms(),
                    failure=refused.failure,
                )
                return
            async with self._engine_lock:
                if outcome.slot_updates or outcome.clarification_needed:
                    self.engine.apply_extraction(
                        request.step_id, outcome.slot_updates, outcome.clarification_needed
                    )
            self._transition(
                work_id,
                state=(
                    WorkState.COMPLETED_SUPPRESSED
                    if work_id in self._suppressed
                    else WorkState.COMPLETED
                ),
                finished_at_ms=self.clock.now_ms(),
            )
            # Only a Work that actually reached COMPLETED speaks. A cancel
            # while running lands it in COMPLETED_SUPPRESSED, and a restart
            # left it FAILED before the handler returned — in both cases the
            # write stands and the speech does not happen.
            if self._records[work_id].state is WorkState.COMPLETED:
                self._ready.append(result)
        finally:
            self._in_flight.remove(work_id)

    async def _produce(
        self, work_id: str, request: WorkRequest
    ) -> tuple[WorkOutcome, BackendResult]:
        """Run the handler and build the result — **before** any engine write.

        Order is the point. A result that cannot be represented (invariant 22)
        or cannot be authorised (invariant 9) fails the whole Work, and the
        write it would have carried does not happen. Repairing it — dropping
        the number, downgrading the priority, storing the slots anyway — would
        be an engineering decision standing in for a clinical one.
        """
        handler = self.handlers.get(request.work_type)
        if handler is None:
            raise _Refused(WorkFailure.NO_HANDLER)
        try:
            outcome = await handler(
                ReadOnlyContext(work_id=work_id, snapshot=self.engine.snapshot), request
            )
        except Exception as err:  # noqa: BLE001 - the class is kept, the detail never is
            raise _Refused(WorkFailure.HANDLER_ERROR) from err
        if request.work_type is WorkType.PARSE_DOCUMENT and outcome.slot_updates:
            # files/12 §7.4: a document's facts reach the record through a
            # confirm step, never through a write from the work that read it.
            raise _Refused(WorkFailure.RESULT_REFUSED)
        return outcome, self._build_result(work_id, outcome)

    def _build_result(self, work_id: str, outcome: WorkOutcome) -> BackendResult:
        try:
            result = BackendResult(
                work_id=work_id,
                state=WorkState.COMPLETED,
                delivery_class=outcome.delivery_class,
                presentation=Presentation(
                    inline=outcome.inline,
                    speech_tr=outcome.speech_tr,
                    speech_numerics=outcome.speech_numerics,
                    triage_update=outcome.triage_update,
                    candidate_flags=outcome.candidate_flags,
                ),
                priority=outcome.priority,
            )
        except ValidationError as err:
            raise _Refused(WorkFailure.RESULT_REFUSED) from err
        try:
            authorise_preempt(result, rule_ids=self.rule_ids)
        except PreemptRefused as err:
            raise _Refused(WorkFailure.PREEMPT_REFUSED) from err
        return result

    # --- lifecycle -------------------------------------------------------------------------

    def seal_for_red(self) -> tuple[str, ...]:
        """files/12 §7.1: on RED, cancel queued work and seal the queue.

        The running item is left alone — *"it may be the item that produced the
        RED"* — and completes normally. Returns the ids cancelled.
        """
        self._sealed = True
        cancelled = tuple(self._fifo)
        for work_id in cancelled:
            self._transition(work_id, state=WorkState.CANCELLED)
        self._fifo.clear()
        return cancelled

    def fail_active_work_on_restart(self) -> tuple[str, ...]:
        """files/03 §4.3: *"active Work becomes ``failed(reason=restart)``;
        completed results and delivery state are persisted."*

        Content-addressed ids are what make this safe to do bluntly: the
        session re-submits the last unprocessed transcript and gets the same
        ``work_id`` back, so a restart costs one re-run and never a duplicate.
        """
        active = tuple(
            record.work_id
            for record in self._records.values()
            if record.state in (WorkState.QUEUED, WorkState.RUNNING)
        )
        for work_id in active:
            self._transition(
                work_id,
                state=WorkState.FAILED,
                finished_at_ms=self.clock.now_ms(),
                failure=WorkFailure.RESTART,
            )
        self._fifo.clear()
        # ``_in_flight`` is not cleared here: the running coroutine's own
        # ``finally`` releases it, and forcing it would leave that coroutine
        # unable to unwind cleanly. Its record is already terminal, so the
        # result it eventually produces is dropped rather than delivered.
        return active

    # --- internals -------------------------------------------------------------------------

    def _transition(self, work_id: str, **changes: object) -> None:
        record = self._records[work_id]
        state = changes.get("state")
        if isinstance(state, WorkState) and record.state in _TERMINAL_STATES:
            # A terminal Work is terminal: a late cancel or a second completion
            # must not resurrect it, which is the other half of "duplicates
            # impossible" (files/03 §4.3 state machine).
            return
        self._records[work_id] = record.model_copy(update=changes)
