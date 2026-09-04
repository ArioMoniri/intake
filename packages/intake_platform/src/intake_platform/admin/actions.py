"""The ``DangerousAction`` registry (INT-180; files/08 §8.2).

Three tiers, asymmetric by construction: **the safe direction takes one key,
the dangerous direction takes two.** The asymmetry is enforced in
:meth:`DangerousAction.__post_init__` rather than described — a tier-1 entry
that moves the system toward the more capable state cannot be constructed, so
files/08 §9's "any T1 entry that moves the system toward the more capable
state" gate has nothing to catch at review time.

**What is registered and what is not.** This registry holds the actions this
issue actually routes. files/08 §8.2's full table names eighteen more —
`device_functions` on, the study assertion, pack promotion, the egress
allow-list, connector endpoints, key rotation and the rest — every one of
which belongs to a surface INT-180 does not build. Transcribing them here
would produce registry rows with no code behind them, no runbook and no
alert: a control that exists only as a row is not a control (invariant 17).
The mechanism ships whole; the table grows with the surfaces.

The completeness direction that *is* enforced today is the one that matters:
``tests/admin/test_admin_audit.py`` derives every reachable ``/admin`` route
from FastAPI's own table and fails when a mutating route resolves to no entry
here. A route cannot be added without registering the action it performs.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from intake_platform.admin.roles import TIER3_APPROVER_ROLES, AdminRole

__all__ = [
    "BREAK_GLASS_OPEN",
    "DANGEROUS_ACTIONS",
    "MODEL_BENCHMARK_RUN",
    "SAFETY_FLAG_ENABLE",
    "ActionDirection",
    "ActionTier",
    "DangerousAction",
    "dangerous_action",
]


class ActionTier(enum.IntEnum):
    """files/08 §8.2. Ordered so ``tier >= ActionTier.T2`` reads as "needs a
    second key"."""

    T1 = 1
    T2 = 2
    T3 = 3


class ActionDirection(enum.StrEnum):
    """Which way the action moves the system.

    ``SAFE`` is the direction that reduces capability — the kill switch, a
    pack quarantine, `device_functions` **off**. ``DANGEROUS`` is the
    direction that adds it. Only ``SAFE`` may be tier 1.
    """

    SAFE = "safe"
    DANGEROUS = "dangerous"


@dataclass(frozen=True)
class DangerousAction:
    id: str
    tier: ActionTier
    direction: ActionDirection
    #: Roles that may REQUEST the action.
    actor_roles: frozenset[AdminRole]
    #: Roles that may stand as the second key. Empty exactly at tier 1.
    approver_roles: frozenset[AdminRole]
    #: Tier 3 demands two organisations; tier 2 demands two authenticators.
    approver_must_differ_org: bool
    #: Repository-relative runbook the alert links to (files/08 §5).
    runbook: str
    #: The catalogued metric id that pages on this action.
    alert_metric: str

    def __post_init__(self) -> None:
        if self.tier is ActionTier.T1:
            if self.direction is not ActionDirection.SAFE:
                raise ValueError(
                    f"{self.id}: a tier-1 action takes one key, so it may only move the "
                    "system toward the LESS capable state (files/08 §8.2, invariants 31-33)"
                )
            if self.approver_roles:
                raise ValueError(f"{self.id}: tier 1 is single-actor and takes no approver")
            if self.approver_must_differ_org:
                raise ValueError(f"{self.id}: tier 1 has no approver to place in an organisation")
        else:
            if not self.approver_roles:
                raise ValueError(f"{self.id}: tier {self.tier} needs a second key")
            if self.direction is not ActionDirection.DANGEROUS:
                raise ValueError(
                    f"{self.id}: a two-key ceremony guards the dangerous direction; a safe "
                    "action behind two keys is a safe action nobody can take in an incident"
                )
        if self.tier is ActionTier.T3:
            if not self.approver_must_differ_org:
                raise ValueError(f"{self.id}: tier 3 requires two organisations (files/08 §8.2)")
            if not self.approver_roles & TIER3_APPROVER_ROLES:
                raise ValueError(
                    f"{self.id}: tier 3 needs at least one approver from "
                    "{clinical_lead, qms_owner, compliance_officer}"
                )
        if not self.runbook.startswith("docs/runbooks/"):
            raise ValueError(f"{self.id}: an alert without a runbook is a page nobody can answer")
        if not self.alert_metric:
            raise ValueError(f"{self.id}: a registered action with no alert is not detected")


