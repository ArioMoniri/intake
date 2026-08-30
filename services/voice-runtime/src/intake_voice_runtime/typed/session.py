"""Layer A without a microphone: the typed lane for one session (INT-096).

The same six tools, the same engine, the same Work queue — and no audio port
at all. That last clause is the design:
:class:`~intake_voice_runtime.talker.session.TalkerSession` takes a
``ClipStore``, a ``SpeechSynthesizer`` and an ``AudioSink``; this class takes
none of the three, holds no frames, and has no ``cancel`` to call on a
playback that does not exist. CLAUDE.md invariant 3 is therefore a property of
the typed path's *type*, not of its behaviour — there is no buffer to zero
because there is no buffer.

**No seventh tool.** files/03 §4.2's six are the Talker's whole surface and
invariant 9 makes the set an equality. The typed lane needs nothing outside
it: the switch that puts a session here already travels as
``RepeatReason.TYPED_SWITCH`` on ``request_repeat_or_clarify``, and the
displayed prompt is a projection of ``protocol_next``'s own return value
rather than a call of its own. :func:`build_typed_tools` registers the same
six names and seals the registry, and the suite runs the Talker's own
``assert_six_tool_surface`` over the result.

**Two rungs of files/12 §7.6 are inapplicable here, and none is skipped.**
The consent ladder gates a *spoken* answer: the span must start after the
prompt audio ended, it must not overlap agent playback (the *"hı-hı"* fix),
and the transcription confidence must clear a floor. In typed there is no
prompt audio, no playback and no transcription — the failure each rung guards
against cannot occur, because the answer is a decision the patient selected
rather than a sound the recogniser interpreted. The rungs that survive the
change of channel are all kept and all enforced: an open request, the sixty
second window, the prompt hash, and the read-back. The consent **text** those
prompts render is a separate matter and remains blocked (INT-038).

**There is no preemption path here.** Only a rules-engine RED may preempt
(invariant 9) and preemption means cutting playback. files/04 §272 records the
consequence in the accessibility suite's own words — *"the RED design is
defined in terms of cutting playback within 150 ms, which is meaningless in
typed mode"* — so this class has no scheduler, no ``accept_result`` and no
sink. The RED script reaches the device over the data channel either way
(files/03 §4.6 invariant 4), which is the path that does not change.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.ports import (
    Clock,
    EngineSnapshotSource,
    PatientMemoryKey,
    PatientMemoryStore,
    PatientRecord,
    WorkSubmitter,
    WorkTicket,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import NextStep
from intake_voice_runtime.talker.policy_guard import FormOfAddress, PolicyGuard
from intake_voice_runtime.talker.registry import ToolRegistry
from intake_voice_runtime.talker.tools import (
    PERMISSION_WINDOW_MS,
    ConsentDecision,
    MemoryOp,
    PermissionAck,
    PermissionRequest,
    PermissionState,
    RepeatDirective,
    RepeatReason,
)
from intake_voice_runtime.typed.affordance import SlotFacts
from intake_voice_runtime.typed.render import TypedPrompt, typed_prompt
from intake_voice_runtime.utterance import submit_extraction

__all__ = ["TypedConfig", "TypedSession", "build_typed_tools"]


class TypedConfig(FrozenModel):
    """Everything about one typed session that does not change during it.

    There is no ``voice_id`` and no ``deadlines`` table: nothing is
    synthesised and nothing waits for a safe insertion window, because a
    displayed sentence never interrupts anybody.
    """

    session_id: str = Field(min_length=1)
    protocol_hash: str = Field(min_length=1, description="The session's pinned pack hash.")
    rule_ids: frozenset[str] = Field(
        default=frozenset(),
        description="Rule ids of the pinned pack, carried so a RED reaching this "
        "session can be attributed to packages/protocols/triage. Nothing here "
        "evaluates a rule (CLAUDE.md invariant 1).",
    )


def _origin_of(step_id: str) -> str:
    """A clarification re-entry answers its origin slot (files/13 §11.1)."""
    return step_id.split("/clarify/", 1)[0]


@dataclass
class TypedSession:
    """The typed lane for one intake session."""

    config: TypedConfig
    engine: EngineSnapshotSource
    backend: WorkSubmitter
    memory: PatientMemoryStore
    clock: Clock
    facts: Mapping[str, SlotFacts]
    policy_guard: PolicyGuard | None = None
    guard: PolicyGuard = field(init=False)
    _last_step: NextStep | None = field(default=None, init=False)
    _permissions: dict[str, PermissionRequest] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.guard = self.policy_guard or PolicyGuard(profile=VoiceProfile.TYPED)

    # --- the six tools, as methods -------------------------------------------------

    def protocol_next(self) -> NextStep | None:
        """A lock-free atomic attribute read (files/12 §7.2), as in voice."""
        snapshot = self.engine.snapshot
        if snapshot.next_step is None:
            self._last_step = None
            return None
        self._last_step = NextStep.of(snapshot.next_step, snapshot.version)
        return self._last_step

    def submit_utterance(self, step_id: str, entry: str) -> WorkTicket:
        """Hand the typed answer to Layer B and return at once (ADR-009)."""
        return submit_extraction(
            self.backend,
            session_id=self.config.session_id,
            step_id=step_id,
            transcript=entry,
            protocol_hash=self.config.protocol_hash,
            engine_version=self._last_step.engine_version if self._last_step else 0,
        )

    def cancel_work(self, work_id: str, reason: str) -> WorkTicket:
        return self.backend.cancel(work_id, reason)

    def request_repeat_or_clarify(self, reason: RepeatReason) -> RepeatDirective:
        """Re-put the current step verbatim. No ``clip_id``: nothing is played.

        ``RepeatReason.TYPED_SWITCH`` is the in-band signal that put the
        session in this lane in the first place (files/03 §4.2, §4.5b T3), so
        the fallback needs no tool of its own.
        """
        step = self._last_step or self.protocol_next()
        if step is None:
            raise LookupError("there is no current step to repeat")
        return RepeatDirective(text_tr=step.text_tr, clip_id=None, reason=reason)

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

    def respond_permission(
        self, *, request_id: str, decision: ConsentDecision, prompt_text_hash: str
    ) -> PermissionAck:
        """The rungs of files/12 §7.6 that survive the change of channel.

        Every refusal is returned, never raised: the lane must always be able
        to answer, and a consent gate that surfaced as an exception would
        leave the patient looking at a screen that did nothing.
        """

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
        if decision is ConsentDecision.NO:
            self._permissions.pop(request_id, None)
            return PermissionAck(
                request_id=request_id, state=PermissionState.DECLINED, reason="declined"
            )
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

    # --- the screen (a projection, not a tool) ---------------------------------------

    def open_permission_request(self, request: PermissionRequest) -> None:
        """Layer B opens a consent prompt; the lane relays the answer."""
        self._permissions[request.request_id] = request

    def prompt(self, step: NextStep) -> TypedPrompt:
        """What the screen shows for one step.

        PolicyGuard runs with ``scripted=True`` unconditionally, because the
        typed lane holds no generator: every string it displays is the pack's
        own ``text_tr``, and invariant 10 leaves no route to a reworded one.
        So the guard reports here rather than rewrites — the same treatment
        the Talker gives an authored question.
        """
        self.guard.filter(step.text_tr, scripted=True)
        facts = self.facts.get(_origin_of(step.step_id))
        if facts is None:
            raise LookupError(
                f"{step.step_id!r} has no slot in the pinned protocol, so the typed "
                "lane has no affordance rule to apply to it"
            )
        return typed_prompt(step, facts)

    def retained_frames(self) -> int:
        """How many audio buffers this session references — zero, counted.

        Asserted by counting rather than by inspection, so a future field that
        *did* retain audio would be caught (CLAUDE.md invariant 3).
        """
        return sum(1 for value in vars(self).values() if isinstance(value, bytes | bytearray))


def build_typed_tools(session: TypedSession) -> ToolRegistry:
    """Register exactly the six tools of invariant 9, then seal the registry.

    The same names, the same order and the same sealed registry the Talker
    builds. Two signatures differ from their spoken counterparts and both
    differences are subtractions: ``request_repeat_or_clarify`` returns no
    ``clip_id``, and ``respond_permission`` takes no audio span and no ASR
    confidence (see the module docstring).
    """
    registry = ToolRegistry()

    def protocol_next() -> NextStep | None:
        """Lock-free read of the engine snapshot (files/12 §7.2)."""
        return session.protocol_next()

    def submit_utterance(step_id: str, transcript: str) -> WorkTicket:
        """Hand the typed answer to Layer B and return at once (ADR-009)."""
        return session.submit_utterance(step_id, transcript)

    def cancel_work(work_id: str, reason: str) -> WorkTicket:
        """Cancel a submitted Work (files/12 §7.1)."""
        return session.cancel_work(work_id, reason)

    def request_repeat_or_clarify(reason: RepeatReason) -> RepeatDirective:
        """Re-put the current step **verbatim** (files/03 §4.4b)."""
        return session.request_repeat_or_clarify(reason)

    def patient_memory(
        op: MemoryOp, key: str | PatientMemoryKey, value: str | None = None
    ) -> PatientRecord | None:
        """Non-clinical memory only: the key set is closed (files/03 §4.2)."""
        return session.patient_memory(op, key, value)

    def respond_permission(
        *, request_id: str, decision: ConsentDecision, prompt_text_hash: str
    ) -> PermissionAck:
        """Relay a selected, current-turn yes/no through the §7.6 gates."""
        return session.respond_permission(
            request_id=request_id, decision=decision, prompt_text_hash=prompt_text_hash
        )

    for name, handler in (
        ("protocol_next", protocol_next),
        ("submit_utterance", submit_utterance),
        ("cancel_work", cancel_work),
        ("request_repeat_or_clarify", request_repeat_or_clarify),
        ("patient_memory", patient_memory),
        ("respond_permission", respond_permission),
    ):
        registry.register(name, handler)
    registry.seal()
    return registry
