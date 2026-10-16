"""The admin route descriptor table and the console's wiring (INT-180).

**Why the routes are declared as data.** files/08 §8 rule (b) says there is no
such thing as an unregistered admin write, and invariant 4 says every action
is audited. Both properties are structural here rather than reviewed: the
FastAPI router in :mod:`intake_api.admin` is BUILT from this tuple, so a route
cannot come into existence without an audit action attached to it, and
``tests/admin/test_admin_audit.py`` reads the served route table off FastAPI
itself and fails when the two sets differ. The audited-route list is therefore
derived from what is reachable, never maintained alongside it.

``AdminWiring`` is the console's injectable dependency block. Two of its
fields ship deliberately barren:

- ``ip_allowlist`` — empty, so the console admits nobody until a deployment
  names its ranges (files/08 §2.3 names none);
- ``deployments`` — empty, so break-glass refuses for every tenant until the
  controller/processor question is answered per tenant (files/08 §2.6).

Neither is a gap to be filled with a plausible value; both are the fail-closed
state the design asks for. INT-366 adds a third: ``identity`` (Keycloak and
OpenBao admin access) ships unset, so the access review and offboarding answer
503 until a deployment wires them — while the review ledger, which reads only
the audit chain, is always there and downgrades until a review is countersigned.
INT-406 adds a fourth: ``safety_inbox`` ships unset, so the Safety queue answers
503 — never an empty queue that reads as "nobody is waiting" — and the API
reports the inbox unreadable, which pages, until a deployment wires the store.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from intake_platform.admin.access import IdentityWiring
from intake_platform.admin.access.review import ReviewLedger
from intake_platform.admin.actions import (
    ACCESS_REVIEW_SIGN,
    BREAK_GLASS_OPEN,
    DEPLOY_FREEZE_ENGAGE,
    DEPLOY_FREEZE_LIFT,
    MODEL_BENCHMARK_RUN,
    MODEL_LANES_HOSTED_DISABLE,
    MODEL_LANES_HOSTED_RELEASE,
    MODEL_LANES_KEY_SET,
    MODEL_LANES_ROUTE_SWITCH,
    MODEL_LANES_SELF_HOSTED_ENGAGE,
    OFFBOARD,
    SAFETY_QUEUE_ACKNOWLEDGE,
    VOICE_CANARY_SET,
    VOICE_KILL_SWITCH_ENGAGE,
    VOICE_KILL_SWITCH_RELEASE,
    VOICE_PROFILE_SWITCH,
)
from intake_platform.admin.break_glass import Deployment
from intake_platform.admin.four_eyes import FourEyesService
from intake_platform.admin.ip_allowlist import IpAllowList
from intake_platform.admin.principal import AdminClaimsVerifier
from intake_platform.admin.roles import ADMIN_ROLES, ROLE_SPECS, AdminRole, RoleScope
from intake_platform.model_lanes.wiring import ModelLanesWiring
from intake_platform.release_freeze import ReleaseFreezeStore
from intake_platform.safety_inbox import SafetyInbox
from intake_platform.voice_control import VoiceControlStore

__all__ = ["ADMIN_ROUTES", "AdminRoute", "AdminWiring"]

_ANY_CONSOLE_ROLE = frozenset(ADMIN_ROLES)

#: The self-hosting registry is a statement about the PLATFORM — which hosts,
#: which licences, which fallbacks, which release gate. A role scoped to one
#: tenant, one study or one patient grant has no reach over any of that, so
#: the read is the set of roles whose scope is the platform or all tenants.
#: Derived from ``ROLE_SPECS`` rather than listed, so a role added to files/08
#: §2.1 lands on the correct side of this line by construction instead of by
#: somebody remembering to edit a second list (INT-183).
_PLATFORM_SCOPE_ROLES = frozenset(
    role
    for role, spec in ROLE_SPECS.items()
    if spec.scope in {RoleScope.ALL_TENANTS, RoleScope.PLATFORM_INFRASTRUCTURE}
)

#: The brief is what the second pair of eyes reads before deciding, so it is
#: readable by the roles that may open a ceremony, the roles that may approve
#: one, and `auditor` — read-only evidence export, every read audited (§2.1).
_BRIEF_READERS = (
    BREAK_GLASS_OPEN.actor_roles | BREAK_GLASS_OPEN.approver_roles | {AdminRole.AUDITOR}
)

#: The Compliance module (INT-189, files/08 §4). files/08 §2.1 gives
#: `compliance_officer` "consent, DSAR, transfer register" and `auditor`
#: "read-only evidence export"; `platform_owner` sees all tenants. No other
#: role reaches these reads — an `sre_oncall` or `tenant_admin` asking for the
#: DSAR queue is refused, and the refusal is audited like any other action.
_COMPLIANCE_READERS = frozenset(
    {AdminRole.COMPLIANCE_OFFICER, AdminRole.AUDITOR, AdminRole.PLATFORM_OWNER}
)

#: INT-182. A voice ceremony's brief is read by whoever may take a voice
#: action or stand as its second key, and by `auditor` — the same shape as the
#: break-glass brief readers above.
_VOICE_BRIEF_READERS = (
    VOICE_KILL_SWITCH_ENGAGE.actor_roles
    | VOICE_PROFILE_SWITCH.actor_roles
    | VOICE_PROFILE_SWITCH.approver_roles
    | {AdminRole.AUDITOR}
)

#: INT-187. A lift request's brief is read by whoever may freeze, request a
#: lift or approve one, and by `auditor` — the voice module's shape.
_FREEZE_BRIEF_READERS = (
    DEPLOY_FREEZE_ENGAGE.actor_roles
    | DEPLOY_FREEZE_LIFT.actor_roles
    | DEPLOY_FREEZE_LIFT.approver_roles
    | {AdminRole.AUDITOR}
)

#: INT-428. A model-lane ceremony's brief is read by whoever may take a lane
#: action or stand as its second key, and by `auditor` — the voice shape.
_LANES_BRIEF_READERS = (
    MODEL_LANES_HOSTED_DISABLE.actor_roles
    | MODEL_LANES_ROUTE_SWITCH.actor_roles
    | MODEL_LANES_ROUTE_SWITCH.approver_roles
    | {AdminRole.AUDITOR}
)

#: INT-366 — the quarterly access review (files/08 §2.7). Read by those who
#: sign or countersign it, by `auditor` (read-only evidence, §2.1) and by
#: `platform_owner`. A `tenant_clinical_responsible` reads it too, scoped to
#: their own tenant's clinician section and nothing else.
_ACCESS_REVIEW_READERS = frozenset(
    ACCESS_REVIEW_SIGN.actor_roles
    | ACCESS_REVIEW_SIGN.approver_roles
    | {AdminRole.AUDITOR, AdminRole.PLATFORM_OWNER}
)

#: INT-406 — the Safety queue (files/08 §3). The tenant's clinical responsible
#: answers it; `clinical_lead` (all tenants, clinical) and `platform_owner` read
#: it; `auditor` reads it as evidence (§2.1). Ids and clocks only — no patient
#: words — so no role reaches content through it. `sre_oncall` is paged by the
#: tenant id on the alert and has no reason to hold the entries.
_SAFETY_QUEUE_READERS = frozenset(
    SAFETY_QUEUE_ACKNOWLEDGE.actor_roles
    | {AdminRole.CLINICAL_LEAD, AdminRole.PLATFORM_OWNER, AdminRole.AUDITOR}
)


@dataclass(frozen=True)
class AdminRoute:
    method: str
    path: str
    #: The dotted name the chain records. The write-ahead pair appends
    #: ``<audit_action>.intent`` and then ``<audit_action>.success|failure``.
    audit_action: str
    permitted_roles: frozenset[AdminRole]
    #: Set for every mutating route (files/08 §8 rule b).
    dangerous_action_id: str | None = None


ADMIN_ROUTES: tuple[AdminRoute, ...] = (
    AdminRoute("GET", "/admin/whoami", "admin.whoami.read", _ANY_CONSOLE_ROLE),
    AdminRoute("GET", "/admin/access/roles", "admin.access.roles.read", _ANY_CONSOLE_ROLE),
    AdminRoute("GET", "/admin/actions", "admin.actions.read", _ANY_CONSOLE_ROLE),
    # INT-183 — files/08 §8: `GET /admin/models` and
    # `POST /admin/models/{id}/benchmark`. The read is open to every console
    # role because the self-hosting posture is what §0 says the console exists
    # to show and it carries no patient content; the trigger is narrowed to
    # the roles that answer for capacity, and registered as the tier-2 action
    # its execution will require.
    AdminRoute("GET", "/admin/models", "admin.models.read", _PLATFORM_SCOPE_ROLES),
    # INT-351 — the ops console composite (files/08 §3 Ops): API health, model
    # hosts and GPU, model usage, clip cache, wait time, satisfaction, CI/CD.
    # A statement about the PLATFORM, aggregates and ids only, read only — so
    # the same platform-scope set as the registry read, and no DangerousAction.
    AdminRoute("GET", "/admin/ops", "admin.ops.read", _PLATFORM_SCOPE_ROLES),
    # INT-181 — the reliability composite (files/08 §3 Overview, Reliability):
    # SLO tiles and burn rates, the synthetic probe matrix, dependency health.
    # The same kind of read as /admin/ops — platform facts, ids only — so the
    # same platform-scope set and no DangerousAction.
    AdminRoute("GET", "/admin/reliability", "admin.reliability.read", _PLATFORM_SCOPE_ROLES),
    # INT-481 — the alerts feed (files/08 §3): what Alertmanager holds, read
    # server-side (files/08 §0b F1), ids only. A platform fact like /admin/ops,
    # so the same platform-scope set and no DangerousAction.
    AdminRoute("GET", "/admin/alerts", "admin.alerts.read", _PLATFORM_SCOPE_ROLES),
    AdminRoute(
        "POST",
        "/admin/models/{component}/benchmark",
        "admin.models.benchmark",
        MODEL_BENCHMARK_RUN.actor_roles,
        MODEL_BENCHMARK_RUN.id,
    ),
    AdminRoute(
        "POST",
        "/admin/break-glass",
        "admin.break_glass.open",
        BREAK_GLASS_OPEN.actor_roles,
        BREAK_GLASS_OPEN.id,
    ),
    AdminRoute(
        "GET",
        "/admin/break-glass/{action_id}",
        "admin.break_glass.brief.read",
        frozenset(_BRIEF_READERS),
    ),
    AdminRoute(
        "POST",
        "/admin/break-glass/{action_id}/approve",
        "admin.break_glass.approve",
        BREAK_GLASS_OPEN.approver_roles,
        BREAK_GLASS_OPEN.id,
    ),
    # INT-189 — the Compliance module (files/08 §4). All reads: the register is
    # a projection of the egress feed, the searches and queues are ids/counts
    # only (invariant 6), and the evidence export is text-typed (invariant 47).
    # No mutation, so no `DangerousAction` — the module records notifications
    # and runs DSAR export/delete through the tier-2 surfaces those already own.
    AdminRoute(
        "GET",
        "/admin/compliance/vendor-register",
        "admin.compliance.vendor_register.read",
        _COMPLIANCE_READERS,
    ),
    AdminRoute(
        "GET",
        "/admin/compliance/consents",
        "admin.compliance.consents.read",
        _COMPLIANCE_READERS,
    ),
    AdminRoute(
        "GET",
        "/admin/compliance/audit-search",
        "admin.compliance.audit_search.read",
        _COMPLIANCE_READERS,
    ),
    AdminRoute(
        "GET",
        "/admin/compliance/dsar",
        "admin.compliance.dsar.read",
        _COMPLIANCE_READERS,
    ),
    AdminRoute(
        "GET",
        "/admin/compliance/evidence-export",
        "admin.compliance.evidence.export",
        _COMPLIANCE_READERS,
    ),
    # INT-182 — the Voice module (files/08 §3 "Voice runtime", §8). The read is
    # platform facts plus every tenant's voice control, ids only — the same
    # platform-scope set as /admin/ops. The kill switch is tier 1 (one key,
    # toward typed); release, default-profile switch and canary weight are
    # tier-2 ceremonies (two keys, toward voice), each approved on its own
    # route so the audit row names exactly the action it approved.
    AdminRoute("GET", "/admin/voice", "admin.voice.read", _PLATFORM_SCOPE_ROLES),
    AdminRoute(
        "POST",
        "/admin/voice/kill-switch",
        "admin.voice.kill_switch.engage",
        VOICE_KILL_SWITCH_ENGAGE.actor_roles,
        VOICE_KILL_SWITCH_ENGAGE.id,
    ),
    AdminRoute(
        "POST",
        "/admin/voice/kill-switch/release",
        "admin.voice.kill_switch.release",
        VOICE_KILL_SWITCH_RELEASE.actor_roles,
        VOICE_KILL_SWITCH_RELEASE.id,
    ),
    AdminRoute(
        "POST",
        "/admin/voice/kill-switch/release/{action_id}/approve",
        "admin.voice.kill_switch.release.approve",
        VOICE_KILL_SWITCH_RELEASE.approver_roles,
        VOICE_KILL_SWITCH_RELEASE.id,
    ),
    AdminRoute(
        "PUT",
        "/admin/voice/profile/{tenant}",
        "admin.voice.profile.switch",
        VOICE_PROFILE_SWITCH.actor_roles,
        VOICE_PROFILE_SWITCH.id,
    ),
    AdminRoute(
        "POST",
        "/admin/voice/profile/pending/{action_id}/approve",
        "admin.voice.profile.switch.approve",
        VOICE_PROFILE_SWITCH.approver_roles,
        VOICE_PROFILE_SWITCH.id,
    ),
    AdminRoute(
        "PUT",
        "/admin/voice/canary/{tenant}",
        "admin.voice.canary.set",
        VOICE_CANARY_SET.actor_roles,
        VOICE_CANARY_SET.id,
    ),
    AdminRoute(
        "POST",
        "/admin/voice/canary/pending/{action_id}/approve",
        "admin.voice.canary.set.approve",
        VOICE_CANARY_SET.approver_roles,
        VOICE_CANARY_SET.id,
    ),
    AdminRoute(
        "GET",
        "/admin/voice/pending/{action_id}",
        "admin.voice.pending.brief.read",
        frozenset(_VOICE_BRIEF_READERS),
    ),
    # INT-187 — the CI/CD & releases module (files/08 §3, §8, §8.2). The read
    # is platform facts, ids only — the same platform-scope set as /admin/ops.
    # Freezing deploys is tier 1 (one key, the safe direction); lifting a
    # freeze is a tier-2 ceremony, approved on its own route so the audit row
    # names exactly the action it approved.
    AdminRoute("GET", "/admin/cicd", "admin.cicd.read", _PLATFORM_SCOPE_ROLES),
    AdminRoute(
        "POST",
        "/admin/cicd/freeze",
        "admin.cicd.freeze.engage",
        DEPLOY_FREEZE_ENGAGE.actor_roles,
        DEPLOY_FREEZE_ENGAGE.id,
    ),
    AdminRoute(
        "POST",
        "/admin/cicd/freeze/lift",
        "admin.cicd.freeze.lift",
        DEPLOY_FREEZE_LIFT.actor_roles,
        DEPLOY_FREEZE_LIFT.id,
    ),
    AdminRoute(
        "POST",
        "/admin/cicd/freeze/lift/{action_id}/approve",
        "admin.cicd.freeze.lift.approve",
        DEPLOY_FREEZE_LIFT.approver_roles,
        DEPLOY_FREEZE_LIFT.id,
    ),
    AdminRoute(
        "GET",
        "/admin/cicd/pending/{action_id}",
        "admin.cicd.pending.brief.read",
        frozenset(_FREEZE_BRIEF_READERS),
    ),
    # INT-428 — the Model lanes module (ADR-035). The read is platform facts,
    # ids only. Toward self-hosting is tier 1 (disable every hosted lane; the
    # one-click switch to GPU); toward a hosted provider is a tier-2 ceremony
    # (a route switch, a provider key, releasing the hosted kill switch), each
    # approved on its own route so the audit row names what it approved.
    AdminRoute("GET", "/admin/model-lanes", "admin.model_lanes.read", _PLATFORM_SCOPE_ROLES),
    AdminRoute(
        "POST",
        "/admin/model-lanes/hosted/disable",
        "admin.model_lanes.hosted.disable",
        MODEL_LANES_HOSTED_DISABLE.actor_roles,
        MODEL_LANES_HOSTED_DISABLE.id,
    ),
    AdminRoute(
        "POST",
        "/admin/model-lanes/self-hosted",
        "admin.model_lanes.self_hosted.engage",
        MODEL_LANES_SELF_HOSTED_ENGAGE.actor_roles,
        MODEL_LANES_SELF_HOSTED_ENGAGE.id,
    ),
    AdminRoute(
        "POST",
        "/admin/model-lanes/hosted/release",
        "admin.model_lanes.hosted.release",
        MODEL_LANES_HOSTED_RELEASE.actor_roles,
        MODEL_LANES_HOSTED_RELEASE.id,
    ),
    AdminRoute(
        "POST",
        "/admin/model-lanes/hosted/release/{action_id}/approve",
        "admin.model_lanes.hosted.release.approve",
        MODEL_LANES_HOSTED_RELEASE.approver_roles,
        MODEL_LANES_HOSTED_RELEASE.id,
    ),
    AdminRoute(
        "PUT",
        "/admin/model-lanes/route/{role}",
        "admin.model_lanes.route.switch",
        MODEL_LANES_ROUTE_SWITCH.actor_roles,
        MODEL_LANES_ROUTE_SWITCH.id,
    ),
    AdminRoute(
        "POST",
        "/admin/model-lanes/route/pending/{action_id}/approve",
        "admin.model_lanes.route.switch.approve",
        MODEL_LANES_ROUTE_SWITCH.approver_roles,
        MODEL_LANES_ROUTE_SWITCH.id,
    ),
    AdminRoute(
        "PUT",
        "/admin/model-lanes/keys/{provider}",
        "admin.model_lanes.key.set",
        MODEL_LANES_KEY_SET.actor_roles,
        MODEL_LANES_KEY_SET.id,
    ),
    AdminRoute(
        "POST",
        "/admin/model-lanes/keys/pending/{action_id}/approve",
        "admin.model_lanes.key.set.approve",
        MODEL_LANES_KEY_SET.approver_roles,
        MODEL_LANES_KEY_SET.id,
    ),
    AdminRoute(
        "GET",
        "/admin/model-lanes/pending/{action_id}",
        "admin.model_lanes.pending.brief.read",
        frozenset(_LANES_BRIEF_READERS),
    ),
    # INT-366 — Access & identity (files/08 §2.4, §2.7, §3). `GET
    # /admin/access/review` is §8's route; the sign/countersign pair is the
    # tier-2 ceremony that lifts the read-only downgrade; offboarding and the
    # confirmation of its manual steps are one tier-1 action.
    AdminRoute("GET", "/admin/access/review", "admin.access.review.read", _ACCESS_REVIEW_READERS),
    AdminRoute(
        "POST",
        "/admin/access/review/sign",
        "admin.access.review.sign",
        ACCESS_REVIEW_SIGN.actor_roles,
        ACCESS_REVIEW_SIGN.id,
    ),
    AdminRoute(
        "POST",
        "/admin/access/review/sign/{action_id}/countersign",
        "admin.access.review.countersign",
        ACCESS_REVIEW_SIGN.approver_roles,
        ACCESS_REVIEW_SIGN.id,
    ),
    AdminRoute(
        "POST", "/admin/access/offboard", "admin.access.offboard", OFFBOARD.actor_roles, OFFBOARD.id
    ),
    AdminRoute(
        "POST",
        "/admin/access/offboard/{offboarding_id}/confirm",
        "admin.access.offboard.confirm",
        OFFBOARD.actor_roles,
        OFFBOARD.id,
    ),
    # INT-406 — the Safety queue (files/08 §3, §0c F19; invariant 49). The read
    # is tenant-scoped from the claim; the acknowledgement is tier 1, one key,
    # the tenant's clinical responsible's alone.
    AdminRoute("GET", "/admin/safety-queue", "admin.safety_queue.read", _SAFETY_QUEUE_READERS),
    AdminRoute(
        "POST",
        "/admin/safety-queue/{entry_id}/acknowledge",
        "admin.safety_queue.acknowledge",
        SAFETY_QUEUE_ACKNOWLEDGE.actor_roles,
        SAFETY_QUEUE_ACKNOWLEDGE.id,
    ),
)


@dataclass
class AdminWiring:
    claims: AdminClaimsVerifier
    ip_allowlist: IpAllowList = field(default_factory=lambda: IpAllowList(networks=()))
    four_eyes: FourEyesService = field(default_factory=FourEyesService)
    #: tenant id -> which side of the controller/processor line it sits on.
    #: Empty by default: no file in this repository records it, and a guessed
    #: entry would decide a lawful-basis question (files/08 §2.6, HB-L6).
    deployments: Mapping[str, Deployment] = field(default_factory=dict)
    #: INT-182: the per-tenant voice control store the runtime reads at every
    #: session start. ``None`` = unconfigured: the voice mutations answer 503
    #: and the Voice module's controls tile reads unknown (fail closed).
    voice_controls: VoiceControlStore | None = None
    #: INT-187: the deployment's deploy-freeze record, which the deploy path's
    #: release gate reads before it touches the host. ``None`` = unconfigured:
    #: the freeze controls answer 503, the freeze tile reads unknown, and the
    #: console's deploy gate shows what deploy.sh would do — refuse.
    release_freeze: ReleaseFreezeStore | None = None
    #: INT-366: when the console access review was last countersigned, read
    #: back from the audit chain. Always present — the §2.7 read-only
    #: downgrade needs only the chain, and an unread ledger downgrades.
    review_ledger: ReviewLedger = field(default_factory=ReviewLedger)
    #: INT-366: Keycloak, OpenBao and the other console systems. ``None``
    #: leaves the review and offboarding answering 503 (fail closed).
    identity: IdentityWiring | None = None
    #: INT-406: the clinic Safety inbox (``INTAKE_SAFETY_INBOX_REDIS_URL``, the
    #: store the voice runtime writes). ``None`` leaves the Safety queue
    #: answering 503 and the inbox reported unreadable, which pages.
    safety_inbox: SafetyInbox | None = None

    #: INT-428 (ADR-035): the model-lane control store, the router over it and
    #: the hosted adapters. ``None`` = unconfigured: the model-lane mutations
    #: answer 503 and the module's tiles read unknown (fail closed).
    model_lanes: ModelLanesWiring | None = None
