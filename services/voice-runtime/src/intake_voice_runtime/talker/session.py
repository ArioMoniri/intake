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

**A RED does not wait for a turn** (INT-531). Beside the turns the Talker runs
one loop of its own, :meth:`TalkerSession.watch_reds`, parked on the session's
:class:`~intake_voice_runtime.talker.red_push.RedMailbox`. Layer B posts every
rules-engine RED it settles there — a non-blocking post, from whichever thread
its pump runs on — and the watch hands it to the RED path the moment it lands:
mid-silence, while the patient is speaking, while the agent's own audio plays.
The path stops that audio within the stop budget and then triggers. A turn
that was speaking returns stopped without recording its cut question as asked.
The watch awaits the mailbox and the RED path, never Backend Work, and the
first turn starts it on the turn's own event loop. The turn's drain still
delivers any RED the watch has not, and each RED reaches the path once
whichever route sees it first.

What this module deliberately does **not** contain:

- **the RED preemption path.** Only its authorisation gate lives here
  (:func:`~intake_voice_runtime.talker.preemption.authorise_preempt`); the
  flush → cancel → pre-positioned-clip sequence over the data channel is
  INT-093, and files/03 §4.6 invariant 4 requires that path to touch no media
  transport at all — which is precisely why it is not plumbed through this
  audio sink. A turn drains Layer B and hands any RED to that path before it
  submits, schedules or asks anything (INT-521), and once the intake has
  stopped it submits and asks nothing.
- **an LLM.** Dynamic text arrives as a string from Layer B or from the
  Talker's small model behind ADR-006's gateway; this module routes and guards
  it. There is no model call here to mock.
- **the safe-bridge copy.** PolicyGuard reports ``bridge_required``; the
  sentence spoken in its place is clinical patient copy that no human has
  supplied, so :class:`TalkerConfig` leaves it ``None`` and the turn stays
  silent rather than inventing one. The ask is in docs/evidence/INT-091.md.
