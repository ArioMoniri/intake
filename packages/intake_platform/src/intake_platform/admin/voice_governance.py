"""Voice control governance — kill switch, profile switch, canary (INT-182).

The write side of :mod:`intake_platform.voice_control`, and the rule that
makes files/08 §8.2's asymmetry checkable for the voice path:

- **Toward typed, one key.** :meth:`VoiceControlGovernor.engage_kill_switch`
  is tier 1 (:data:`~intake_platform.admin.actions.VOICE_KILL_SWITCH_ENGAGE`):
  one eligible actor, a mandatory reason, no approver. A second key on the
  safe direction is an availability control on a safety control (§0c F17).
  Engaging an engaged switch changes nothing and says so.
- **Toward voice, two keys.** Releasing the switch, switching the default
  profile and setting a canary weight each open a tier-2 four-eyes ceremony
  through the INT-180 :class:`~intake_platform.admin.four_eyes.FourEyesService`
  and apply only when a distinct human, credential and session approves with
  a fresh single-use assertion. Nothing takes effect at request time.
- **An approval binds to what it approved.** The ceremony carries the
  record's revision at request time, and approval refuses if the control has
  moved since — a kill switch pulled after a profile switch was requested
  must not be silently undone by approving the request.
- **Only profiles that exist; weights in 0..100.** Parsed before a ceremony
  opens, so a refused value never becomes a pending action.

Change reasons are INT-188's: a closed :class:`~intake_platform.admin.
flag_governance.FlagChangeReason` plus mandatory free text, which never enters
the store or the ceremony's evidence (invariant 6). Like the other governors
this module is pure rule over injected state — the write-ahead audit row and
the metrics belong to the route that calls it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from intake_platform.admin.actions import (
    VOICE_CANARY_SET,
    VOICE_CEREMONIES,
    VOICE_KILL_SWITCH_ENGAGE,
    VOICE_KILL_SWITCH_RELEASE,
    VOICE_PROFILE_SWITCH,
    DangerousAction,
)
from intake_platform.admin.flag_governance import ChangeReasonMissing
from intake_platform.admin.four_eyes import (
    ActorBlock,
    FourEyesService,
    Justification,
    PendingAction,
)
from intake_platform.voice_control import (
    CANARY_WEIGHT_MIN,
    TenantVoiceControl,
    VoiceControlChange,
    VoiceControlConflict,
    VoiceControlStore,
    parse_canary_weight,
    parse_profile,
    require_tenant_id,
)

__all__ = [
    "VOICE_PENDING_TTL",
    "VoiceActionMismatch",
    "VoiceCanaryIsDefault",
    "VoiceChangeResult",
    "VoiceControlChanged",
    "VoiceControlGovernor",
    "VoiceGovernanceRefused",
    "VoiceKillSwitchNotEngaged",
    "VoiceProfileUnchanged",
    "VoiceRoleIneligible",
]

#: files/10 §2: "Actor initiates → 15-minute TTL → a different sub … approves".
VOICE_PENDING_TTL: Final = timedelta(minutes=15)

#: The safe direction must not bounce off a concurrent write: an incident
#: responder should not have to press the button twice because another change
#: landed in the same millisecond. Re-read and re-apply, a bounded number of times.
_ENGAGE_ATTEMPTS: Final = 3


class VoiceGovernanceRefused(Exception):
    """Base refusal; ``code`` is machine-shaped and reaches an HTTP body."""

    code = "voice_governance_refused"


class VoiceRoleIneligible(VoiceGovernanceRefused):
    code = "voice_role_ineligible"


class VoiceKillSwitchNotEngaged(VoiceGovernanceRefused):
    code = "voice_kill_switch_not_engaged"


class VoiceProfileUnchanged(VoiceGovernanceRefused):
    code = "voice_profile_unchanged"


class VoiceCanaryIsDefault(VoiceGovernanceRefused):
    """A canary of the profile every other session already gets routes
    nothing anywhere new; a default switch onto the running canary would
    leave the record incoherent. Both are refused rather than normalised."""

    code = "voice_canary_is_default"


class VoiceControlChanged(VoiceGovernanceRefused):
    code = "voice_control_changed"


class VoiceActionMismatch(VoiceGovernanceRefused):
    code = "voice_action_mismatch"


@dataclass(frozen=True)
class VoiceChangeResult:
    control: TenantVoiceControl
    changed: bool


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _require_reason(justification: Justification) -> None:
    """INT-188: a change reason is mandatory at the write, not only at the
    builder — on the safe direction too."""
    if not justification.free_text.strip():
        raise ChangeReasonMissing("a voice control change needs a reason (INT-188)")


class VoiceControlGovernor:
    """See the module docstring. Every refusal is typed; nothing returns a
    boolean, because a control change that fails silently did not happen."""

    def __init__(
        self,
        four_eyes: FourEyesService,
        store: VoiceControlStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._four_eyes = four_eyes
        self._store = store
        self._clock = clock if clock is not None else _utc_now

    # -- tier 1: toward typed ---------------------------------------------------------

    def engage_kill_switch(
        self, *, tenant_id: str, actor: ActorBlock, justification: Justification
    ) -> VoiceChangeResult:
        tenant = require_tenant_id(tenant_id)
        if actor.role not in VOICE_KILL_SWITCH_ENGAGE.actor_roles:
            raise VoiceRoleIneligible(f"{actor.role.value} may not pull the voice kill switch")
        _require_reason(justification)
        for _ in range(_ENGAGE_ATTEMPTS):
            current = self._store.read(tenant)
            if current.kill_switch:
                return VoiceChangeResult(control=current, changed=False)
            engaged = self._next(
                current,
                {"kill_switch": True},
                change=VoiceControlChange.KILL_SWITCH_ENGAGE,
                changed_by=actor.subject,
                approved_by=None,
            )
            try:
                written = self._store.write(engaged, expected_revision=current.revision)
            except VoiceControlConflict:
                continue
            return VoiceChangeResult(control=written, changed=True)
        raise VoiceControlChanged("the control kept moving while the switch was pulled")

    # -- tier 2: toward voice ---------------------------------------------------------

    def open_kill_switch_release(
        self, *, tenant_id: str, actor: ActorBlock, justification: Justification
    ) -> PendingAction:
        tenant = require_tenant_id(tenant_id)
        _require_reason(justification)
        current = self._store.read(tenant)
        if not current.kill_switch:
            raise VoiceKillSwitchNotEngaged("there is no engaged kill switch to release")
        return self._open(
            VOICE_KILL_SWITCH_RELEASE,
            current,
            actor,
            justification,
            {"control": VoiceControlChange.KILL_SWITCH_RELEASE.value},
        )

    def open_profile_switch(
        self,
        *,
        tenant_id: str,
        profile: object,
        actor: ActorBlock,
        justification: Justification,
    ) -> PendingAction:
        tenant = require_tenant_id(tenant_id)
        target = parse_profile(profile)
        _require_reason(justification)
        current = self._store.read(tenant)
        if target is current.default_profile:
            raise VoiceProfileUnchanged("that profile is already the tenant's default")
        if current.canary_weight > CANARY_WEIGHT_MIN and current.canary_profile is target:
            raise VoiceCanaryIsDefault("stop the canary on that profile before making it default")
        return self._open(
            VOICE_PROFILE_SWITCH,
            current,
            actor,
            justification,
            {"control": VoiceControlChange.DEFAULT_PROFILE.value, "profile": target.value},
        )

    def open_canary(
        self,
        *,
        tenant_id: str,
        profile: object,
        weight: object,
        actor: ActorBlock,
        justification: Justification,
    ) -> PendingAction:
        tenant = require_tenant_id(tenant_id)
        target = parse_profile(profile)
        share = parse_canary_weight(weight)
        _require_reason(justification)
        current = self._store.read(tenant)
        if share > CANARY_WEIGHT_MIN and target is current.default_profile:
            raise VoiceCanaryIsDefault("a canary of the default profile routes nothing new")
        return self._open(
            VOICE_CANARY_SET,
            current,
            actor,
            justification,
            {
                "control": VoiceControlChange.CANARY.value,
                "profile": target.value,
                "weight": str(share),
            },
        )

    def approve(
        self,
        pending_id: str,
        *,
        action: DangerousAction,
        approver: ActorBlock,
        assertion_id: str,
    ) -> TenantVoiceControl:
        """The second key. Refuses — without spending the ceremony — when the
        route names another action or the control moved since the request."""
        pending = self._four_eyes.get(pending_id)
        if pending.action.id != action.id or action not in VOICE_CEREMONIES:
            raise VoiceActionMismatch("that pending action belongs to another route")
        tenant = pending.evidence["tenant"]
        base = int(pending.evidence["base_revision"])
        current = self._store.read(tenant)
        if current.revision != base:
            raise VoiceControlChanged("the control moved since this change was requested")
        approved = self._four_eyes.approve(pending_id, approver=approver, assertion_id=assertion_id)
        updated = self._apply(
            current, approved.evidence, requester=approved.actor, approver=approver
        )
        try:
            return self._store.write(updated, expected_revision=base)
        except VoiceControlConflict:
            raise VoiceControlChanged("the control moved while the approval landed") from None

    def pending(self) -> tuple[PendingAction, ...]:
        """Voice ceremonies still awaiting their second key."""
        return tuple(p for p in self._four_eyes.pending() if p.action in VOICE_CEREMONIES)

    # -- internals ---------------------------------------------------------------------

    def _open(
        self,
        action: DangerousAction,
        current: TenantVoiceControl,
        actor: ActorBlock,
        justification: Justification,
        extra: Mapping[str, str],
    ) -> PendingAction:
        return self._four_eyes.open(
            action=action,
            actor=actor,
            target_ref=f"voice:{current.tenant_id}",
            justification=justification,
            evidence={
                "tenant": current.tenant_id,
                "base_revision": str(current.revision),
                **extra,
            },
            ttl=VOICE_PENDING_TTL,
        )

    def _apply(
        self,
        current: TenantVoiceControl,
        evidence: Mapping[str, str],
        *,
        requester: ActorBlock,
        approver: ActorBlock,
    ) -> TenantVoiceControl:
        change = VoiceControlChange(evidence["control"])
        fields: dict[str, object]
        if change is VoiceControlChange.KILL_SWITCH_RELEASE:
            fields = {"kill_switch": False}
        elif change is VoiceControlChange.DEFAULT_PROFILE:
            fields = {"default_profile": parse_profile(evidence["profile"])}
        else:
            share = parse_canary_weight(int(evidence["weight"]))
            profile = parse_profile(evidence["profile"]) if share > CANARY_WEIGHT_MIN else None
            fields = {"canary_profile": profile, "canary_weight": share}
        return self._next(
            current,
            fields,
            change=change,
            changed_by=requester.subject,
            approved_by=approver.subject,
        )

    def _next(
        self,
        current: TenantVoiceControl,
        fields: Mapping[str, object],
        *,
        change: VoiceControlChange,
        changed_by: str,
        approved_by: str | None,
    ) -> TenantVoiceControl:
        return TenantVoiceControl.model_validate(
            {
                **current.model_dump(),
                **fields,
                "revision": current.revision + 1,
                "changed_at": self._clock(),
                "changed_by": changed_by,
                "approved_by": approved_by,
                "last_change": change,
            }
        )
