"""The one thing that may interrupt a patient, and the two numbers on it.

files/03 §4.6 invariant 4 states both budgets and then corrects the design
that would have made them unreachable:

    **RED latency:** end-to-end RED preemption ≤ 300 ms; playback cancel
    ≤ 150 ms. … **Fix: the RED script is pre-positioned on the device** —
    bundled with the app build rather than streamed — and triggered by a
    **data-channel** message (SCTP-over-DTLS, reliable and ordered): one
    downlink one-way (~10–25 ms) plus local playback. … **The test changes
    too: it must assert the RED path touches no media transport**, not merely
    that the deadline was met.

So this module has exactly two egress ports, and neither is media:
:class:`PlaybackStop`, which can stop in-flight agent audio and cannot start
any, and :class:`RedDataChannel`, which carries the trigger. There is no
synthesiser here, no clip store, no audio sink and no import that could reach
one — ``tests/voice/test_red_preemption.py`` asserts that over the module's
import closure and its AST, not with a mock.

**"Preempt" is not one behaviour.** files/02 §5.3 gives RED three axes, and
the register axis decides whether anything is audible at all:
``protocols.dsl.REGISTER_AUDIO`` is the blueprint's own table and
:func:`red_delivery` reads it rather than restating it. ``SILENT`` is *"Screen
only … No audio, ever"*, so nothing is cut off mid-sentence either — an abrupt
cut is itself an audible event, and that register exists for the room where
being overheard is the harm. ``DEFERRED_CLINICIAN`` is *"Patient screen
unchanged"*, so Layer A does nothing at all; the finding reaches the clinician
through the unconditional server-side effects of §5.3, which are not the
Talker's to run.

**A late RED still fires.** :class:`RedPreemptOutcome` reports both budgets and
whether each was met; nothing here withholds an emergency instruction for
being slow. Refusals are the other way round — an unauthorised RED, or one
whose pre-positioned script cannot be resolved, raises before anything is cut
off or sent.

The metric this path belongs to, ``preempt.red_latency_ms``, is catalogued
(files/08 §4) and still ``status: planned``; ``intake_voice_runtime.metrics``
declares nothing for it on this branch, so this module emits nothing rather
than an uncatalogued series (CLAUDE.md invariant 13). The measurement is on
the returned outcome, which is what the caller records.
"""

from __future__ import annotations

import warnings
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel
from clinical_schemas.triage import RedLocation, RedRegister, RulesTriageResult, TriageLevel
from protocols.dsl import REGISTER_AUDIO, RedAudio
from pydantic import Field

from intake_voice_runtime.ports import Clock
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.preemption import BackendResult, Priority, authorise_preempt
from intake_voice_runtime.talker.red_script import (
    RedScriptKind,
    RedScriptRef,
    RedScriptUnavailable,
)

__all__ = [
    "E2E_BUDGET_MS",
    "STOP_BUDGET_MS",
    "PlaybackStop",
    "RedDataChannel",
    "RedDelivery",
    "RedPathNotWired",
    "RedPreemptOutcome",
    "RedPreemptRefused",
    "RedPreemption",
    "RedTrigger",
    "red_delivery",
]

#: files/03 §4.6 invariant 4 — *"playback cancel ≤ 150 ms"*.
STOP_BUDGET_MS: Final = 150.0
#: files/03 §4.6 invariant 4 — *"end-to-end RED preemption ≤ 300 ms"*, which
#: holds at p99 only because the script never travels the audio path.
E2E_BUDGET_MS: Final = 300.0


# The blueprint names the RED axis field `register` (CLAUDE.md invariant 21;
# files/02 §5.3); pydantic warns because ABCMeta exposes a classmethod of the
# same name. The blueprint name wins on both models that carry the axis.
for _shadowing_model in ("RedTrigger", "RedPreemptOutcome"):
    warnings.filterwarnings(
        "ignore",
        message=f'Field name "register" in "{_shadowing_model}" shadows an attribute in parent',
        category=UserWarning,
    )


class RedPreemptRefused(PermissionError):
    """Something that is not a rules-engine RED was handed the RED path."""


class RedPathNotWired(RuntimeError):
    """A RED was accepted by a session with no data channel to trigger it on."""


# --- the two egress ports, and neither of them is media ------------------------------------