#: files/08 §2.5. The ceremony is "a distinct human approver, different
#: WebAuthn authenticator, own session" — which is exactly tier 2, NOT tier 3:
#: §8.2's tier-3 list does not contain break-glass, and requiring two
#: organisations would make an all-INTAKE ceremony impossible. What that costs
#: is stated plainly in tests/admin/test_four_eyes.py.
BREAK_GLASS_OPEN = DangerousAction(
    id="admin.break_glass.open",
    tier=ActionTier.T2,
    direction=ActionDirection.DANGEROUS,
    actor_roles=frozenset(
        {AdminRole.PLATFORM_OWNER, AdminRole.CLINICAL_LEAD, AdminRole.COMPLIANCE_OFFICER}
    ),
    approver_roles=frozenset(
        {AdminRole.CLINICAL_LEAD, AdminRole.COMPLIANCE_OFFICER, AdminRole.QMS_OWNER}
    ),
    approver_must_differ_org=False,
    runbook="docs/runbooks/break-glass.md",
    alert_metric="admin.break_glass_opened_total",
)

#: files/08 §148 "run benchmark", §8 `POST /admin/models/{id}/benchmark`
#: (INT-183). Tier 2 and DANGEROUS because *executing* a benchmark spends
#: capacity on a host that serves the PHI path, and a model host degraded
#: mid-session is a patient waiting on a turn. It is not tier 1: nothing about
#: running a benchmark moves the system toward the LESS capable state, and a
#: tier chosen to fit the surface rather than the risk is the failure mode
#: §8.2's asymmetry exists to prevent.
#:
#: What the route registered against it does TODAY is resolve and return the
#: plan — which component, which probe, which budget, and the named basis any
#: resulting measurement would carry. Planning reads; it changes nothing and
#: spends nothing. The two keys guard EXECUTION, and no benchmark runner
#: exists yet for them to guard: the approve half lands with the runner rather
#: than as a ceremony over a no-op (the same reason the eighteen unbuilt
#: §8.2 rows above are absent).
MODEL_BENCHMARK_RUN = DangerousAction(
    id="admin.models.benchmark.run",
    tier=ActionTier.T2,
    direction=ActionDirection.DANGEROUS,
    actor_roles=frozenset(
        {AdminRole.PLATFORM_OWNER, AdminRole.PLATFORM_ADMIN, AdminRole.SRE_ONCALL}
    ),
    approver_roles=frozenset(
        {AdminRole.PLATFORM_OWNER, AdminRole.QMS_OWNER, AdminRole.COMPLIANCE_OFFICER}
    ),
    approver_must_differ_org=False,
    runbook="docs/runbooks/model-benchmark.md",
    alert_metric="admin.model_benchmark_requested_total",
)

#: files/08 §0b F1/F2, §3, §8.2 and invariant 34 (INT-188). Enabling a
#: safety-list capability — `device_functions`, `s2s`, `learning_apply`,
#: `satisfaction_prompts`, `guardian_link`, `commercial_messaging` — is the
#: DANGEROUS direction and takes two keys. Tier 3 mirrors the device-mode
#: ceremony (F2): a second human from {clinical_lead, qms_owner,
#: compliance_officer}, on a distinct authenticator and session, from a
#: DIFFERENT organisation. The code behind it is
#: :class:`intake_platform.admin.flag_governance.FlagGovernor`, which opens the
#: ceremony and applies the flip only after a distinct principal approves — the
#: same relationship MODEL_BENCHMARK_RUN has with its runner.
#:
#: The SAFE direction (turning a safety flag OFF) is deliberately NOT a
#: DangerousAction: it takes one key (`SAFETY_FLAG_DISABLE_ROLES` in
#: :mod:`~intake_platform.admin.flag_governance`), because a two-key ceremony on
#: the safe direction is an availability control on a safety control — the
#: exact failure §0c F17 exists to prevent, and the asymmetry the tier-1
#: constructor enforces (a tier-1 action may only move toward the LESS capable
#: state).
SAFETY_FLAG_ENABLE = DangerousAction(
    id="admin.flags.safety.enable",
    tier=ActionTier.T3,
    direction=ActionDirection.DANGEROUS,
    actor_roles=frozenset({AdminRole.PLATFORM_OWNER, AdminRole.CLINICAL_LEAD}),
    approver_roles=frozenset(
        {AdminRole.CLINICAL_LEAD, AdminRole.QMS_OWNER, AdminRole.COMPLIANCE_OFFICER}
    ),
    approver_must_differ_org=True,
    runbook="docs/runbooks/flag-governance.md",
    alert_metric="admin.four_eyes_self_approval_attempt_total",
)

DANGEROUS_ACTIONS: dict[str, DangerousAction] = {
    BREAK_GLASS_OPEN.id: BREAK_GLASS_OPEN,
    MODEL_BENCHMARK_RUN.id: MODEL_BENCHMARK_RUN,
    SAFETY_FLAG_ENABLE.id: SAFETY_FLAG_ENABLE,
}


def dangerous_action(action_id: str) -> DangerousAction:
    """Resolve a registered action. A mutating route whose action is not
    registered cannot execute, because it cannot be logged (files/08 §8.1)."""
    try:
        return DANGEROUS_ACTIONS[action_id]
    except KeyError:  # pragma: no cover - the route table is held against this
        raise KeyError(f"{action_id} is not a registered DangerousAction") from None
