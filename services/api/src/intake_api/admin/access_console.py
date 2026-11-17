"""Access & identity handlers (INT-366; files/08 §2.4, §2.7, §3).

Five handlers, registered through the descriptor table like every console
route, so each is audited write-ahead, role-checked and — for the writes —
subject to the §2.7 read-only downgrade by the router before it runs:

- ``GET /admin/access/review`` — the review, generated on request from the
  Keycloak admin API and the audit chain;
- ``POST /admin/access/review/sign`` and ``.../{action_id}/countersign`` —
  the tier-2 ceremony that countersigns one section and lifts the downgrade;
- ``POST /admin/access/offboard`` and ``.../{offboarding_id}/confirm`` — the
  tier-1 offboarding and the audited confirmation of its manual steps.

Directory and OpenBao calls are synchronous httpx, so they run off the event
loop. Everything returned is an id, a role or enum name, a flag, a count, an
instant or a 128-bit digest — never a name or a mail address, and never chain
material (invariant 6, HB-I12).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Final

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from intake_platform.admin import AdminRole, AdminWiring, FourEyesRefused, Justification
from intake_platform.admin.access import DirectoryUnavailable, IdentityWiring, is_subject
from intake_platform.admin.access.directory import DirectoryUser
from intake_platform.admin.access.offboarding import (
    DORMANT_AFTER_DAYS,
    Offboarding,
    OffboardingReason,
    OffboardingRefused,
    StepOutcome,
    confirm_manual,
    offboard,
    offboardings_from,
)
from intake_platform.admin.access.review import (
    READ_ONLY_ROLES,
    REVIEW_MAX_AGE_DAYS,
    SIGNED_ACTION,
    AccessReview,
    generate_review,
    last_console_actions,
    scoped_to_tenant,
    section_rule,
    signed_resource_ref,
)
from intake_platform.admin.actions import ACCESS_REVIEW_SIGN
from intake_platform.admin.audit import ADMIN_BASIS_REF
from intake_platform.admin.four_eyes import SelfApproval
from intake_platform.admin.metrics import (
    ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL,
    ADMIN_PENDING_ACTION_EXPIRED_TOTAL,
)

from intake_api.admin.deps import AdminCaller
from intake_api.admin.views import pending_view
from intake_api.errors import (
    access_refused,
    access_request_invalid,
    access_unconfigured,
    directory_unavailable,
    four_eyes_refused,
    not_found,
)
from intake_api.state import get_state

__all__ = [
    "REVIEW_SCHEMA",
    "offboard_confirm",
    "offboard_run",
    "review_countersign",
    "review_read",
    "review_sign",
    "review_view",
]

REVIEW_SCHEMA: Final = "intake.admin.access_review.v1"

#: How long a signature waits for its countersignature. The countersign binds
#: to the population the signer saw (the digest is re-checked), so the window
#: bounds how long a signature can sit, not what it can approve; a day lets a
#: second reviewer in another organisation answer within one working day, and
#: an expired one is simply signed again (files/08 §2.4: pending approvals
#: expire rather than wait to be inherited).
SIGN_TTL: Final = timedelta(hours=24)

_OFFBOARDING_ID: Final = re.compile(r"[0-9a-f]{32}")
_SYSTEM_ID: Final = re.compile(r"[a-z][a-z0-9_]{1,31}")
#: The dormant reason is the scheduled job's; a person offboards for a reason.
_CONSOLE_REASONS: Final = frozenset(OffboardingReason) - {OffboardingReason.DORMANT}


# --- plumbing -------------------------------------------------------------------------


def _identity(wiring: AdminWiring) -> IdentityWiring:
    if wiring.identity is None:
        raise access_unconfigured()
    return wiring.identity


async def _body(request: Request, keys: frozenset[str]) -> Mapping[str, Any]:
    """The closed body shape, or 422. An extra key is refused rather than
    ignored — a field the server silently drops is a field nobody notices
    carrying something it should not."""
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise access_request_invalid("body_not_json") from None
    if not isinstance(payload, dict) or set(payload) != keys:
        raise access_request_invalid("body_shape")
    if not all(isinstance(value, str) for value in payload.values()):
        raise access_request_invalid("body_shape")
    return payload


def _sweep_expired(wiring: AdminWiring) -> None:
    expired = wiring.four_eyes.expire_due()
    if expired:
        ADMIN_PENDING_ACTION_EXPIRED_TOTAL.inc(expired)


async def _staff(identity: IdentityWiring) -> list[DirectoryUser]:
    try:
        return await run_in_threadpool(identity.directory.staff_users)
    except DirectoryUnavailable as err:
        raise directory_unavailable(err.code) from None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _days(value: float) -> float | None:
    """A day count for JSON; an unbounded age is ``null``, never ``Infinity``."""
    return None if value == float("inf") else round(value, 3)


def _current_digests(users: Sequence[DirectoryUser], wiring: AdminWiring) -> dict[str, str]:
    now = wiring.review_ledger.now()
    review = generate_review(users, wiring.review_ledger, {}, now=now)
    return {section.section: section.review_digest for section in review.sections}


# --- views ----------------------------------------------------------------------------


def review_view(review: AccessReview, pending: Sequence[Offboarding]) -> dict[str, Any]:
    return {
        "schema": REVIEW_SCHEMA,
        "generated_at": review.generated_at.isoformat(),
        "policy": {
            "review_max_age_days": REVIEW_MAX_AGE_DAYS,
            "auto_disable_after_days": DORMANT_AFTER_DAYS,
            "read_only_roles": sorted(role.value for role in READ_ONLY_ROLES),
        },
        "status": {
            "review_age_days": _days(review.review_age_days),
            "never_reviewed": review.review_age_days == float("inf"),
            "read_only_roles": sorted(role.value for role in review.read_only_roles),
        },
        "sections": [
            {
                "section": section.section,
                "signer_role": section.signer_role.value,
                "signer_tenant": section.signer_tenant,
                "countersigner": (
                    "different_organisation" if section.countersigner_external else "second_person"
                ),
                "holders": list(section.holders),
                "review_digest": section.review_digest,
                "last_signed_at": _iso(section.last_signed_at),
                "age_days": _days(section.age_days),
                "overdue": section.overdue,
            }
            for section in review.sections
        ],
        "holders": [
            {
                "subject": holder.subject,
                "username": holder.username,
                "enabled": holder.enabled,
                "roles": list(holder.roles),
                "tenant": holder.tenant,
                "org": holder.org,
                "sections": list(holder.sections),
                "created_at": holder.created_at.isoformat(),
                "last_login_at": _iso(holder.last_login_at),
                "days_since_activity": round(holder.days_since_activity, 3),
                "days_until_auto_disable": round(holder.days_until_auto_disable, 3),
                "last_console_action_at": _iso(holder.last_console_action_at),
                "last_reviewed_at": _iso(holder.last_reviewed_at),
            }
            for holder in review.holders
        ],
        "pending_offboardings": [
            {
                "offboarding_id": item.offboarding_id,
                "subject": item.subject,
                "reason_class": item.reason.value,
                "pending_systems": [
                    step.system
                    for step in item.steps
                    if step.outcome is StepOutcome.PENDING_CONFIRMATION
                ],
                "failed_systems": [
                    step.system for step in item.steps if step.outcome is StepOutcome.FAILED
                ],
            }
            for item in pending
        ],
    }


def _offboarding_view(result: Offboarding) -> dict[str, Any]:
    return {
        "offboarding_id": result.offboarding_id,
        "subject": result.subject,
        "reason_class": result.reason.value,
        "complete": result.complete,
        "expired_pending_actions": result.expired_pending_actions,
        "steps": [
            {
                "system": step.system,
                "kind": "manual" if step.manual else "programmatic",
                "outcome": step.outcome.value,
                "runbook": step.runbook,
            }
            for step in result.steps
        ],
    }


# --- the review -----------------------------------------------------------------------


async def review_read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    identity = _identity(wiring)
    entries = await wiring.review_ledger.refresh(get_state(request).audit)
    users = await _staff(identity)
    review = generate_review(
        users, wiring.review_ledger, last_console_actions(entries), now=wiring.review_ledger.now()
    )
    pending = [
        item for item in offboardings_from(entries, identity.systems).values() if not item.complete
    ]
    if role is AdminRole.TENANT_CLINICAL_RESPONSIBLE:
        return review_view(scoped_to_tenant(review, caller.tenant), ())
    return review_view(review, pending)


async def review_sign(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep_expired(wiring)
    identity = _identity(wiring)
    payload = await _body(request, frozenset({"section", "review_digest"}))
    section, digest = payload["section"], payload["review_digest"]
    rule = section_rule(section)
    if rule is None:
        raise access_refused("access_review_section_unknown")
    await wiring.review_ledger.refresh(get_state(request).audit)
    current = _current_digests(await _staff(identity), wiring)
    if section not in current:
        raise access_refused("access_review_section_unknown")
    if rule.signer_role not in caller.principal.roles or (
        rule.signer_tenant is not None and caller.tenant != rule.signer_tenant
    ):
        raise access_refused("access_review_signer_ineligible")
    if current[section] != digest:
        raise access_refused("access_review_changed")
    try:
        pending = wiring.four_eyes.open(
            action=ACCESS_REVIEW_SIGN,
            actor=caller.principal.actor_block(rule.signer_role),
            target_ref=signed_resource_ref(section, digest),
            justification=Justification(
                reason_class="access_review_signoff", free_text="", controller_instruction_ref=None
            ),
            evidence={"section": section, "review_digest": digest},
            ttl=SIGN_TTL,
        )
    except FourEyesRefused as refusal:
        raise four_eyes_refused(refusal.code) from None
    return {**pending_view(pending), "section": section, "review_digest": digest}


async def review_countersign(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep_expired(wiring)
    identity = _identity(wiring)
    payload = await _body(request, frozenset({"assertion_id"}))
    try:
        pending = wiring.four_eyes.get(request.path_params["action_id"])
    except FourEyesRefused:
        raise not_found() from None
    if pending.action.id != ACCESS_REVIEW_SIGN.id:
        raise not_found()
    section = pending.evidence["section"]
    digest = pending.evidence["review_digest"]
    rule = section_rule(section)
    if rule is None:
        raise not_found()
    approver = caller.principal.actor_block(role)
    # files/08 §2.7: "compliance_officer plus an external signature for
    # platform_owner". Checked before the ceremony spends the assertion; a
    # self-countersign is left for the ceremony to name as what it is.
    if (
        rule.countersigner_external
        and approver.subject != pending.actor.subject
        and approver.org == pending.actor.org
    ):
        raise four_eyes_refused("four_eyes_shared_organisation")
    current = _current_digests(await _staff(identity), wiring)
    if current.get(section) != digest:
        raise access_refused("access_review_changed")
    try:
        wiring.four_eyes.approve(
            pending.id, approver=approver, assertion_id=payload["assertion_id"]
        )
    except SelfApproval as refusal:
        ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL.inc()
        raise four_eyes_refused(refusal.code) from None
    except FourEyesRefused as refusal:
        raise four_eyes_refused(refusal.code) from None
    audit = get_state(request).audit
    await audit.record(
        actor=caller.principal.subject,
        action=SIGNED_ACTION,
        resource_ref=signed_resource_ref(section, digest),
        consent_scope=ADMIN_BASIS_REF,
    )
    await wiring.review_ledger.refresh(audit)
    return {
        "state": "signed",
        "action_id": pending.id,
        "section": section,
        "review_digest": digest,
        "signed_by": pending.actor.subject,
        "countersigned_by": caller.principal.subject,
        "last_signed_at": _iso(wiring.review_ledger.last_signed(section)),
    }


# --- offboarding ----------------------------------------------------------------------


async def offboard_run(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    payload = await _body(request, frozenset({"subject", "reason_class"}))
    subject = payload["subject"]
    if not is_subject(subject):
        raise access_request_invalid("subject_malformed")
    try:
        reason = OffboardingReason(payload["reason_class"])
    except ValueError:
        raise access_request_invalid("reason_class_unknown") from None
    if reason not in _CONSOLE_REASONS:
        raise access_request_invalid("reason_class_unknown")
    identity = _identity(wiring)
    try:
        user = await run_in_threadpool(identity.directory.user, subject)
    except DirectoryUnavailable as err:
        raise directory_unavailable(err.code) from None
    if user is None:
        raise not_found()
    result = await offboard(
        subject=subject,
        reason=reason,
        actor=caller.principal.subject,
        directory=identity.directory,
        leases=identity.leases,
        systems=identity.systems,
        adapters=identity.adapters,
        sink=get_state(request).audit,
        trigger="console",
    )
    expired = wiring.four_eyes.expire_requested_by(subject)
    if expired:
        ADMIN_PENDING_ACTION_EXPIRED_TOTAL.inc(expired)
    return _offboarding_view(replace(result, expired_pending_actions=expired))


async def offboard_confirm(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    payload = await _body(request, frozenset({"system"}))
    system = payload["system"]
    if not _SYSTEM_ID.fullmatch(system):
        raise access_request_invalid("system_malformed")
    offboarding_id = request.path_params["offboarding_id"]
    if not _OFFBOARDING_ID.fullmatch(offboarding_id):
        raise not_found()
    audit = get_state(request).audit
    systems = wiring.identity.systems if wiring.identity is not None else ()
    found = offboardings_from(await audit.entries(), systems).get(offboarding_id)
    if found is None:
        raise not_found()
    try:
        confirmed = await confirm_manual(
            found, system=system, actor=caller.principal.subject, sink=audit
        )
    except OffboardingRefused as refusal:
        raise access_refused(refusal.code) from None
    return _offboarding_view(confirmed)
