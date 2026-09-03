"""Response bodies for the console (INT-180).

Every field here is an identifier, an enum member, a count or a timestamp.
Two things are deliberately absent:

- **Any chain material.** No entry hash, no head, no sequence number, no WORM
  bundle. The console sits inside the ``platform_admin`` blast radius that
  HUMAN_BLOCKERS **HB-I12** exists to publish the chain's head *outside* of,
  and a console that could read the head could check its own forgery.
- **Any patient content.** INT-180 ships the break-glass *ceremony*, not the
  redacted transcript view it eventually authorises (files/08 §2.5 item 5,
  sequenced to P1-P2 in §10). The only free text that crosses this boundary
  is the requester's own justification, rendered back to the approver because
  an approval screen that shows less than that is theatre.
"""

from __future__ import annotations

from typing import Any

from intake_platform.admin import (
    ADMIN_ROUTES,
    DANGEROUS_ACTIONS,
    ROLE_SPECS,
    AdminPrincipal,
    ApprovalBrief,
    PendingAction,
)

__all__ = ["action_registry_view", "brief_view", "pending_view", "role_registry_view", "whoami"]


def whoami(principal: AdminPrincipal, tenant: str | None) -> dict[str, Any]:
    """The caller's own identity and reach. ``capabilities`` is derived from
    the route table, so the console shows what the server will actually
    allow rather than a second copy of the rules."""
    return {
        "subject": principal.subject,
        "roles": sorted(role.value for role in principal.roles),
        "org": principal.org,
        "tenant": tenant,
        "capabilities": sorted(
            route.audit_action
            for route in ADMIN_ROUTES
            if principal.roles & route.permitted_roles
        ),
    }


def role_registry_view() -> dict[str, Any]:
    return {
        "roles": [
            {
                "role": role.value,
                "scope": spec.scope.value,
                "patient_content": spec.patient_content.value,
                "may_approve_tier3": spec.may_approve_tier3,
                "privileged": spec.privileged,
            }
            for role, spec in ROLE_SPECS.items()
        ]
    }


def action_registry_view() -> dict[str, Any]:
    return {
        "actions": [
            {
                "id": action.id,
                "tier": int(action.tier),
                "direction": action.direction.value,
                "actor_roles": sorted(role.value for role in action.actor_roles),
                "approver_roles": sorted(role.value for role in action.approver_roles),
                "approver_must_differ_org": action.approver_must_differ_org,
                "runbook": action.runbook,
                "alert_metric": action.alert_metric,
            }
            for action in DANGEROUS_ACTIONS.values()
        ]
    }


def pending_view(pending: PendingAction) -> dict[str, Any]:
    return {
        "action_id": pending.id,
        "dangerous_action_id": pending.action.id,
        "tier": int(pending.action.tier),
        "state": pending.state.value,
        "expires_at": pending.expires_at.isoformat(),
        "approver_role": pending.approver.role.value if pending.approver is not None else None,
    }


def brief_view(brief: ApprovalBrief) -> dict[str, Any]:
    """What the second pair of eyes reads. The requester's identity block,
    the tier, the target, the reason class, the full free text, the
    controller-instruction reference and the evidence — enough to disagree."""
    return {
        "action_id": brief.action_id,
        "dangerous_action_id": brief.dangerous_action_id,
        "tier": int(brief.tier),
        "state": brief.state.value,
        "requested_by": {
            "subject": brief.requested_by.subject,
            "role": brief.requested_by.role.value,
            "org": brief.requested_by.org,
            "authenticator_aaguid": brief.requested_by.authenticator_aaguid,
            "credential_id": brief.requested_by.credential_id,
            "session_id": brief.requested_by.session_id,
        },
        "target_ref": brief.target_ref,
        "reason_class": str(brief.reason_class),
        "justification": brief.free_text,
        "controller_instruction_ref": brief.controller_instruction_ref,
        "evidence": dict(brief.evidence),
        "created_at": brief.created_at.isoformat(),
        "expires_at": brief.expires_at.isoformat(),
        "approver_rule": brief.approver_rule,
    }