@runtime_checkable
class PlaybackStop(Protocol):
    """Stop in-flight agent playback.

    Deliberately narrower than ``ports.AudioSink``: the member set is
    ``cancel`` and nothing else, so the RED path is statically unable to play,
    synthesise or fetch a byte of audio. An ``AudioSink`` satisfies it, which
    is how a composition root wires it without an adapter.
    """

    def cancel(self) -> Awaitable[None]: ...


@runtime_checkable
class RedDataChannel(Protocol):
    """The reliable, ordered data channel (SCTP-over-DTLS; files/03 §4.6).

    It carries the *trigger*, never the script: the script is bundled with the
    app build. That is what keeps the RED path off the media transport and the
    end-to-end budget reachable at p99.
    """

    def trigger(self, message: RedTrigger) -> Awaitable[None]: ...


# --- what a register does ------------------------------------------------------------------


class RedDelivery(FrozenModel):
    """How one register is delivered, for one profile."""

    audible: bool = Field(description="Whether the script is voiced at all (files/02 §5.3).")
    patient_facing: bool = Field(
        description="Whether the patient's device presents anything. False only "
        "under DEFERRED_CLINICIAN — *'patient screen unchanged'*."
    )
    audio: RedAudio = Field(
        description="The register's row of the files/02 §5.3 audio table, passed "
        "to the device so prosody and alert sound are the register's, never the "
        "device's choice."
    )


def red_delivery(register: RedRegister, profile: VoiceProfile) -> RedDelivery:
    """Read the blueprint's register table; do not restate it.

    ``protocols.dsl.REGISTER_AUDIO`` is files/02 §5.3's Audio column
    transcribed, and it is already the single source the protocol compiler
    checks every rule's ``audio`` block against. Reading it here means the
    runtime and the compiler cannot disagree about whether a register speaks.

    ``typed`` has no audio port at all (ADR-010; CLAUDE.md invariant 19), so no
    register is audible on it and nothing is ever cut off.
    """
    audio = REGISTER_AUDIO[register]
    return RedDelivery(
        audible=audio.spoken and profile is VoiceProfile.RESIDENCY_TR,
        patient_facing=register is not RedRegister.DEFERRED_CLINICIAN,
        audio=audio,
    )


# --- the message, and what the trigger cost ------------------------------------------------


class RedTrigger(FrozenModel):
    """The data-channel message: an identity and closed enumerations.

    No patient text and no clinical narrative crosses here — the script is
    already on the device — which is also why this message is safe to count and
    time without CLAUDE.md invariant 6 becoming a question.
    """

    work_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    script_id: str = Field(min_length=1)
    script_hash: str = Field(min_length=64, max_length=64)
    kind: RedScriptKind
    register: RedRegister
    location: RedLocation
    audio: RedAudio
    audible: bool
    show_112: bool
    notify_staff: bool
    playback_stopped: bool
    sent_at_ms: float = Field(ge=0.0, description="Session-clock stamp of the send.")


class RedPreemptOutcome(FrozenModel):
    """What the preemption did, and what each half of it cost."""

    work_id: str
    register: RedRegister
    location: RedLocation
    audible: bool
    playback_stopped: bool
    patient_script_triggered: bool
    stop_ms: float | None = Field(
        default=None,
        description="Milliseconds from acceptance to playback stopped; None when "
        "the register interrupts nothing.",
    )
    script_start_ms: float | None = Field(
        default=None,
        description="Milliseconds from acceptance to the trigger committed to the "
        "data channel — the runtime's end of 'script start', since the clip "
        "itself is already on the device. None under DEFERRED_CLINICIAN.",
    )

    @property
    def within_stop_budget(self) -> bool:
        return self.stop_ms is None or self.stop_ms <= STOP_BUDGET_MS

    @property
    def within_e2e_budget(self) -> bool:
        return self.script_start_ms is None or self.script_start_ms <= E2E_BUDGET_MS


# --- the path ------------------------------------------------------------------------------


