"""Deploy-freeze governance — one key to freeze, four eyes to lift (INT-187).

The write side of :mod:`intake_platform.release_freeze`, and the rule that
makes files/08 §8.2's asymmetry checkable for the deploy path:

- **Toward frozen, one key.** :meth:`DeployFreezeGovernor.engage` is tier 1
  (:data:`~intake_platform.admin.actions.DEPLOY_FREEZE_ENGAGE`): one eligible
  actor, a mandatory reason, no approver. A second key on the safe direction is
  an availability control on a safety control (files/08 §0c F17). Engaging an
  engaged freeze changes nothing and says so.
- **Toward shipping, two keys.** :meth:`DeployFreezeGovernor.open_lift` opens a
  tier-2 ceremony through the INT-180
  :class:`~intake_platform.admin.four_eyes.FourEyesService`; nothing changes
  until a distinct human, credential and session approves with a fresh
  single-use assertion.
- **An approval binds to what it approved.** The ceremony carries the record's
  revision at request time, and the approval refuses — without spending the
  ceremony — if the freeze moved since: a freeze lifted and re-engaged for a
  new incident must not be undone by approving the old request.

Change reasons are INT-188's: a closed
:class:`~intake_platform.admin.flag_governance.FlagChangeReason` plus mandatory
free text, which never enters the store or the ceremony's evidence (invariant
6). The freeze is deliberately **not** a key in the generic flag store —
Unleash tokens flip flags with no audit row and CI runners hold them
(invariant 34), and a freeze the pipeline can lift is no freeze. Like the other
governors this module is pure rule over injected state: the write-ahead audit
row and the metric belong to the route that calls it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from intake_platform.admin.actions import (
    CICD_CEREMONIES,
    DEPLOY_FREEZE_ENGAGE,
    DEPLOY_FREEZE_LIFT,
)
from intake_platform.admin.flag_governance import ChangeReasonMissing
from intake_platform.admin.four_eyes import (
    ActorBlock,
    FourEyesService,
    Justification,
    PendingAction,
)
from intake_platform.release_freeze import (
    DeployFreeze,
    DeployFreezeChange,
    ReleaseFreezeConflict,
    ReleaseFreezeStore,
)

__all__ = [
    "FREEZE_PENDING_TTL",
    "FREEZE_TARGET",
    "DeployFreezeGovernor",
    "FreezeActionMismatch",
    "FreezeChangeResult",
    "FreezeChanged",
    "FreezeGovernanceRefused",
    "FreezeNotEngaged",
    "FreezeRoleIneligible",
]

#: files/10 §2: "Actor initiates → 15-minute TTL → a different sub … approves".
FREEZE_PENDING_TTL: Final = timedelta(minutes=15)
#: The ceremony's target: the deployment's freeze, which is one record.
FREEZE_TARGET: Final = "release:deploy-freeze"

#: The safe direction must not bounce off a concurrent write: an incident
#: responder should not press the button twice because another change landed
#: in the same millisecond. Re-read and re-apply, a bounded number of times.
_ENGAGE_ATTEMPTS: Final = 3


class FreezeGovernanceRefused(Exception):
    """Base refusal; ``code`` is machine-shaped and reaches an HTTP body."""

    code = "release_freeze_refused"


class FreezeRoleIneligible(FreezeGovernanceRefused):
    code = "release_freeze_role_ineligible"


class FreezeNotEngaged(FreezeGovernanceRefused):
    code = "release_freeze_not_engaged"


class FreezeChanged(FreezeGovernanceRefused):
    code = "release_freeze_changed"


class FreezeActionMismatch(FreezeGovernanceRefused):
    code = "release_freeze_action_mismatch"


@dataclass(frozen=True)
class FreezeChangeResult:
    freeze: DeployFreeze
    changed: bool


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _require_reason(justification: Justification) -> None:
    """INT-188: a change reason is mandatory at the write, on both directions."""
    if not justification.free_text.strip():
        raise ChangeReasonMissing("a deploy freeze change needs a reason (INT-188)")


def _reason_class(justification: Justification) -> str:
    value = justification.reason_class
    return str(getattr(value, "value", value))


class DeployFreezeGovernor:
    """See the module docstring. Every refusal is typed; nothing returns a
    boolean, because a freeze change that fails silently did not happen."""

    def __init__(
        self,
        four_eyes: FourEyesService,
        store: ReleaseFreezeStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._four_eyes = four_eyes
        self._store = store
        self._clock = clock if clock is not None else _utc_now

    # -- tier 1: toward frozen --------------------------------------------------------

    def engage(self, *, actor: ActorBlock, justification: Justification) -> FreezeChangeResult:
        if actor.role not in DEPLOY_FREEZE_ENGAGE.actor_roles:
            raise FreezeRoleIneligible(f"{actor.role.value} may not freeze deploys")
        _require_reason(justification)
        for _ in range(_ENGAGE_ATTEMPTS):
            current = self._store.read()
            if current.engaged:
                return FreezeChangeResult(freeze=current, changed=False)
            engaged = self._next(
                current,
                engaged=True,
                change=DeployFreezeChange.ENGAGE,
                changed_by=actor.subject,
                approved_by=None,
                reason_class=_reason_class(justification),
            )
            try:
                written = self._store.write(engaged, expected_revision=current.revision)
            except ReleaseFreezeConflict:
                continue
            return FreezeChangeResult(freeze=written, changed=True)
        raise FreezeChanged("the freeze kept moving while it was engaged")

    # -- tier 2: toward shipping ------------------------------------------------------

    def open_lift(self, *, actor: ActorBlock, justification: Justification) -> PendingAction:
        _require_reason(justification)
        current = self._store.read()
        if not current.engaged:
            raise FreezeNotEngaged("deploys are not frozen; there is nothing to lift")
        return self._four_eyes.open(
            action=DEPLOY_FREEZE_LIFT,
            actor=actor,
            target_ref=FREEZE_TARGET,
            justification=justification,
            evidence={
                "control": DeployFreezeChange.LIFT.value,
                "base_revision": str(current.revision),
            },
            ttl=FREEZE_PENDING_TTL,
        )

    def approve_lift(
        self, pending_id: str, *, approver: ActorBlock, assertion_id: str
    ) -> DeployFreeze:
        """The second key. Refuses — without spending the ceremony — when the
        id names another module's action or the freeze moved since the request."""
        pending = self._four_eyes.get(pending_id)
        if pending.action not in CICD_CEREMONIES:
            raise FreezeActionMismatch("that pending action belongs to another route")
        base = int(pending.evidence["base_revision"])
        current = self._store.read()
        if current.revision != base or not current.engaged:
            raise FreezeChanged("the freeze moved since this lift was requested")
        approved = self._four_eyes.approve(pending_id, approver=approver, assertion_id=assertion_id)
        lifted = self._next(
            current,
            engaged=False,
            change=DeployFreezeChange.LIFT,
            changed_by=approved.actor.subject,
            approved_by=approver.subject,
            reason_class=_reason_class(approved.justification),
        )
        try:
            return self._store.write(lifted, expected_revision=base)
        except ReleaseFreezeConflict:
            raise FreezeChanged("the freeze moved while the approval landed") from None

    def pending(self) -> tuple[PendingAction, ...]:
        """Lift requests still awaiting their second key."""
        return tuple(p for p in self._four_eyes.pending() if p.action in CICD_CEREMONIES)

    # -- internals ---------------------------------------------------------------------

    def _next(
        self,
        current: DeployFreeze,
        *,
        engaged: bool,
        change: DeployFreezeChange,
        changed_by: str,
        approved_by: str | None,
        reason_class: str,
    ) -> DeployFreeze:
        fields: Mapping[str, object] = {
            "engaged": engaged,
            "revision": current.revision + 1,
            "changed_at": self._clock(),
            "changed_by": changed_by,
            "approved_by": approved_by,
            "last_change": change,
            "reason_class": reason_class,
        }
        return DeployFreeze.model_validate({**current.model_dump(), **fields})
