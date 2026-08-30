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

from dataclasses import dataclass, field

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.ports import (
    AudioSink,
    ClipStore,
    Clock,
    EngineSnapshotSource,
    PatientMemoryKey,
    PatientMemoryStore,
    PatientRecord,
    SpeechSynthesizer,
    WorkSubmitter,
    WorkTicket,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import NextStep
from intake_voice_runtime.talker.clips import ClipCatalogue
from intake_voice_runtime.talker.delivery import DeliveryDeadlines, DuplexState
from intake_voice_runtime.talker.insertion import InsertionScheduler, PendingSpeech, Speak
from intake_voice_runtime.talker.policy_guard import FormOfAddress, PolicyGuard
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    Priority,
    authorise_preempt,
)
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
from intake_voice_runtime.utterance import submit_extraction

__all__ = ["TalkerConfig", "TalkerSession", "TurnOutcome"]


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
    guard: PolicyGuard = field(init=False)
    scheduler: InsertionScheduler = field(init=False)
    router: SpeechRouter = field(init=False)
    preempts: tuple[BackendResult, ...] = field(default=(), init=False)
    duplex: DuplexState = field(init=False)
    undelivered: list[str] = field(default_factory=list, init=False)
    _last_step: NextStep | None = field(default=None, init=False)
    _permissions: dict[str, PermissionRequest] = field(default_factory=dict, init=False)
    _playback: list[tuple[float, float]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
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

    def submit_utterance(self, step_id: str, transcript: str) -> WorkTicket:
        """Return a ticket immediately; Layer B runs on its own time.

        The request shape and the derived-``work_id`` check are shared with
        the typed lane (:mod:`intake_voice_runtime.utterance`): both lanes
        feed one queue, and two copies of that check would be two things that
        can drift apart silently.
        """
        return submit_extraction(
            self.backend,
            session_id=self.config.session_id,
            step_id=step_id,
            transcript=transcript,
            protocol_hash=self.config.protocol_hash,
            engine_version=self._last_step.engine_version if self._last_step else 0,
        )

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
        step = self.protocol_next()

        work_id: str | None = None
        if transcript is not None and step is not None:
            work_id = self.submit_utterance(step.step_id, transcript).work_id

        drained = self.backend.drain_results()
        for result in drained:
            if isinstance(result, BackendResult):
                self.accept_result(result)

        delivered: list[str] = []
        for decision in self.scheduler.tick(self.duplex, now_ms=self.clock.now_ms()):
            if isinstance(decision, Speak) and decision.item.presentation.speech_tr is not None:
                await self._speak_backend(decision)
                delivered.append(decision.item.work_id)

        spoken = ""
        from_clip = False
        if step is not None:
            outcome = await self.speak_step(step)
            spoken, from_clip = outcome.spoken_text, outcome.from_clip

        return TurnOutcome(
            step_id=step.step_id if step else None,
            spoken_text=spoken,
            from_clip=from_clip,
            work_id=work_id,
            drained_results=len(drained),
            delivered_work_ids=tuple(delivered),
            elapsed_ms=self.clock.now_ms() - started_ms,
        )

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

    def observe_duplex(self, state: DuplexState) -> None:
        """The VAD/turn-detector view, refreshed by the transport adapter."""
        self.duplex = state