@dataclass
class RedPreemption:
    """Cancel playback, trigger the pre-positioned script, report both times."""

    clock: Clock
    playback: PlaybackStop
    channel: RedDataChannel
    rule_ids: frozenset[str]
    profile: VoiceProfile = VoiceProfile.RESIDENCY_TR

    async def trigger(
        self, result: BackendResult, *, accepted_at_ms: float | None = None
    ) -> RedPreemptOutcome:
        """Run the preemption for one authorised rules-engine RED.

        ``accepted_at_ms`` is the session-clock stamp of the moment the result
        was accepted; the budgets are measured from it rather than from this
        call, so time spent between the two is charged where it is spent.
        """
        started_ms = self.clock.now_ms() if accepted_at_ms is None else accepted_at_ms
        triage = self._authorised_determination(result)
        register, location = self._axes(triage)
        delivery = red_delivery(register, self.profile)
        # Every refusal is settled *before* the stop, so a RED that cannot be
        # delivered never cuts the patient off for nothing. All of it is pure
        # computation with no await in it, so it costs nothing on the clock.
        script = (
            self._resolved_script(result, triage, register, location)
            if delivery.patient_facing
            else None
        )

        stop_ms: float | None = None
        if delivery.audible:
            await self.playback.cancel()
            stop_ms = self.clock.now_ms() - started_ms

        script_start_ms: float | None = None
        if script is not None:
            message = RedTrigger(
                work_id=result.work_id,
                rule_id=script.rule_id,
                script_id=script.script_id,
                script_hash=script.script_hash,
                kind=script.kind,
                register=register,
                location=location,
                audio=delivery.audio,
                audible=delivery.audible,
                show_112=script.show_112,
                notify_staff=script.notify_staff,
                playback_stopped=stop_ms is not None,
                sent_at_ms=self.clock.now_ms(),
            )
            await self.channel.trigger(message)
            script_start_ms = self.clock.now_ms() - started_ms

        return RedPreemptOutcome(
            work_id=result.work_id,
            register=register,
            location=location,
            audible=delivery.audible,
            playback_stopped=stop_ms is not None,
            patient_script_triggered=script_start_ms is not None,
            stop_ms=stop_ms,
            script_start_ms=script_start_ms,
        )

    # --- refusals, all of them before anything is cut off or sent ---------------------

    def _authorised_determination(self, result: BackendResult) -> RulesTriageResult:
        """Both INT-091 gates again, on the path they guard.

        The shape gate already ran on ``BackendResult`` and the provenance gate
        already ran in Layer B's queue (INT-092). Running them here too is
        defence in depth for the one path where a miss is an unauthorised
        interruption of a patient — and it is what makes the near-miss controls
        exercise *this* code rather than the constructor's.
        """
        if result.priority is not Priority.PREEMPT:
            raise RedPreemptRefused(
                f"work {result.work_id!r} carries priority={result.priority.value!r}; "
                "the RED path is not a delivery channel — everything else waits for a "
                "safe insertion window (files/03 §4.3; CLAUDE.md invariant 9)"
            )
        authorise_preempt(result, rule_ids=self.rule_ids)
        triage = result.presentation.triage_update
        if not isinstance(triage, RulesTriageResult) or triage.level is not TriageLevel.RED:
            # Unreachable past the shape gate; kept because this is the branch
            # whose absence would be an unauthorised interrupt (invariant 1).
            raise RedPreemptRefused("only a rules-engine RED may preempt")
        return triage

    @staticmethod
    def _axes(triage: RulesTriageResult) -> tuple[RedRegister, RedLocation]:
        """CLAUDE.md invariant 21: both axes are required with no default.

        ``RulesTriageResult`` already refuses a RED missing either, so this
        narrows the optional types without inventing a fallback — there is no
        ``or ALERT`` anywhere on this path.
        """
        if triage.register is None or triage.location is None:
            raise RedPreemptRefused(
                "a RED carries register and location with no permitted default "
                "(CLAUDE.md invariant 21; files/02 §5.3)"
            )
        return triage.register, triage.location

    @staticmethod
    def _resolved_script(
        result: BackendResult,
        triage: RulesTriageResult,
        register: RedRegister,
        location: RedLocation,
    ) -> RedScriptRef:
        script = result.presentation.red_script
        if script is None:
            raise RedScriptUnavailable(
                f"RED {result.work_id!r} carries no pre-positioned script reference, "
                "so there is nothing for the device to present. Layer B resolves it "
                "from the winning rule's action block (protocols.triage.engine's "
                "TriageEvaluation.action) — see docs/evidence/INT-093.md"
            )
        script.assert_resolves(
            rule_ids=frozenset(fire.id for fire in triage.rules),
            register=register,
            location=location,
        )
        return script
