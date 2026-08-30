"""The kill switch: voice → typed, once, and never back (INT-096).

Three routes into typed exist in the blueprint and each is a member of
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

**It is a latch, and that is a decision rather than an omission.** T9 says
*complete* in typed. §4.5b's anti-flap rule — *"never change state more than
once per 30 s"*, 15 s clean to recover — is written for the degradation
ladder, and no hysteresis for returning a *session* to voice is stated
anywhere. A switch that could flip back would need one, and inventing it would
be an engineering decision standing in for a clinical one. So there is no
``to_voice``: a second :meth:`LaneSwitch.to_typed` returns the first record
unchanged, and a session that started typed refuses.

**It holds no engine reference, and that is the whole safety argument.** Both
lanes drive one ``IntakeEngine``; this object only records which lane is
speaking. A flip therefore cannot lose a bound slot value, because there is
nothing here for a value to be lost from — which is what
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

__all__ = ["LaneSwitch", "LaneSwitchLatched", "LaneSwitchReason", "LaneSwitchRecord"]


class LaneSwitchLatched(RuntimeError):
    """The session is already typed; there is no second switch and no way back."""


class LaneSwitchReason(enum.StrEnum):
    """Why the session moved to the keyboard. A closed set (see the module
    docstring for the blueprint line behind each member)."""

    OPERATOR_KILL_SWITCH = "operator_kill_switch"
    UNRELIABLE_AUDIO = "unreliable_audio"
    ABORT_VOICE = "abort_voice"


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
    """Which lane is speaking for one session. One way, latched."""

    def __init__(self, *, profile: VoiceProfile = VoiceProfile.RESIDENCY_TR) -> None:
        self._profile = profile
        self._record: LaneSwitchRecord | None = None

    @property
    def profile(self) -> VoiceProfile:
        """The lane in force right now."""
        return self._profile

    @property
    def record(self) -> LaneSwitchRecord | None:
        """The flip, if one happened. ``None`` for a session that never left
        voice **and** for one that started typed — a session that was never in
        voice was not switched."""
        return self._record

    @property
    def modality_degraded(self) -> bool:
        """Whether this session's answers reached the record through a lane it
        did not start in."""
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
                "session to the safer lane and there is no route back (files/03 "
                "§4.5b T9 — complete in typed mode)"
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
