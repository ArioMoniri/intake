"""The kill switch: voice → typed, once, and never back (INT-096).

Four routes into typed exist in the blueprint and each is a member of
:class:`LaneSwitchReason`:

- **operator** — files/02 §375: *"the admin console can switch a tenant to
  typed mode (kill switch) without a deploy"*. files/08 §8.2 makes it a **T1
  safe-direction** action: one actor, audited, no second approver, because
  requiring four eyes to make the product safer is an availability control on
  a safety control.
- **``unreliable_audio``** — files/03 §4.5b T3: concealment above 10 % for
  10 s, or two consecutive ``request_repeat_or_clarify`` on the same step;
  *"offer typed, keep the session and every slot"*.
- **``abort_voice``** — files/03 §4.5b T9: three T2 events in one session, or
  more than 25 % of turns degraded; *"complete in typed mode; mark the session
  ``modality_degraded``"*.
- **``speech_lanes_exhausted``** — files/03 §4.9.4 row 11, *"then to row 12
  for the rest of the session, then to ``typed``"*, and row 7, *"repeated
  failure routes to ``typed``"* (INT-100): every speech lane the registry
  orders has failed or is behind an open breaker, so the question the patient
  could not hear is drawn on their screen in the same turn.

**It is a latch, and that is a decision rather than an omission.** T9 says
*complete* in typed. §4.5b's anti-flap rule — *"never change state more than
once per 30 s"*, 15 s clean to recover — is written for the degradation
ladder, and no hysteresis for returning a *session* to voice is stated
anywhere. A switch that could flip back would need one, and inventing it would
be an engineering decision standing in for a clinical one. So there is no
``to_voice``: a second :meth:`LaneSwitch.to_typed` returns the first record
unchanged, and a session that started typed refuses.

**It holds no engine reference, and that is half the safety argument.** This
object records which transport is in force and nothing else, so a flip cannot
lose a bound slot value because there is nothing here for a value to be lost
from. The other half is in
:meth:`~intake_voice_runtime.talker.session.TalkerSession.fall_back_to_typed`,
which swaps one field — the egress — and touches neither the engine, the Work
queue, the transcript vault nor the ask ledger. Together they are what
files/03 §4.5b T3 means by *"keep the session and every slot"*.

The record carries a reason, two profiles, a flag and a timestamp: ids and
closed enumerations only, no session id and no free text (CLAUDE.md
invariant 6; files/03 §4.6 invariant 10).
"""

from __future__ import annotations

import enum

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.profiles import VoiceProfile

__all__ = [
    "KillSwitchNotArmed",
    "LaneSwitch",
    "LaneSwitchLatched",
    "LaneSwitchReason",
    "LaneSwitchRecord",
]


class LaneSwitchLatched(RuntimeError):
    """The session is already typed; there is no second switch and no way back."""


class KillSwitchNotArmed(RuntimeError):
    """The session has no screen to render on, so it is not a kill-switch target.

    Raised rather than shrugged. A session that took the audio away with
    nowhere to put the questions is a session that has gone silent mid-intake,
    which is a worse state than the degraded voice it was trying to leave —
    so the switch refuses and the voice profile stays in force.
    """


class LaneSwitchReason(enum.StrEnum):
    """Why the session moved to the keyboard. A closed set (see the module
    docstring for the blueprint line behind each member)."""

    OPERATOR_KILL_SWITCH = "operator_kill_switch"
    UNRELIABLE_AUDIO = "unreliable_audio"
    ABORT_VOICE = "abort_voice"
    SPEECH_LANES_EXHAUSTED = "speech_lanes_exhausted"


class LaneSwitchRecord(FrozenModel):
    """One flip, as the session event log and the clinician's note see it."""

    reason: LaneSwitchReason
    from_profile: VoiceProfile
    to_profile: VoiceProfile
    modality_degraded: bool = Field(
        description="files/03 §4.5b T9: the clinician is told the answers were "
        "not elicited the way the pack was authored for. True on every route "
        "into typed — an operator flip changes the channel just as a degraded "
        "one does, and the note reader cannot tell which from the answers."
    )
    at_ms: float = Field(ge=0.0, description="Session-clock milliseconds; not a wall clock.")


class LaneSwitch:
    """Which transport is in force for one session. One way, latched."""

    def __init__(self, *, profile: VoiceProfile = VoiceProfile.RESIDENCY_TR) -> None:
        self._profile = profile
        self._record: LaneSwitchRecord | None = None

    @property
    def profile(self) -> VoiceProfile:
        """The transport in force right now."""
        return self._profile

    @property
    def record(self) -> LaneSwitchRecord | None:
        """The flip, if one happened. ``None`` for a session that never left
        voice **and** for one that started typed — a session that was never in
        voice was not switched."""
        return self._record

    @property
    def modality_degraded(self) -> bool:
        """Whether this session's answers reached the record through a channel
        it did not start in."""
        return self._record is not None

    def to_typed(self, reason: LaneSwitchReason, *, now_ms: float) -> LaneSwitchRecord:
        """Move the session to the keyboard. Idempotent; the first reason wins.

        A second call returns the first record rather than overwriting it: the
        first trigger is the one that explains the session, and a later T9
        after an earlier T3 would otherwise erase the reason the patient was
        actually offered typed.
        """
        if self._record is not None:
            return self._record
        if self._profile is VoiceProfile.TYPED:
            raise LaneSwitchLatched(
                "this session is already running typed; the kill switch moves a "
                "session to the safer transport and there is no route back "
                "(files/03 §4.5b T9 — complete in typed mode)"
            )
        self._record = LaneSwitchRecord(
            reason=reason,
            from_profile=self._profile,
            to_profile=VoiceProfile.TYPED,
            modality_degraded=True,
            at_ms=now_ms,
        )
        self._profile = VoiceProfile.TYPED
        return self._record
