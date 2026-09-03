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
from intake_probes.console import BenchmarkKind, BenchmarkPlan, BenchmarkResult, ModelsModule

from intake_api.admin.models_source import PROBE_CLIENTS_ENV

__all__ = [
    "action_registry_view",
    "benchmark_plan_view",
    "benchmark_result_view",
    "brief_view",
    "models_module_view",
    "pending_view",
    "role_registry_view",
    "whoami",
]


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
            route.audit_action for route in ADMIN_ROUTES if principal.roles & route.permitted_roles
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


# --------------------------------------------------------------------------
# INT-183 — the models module
# --------------------------------------------------------------------------

#: Why every row advertises both lanes rather than only the one that works:
#: a control that is missing reads as "not applicable"; a control that is
#: present and disabled with its reason reads as "someone decided this, and
#: here is what they decided". files/HUMAN_BLOCKERS.md HB-C10 is the decision.
_QUALITY_LANE_DISABLED = (
    "no named evaluation corpus is declared — a quality figure would have no corpus and no "
    "date to attach to (CLAUDE.md invariant 20; HUMAN_BLOCKERS HB-C10 and HB-A13 are open)"
)


def models_module_view(module: ModelsModule) -> dict[str, Any]:
    """The `GET /admin/models` body.

    Every field is projected from ``observability/registry.yaml`` or from the
    INT-022 release gate's own verdict. Nothing here is a second opinion about
    either, and nothing here is patient-shaped: the rows are component ids,
    host strings, licence strings, probe ids and integers (invariant 6).
    """
    return {
        "release": {
            "blocked": module.release.blocked,
            "reasons": [
                {"component": reason.component, "reason": reason.reason}
                for reason in module.release.reasons
            ],
        },
        "rows": [
            {
                "component": row.component,
                "self_hostable": row.self_hostable,
                "self_hosted_now": row.self_hosted_now,
                "host": row.host,
                "license": row.license,
                "probe": row.probe,
                "budget_ms": row.budget_ms,
                "fallback": row.fallback,
                "phi_path": row.phi_path,
                "pin": row.pin,
                "licence_verified_at": (
                    row.licence_verified_at.isoformat()
                    if row.licence_verified_at is not None
                    else None
                ),
                "severity": row.severity.value,
                "findings": [
                    {"code": finding.code, "detail": finding.detail} for finding in row.findings
                ],
                "benchmark": {
                    "lanes": {
                        BenchmarkKind.LATENCY.value: {"enabled": True, "disabled_reason": None},
                        BenchmarkKind.QUALITY.value: {
                            "enabled": False,
                            "disabled_reason": _QUALITY_LANE_DISABLED,
                        },
                    }
                },
            }
            for row in module.rows
        ],
    }


def benchmark_plan_view(plan: BenchmarkPlan) -> dict[str, Any]:
    """The `POST /admin/models/{id}/benchmark` body.

    ``state`` is ``planned`` and ``executes`` is ``false`` because that is
    what happens: the route resolves what a run would measure and over what
    named basis, and runs nothing. Executing it is the tier-2 ceremony
    ``admin.models.benchmark.run`` registers, and the runner that ceremony
    would guard does not exist yet — so the plan is the honest end of this
    route rather than a button that pretends.
    """
    return {
        "component": plan.component,
        "kind": plan.kind.value,
        "probe": plan.probe,
        "budget_ms": plan.budget_ms,
        "corpus": plan.corpus,
        "state": "planned",
        "executes": False,
        "not_executed_reason": (
            "no probe client is wired in this environment "
            f"(set {PROBE_CLIENTS_ENV}=dev against a running dev stack)"
        ),
        "measurement": None,
    }


def benchmark_result_view(result: BenchmarkResult) -> dict[str, Any]:
    """The body when the latency lane actually ran.

    ``measurement`` is the rendered string and never a bare number: it carries
    the probe and host it was taken against and the date it was taken, because
    a latency figure with neither attached is a claim about the product rather
    than an observation of one deployment (invariant 20, ADR-022). When the
    probe could not run at all the field is ``null`` and ``detail`` says why —
    a benchmark that reached nothing reports that, never a zero.
    """
    body = benchmark_plan_view(result.plan)
    body["state"] = result.status.value
    body["executes"] = True
    body["not_executed_reason"] = None
    body["detail"] = result.detail
    body["measurement"] = result.measurement.render() if result.measurement is not None else None
    return body
