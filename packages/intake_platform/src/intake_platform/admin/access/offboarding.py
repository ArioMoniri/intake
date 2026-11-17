"""One-action offboarding and the 60-day dormancy rule (INT-366; files/08 §2.4).

    "Offboarding: Keycloak is the single source of truth. An SCIM/HR-triggered
    disable revokes OIDC sessions and OpenBao leases and the Grafana / Langfuse
    / Unleash accounts in one action [...] 60-day auto-disable on no login. A
    departed clinical_lead's pending four-eyes approvals expire."

**The pipeline**, in this order, each step write-ahead on the audit chain
(``admin.offboarding.<system>.intent`` before the call, then ``.revoked`` or
``.failed``):

1. ``keycloak_account`` — disable the account first, so no new login and no
   offline-token refresh can happen while the rest runs;
2. ``keycloak_sessions`` — end every session it holds;
3. ``openbao_leases`` — disable the OpenBao identity and revoke its tokens,
   which revokes their leases;
4. every configured console system: a programmatic one runs its adapter like
   the steps above; a manual one is recorded ``manual_pending`` and stays so
   until an audited ``manual_confirmed``.

A failed step does not stop the next one — a Keycloak outage is no reason to
leave OpenBao tokens alive — and it keeps the offboarding incomplete. Nothing
is skipped silently: every configured system gets a row.

**State lives on the chain.** Rows carry ``offboarding:<id>:<subject>`` and
:func:`offboardings_from` folds them back into :class:`Offboarding` values, so
an incomplete offboarding survives a restart and is visible from every replica.
Ids only (invariant 6): the subject is the Keycloak user id, the reason is a
closed enum member, and nothing else travels.
"""

from __future__ import annotations

import asyncio
import enum
import re
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import partial
from typing import Final

from intake_platform.admin.access.directory import (
    DirectoryUser,
    IdentityDirectory,
    LeaseRevoker,
    RevocationFailed,
)
from intake_platform.admin.access.systems import (
    BUILT_IN_SYSTEMS,
    AccountRevoker,
    ConsoleAccountSystem,
    Revocation,
)
from intake_platform.admin.audit import ADMIN_BASIS_REF, AdminAuditSink
from intake_platform.admin.metrics import ADMIN_OFFBOARDING_TOTAL
from intake_platform.audit import AuditEntry

__all__ = [
    "DORMANT_AFTER_DAYS",
    "STEP_PREFIX",
    "Offboarding",
    "OffboardingReason",
    "OffboardingRefused",
    "OffboardingStep",
    "StepOutcome",
    "confirm_manual",
    "dormant_users",
    "offboard",
    "offboardings_from",
]

#: files/08 §2.4: "60-day auto-disable on no login".
DORMANT_AFTER_DAYS: Final = 60

STEP_PREFIX: Final = "admin.offboarding."
_REF_PREFIX: Final = "offboarding:"
_ID: Final = re.compile(r"[0-9a-f]{32}")


class OffboardingRefused(Exception):
    """A request the pipeline will not run. ``code`` is machine-shaped."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OffboardingReason(enum.StrEnum):
    """Why access ends. KVKK 2018/10 measure 2(d) names the first two
    ("görev değişikliği olan ya da işten ayrılan"); the dormant reason is the
    scheduled job's alone and a console caller may not claim it."""

    DEPARTURE = "departure"
    ROLE_CHANGE = "role_change"
    ACCESS_REVIEW = "access_review"
    SECURITY_INCIDENT = "security_incident"
    DORMANT = "dormant_60d"


class StepOutcome(enum.StrEnum):
    REVOKED = "revoked"
    FAILED = "failed"
    PENDING_CONFIRMATION = "manual_pending"
    CONFIRMED = "manual_confirmed"


_DONE: Final = frozenset({StepOutcome.REVOKED, StepOutcome.CONFIRMED})


@dataclass(frozen=True)
class OffboardingStep:
    system: str
    manual: bool
    outcome: StepOutcome
    runbook: str | None


@dataclass(frozen=True)
class Offboarding:
    offboarding_id: str
    subject: str
    reason: OffboardingReason
    steps: tuple[OffboardingStep, ...]
    expired_pending_actions: int = 0

    @property
    def complete(self) -> bool:
        return bool(self.steps) and all(step.outcome in _DONE for step in self.steps)

    def step(self, system: str) -> OffboardingStep | None:
        return next((step for step in self.steps if step.system == system), None)


def _ref(offboarding_id: str, subject: str) -> str:
    return f"{_REF_PREFIX}{offboarding_id}:{subject}"


async def _record(sink: AdminAuditSink, actor: str, action: str, ref: str) -> None:
    await sink.record(actor=actor, action=action, resource_ref=ref, consent_scope=ADMIN_BASIS_REF)


async def _run_step(
    sink: AdminAuditSink,
    actor: str,
    ref: str,
    system: str,
    call: Callable[[], object],
    runbook: str | None,
) -> OffboardingStep:
    await _record(sink, actor, f"{STEP_PREFIX}{system}.intent", ref)
    try:
        await asyncio.to_thread(call)
    except RevocationFailed:
        outcome = StepOutcome.FAILED
    else:
        outcome = StepOutcome.REVOKED
    await _record(sink, actor, f"{STEP_PREFIX}{system}.{outcome.value}", ref)
    return OffboardingStep(system=system, manual=False, outcome=outcome, runbook=runbook)