"""

from __future__ import annotations

import asyncio
import enum
import logging
from dataclasses import dataclass, field

from clinical_schemas.common import FrozenModel
from intake_platform.locale import DEFAULT_LOCALE
from pydantic import Field, model_validator

from intake_voice_runtime.metrics import RED_WATCH_FAILURES_TOTAL
from intake_voice_runtime.ports import (
    AskLedger,
    AudioSink,
    ClipStore,
    Clock,
    EngineSnapshotSource,
    PatientMemoryKey,
    PatientMemoryStore,
    PatientRecord,
    QueueSealed,
    ScreenSink,
    SpeechSynthesizer,
    WorkRequest,
    WorkSubmitter,
    WorkTicket,
    WorkType,
    work_key,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.resilience.failover import SpeechLanesExhausted
from intake_voice_runtime.steps import NextStep
from intake_voice_runtime.talker.clips import ClipCatalogue
from intake_voice_runtime.talker.delivery import (
    ADAPTIVE_JITTER_THRESHOLD_MS,
    DeliveryDeadlines,
    DuplexState,
    TurnYieldPolicy,
)
from intake_voice_runtime.talker.egress import Emission, TurnEgress, text_for
from intake_voice_runtime.talker.insertion import InsertionScheduler, PendingSpeech, Speak
from intake_voice_runtime.talker.policy_guard import (
    FormOfAddress,
    PolicyGuard,
    policy_guard_for,
)
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    PreemptRefused,
    Priority,
    authorise_preempt,
)
from intake_voice_runtime.talker.red_path import (
    REGISTER_DELIVERY,
    RedPathNotWired,
    RedPathViolation,
    RedPreemption,
    RedPreemptionOutcome,
)
from intake_voice_runtime.talker.red_push import RedMailbox
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
from intake_voice_runtime.typed.egress import TypedEgress
from intake_voice_runtime.typed.switch import (
    KillSwitchNotArmed,
    LaneSwitch,
    LaneSwitchReason,
    LaneSwitchRecord,
)

__all__ = [
    "UNMEASURED_JITTER",
    "AskLedgerNotWired",
    "ProfileNotWired",
    "RedDeliveryFailed",
    "TalkerConfig",
    "TalkerSession",
    "TurnHold",
    "TurnOutcome",
]

logger = logging.getLogger("intake_voice_runtime.talker.session")


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


class RedDeliveryFailed(RuntimeError):
    """A RED the between-turn watch could not deliver (INT-531 round 2).

    Raised by the session's next turn, after that turn has tried the RED again,
    and ahead of the stopped-intake return: the watch has no caller of its own,
    and a RED that never reached the patient must reach somebody. Carries the
    work ids only (invariant 6); the first failure is the ``__cause__``.
    """

    def __init__(self, work_ids: tuple[str, ...]) -> None:
        self.work_ids = work_ids
        super().__init__(
            f"the between-turn RED watch could not deliver {list(work_ids)}; this turn "
            "tried again, and any that failed again is tried and raised on the next"
        )


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


class ProfileNotWired(ValueError):
    """The session's ports do not match the profile it claims to be.

    Both directions are refused and both are fail-closed. A ``typed`` session
    holding an audio sink is a session that *could* speak, which is not what
    the kill switch moved anybody to; a ``residency_tr`` session with no
    synthesizer is one that will discover it cannot speak on its first
    question rather than at construction.
    """


class TalkerConfig(FrozenModel):
    """Everything about one session that does not change during it.

    ``profile`` is the exception the name admits to: the kill switch replaces
    this whole object (files/03 §4.5b T9), because "which transport is in
    force" is precisely the one thing about a session that may change during
    it, and a mutable field on a frozen model would be a worse lie than a
    replacement.
    """

    session_id: str = Field(min_length=1)
    voice_id: str | None = Field(
        default=None,
        min_length=1,
        description="The pinned voice. ``None`` on ``typed``, which synthesises "
        "nothing — files/03 §4.4 gives that profile a dash in every column but "
        "the input one, and a voice id it can never use would eventually be read "
        "as permission to use one.",
    )
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
        "and silence is safer than an invented sentence (CLAUDE.md). Always unset "
        "on ``typed`` — it names a clip, and a screen has no player.",
    )

    @model_validator(mode="after")
    def _the_profile_and_its_voice_agree(self) -> TalkerConfig:
        speaks = self.profile is not VoiceProfile.TYPED
        if speaks and self.voice_id is None:
            raise ValueError(
                f"profile {self.profile.value!r} synthesises speech and no voice_id "
                "is pinned; files/03 §4.4 pins one voice per session and §4.9.1 row "
                "11 forbids swapping it mid-session, so it cannot be chosen later"
            )
        if not speaks and self.voice_id is not None:
            raise ValueError(
                f"profile 'typed' carries voice_id {self.voice_id!r}; it synthesises "
                "nothing (files/03 §4.4) and an unusable voice id is a field that "
                "will eventually be read as permission to use one"
            )
        if not speaks and self.safe_bridge_clip_id is not None:
            raise ValueError(
                "profile 'typed' carries a safe_bridge_clip_id; the bridge is a "
                "cached audio clip (files/03 §4.2) and a screen has no player"
            )
        return self


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
    memory: PatientMemoryStore
    clock: Clock
    #: The four speech ports. Every one is optional, and every one is absent
    #: on ``typed`` — that is what makes CLAUDE.md invariant 3 a property of
    #: the typed path's *shape* rather than of its behaviour: there is no
    #: buffer to zero because there is no object that could hold one. The
    #: kill switch drops all four (see :meth:`fall_back_to_typed`), so the
    #: guarantee is the same whether a session started typed or arrived there.
    catalogue: ClipCatalogue | None = None
    clip_store: ClipStore | None = None
    synthesizer: SpeechSynthesizer | None = None
    sink: AudioSink | None = None
    #: Where the questions are drawn in ``typed``. A ``residency_tr`` session
    #: may carry one too, and must if it is to be a kill-switch target: the
    #: switch has to have somewhere to render before it may take the audio.
    screen: ScreenSink | None = None
    policy_guard: PolicyGuard | None = None
    preemption: RedPreemption | None = None
    #: The Talker's end of the between-turn push (INT-531): Layer B posts each
    #: rules-engine RED here and :meth:`watch_reds` takes it. ``None`` where no
    #: RED path is bound, and then a RED waits for the turn's drain.
    red_mailbox: RedMailbox | None = None
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
    #: The one thing a profile changes (INT-096). Typed as the port rather
    #: than as either implementation, so nothing above this line can reach a
    #: sink, a clip or a synthesizer without going through the seam.
    router: TurnEgress = field(init=False)
    #: Which transport is in force, and the record of the flip if there was
    #: one. Latched: there is no route back (files/03 §4.5b T9).
    lane_switch: LaneSwitch = field(init=False)
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
    #: INT-531: the work ids of the REDs handed to the path, by either route.
    #: A RED is settled once and seen twice — pushed and drained — so the
    #: second sighting is dropped here.
    _reds_seen: set[str] = field(default_factory=set, init=False, repr=False)
    _red_watch: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    #: INT-531 round 2: deliveries in flight, held apart from the watch so the
    #: session ending mid-delivery cannot cut a RED between its stop and its
    #: trigger.
    _red_deliveries: set[asyncio.Task[None]] = field(default_factory=set, init=False, repr=False)
    #: REDs the watch could not deliver, by work id, with what stopped them.
    #: The next turn tries each again and raises :class:`RedDeliveryFailed`.
    _red_failed: dict[str, tuple[BackendResult, BaseException]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        # The Backend agent is the ledger when it is one — one object, one
        # session, and the notes then queue behind the same lock the Work
        # does. Anything else gets the refusing default.
        self.ask_ledger = (
            self.backend if isinstance(self.backend, AskLedger) else _UnwiredAskLedger()
        )
        # One language per guard (INT-298): the guard is built from the
        # signed lexicon for this session's locale, and there is no signed
        # lexicon for any language but `tr` (HUMAN_BLOCKERS HB-C19). The
        # locale is stated rather than inferred — INT-296's registry holds
        # exactly one, and a second reaches this line as a session field,
        # never as a fallback.
        self.guard = self.policy_guard or policy_guard_for(
            locale=DEFAULT_LOCALE, profile=self.config.profile
        )
        self.scheduler = InsertionScheduler(
            deadlines=self.config.deadlines, note_flag=self._note_undelivered
        )
        self.lane_switch = LaneSwitch(profile=self.config.profile)
        self.router = self._build_egress()
        self.duplex = DuplexState(patient_silence_ms=0.0, talker_idle=True, pending_response=False)

    def _build_egress(self) -> TurnEgress:
        """The one place a profile becomes a transport (INT-096).

        Both branches refuse rather than degrade, and both refusals are of the
        *ports*, not of the profile name: a session is typed because it has a
        screen and no sink, and is ``residency_tr`` because it has the three
        speech ports. Checking the wiring here means a mis-wired session is a
        construction error rather than a first-question one.
        """
        if self.config.profile is VoiceProfile.TYPED:
            audio = {
                "clip_store": self.clip_store,
                "synthesizer": self.synthesizer,
                "sink": self.sink,
                "catalogue": self.catalogue,
            }
            bound = sorted(name for name, port in audio.items() if port is not None)
            if bound:
                raise ProfileNotWired(
                    f"a 'typed' session was handed {bound}; the profile's whole "
                    "content is that it has no audio egress (files/03 §4.4), and a "
                    "typed session that could speak is not the state the kill switch "
                    "moves anybody to (CLAUDE.md invariants 3 and 19)"
                )
            if self.screen is None:
                raise ProfileNotWired(
                    "a 'typed' session needs a ScreenSink: it is the profile's only "
                    "egress, and one without it could ask no question at all"
                )
            return TypedEgress(screen=self.screen)
        voice_id, clips, tts, sink = (
            self.config.voice_id,
            self.clip_store,
            self.synthesizer,
            self.sink,
        )
        missing = sorted(
            name
            for name, port in (
                ("voice_id", voice_id),
                ("clip_store", clips),
                ("synthesizer", tts),
                ("sink", sink),
                ("catalogue", self.catalogue),
            )
            if port is None
        )
        if missing or voice_id is None or clips is None or tts is None or sink is None:
            raise ProfileNotWired(
                f"profile {self.config.profile.value!r} speaks and is missing {missing}; "
                "refusing at construction rather than on the first question"
            )
        return SpeechRouter(voice_id=voice_id, clip_store=clips, synthesizer=tts, sink=sink)

    # --- the kill switch (files/08 §8.2 T1; files/03 §4.5b T3, T9) -------------------

    def fall_back_to_typed(self, reason: LaneSwitchReason) -> LaneSwitchRecord:
        """Move this live session to the keyboard. One actor, one direction.

        files/08 §0c F17: *"The kill switch moves the system to the **safer**
        state (typed mode). Requiring a second approver at 03:00 to make the
        product safer is an availability control placed on a safety control."*
        So there is no approver argument here and no gate but one — the
        session must have a screen — and that gate exists because the failure
        it prevents is going silent mid-intake, which is worse than the
        degraded voice the switch was leaving.

        **What it touches is the list that makes the parity claim true.** One
        field: the egress. Not the engine, not the Work queue, not the
        transcript vault, not the ask ledger, not the insertion scheduler, not
        PolicyGuard's learned form of address. files/03 §4.5b T3 asks the
        switch to *"keep the session and every slot"*, and the way that is
        guaranteed is that there is no expression here that could drop one.

        The four speech ports are dropped rather than left unused. An unused
        sink is a rule someone has to keep; ``None`` is a fact.
        """
        if self.screen is None:
            raise KillSwitchNotArmed(
                "this session has no ScreenSink bound, so the kill switch has "
                "nowhere to put the remaining questions; the voice profile stays in "
                "force rather than the session going silent mid-intake"
            )
        record = self.lane_switch.to_typed(reason, now_ms=self.clock.now_ms())
        if self.config.profile is VoiceProfile.TYPED:
            # Idempotent: the latch already returned the first record, and the
            # ports were dropped the first time round.
            return record
        self.config = self.config.model_copy(
            update={
                "profile": VoiceProfile.TYPED,
                "voice_id": None,
                "safe_bridge_clip_id": None,
            }
        )
        self.clip_store = None
        self.synthesizer = None
        self.sink = None
        self.catalogue = None
        # The guard follows the profile so its metric label is not stale, and
        # keeps its `form_of_address`: the register the patient mirrored is a
        # fact about the patient, not about the channel (files/03 §4.2).
        self.guard.profile = VoiceProfile.TYPED
        self.router = self._build_egress()
        return record

    @property
    def modality_degraded(self) -> bool:
        """files/03 §4.5b T9 — the clinician is told the answers were not
        elicited the way the pack was authored for."""
        return self.lane_switch.modality_degraded

    @property
    def modality_switch(self) -> LaneSwitchRecord | None:
        """The flip, if there was one. ``None`` for a session that never left
        voice and for one that started typed."""
        return self.lane_switch.record

    # --- the six tools, as methods -------------------------------------------------

    def protocol_next(self) -> NextStep | None:
        """A lock-free atomic attribute read (files/12 §7.2).

        After a patient-facing RED it offers nothing (CD-24 ``generic_red_stops_
        intake``; files/03 §4.6). The Talker calls this tool directly, outside the
        turn loop, so the gate belongs here rather than only in :meth:`take_turn`:
        a question asked after a life threat is the failure the preemption
        exists to prevent.
        """
        if self._red_stopped:
            self._last_step = None
            return None
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
        return RepeatDirective(
            text_tr=step.text_tr,
            clip_id=self._clip_for(step.text_tr),
            reason=reason,
        )

    def _clip_for(self, text_tr: str) -> str | None:
        """The cached clip for this exact Turkish, if this profile has clips.

        ``None`` on ``typed`` because the catalogue is ``None`` there — the
        one lookup both profiles share, rather than a branch on the profile
        name at each of the two call sites.
        """
        if self.catalogue is None:
            return None
        cached = self.catalogue.get(text_tr)
        return cached.clip_id if cached else None

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
        if register is not None and REGISTER_DELIVERY[register].stops_intake:
            # INT-531: latched before the path awaits anything, so a turn that
            # resumes while the stop and the trigger are in flight asks nothing.
            self._red_stopped = True
        return await self.preemption.trigger(result, evaluated_at_ms=evaluated_at_ms)

    async def _drain_and_deliver(self) -> tuple[object, ...]:
        """Drain Layer B and hand every rules-engine RED to the RED path.

        Every result is accepted first (provenance gate, insertion scheduler),
        then each preempt is delivered. Draining never blocks; delivering
        awaits only the RED path's cancel and data-channel trigger. A RED the
        between-turn watch already handed to the path is skipped (INT-531).
        """
        drained = self.backend.drain_results()
        reds: list[BackendResult] = []
        for result in drained:
            if not isinstance(result, BackendResult):
                continue
            if result.priority is Priority.PREEMPT and result.work_id in self._reds_seen:
                continue
            self.accept_result(result)
            if result.priority is Priority.PREEMPT:
                self._reds_seen.add(result.work_id)
                reds.append(result)
        for result in reds:
            await self.deliver_preempt(result, evaluated_at_ms=self._evaluated_at(result))
        return drained

    # --- the between-turn RED watch (INT-531) ------------------------------------------

    def ensure_red_watch(self) -> asyncio.Task[None] | None:
        """Start :meth:`watch_reds` on the running event loop, once per loop.

        :meth:`take_turn` calls this on entry, so a session that has taken a
        turn is watching; a worker may call it at session start to cover the
        moments before the first turn too. ``None`` where no push is wired —
        no mailbox, or no RED path to hand a RED to.
        """
        if self.red_mailbox is None or self.preemption is None:
            return None
        running = asyncio.get_running_loop()
        watch = self._red_watch
        if watch is None or watch.done() or watch.get_loop() is not running:
            watch = running.create_task(self.watch_reds(), name="talker-red-watch")
            watch.add_done_callback(self._red_watch_ended)
            self._red_watch = watch
        return watch

    def stop_red_watch(self) -> None:
        """Cancel the between-turn watch when the session ends. Idempotent.

        The watch never returns on its own, so an ended session that left it
        parked on its mailbox would keep the session alive until its event
        loop closed. A delivery already in flight is not cancelled with it: it
        runs apart from the watch and still reaches the device. Awaits nothing.
        """
        watch, self._red_watch = self._red_watch, None
        if watch is not None and not watch.done():
            watch.cancel()

    @property
    def red_watch_idle(self) -> bool:
        """True when the watch has nothing left to do (INT-545): no RED posted
        and not yet taken, and no RED it took still in delivery.

        The session router reads this before it lets an ended session's watch
        go. A session with no mailbox has nothing to watch, so it is idle. A
        RED whose delivery failed is not in flight; :meth:`end_red_watch` tells
        the clinician of it.
        """
        mailbox = self.red_mailbox
        return (mailbox is None or mailbox.empty) and not self._red_deliveries

    def end_red_watch(self) -> tuple[str, ...]:
        """The session is over: stop the watch and tell the clinician of every
        RED it could not deliver (INT-545). Returns their work ids. Idempotent;
        awaits nothing.

        The router calls this once the watch is idle, so what is left is
        exactly the REDs whose delivery failed and were waiting for the next
        turn to retry them — and an ended session takes no next turn. Each goes
        to the clinician route again, stating that the device was not reached;
        each is counted (``red_watch_failures_total{kind="unreached"}``) and
        logged by work id.
        """
        self.stop_red_watch()
        preemption = self.preemption
        if preemption is None:
            # No RED path: the watch never ran, so no delivery of its can have failed.
            return ()
        unreached = tuple(result for result, _ in self._red_failed.values())
        self._red_failed.clear()
        for result in unreached:
            RED_WATCH_FAILURES_TOTAL.labels(kind="unreached").inc()
            logger.error("red never reached the device", extra={"work_id": result.work_id})
            preemption.not_reached(result, evaluated_at_ms=self._evaluated_at(result))
        return tuple(result.work_id for result in unreached)

    async def watch_reds(self) -> None:
        """The Talker's own between-turn loop: a RED reaches the patient now.

        Parks on the session's mailbox and hands each RED Layer B posts to the
        preemption path the moment it lands, whether or not a turn is running.
        It awaits the mailbox and the path — the cancel of the agent's audio,
        bounded by the stop budget, then the trigger over the data channel —
        and nothing of Layer B's. It never returns; cancel the task to stop it.

        Each batch is delivered in a task of its own that the watch only
        shields: cancelling the watch — the session ending, say — never cuts a
        RED between its stop and its trigger (INT-531 round 2).
        """
        mailbox = self.red_mailbox
        if mailbox is None or self.preemption is None:
            raise RedPathNotWired(
                "the between-turn RED watch needs both the session's mailbox and its "
                "RED preemption path; refusing to watch for a RED it could not deliver "
                "(CLAUDE.md invariant 21)"
            )
        while True:
            batch = await mailbox.take()
            delivery = asyncio.ensure_future(self._deliver_batch(batch))
            self._red_deliveries.add(delivery)
            delivery.add_done_callback(self._red_deliveries.discard)
            await asyncio.shield(delivery)

    async def _deliver_batch(self, batch: tuple[BackendResult, ...]) -> None:
        for result in batch:
            await self._deliver_pushed(result)

    async def _deliver_pushed(self, result: BackendResult) -> None:
        """One pushed RED: the same gate and path as a drained one, once.

        The watch has no caller to raise to. A provenance refusal and a
        violation are each logged by work id (the violation is also counted by
        the path) and the watch serves the next RED; a refused RED is not marked
        seen, so the turn's drain meets it again and raises. Anything else the
        path raises — a data channel that fails, the event loop cancelling the
        delivery — leaves the RED undelivered: it is logged by work id and
        error class, counted, and tried again and raised by the next turn.
        """
        if result.work_id in self._reds_seen:
            return
        try:
            self.accept_result(result)
        except PreemptRefused:
            logger.error("pushed red refused", extra={"work_id": result.work_id})
            return
        self._reds_seen.add(result.work_id)
        try:
            await self.deliver_preempt(result, evaluated_at_ms=self._evaluated_at(result))
        except RedPathViolation as violation:
            logger.error(
                "red path violation",
                extra={
                    "work_id": result.work_id,
                    "violations": [value.value for value in violation.violations],
                },
            )
        except asyncio.CancelledError as cancelled:
            self._red_undelivered(result, cancelled, kind="cancelled")
            raise
        except Exception as err:  # the watch must outlive any one RED's failure
            self._red_undelivered(result, err, kind="delivery")

    def _red_undelivered(self, result: BackendResult, error: BaseException, *, kind: str) -> None:
        """Record a RED the watch did not deliver, for the next turn to retry and raise."""
        self._reds_seen.discard(result.work_id)
        self._red_failed[result.work_id] = (result, error)
        RED_WATCH_FAILURES_TOTAL.labels(kind=kind).inc()
        logger.error(
            "pushed red delivery cancelled"
            if kind == "cancelled"
            else "pushed red delivery failed",
            extra={"work_id": result.work_id, "error": type(error).__name__},
        )

    def _red_watch_ended(self, watch: asyncio.Task[None]) -> None:
        """The watch's done-callback: an end other than a cancel is a failure.

        Counted and logged by error class; the next turn starts a new watch.
        """
        if watch.cancelled():
            return
        RED_WATCH_FAILURES_TOTAL.labels(kind="exit").inc()
        logger.error("red watch exited", extra={"error": type(watch.exception()).__name__})

    async def _retry_undelivered_reds(self) -> None:
        """Try every RED the watch could not deliver again, then raise.

        Runs at the top of a turn, ahead of the stopped-intake return: the RED
        latched the intake before it failed, so without this the turn would
        return stopped with the RED never shown. A RED that fails again is
        recorded again, so the next turn tries it and raises again.
        """
        failed = dict(self._red_failed)
        self._red_failed.clear()
        for result, _ in failed.values():
            await self._deliver_pushed(result)
        first = next(iter(failed.values()))[1]
        raise RedDeliveryFailed(tuple(failed)) from first

    def _evaluated_at(self, result: BackendResult) -> float:
        """When the rules engine made this RED's determination (INT-521).

        Layer B stamps every ``preempt`` it settles. A RED from another source
        carries no stamp; it is delivered all the same, measured from the
        moment it was drained, because a patient shown nothing is the one
        outcome the RED path must never produce — and the gap is logged by
        work id so the unmeasured hop is visible rather than silent.
        """
        if result.evaluated_at_ms is not None:
            return result.evaluated_at_ms
        logger.warning("red drained without an evaluation stamp", extra={"work_id": result.work_id})
        return self.clock.now_ms()

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
        # INT-531: the between-turn RED watch runs beside every turn from the
        # first one on. Starting it awaits nothing.
        self.ensure_red_watch()
        if self._red_failed:
            # A RED the watch could not deliver is tried again and raised
            # before anything else, the stopped-intake return included.
            await self._retry_undelivered_reds()
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

        # INT-521: a rules-engine RED is drained and delivered before this turn
        # submits anything (files/03 §4.3: preempt, stop intake). A RED that
        # stops the intake seals Layer B's queue, so the patient's next answer
        # cannot be submitted; submitting first is how a RED came to sit
        # undelivered behind a QueueSealed. The path cancels the agent's audio
        # and triggers the pre-positioned script over the data channel; it
        # awaits no Backend Work.
        drained = list(await self._drain_and_deliver())
        if self._red_stopped:
            return TurnOutcome(
                drained_results=len(drained),
                held=TurnHold.INTAKE_STOPPED,
                elapsed_ms=self.clock.now_ms() - started_ms,
            )

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
            try:
                work_id = self.submit_utterance(answered.step_id, transcript).work_id
            except QueueSealed:
                # A RED sealed the queue between the drain above and this
                # submit: Layer B settles it into its results before it seals,
                # so it is waiting there now. Deliver it; a seal with no RED
                # behind it is a defect and is raised.
                drained.extend(await self._drain_and_deliver())
                if not self._red_stopped:
                    raise
                return TurnOutcome(
                    drained_results=len(drained),
                    held=TurnHold.INTAKE_STOPPED,
                    elapsed_ms=self.clock.now_ms() - started_ms,
                )

        delivered: list[str] = []
        for decision in self.scheduler.tick(self.duplex, now_ms=self.clock.now_ms()):
            if (
                isinstance(decision, Speak)
                and decision.item.presentation.speech_tr is not None
                and await self._speak_backend(decision)
            ):
                delivered.append(decision.item.work_id)
        if self._red_stopped:
            # INT-531: a RED reached the path while Layer B's speech was going
            # out; the path cut it, and nothing is asked after a life threat.
            return TurnOutcome(
                work_id=work_id,
                drained_results=len(drained),
                delivered_work_ids=tuple(delivered),
                held=TurnHold.INTAKE_STOPPED,
                elapsed_ms=self.clock.now_ms() - started_ms,
            )

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
            if self._red_stopped:
                # INT-531: a RED reached the path while this question was going
                # out. The path cut it; the patient heard at most part of it,
                # so it is not recorded as asked and the turn reports the stop.
                held = TurnHold.INTAKE_STOPPED
            else:
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
        """Deliver one step: clip cache first, verbatim TTS second — or, on
        ``typed``, the same string to the screen.

        Every line above the last is profile-independent, which is the parity
        claim in one method: the paraphrase permission, PolicyGuard, the
        bridge decision and the playback record are the same code on both
        transports, and only :meth:`TurnEgress.emit` differs.
        """
        started_ms = self.clock.now_ms()
        if step is None:
            return TurnOutcome(elapsed_ms=0.0)
        text = text_for(step, paraphrase)
        verdict = self.guard.filter(text, scripted=not step.allow_paraphrase)
        if verdict.bridge_required:
            return await self._speak_bridge(step, started_ms)
        emitted = await self._emit(
            verdict.text_tr, clip_id=self._clip_for(verdict.text_tr), label=step.step_id
        )
        if emitted is None:
            return TurnOutcome(step_id=step.step_id, elapsed_ms=self.clock.now_ms() - started_ms)
        self._record_playback(started_ms)
        return TurnOutcome(
            step_id=step.step_id,
            spoken_text=emitted.text_tr,
            from_clip=emitted.from_clip,
            elapsed_ms=self.clock.now_ms() - started_ms,
        )

    async def _speak_bridge(self, step: NextStep, started_ms: float) -> TurnOutcome:
        """PolicyGuard dropped the whole turn. Play the cached bridge if one
        has been signed off; otherwise say nothing — never improvise copy.

        On ``typed`` the config validator has already refused a bridge clip
        id, so this always takes the silent branch — which is the same
        behaviour a voice session has today, the bridge's Turkish being copy
        no human has signed off (docs/evidence/INT-091.md).
        """
        clip_id = self.config.safe_bridge_clip_id
        if clip_id is None:
            return TurnOutcome(step_id=step.step_id, elapsed_ms=self.clock.now_ms() - started_ms)
        if await self._emit("", clip_id=clip_id, label="safe_bridge") is not None:
            self._record_playback(started_ms)
        return TurnOutcome(step_id=step.step_id, elapsed_ms=self.clock.now_ms() - started_ms)

    async def _speak_backend(self, decision: Speak) -> bool:
        """Deliver Layer B's material at the window it earned.

        The scheduler is the same on both profiles and so is this method: the
        files/12 §6 ladder, the ``work_id`` dedupe and the undelivered note
        are clinical delivery semantics, not audio ones. A YELLOW that expires
        unheard must reach the note whether the patient was listening or
        reading, which is why none of it is skipped on ``typed``.

        Returns whether anything was spoken. An INTERJECT item awaits the
        cancel of the agent's other playback first, and a RED can latch the
        intake during that cancel; :meth:`_emit` then starts nothing, and the
        item is not reported delivered (INT-531 round 2).
        """
        started_ms = self.clock.now_ms()
        if decision.cancel_non_red_playback:
            await self.router.cancel()
        text = decision.item.presentation.speech_tr or ""
        verdict = self.guard.filter(text, scripted=False)
        if not verdict.text_tr:
            return False
        emitted = await self._emit(
            verdict.text_tr,
            clip_id=self._clip_for(verdict.text_tr),
            label=decision.item.work_id,
        )
        if emitted is None:
            return False
        self._record_playback(started_ms)
        return True

    async def _emit(self, text_tr: str, *, clip_id: str | None, label: str) -> Emission | None:
        """Hand one sentence to the egress — and, if no voice is left, to the screen.

        INT-100. files/03 §4.9.4 row 11 ends *"then to ``typed``"*: when the
        failover ladder has no speech lane left it raises
        :class:`~intake_voice_runtime.resilience.failover.SpeechLanesExhausted`,
        and this is the one place that turns it into the typed profile. It does
        so **inside the turn**, re-emitting the same verbatim string on the
        screen, because a question the patient never heard is a question they
        must still be able to answer — the ladder already spent at most the
        2 s budget, and the screen write adds no playback.

        Only the synthesis path can raise it (a cached clip never touches a
        speech lane), so the retry carries no ``clip_id`` — the typed egress
        refuses one. A session with no screen re-raises from
        :meth:`fall_back_to_typed` as ``KillSwitchNotArmed``, chained to the
        exhaustion: loud, rather than a session that goes silent mid-intake.

        **Nothing starts after a RED** (CLAUDE.md invariant 21; INT-531 round
        2). Every egress start — a step's question, the safe bridge, Layer B's
        speech — comes through here, and once a patient-facing RED has latched
        the intake it returns ``None`` and emits nothing. Up to the egress's
        own playback there is no await, so the gate holds until the frame is
        handed over; a RED that lands after that cuts the playback through
        the RED path's cancel.
        """
        if self._red_stopped:
            return None
        try:
            return await self.router.emit(text_tr, clip_id=clip_id, label=label)
        except SpeechLanesExhausted:
            self.fall_back_to_typed(LaneSwitchReason.SPEECH_LANES_EXHAUSTED)
            return await self.router.emit(text_tr, clip_id=None, label=label)

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
