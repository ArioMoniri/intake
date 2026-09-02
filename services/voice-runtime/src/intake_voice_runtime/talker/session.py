"""The Talker itself: one turn, and the four things it may never do.

files/03 §4.1 draws the loop this module implements:

    Layer A Talker ─ protocol_next() ──► scripted question? ──► play cached clip
          │                              dynamic text?     ──► LLM ─► PolicyGuard ─► TTS
          │ submit_utterance(step_id, transcript) → returns work_id immediately
          ▼
    Layer B Clinical Backend Agent (per-session FIFO, one in flight)

A turn is: read the snapshot (lock-free), hand any transcript to Layer B
without waiting, drain whatever Layer B has *already* finished, tick the
insertion scheduler against the current duplex state, then speak the next
step. Every step in that list is non-blocking with respect to Backend Work,
which is the whole point of ADR-009 and the reason the turn budget survives a
stalled backend.

What this module deliberately does **not** contain:

- **the RED preemption path.** Only its authorisation gate lives here
  (:func:`~intake_voice_runtime.talker.preemption.authorise_preempt`); the
  flush → cancel → pre-positioned-clip sequence over the data channel is
  INT-093, and files/03 §4.6 invariant 4 requires that path to touch no media
  transport at all — which is precisely why it is not plumbed through this
  audio sink.
- **an LLM.** Dynamic text arrives as a string from Layer B or from the
  Talker's small model behind ADR-006's gateway; this module routes and guards
  it. There is no model call here to mock.
- **the safe-bridge copy.** PolicyGuard reports ``bridge_required``; the
  sentence spoken in its place is clinical patient copy that no human has
  supplied, so :class:`TalkerConfig` leaves it ``None`` and the turn stays
  silent rather than inventing one. The ask is in docs/evidence/INT-091.md.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.ports import (
    AskLedger,
    AudioSink,
    ClipStore,
    Clock,
    EngineSnapshotSource,
    PatientMemoryKey,
    PatientMemoryStore,
    PatientRecord,
    SpeechSynthesizer,
    WorkRequest,
    WorkSubmitter,
    WorkTicket,
    WorkType,
    work_key,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import NextStep
from intake_voice_runtime.talker.clips import ClipCatalogue
from intake_voice_runtime.talker.delivery import (
    ADAPTIVE_JITTER_THRESHOLD_MS,
    DeliveryDeadlines,
    DuplexState,
    TurnYieldPolicy,
)
from intake_voice_runtime.talker.insertion import InsertionScheduler, PendingSpeech, Speak
from intake_voice_runtime.talker.policy_guard import FormOfAddress, PolicyGuard
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    Priority,
    authorise_preempt,
)
from intake_voice_runtime.talker.red_path import (
    REGISTER_DELIVERY,
    RedPathNotWired,
    RedPreemption,
    RedPreemptionOutcome,
)
from intake_voice_runtime.talker.speculation import PreemptiveGeneration
from intake_voice_runtime.talker.speech import SpeechRouter
from intake_voice_runtime.talker.tools import (
    BACKCHANNEL_LEXEMES,
    MIN_CONSENT_CONFIDENCE,
    NO_LEXEMES,
    PERMISSION_WINDOW_MS,
    YES_LEXEMES,
    ConsentDecision,
    MemoryOp,
    PermissionAck,
    PermissionRequest,
    PermissionState,
    RepeatDirective,
    RepeatReason,
    normalise_tr,
)
from intake_voice_runtime.transcript import SessionTranscripts, TranscriptDeposit

__all__ = [
    "UNMEASURED_JITTER",
    "AskLedgerNotWired",
    "TalkerConfig",
    "TalkerSession",
    "TurnHold",
    "TurnOutcome",
]


class TurnHold(enum.StrEnum):
    """Why a turn asked nothing. ``None`` on a turn that spoke."""

    #: files/03 §4.4b — an open patient turn has not yielded the floor.
    PATIENT_HOLDS_FLOOR = "patient_holds_floor"
    #: files/03 §4.6 — a patient-facing RED stopped the intake.
    INTAKE_STOPPED = "intake_stopped"
    #: files/03 §4.5 — the step just spoken has not been acknowledged by the
    #: engine yet, so asking again would ask the same question twice. Layer A
    #: cannot take the engine lock (invariant 9), so the mark is eventual and
    #: this is the window it is eventual in: one pump, never more.
    AWAITING_ASK_ACK = "awaiting_ask_ack"


#: files/03 §4.2 keys the yield floor off *measured* uplink jitter: *"150 ms
#: when measured uplink jitter p95 < 30 ms, and 250 ms otherwise."* A session
#: nothing has measured is therefore in the *otherwise* branch, not in the fast
#: one — which is why this constant sits exactly **on** the threshold rather
#: than below it. Defaulting the other way would cut patients off in the
#: waiting room, which §4.5.2 names as the reason the drop is conditional at
#: all.
UNMEASURED_JITTER = TurnYieldPolicy(uplink_jitter_p95_ms=ADAPTIVE_JITTER_THRESHOLD_MS)


class AskLedgerNotWired(RuntimeError):
    """The session spoke a step and has nowhere to record that it did.

    Raised rather than shrugged: without the ask note the engine never leaves
    ``NOT_ASKED``, so every answer is dropped by ``IntakeEngine._bind`` and the
    session looks like a patient who said nothing. Silence would be the worst
    of the three outcomes.
    """


class _UnwiredAskLedger:
    """The fail-closed default. Satisfies the port and refuses every call."""

    def note_asked(self, step_id: str) -> None:
        raise AskLedgerNotWired(
            f"spoke {step_id!r} with no AskLedger bound — bind the session's Backend "
            "agent (intake_voice_runtime.composition) so files/03 §4.5's ask-ahead "
            "mark has a producer"
        )


class TalkerConfig(FrozenModel):
    """Everything about one session that does not change during it."""

    session_id: str = Field(min_length=1)
    voice_id: str = Field(min_length=1)
    profile: VoiceProfile
    protocol_hash: str = Field(min_length=1, description="The session's pinned pack hash.")
    rule_ids: frozenset[str] = Field(
        default=frozenset(),
        description="Rule ids of the pinned pack; an empty set authorises no preempt.",
    )
    deadlines: DeliveryDeadlines = Field(default_factory=DeliveryDeadlines)
    safe_bridge_clip_id: str | None = Field(
        default=None,
        description="The cached bridge played when PolicyGuard drops a whole turn "
        "(files/03 §4.2). Unset: its Turkish is clinical copy awaiting sign-off, "
        "and silence is safer than an invented sentence (CLAUDE.md).",
    )


class TurnOutcome(FrozenModel):
    """What one turn did, and what it cost on the session clock."""

    step_id: str | None = Field(default=None)
    spoken_text: str = Field(default="")
    from_clip: bool = Field(default=False)
    work_id: str | None = Field(default=None)
    drained_results: int = Field(default=0, ge=0)
    delivered_work_ids: tuple[str, ...] = Field(default=())
    held: TurnHold | None = Field(
        default=None,
        description="Set when the turn deliberately asked nothing. A held turn is not "
        "a failed turn: Layer B still ran, results were still drained, and anything "
        "the insertion scheduler judged deliverable was still delivered.",
    )
    elapsed_ms: float = Field(ge=0.0)


@dataclass
class TalkerSession:
    """Layer A for one intake session."""

    config: TalkerConfig
    engine: EngineSnapshotSource
    backend: WorkSubmitter
    catalogue: ClipCatalogue
    clip_store: ClipStore
    synthesizer: SpeechSynthesizer
    sink: AudioSink
    memory: PatientMemoryStore
    clock: Clock
    policy_guard: PolicyGuard | None = None
    preemption: RedPreemption | None = None
    #: Where a deposited transcript lives while its Work is queued. Layer A
    #: holds the **deposit** half only — it cannot read one back — and the
    #: queue still carries nothing but the digest (CLAUDE.md invariants 6, 14).
    transcripts: TranscriptDeposit = field(default_factory=SessionTranscripts)
    #: files/03 §4.2's dynamic-turn speculation. ``None`` means no speculation
    #: is attempted at all, which is the shipped default: it is a latency
    #: optimisation and an unwired one costs correctness nothing.
    speculation: PreemptiveGeneration | None = None
    ask_ledger: AskLedger = field(init=False)
    guard: PolicyGuard = field(init=False)
    scheduler: InsertionScheduler = field(init=False)
    router: SpeechRouter = field(init=False)
    preempts: tuple[BackendResult, ...] = field(default=(), init=False)
    duplex: DuplexState = field(init=False)
    yield_policy: TurnYieldPolicy = field(default=UNMEASURED_JITTER, init=False)
    undelivered: list[str] = field(default_factory=list, init=False)
    _last_step: NextStep | None = field(default=None, init=False)
    #: The step the Talker actually spoke, and the snapshot version it was
    #: spoken at. Together they are the ask-acknowledgement gate: while the
    #: engine still offers that step at that same version, the mark has not
    #: landed and the turn holds rather than asking it twice.
    _asked_step: NextStep | None = field(default=None, init=False)
    _asked_at_version: int = field(default=-1, init=False)
    _permissions: dict[str, PermissionRequest] = field(default_factory=dict, init=False)
    _playback: list[tuple[float, float]] = field(default_factory=list, init=False)
    _red_stopped: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        # The Backend agent is the ledger when it is one — one object, one
        # session, and the notes then queue behind the same lock the Work
        # does. Anything else gets the refusing default.
        self.ask_ledger = (
            self.backend if isinstance(self.backend, AskLedger) else _UnwiredAskLedger()
        )
        self.guard = self.policy_guard or PolicyGuard(profile=self.config.profile)
        self.scheduler = InsertionScheduler(
            deadlines=self.config.deadlines, note_flag=self._note_undelivered
        )
        self.router = SpeechRouter(
            voice_id=self.config.voice_id,
            clip_store=self.clip_store,
            synthesizer=self.synthesizer,
            sink=self.sink,
        )
        self.duplex = DuplexState(patient_silence_ms=0.0, talker_idle=True, pending_response=False)

    # --- the six tools, as methods -------------------------------------------------

    def protocol_next(self) -> NextStep | None:
        """A lock-free atomic attribute read (files/12 §7.2)."""
        snapshot = self.engine.snapshot
        if snapshot.next_step is None:
            self._last_step = None
            return None
        self._last_step = NextStep.of(snapshot.next_step, snapshot.version)
        return self._last_step

    def ask_acknowledged(self, offered: NextStep | None) -> bool:
        """Has Layer B recorded the ask for the step we last spoke?

        The engine bumps its snapshot version on every commit, and
        ``mark_asked`` is a commit — so "the same step is still offered at the
        same version" means the note has not been applied yet, and asking now
        would ask it twice. Any other combination means the engine has moved:
        a step legitimately re-offered after a contradicted confirm (files/09
        §3) carries a newer version and is asked again, as it should be.
        """
        if self._asked_step is None or offered is None:
            return True
        return not (
            offered.step_id == self._asked_step.step_id
            and offered.engine_version == self._asked_at_version
        )

    def submit_utterance(self, step_id: str, transcript: str) -> WorkTicket:
        """Return a ticket immediately; Layer B runs on its own time.

        The transcript is **deposited**, not carried: it goes into the
        session's vault (:mod:`intake_voice_runtime.transcript`) and the
        request carries the digest the vault keyed it by, so the queue stays
        PHI-free by construction (CLAUDE.md invariants 6, 14). The deposit is
        also the boundary crossing, so a transcript carrying the data-block
        control token is refused here — before a Work exists — rather than
        being trimmed downstream (INT-083).
        """
        input_hash = self.transcripts.deposit(transcript)
        request = WorkRequest(
            session_id=self.config.session_id,
            work_type=WorkType.EXTRACT_SLOTS,
            step_id=step_id,
            input_hash=input_hash,
            protocol_hash=self.config.protocol_hash,
            engine_version=self._engine_version_of(step_id),
        )
        ticket = self.backend.submit(request)
        if ticket.work_id != work_key(request):
            raise ValueError(
                "Layer B minted a work_id instead of deriving it; a restart would "
                "then duplicate every re-submitted transcript (files/12 §7.5)"
            )
        return ticket

    def _engine_version_of(self, step_id: str) -> int:
        """The snapshot version the answered question was **offered** at.

        files/12 §7.2 carries this back *"so Layer B can tell a legitimate
        ask-ahead answer from one bound to an invalidated step"*. After
        INT-095 the frontier has already moved past the question by the time
        its answer arrives, so the version that matters is the one stamped
        when the step was spoken, not the one the next step carries.
        """
        if self._asked_step is not None and self._asked_step.step_id == step_id:
            return self._asked_step.engine_version
        return self._last_step.engine_version if self._last_step else 0

    def cancel_work(self, work_id: str, reason: str) -> WorkTicket:
        return self.backend.cancel(work_id, reason)

    def request_repeat_or_clarify(self, reason: RepeatReason) -> RepeatDirective:
        """Re-ask the current step verbatim — never a reworded second attempt."""
        step = self._last_step or self.protocol_next()
        if step is None:
            raise LookupError("there is no current step to repeat")
        cached = self.catalogue.get(step.text_tr)
        return RepeatDirective(
            text_tr=step.text_tr,
            clip_id=cached.clip_id if cached else None,
            reason=reason,
        )

    def patient_memory(
        self, op: MemoryOp, key: str | PatientMemoryKey, value: str | None = None
    ) -> PatientRecord | None:
        """The key set is closed: name, form of address, pace, language."""
        try:
            memory_key = PatientMemoryKey(key)
        except ValueError as err:
            raise ValueError(
                f"{key!r} is not in the closed patient-memory key set "
                f"{sorted(k.value for k in PatientMemoryKey)} — patient_memory holds "
                "nothing clinical (files/03 §4.2)"
            ) from err
        if op is MemoryOp.RECALL:
            return self.memory.recall(memory_key.value)
        if op is MemoryOp.FORGET:
            self.memory.forget(memory_key.value)
            return None
        if value is None:
            raise ValueError("remember needs a value")
        record = self.memory.remember(memory_key.value, value)
        if memory_key is PatientMemoryKey.FORM_OF_ADDRESS:
            # Mirroring, and only mirroring, can move the register off `siz`.
            self.guard.form_of_address = FormOfAddress(record.value)
        return record

    def open_permission_request(self, request: PermissionRequest) -> None:
        """Layer B opens a consent prompt; the Talker relays the answer."""
        self._permissions[request.request_id] = request

    def respond_permission(
        self,
        *,
        request_id: str,
        decision: ConsentDecision,
        span_start_ms: float,
        span_end_ms: float,
        asr_confidence: float,
        prompt_text_hash: str,
    ) -> PermissionAck:
        """The files/12 §7.6 gate ladder, in order, failing closed at each rung."""

        def refuse(reason: str) -> PermissionAck:
            return PermissionAck(
                request_id=request_id, state=PermissionState.REFUSED, reason=reason
            )

        request = self._permissions.get(request_id)
        if request is None:
            return refuse("no open consent request with that id")
        if self.clock.now_ms() - request.opened_at_ms > PERMISSION_WINDOW_MS:
            return refuse("the consent prompt is older than sixty seconds")
        if prompt_text_hash != request.prompt_text_hash:
            return refuse("the prompt hash does not match the open request")
        if span_start_ms < request.prompt_audio_ended_ms:
            return refuse("the answer began before the prompt finished playing")
        if any(span_start_ms < end and start < span_end_ms for start, end in self._playback):
            return refuse(
                "the answer overlaps agent playback — a backchannel inside our own "
                "audio can never be consent"
            )
        if asr_confidence < MIN_CONSENT_CONFIDENCE:
            return refuse("transcription confidence is below the consent floor")

        lexeme = normalise_tr(decision.value)
        if lexeme in BACKCHANNEL_LEXEMES:
            return refuse("a backchannel is not a decision")
        if decision is ConsentDecision.NO or lexeme in NO_LEXEMES:
            self._permissions.pop(request_id, None)
            return PermissionAck(
                request_id=request_id, state=PermissionState.DECLINED, reason="declined"
            )
        if decision is not ConsentDecision.YES and lexeme not in YES_LEXEMES:
            return refuse("the answer is not a whitelisted consent lexeme")

        if request.parent_request_id is None:
            return PermissionAck(
                request_id=request_id,
                state=PermissionState.PROVISIONAL,
                reason="awaiting the read-back confirmation",
            )
        self._permissions.pop(request_id, None)
        return PermissionAck(
            request_id=request_id,
            state=PermissionState.GRANTED,
            reason="confirmed on the read-back",
        )

    # --- Layer B results ---------------------------------------------------------------

    def accept_result(self, result: BackendResult) -> None:
        """Route one result: preempt (authorised) or the insertion scheduler."""
        if result.priority is Priority.PREEMPT:
            authorise_preempt(result, rule_ids=self.config.rule_ids)
            self.preempts = (*self.preempts, result)
            return
        if result.presentation.speech_tr is None:
            return
        self.scheduler.enqueue(
            PendingSpeech(
                work_id=result.work_id,
                delivery_class=result.delivery_class,
                presentation=result.presentation,
            ),
            now_ms=self.clock.now_ms(),
        )

    async def deliver_preempt(
        self, result: BackendResult, *, evaluated_at_ms: float
    ) -> RedPreemptionOutcome:
        """Run the RED preemption path for one rules-engine RED (INT-093).

        ``evaluated_at_ms`` is the moment ``packages/protocols/triage``
        produced the determination — files/02 §8.2 measures the 300 ms from
        rule evaluation, and stamping it here instead would silently discount
        the Layer B hop from the budget it is policing. There is no default
        for the same reason invariant 21 permits no default register.

        The provenance gate runs again before the path: it is cheap, and this
        is the one entry point a future caller could reach without having gone
        through :meth:`accept_result`.
        """
        authorise_preempt(result, rule_ids=self.config.rule_ids)
        if self.preemption is None:
            raise RedPathNotWired(
                "a rules-engine RED arrived and no RED preemption path is bound to "
                "this session; refusing rather than continuing the intake past a "
                "life threat (CLAUDE.md invariant 21)"
            )
        triage = result.presentation.triage_update
        register = getattr(triage, "register", None)
        try:
            return await self.preemption.trigger(result, evaluated_at_ms=evaluated_at_ms)
        finally:
            if register is not None and REGISTER_DELIVERY[register].stops_intake:
                self._red_stopped = True

    @property
    def red_stopped(self) -> bool:
        """True once a patient-facing RED stopped the intake (files/03 §4.6:
        *Kırmızı (RED) = preempt, stop intake*). A ``DEFERRED_CLINICIAN`` RED
        leaves it false: its whole definition is that the patient surface does
        not change."""
        return self._red_stopped

    def _note_undelivered(self, work_id: str) -> None:
        """The transactional note flag of files/12 §6.

        Layer B owns the database transaction (INT-092); until it does, the
        only honest behaviour is to record nothing and let the item expire
        unflagged — which is why this is a named seam rather than a silent
        pass-through, and why the scheduler treats a :class:`NoteFlagFailed`
        from it as a rollback.
        """
        self.undelivered.append(work_id)

    # --- the turn ------------------------------------------------------------------------

    async def take_turn(self, transcript: str | None) -> TurnOutcome:
        """One conversational turn. Nothing here awaits Backend Work."""
        started_ms = self.clock.now_ms()
        if self._red_stopped:
            # The intake stopped when the RED was delivered. Asking the next
            # question after a life threat is the failure the preemption
            # exists to prevent, so the loop yields an empty turn rather than
            # relying on a caller to stop calling it.
            return TurnOutcome(
                held=TurnHold.INTAKE_STOPPED, elapsed_ms=self.clock.now_ms() - started_ms
            )
        # One snapshot read per turn (files/12 §7.2) — the hot path touches
        # the engine exactly once, and `test_talker_never_awaits` counts it.
        step = self.protocol_next()

        # files/03 §4.5: the transcript answers the question that was
        # SPOKEN, which after INT-095 is no longer whatever the frontier
        # happens to be offering — the engine has already moved on to the next
        # step by then. Attributing it to the frontier head is how an answer
        # comes to bind to a question the patient never heard. Before the
        # first question there is nothing spoken to attribute to, and the head
        # is then the only candidate; the engine drops it anyway, because
        # nothing binds to a question that was not asked.
        answered = self._asked_step or step
        work_id: str | None = None
        if transcript is not None and answered is not None:
            work_id = self.submit_utterance(answered.step_id, transcript).work_id

        drained = self.backend.drain_results()
        for result in drained:
            if isinstance(result, BackendResult):
                self.accept_result(result)

        delivered: list[str] = []
        for decision in self.scheduler.tick(self.duplex, now_ms=self.clock.now_ms()):
            if isinstance(decision, Speak) and decision.item.presentation.speech_tr is not None:
                await self._speak_backend(decision)
                delivered.append(decision.item.work_id)

        # files/03 §4.4b: a handover gap is a turn boundary, never silence and
        # never an answer. Asking over an open patient turn is the mirror of
        # that defect — it binds an answer to a question they did not hear —
        # so the question waits and everything else about the turn proceeds.
        held: TurnHold | None = None
        if self.duplex.patient_holds_floor(self.yield_policy):
            held = TurnHold.PATIENT_HOLDS_FLOOR
        elif not self.ask_acknowledged(step):
            held = TurnHold.AWAITING_ASK_ACK

        spoken = ""
        from_clip = False
        if step is not None and held is None:
            speculated = self.speculation.release() if self.speculation is not None else None
            paraphrase = (
                speculated.text_tr
                if speculated is not None and speculated.step_id == step.step_id
                else None
            )
            outcome = await self.speak_step(step, paraphrase)
            spoken, from_clip = outcome.spoken_text, outcome.from_clip
            self._note_asked(step)

        return TurnOutcome(
            step_id=step.step_id if step else None,
            spoken_text=spoken,
            from_clip=from_clip,
            work_id=work_id,
            drained_results=len(drained),
            delivered_work_ids=tuple(delivered),
            held=held,
            elapsed_ms=self.clock.now_ms() - started_ms,
        )

    def _note_asked(self, step: NextStep) -> None:
        """Record the ask with Layer B, and open the acknowledgement window.

        Called only from the speech path, and only after the step was
        actually spoken — that is the whole content of INT-095's choice
        between the two readings of "asked" (see
        :class:`~intake_voice_runtime.ports.AskLedger`). The version stamped
        here is the one the step was *offered* at, which is what
        :meth:`ask_acknowledged` compares against.
        """
        self._asked_step = step
        self._asked_at_version = step.engine_version
        self.ask_ledger.note_asked(step.step_id)

    def speculate(self, step_id: str, partial_transcript: str) -> None:
        """Start the dynamic-turn LLM on a partial utterance (INT-095).

        The speculation is buffered; nothing is synthesised and nothing is
        played. It is released — into ``speak_step``'s ``paraphrase``
        parameter, so invariant 10 still governs it — only after
        :meth:`observe_duplex` sees the patient yield the floor.
        """
        if self.speculation is None:
            raise RuntimeError(
                "no PreemptiveGeneration is bound to this session; speculation is a "
                "latency optimisation and an unwired one is refused rather than "
                "silently skipped"
            )
        self.speculation.speculate(step_id, partial_transcript)

    async def speak_step(self, step: NextStep | None, paraphrase: str | None = None) -> TurnOutcome:
        """Speak one step: clip cache first, verbatim TTS second."""
        started_ms = self.clock.now_ms()
        if step is None:
            return TurnOutcome(elapsed_ms=0.0)
        text = self.router.text_for(step, paraphrase)
        verdict = self.guard.filter(text, scripted=not step.allow_paraphrase)
        if verdict.bridge_required:
            return await self._speak_bridge(step, started_ms)
        cached = self.catalogue.get(verdict.text_tr)
        spoken = await self.router.speak(
            verdict.text_tr, clip_id=cached.clip_id if cached else None, label=step.step_id
        )
        self._record_playback(started_ms)
        return TurnOutcome(
            step_id=step.step_id,
            spoken_text=spoken.text_tr,
            from_clip=spoken.from_clip,
            elapsed_ms=self.clock.now_ms() - started_ms,
        )

    async def _speak_bridge(self, step: NextStep, started_ms: float) -> TurnOutcome:
        """PolicyGuard dropped the whole turn. Play the cached bridge if one
        has been signed off; otherwise say nothing — never improvise copy."""
        clip_id = self.config.safe_bridge_clip_id
        if clip_id is None:
            return TurnOutcome(step_id=step.step_id, elapsed_ms=self.clock.now_ms() - started_ms)
        frames = self.clip_store.fetch(clip_id)
        await self.sink.play(frames, label="safe_bridge")
        self._record_playback(started_ms)
        return TurnOutcome(step_id=step.step_id, elapsed_ms=self.clock.now_ms() - started_ms)

    async def _speak_backend(self, decision: Speak) -> None:
        """Speak Layer B's material at the window it earned."""
        started_ms = self.clock.now_ms()
        if decision.cancel_non_red_playback:
            await self.sink.cancel()
        text = decision.item.presentation.speech_tr or ""
        verdict = self.guard.filter(text, scripted=False)
        if not verdict.text_tr:
            return
        cached = self.catalogue.get(verdict.text_tr)
        await self.router.speak(
            verdict.text_tr,
            clip_id=cached.clip_id if cached else None,
            label=decision.item.work_id,
        )
        self._record_playback(started_ms)

    def _record_playback(self, started_ms: float) -> None:
        """Remember when the agent was audible — the §7.6 overlap gate reads it."""
        self._playback.append((started_ms, self.clock.now_ms()))

    @property
    def playback_intervals(self) -> tuple[tuple[float, float], ...]:
        """When the agent was audible, in session-clock milliseconds."""
        return tuple(self._playback)

    def retained_frames(self) -> int:
        """How many audio buffers this session still references.

        Zero by construction: the router hands frames to the sink and keeps no
        reference, and nothing on Layer A holds a bytes-like attribute. This
        counts the session's own attributes rather than asserting the claim,
        so a future field that *did* retain audio would be caught (invariant 3).
        """
        return sum(1 for value in vars(self).values() if isinstance(value, bytes | bytearray))

    # --- duplex state --------------------------------------------------------------------

    def observe_duplex(self, state: DuplexState, policy: TurnYieldPolicy | None = None) -> None:
        """The VAD/turn-detector view, refreshed by the transport adapter.

        ``policy`` carries the measured uplink jitter the adaptive floor keys
        off (files/03 §4.2). It arrives here rather than in
        :class:`TalkerConfig` because it is measured *during* the session and
        changes with the network, which is the whole point of §4.5b.
        """
        self.duplex = state
        if policy is not None:
            self.yield_policy = policy
        if self.speculation is None:
            return
        if state.patient_speaking:
            # The utterance the speculation was generated against has
            # continued, so the answer is stale. Discard, never store
            # (files/13 §11.3's discipline, applied to speech).
            self.speculation.resume_speech()
        elif state.patient_silence_ms >= self.yield_policy.floor_ms:
            self.speculation.confirm_end_of_utterance()
        # The third state is silence that has not yet reached the adaptive
        # floor — a handover gap, which files/03 §4.4b says is *"a turn
        # boundary, never silence and never an answer"*. The speculation stays
        # buffered: confirming there would release a sentence generated
        # against an utterance the patient is still in the middle of, and
        # discarding it would throw away the latency the speculation bought.
        # ``patient_holds_floor`` cannot be reused for this — its
        # ``patient_speaking`` conjunct makes a session nobody has spoken in
        # indistinguishable from a completed turn, which is right for asking
        # the first question and wrong for confirming an end of utterance.