async def offboard(
    *,
    subject: str,
    reason: OffboardingReason,
    actor: str,
    directory: IdentityDirectory,
    leases: LeaseRevoker,
    systems: Sequence[ConsoleAccountSystem],
    adapters: Mapping[str, AccountRevoker],
    sink: AdminAuditSink,
    trigger: str,
) -> Offboarding:
    """Revoke everything ``subject`` holds, in one action, audited per step."""
    offboarding_id = uuid.uuid4().hex
    ref = _ref(offboarding_id, subject)
    await _record(sink, actor, f"{STEP_PREFIX}opened.{reason.value}", ref)
    built_in: tuple[tuple[str, Callable[[], object]], ...] = (
        ("keycloak_account", partial(directory.disable, subject)),
        ("keycloak_sessions", partial(directory.revoke_sessions, subject)),
        ("openbao_leases", partial(leases.revoke_for, subject)),
    )
    steps = [
        await _run_step(sink, actor, ref, system_id, call, None) for system_id, call in built_in
    ]
    for system in systems:
        if system.revocation is Revocation.PROGRAMMATIC:
            call = partial(adapters[system.id].revoke_for, subject)
            steps.append(await _run_step(sink, actor, ref, system.id, call, system.runbook))
            continue
        await _record(
            sink, actor, f"{STEP_PREFIX}{system.id}.{StepOutcome.PENDING_CONFIRMATION}", ref
        )
        steps.append(
            OffboardingStep(
                system=system.id,
                manual=True,
                outcome=StepOutcome.PENDING_CONFIRMATION,
                runbook=system.runbook,
            )
        )
    result = Offboarding(offboarding_id, subject, reason, tuple(steps))
    ADMIN_OFFBOARDING_TOTAL.labels(trigger=trigger, complete=str(result.complete).lower()).inc()
    return result


async def confirm_manual(
    offboarding: Offboarding, *, system: str, actor: str, sink: AdminAuditSink
) -> Offboarding:
    """Close one manual step. Only a step the offboarding listed as manual,
    and still pending, can be confirmed."""
    step = offboarding.step(system)
    if step is None:
        raise OffboardingRefused("offboarding_system_unknown")
    if not step.manual:
        raise OffboardingRefused("offboarding_step_not_manual")
    if step.outcome is not StepOutcome.PENDING_CONFIRMATION:
        raise OffboardingRefused("offboarding_step_already_confirmed")
    await _record(
        sink,
        actor,
        f"{STEP_PREFIX}{system}.{StepOutcome.CONFIRMED}",
        _ref(offboarding.offboarding_id, offboarding.subject),
    )
    steps = tuple(
        replace(item, outcome=StepOutcome.CONFIRMED) if item.system == system else item
        for item in offboarding.steps
    )
    return replace(offboarding, steps=steps)


def offboardings_from(
    entries: Iterable[AuditEntry], systems: Sequence[ConsoleAccountSystem] = ()
) -> dict[str, Offboarding]:
    """Fold the chain's offboarding rows back into state, keyed by id.

    A step whose intent row has no outcome row — a crash between the two —
    reads as failed: it was attempted and nobody saw it succeed.
    """
    runbooks = {system.id: system.runbook for system in systems}
    opened: dict[str, tuple[str, OffboardingReason]] = {}
    steps: dict[str, dict[str, OffboardingStep]] = {}
    for entry in entries:
        if not entry.action.startswith(STEP_PREFIX) or not entry.resource_ref.startswith(
            _REF_PREFIX
        ):
            continue
        offboarding_id, _, subject = entry.resource_ref[len(_REF_PREFIX) :].partition(":")
        if not _ID.fullmatch(offboarding_id) or not subject:
            continue
        stem, _, verb = entry.action[len(STEP_PREFIX) :].rpartition(".")
        if stem == "opened":
            try:
                opened[offboarding_id] = (subject, OffboardingReason(verb))
            except ValueError:
                continue
            continue
        system = stem
        known = steps.setdefault(offboarding_id, {})
        manual = system not in BUILT_IN_SYSTEMS and verb in {
            StepOutcome.PENDING_CONFIRMATION,
            StepOutcome.CONFIRMED,
        }
        prior = known.get(system)
        if verb == "intent":
            outcome = StepOutcome.FAILED
        else:
            try:
                outcome = StepOutcome(verb)
            except ValueError:
                continue
        known[system] = OffboardingStep(
            system=system,
            manual=manual or (prior is not None and prior.manual),
            outcome=outcome,
            runbook=runbooks.get(system),
        )
    return {
        offboarding_id: Offboarding(
            offboarding_id=offboarding_id,
            subject=subject,
            reason=reason,
            steps=tuple(steps.get(offboarding_id, {}).values()),
        )
        for offboarding_id, (subject, reason) in opened.items()
    }


def dormant_users(users: Iterable[DirectoryUser], *, now: datetime) -> list[DirectoryUser]:
    """Enabled staff accounts with no login for sixty days or more. An account
    that never logged in counts from its creation."""
    threshold = timedelta(days=DORMANT_AFTER_DAYS)
    return [
        user
        for user in users
        if user.enabled and user.is_staff and now - user.last_activity_at >= threshold
    ]
