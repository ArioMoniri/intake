"""Four-eyes as a server-side pending-action protocol (INT-180; files/08 §8.2).

Four-eyes is a **property**, not a screen. This module makes the property
checkable and, just as importantly, bounds it.

**What it covers.** A second key must come from a different account, a
different WebAuthn credential, a different browser session, an eligible
approver role, and — at tier 3 — a different organisation; the assertion is
fresh and single-use across the whole service; and an unapproved action
expires rather than waiting for someone to inherit it (§2.4).

**What it does not cover: two accounts held by one person.** Nothing in an
OIDC claim set says two subs are two humans. The ceremony proves distinct
account, credential and session, and that is all it proves; closing the gap
needs identity proofing or an approver pool the actor cannot enrol into,
which is an operating control, not a field. ``tests/admin/test_four_eyes.py``
asserts the acceptance so the limit stays visible.

**What the approver sees.** :class:`ApprovalBrief` carries the requester's
identity block, the tier, the target, the reason class, the full free text,
the controller-instruction reference and the evidence. An approval screen
showing only "Approve?" is theatre, and a brief that omitted any of these
would produce exactly that screen.

Storage is a process-local mapping behind :class:`FourEyesService`. That is
the failure direction the design already assumes: §2.4 has pending approvals
expire, and a restart that drops them refuses rather than grants.
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from intake_platform.admin.actions import ActionTier, DangerousAction
from intake_platform.admin.roles import AdminRole

__all__ = [
    "ActorBlock",
    "ApprovalBrief",
    "ApproverRoleIneligible",
    "AssertionReused",
    "FourEyesRefused",
    "FourEyesService",
    "Justification",
    "PendingAction",
    "PendingActionDecided",
    "PendingActionExpired",
    "PendingActionState",
    "SelfApproval",
    "SharedCredential",
    "SharedOrganisation",
    "SharedSession",
    "UnknownPendingAction",
]


class FourEyesRefused(Exception):
    """Base refusal. ``code`` is a stable machine code — a refusal reaches an
    HTTP body and a metric label, and narrative in either is how PHI travels
    (invariant 6)."""

    code = "four_eyes_refused"


class SelfApproval(FourEyesRefused):
    code = "four_eyes_self_approval"


class SharedCredential(FourEyesRefused):
    code = "four_eyes_shared_credential"


class SharedSession(FourEyesRefused):
    code = "four_eyes_shared_session"


class SharedOrganisation(FourEyesRefused):
    code = "four_eyes_shared_organisation"


class ApproverRoleIneligible(FourEyesRefused):
    code = "four_eyes_approver_role"


class AssertionReused(FourEyesRefused):
    code = "four_eyes_assertion_reused"


class PendingActionExpired(FourEyesRefused):
    code = "four_eyes_expired"


class PendingActionDecided(FourEyesRefused):
    code = "four_eyes_already_decided"


class UnknownPendingAction(FourEyesRefused):
    code = "four_eyes_unknown"


@dataclass(frozen=True)
class ActorBlock:
    """files/08 §8.1's actor block. The AAGUID and the credential id are what
    make "distinct human" checkable after the fact — and the AAGUID alone is
    not enough, because it identifies an authenticator MODEL, not a key."""

    subject: str
    role: AdminRole
    org: str
    authenticator_aaguid: str
    credential_id: str
    session_id: str

    def replace_role(self, role: AdminRole) -> ActorBlock:
        return replace(self, role=role)

    def replace_org(self, org: str) -> ActorBlock:
        return replace(self, org=org)

    def replace_credential(self, credential_id: str) -> ActorBlock:
        return replace(self, credential_id=credential_id)

    def replace_session(self, session_id: str) -> ActorBlock:
        return replace(self, session_id=session_id)


@dataclass(frozen=True)
class Justification:
    """§8.1's justification block. ``reason_class`` is a closed enum member
    supplied by the caller's own vocabulary; ``free_text`` is staff prose and
    never reaches the chain, a log or a metric label."""

    reason_class: object
    free_text: str
    controller_instruction_ref: str | None


class PendingActionState(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    EXPIRED = "expired"


@dataclass(frozen=True)
class PendingAction:
    id: str
    action: DangerousAction
    actor: ActorBlock
    target_ref: str
    justification: Justification
    evidence: Mapping[str, str]
    created_at: datetime
    expires_at: datetime
    state: PendingActionState
    approver: ActorBlock | None
    assertion_id: str | None


@dataclass(frozen=True)
class ApprovalBrief:
    """Everything the second pair of eyes needs in order to DISAGREE."""

    action_id: str
    dangerous_action_id: str
    tier: ActionTier
    requested_by: ActorBlock
    target_ref: str
    reason_class: object
    free_text: str
    controller_instruction_ref: str | None
    evidence: Mapping[str, str]
    created_at: datetime
    expires_at: datetime
    state: PendingActionState
    approver_rule: str


def _approver_rule(action: DangerousAction) -> str:
    """A sentence the approver can read before deciding. Roles and a boolean
    tell them what the system will enforce; nothing here is a judgement."""
    roles = ", ".join(sorted(role.value for role in action.approver_roles))
    organisation = (
        "from a different organisation"
        if action.approver_must_differ_org
        else "from any organisation"
    )
    return (
        f"tier {int(action.tier)}: a second key held by one of [{roles}], {organisation}, "
        "on a different account, WebAuthn credential and session from the requester, "
        "presenting a fresh single-use assertion"
    )


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class FourEyesService:
    """The pending-action protocol. Every refusal is a typed
    :class:`FourEyesRefused`; nothing here returns a boolean, because a
    ceremony that fails silently is a ceremony that did not happen."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock if clock is not None else _utc_now
        self._pending: dict[str, PendingAction] = {}
        self._used_assertions: set[str] = set()

    def open(
        self,
        *,
        action: DangerousAction,
        actor: ActorBlock,
        target_ref: str,
        justification: Justification,
        evidence: Mapping[str, str],
        ttl: timedelta,
    ) -> PendingAction:
        if actor.role not in action.actor_roles:
            raise ApproverRoleIneligible(
                f"{actor.role.value} may not request {action.id} (files/08 §8.2)"
            )
        if ttl <= timedelta(0):
            raise ValueError("a pending action needs a forward expiry (files/08 §2.4)")
        now = self._clock()
        pending = PendingAction(
            id=uuid.uuid4().hex,
            action=action,
            actor=actor,
            target_ref=target_ref,
            justification=justification,
            evidence=dict(evidence),
            created_at=now,
            expires_at=now + ttl,
            state=PendingActionState.PENDING,
            approver=None,
            assertion_id=None,
        )
        self._pending[pending.id] = pending
        return pending

    def get(self, action_id: str) -> PendingAction:
        try:
            return self._pending[action_id]
        except KeyError:
            raise UnknownPendingAction("no pending action with that id") from None

    def brief(self, action_id: str) -> ApprovalBrief:
        pending = self.get(action_id)
        return ApprovalBrief(
            action_id=pending.id,
            dangerous_action_id=pending.action.id,
            tier=pending.action.tier,
            requested_by=pending.actor,
            target_ref=pending.target_ref,
            reason_class=pending.justification.reason_class,
            free_text=pending.justification.free_text,
            controller_instruction_ref=pending.justification.controller_instruction_ref,
            evidence=pending.evidence,
            created_at=pending.created_at,
            expires_at=pending.expires_at,
            state=pending.state,
            approver_rule=_approver_rule(pending.action),
        )

    def approve(self, action_id: str, *, approver: ActorBlock, assertion_id: str) -> PendingAction:
        pending = self.get(action_id)
        if pending.state is not PendingActionState.PENDING:
            raise PendingActionDecided(f"action is {pending.state.value}")
        if self._clock() > pending.expires_at:
            self._pending[action_id] = replace(pending, state=PendingActionState.EXPIRED)
            raise PendingActionExpired("the approval window closed (files/08 §2.4)")
        self._check_distinct(pending, approver)
        if not assertion_id:
            raise AssertionReused("a step-up assertion id is required (files/08 §2.3)")
        if assertion_id in self._used_assertions:
            raise AssertionReused(
                "that WebAuthn assertion has already been spent; a remembered device is "
                "how a four-eyes ceremony becomes one person with two tabs"
            )
        self._used_assertions.add(assertion_id)
        approved = replace(
            pending,
            state=PendingActionState.APPROVED,
            approver=approver,
            assertion_id=assertion_id,
        )
        self._pending[action_id] = approved
        return approved

    def check_approvable(self, action_id: str, *, approver: ActorBlock) -> PendingAction:
        """What :meth:`approve` checks before it spends an assertion — state,
        window, distinctness, role — and nothing spent. INT-563: the step-up
        refuses an approval that could never pass before anyone is asked for
        a passkey. :meth:`approve` checks all of it again."""
        pending = self.get(action_id)
        if pending.state is not PendingActionState.PENDING:
            raise PendingActionDecided(f"action is {pending.state.value}")
        if self._clock() > pending.expires_at:
            raise PendingActionExpired("the approval window closed (files/08 §2.4)")
        self._check_distinct(pending, approver)
        return pending

    def _check_distinct(self, pending: PendingAction, approver: ActorBlock) -> None:
        actor = pending.actor
        if approver.subject == actor.subject:
            raise SelfApproval("an actor may not approve their own action (files/08 §2.1)")
        if approver.credential_id == actor.credential_id:
            raise SharedCredential("the approver presented the requester's WebAuthn credential")
        if approver.session_id == actor.session_id:
            raise SharedSession("the approver is in the requester's session")
        if approver.role not in pending.action.approver_roles:
            raise ApproverRoleIneligible(
                f"{approver.role.value} may not approve {pending.action.id}"
            )
        if pending.action.approver_must_differ_org and approver.org == actor.org:
            raise SharedOrganisation("tier 3 requires two organisations (files/08 §8.2)")

    def pending(self) -> tuple[PendingAction, ...]:
        """Every action still awaiting its second key and inside its window,
        oldest first — what a console lists for an approver (INT-182). Read
        only: the sweep that marks and counts expiry stays :meth:`expire_due`."""
        now = self._clock()
        waiting = (
            pending
            for pending in self._pending.values()
            if pending.state is PendingActionState.PENDING and now <= pending.expires_at
        )
        return tuple(sorted(waiting, key=lambda pending: (pending.created_at, pending.id)))

    def expire_requested_by(self, subject: str) -> int:
        """files/08 §2.4: a departed person's pending requests expire; they do
        not sit in a queue waiting for someone to inherit them. Returns how
        many were expired."""
        expired = 0
        for action_id, pending in list(self._pending.items()):
            if pending.state is PendingActionState.PENDING and pending.actor.subject == subject:
                self._pending[action_id] = replace(pending, state=PendingActionState.EXPIRED)
                expired += 1
        return expired

    def expire_due(self) -> int:
        """Sweep the pending set. Returns how many actions expired, which is
        what ``admin.pending_action_expired_total`` counts."""
        now = self._clock()
        expired = 0
        for action_id, pending in list(self._pending.items()):
            if pending.state is PendingActionState.PENDING and now > pending.expires_at:
                self._pending[action_id] = replace(pending, state=PendingActionState.EXPIRED)
                expired += 1
        return expired
