"""Admin-control signals (INT-180; files/08 §4 groups M and O, §5).

Group O exists because ``sec.admin_actions_total`` and ``sec.break_glass_total``
were metrics with nothing attached to them — no alert, no detection. These five
are the ones INT-180's mechanism actually produces; the rest of group O lands
with the surfaces that perform those actions, and every id here is catalogued
in observability/metrics_catalog.yaml (invariant 13).

Label discipline (invariant 6): ``reason_class`` is a closed
:class:`~intake_platform.admin.break_glass.BreakGlassReason` member and
``actor`` is a staff account subject — an identifier, bounded by headcount,
never a patient and never free text. files/08 §4 states both labels by name.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

__all__ = [
    "ADMIN_ACCESS_REVIEW_AGE_DAYS",
    "ADMIN_BREAK_GLASS_OPENED_TOTAL",
    "ADMIN_DEPLOY_FREEZE_CHANGES_TOTAL",
    "ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL",
    "ADMIN_MODEL_BENCHMARK_REQUESTED_TOTAL",
    "ADMIN_OFFBOARDING_TOTAL",
    "ADMIN_PENDING_ACTION_EXPIRED_TOTAL",
    "ADMIN_VOICE_CONTROL_CHANGES_TOTAL",
    "SEC_ADMIN_ACTIONS_TOTAL",
    "SEC_BREAK_GLASS_TOTAL",
]

SEC_ADMIN_ACTIONS_TOTAL = Counter(
    "sec_admin_actions_total",
    "Admin actions executed, counted once per audited console action.",
)

SEC_BREAK_GLASS_TOTAL = Counter(
    "sec_break_glass_total",
    "Break-glass grants opened.",
)

ADMIN_BREAK_GLASS_OPENED_TOTAL = Counter(
    "admin_break_glass_opened_total",
    "Break-glass grants opened, by actor and reason class.",
    ["actor", "reason_class"],
)

#: files/08 §5: "that one is an intrusion signal, not a hygiene metric.
#: Nobody attempts to approve their own tier-3 action by accident twice."
ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL = Counter(
    "admin_four_eyes_self_approval_attempt_total",
    "Attempts to approve one's own pending action.",
)

ADMIN_PENDING_ACTION_EXPIRED_TOTAL = Counter(
    "admin_pending_action_expired_total",
    "Pending dangerous actions that expired unapproved.",
)

#: INT-183. The alert attached to `admin.models.benchmark.run` (files/08 §8.2
#: requires one: "a registered action with no alert is not detected"). Both
#: labels are closed: `actor` is a staff account subject, `kind` a
#: BenchmarkKind member, `outcome` a two-valued verdict — never a patient,
#: never free text, never a component's own name, which is unbounded by
#: nothing but the registry (invariant 6).
ADMIN_MODEL_BENCHMARK_REQUESTED_TOTAL = Counter(
    "admin_model_benchmark_requested_total",
    "Model benchmark triggers, by actor, lane and outcome.",
    ["actor", "kind", "outcome"],
)

#: INT-182. The alert attached to the four voice actions of the
#: ``DangerousAction`` registry. ``control`` is a closed
#: :class:`~intake_platform.voice_control.VoiceControlChange` member and
#: ``outcome`` one of requested / applied / unchanged / refused — no tenant, no
#: actor, no text: who did it is on the audit chain and in the store, and a
#: label is not the place for either (invariant 6).
ADMIN_VOICE_CONTROL_CHANGES_TOTAL = Counter(
    "admin_voice_control_changes_total",
    "Voice control changes (kill switch, default profile, canary), by control and outcome.",
    ["control", "outcome"],
)

#: INT-187. The alert attached to the two deploy-freeze actions of the
#: ``DangerousAction`` registry. ``control`` is a closed
#: :class:`~intake_platform.release_freeze.DeployFreezeChange` member and
#: ``outcome`` one of requested / applied / unchanged / refused — no actor and
#: no text: who did it is on the audit chain and in the store (invariant 6).
ADMIN_DEPLOY_FREEZE_CHANGES_TOTAL = Counter(
    "admin_deploy_freeze_changes_total",
    "Deploy freeze changes (engage, lift), by control and outcome.",
    ["control", "outcome"],
)

#: INT-366, files/08 §2.7 and §4 group O: the age of the console access review
#: (the staler of its `platform_owner` and `console_roles` sections), in days.
#: No labels. Computed at scrape time from the sign-off instants the review
#: ledger read off the audit chain, so it keeps counting while nobody opens the
#: console; +Inf when no review was ever countersigned, or the chain has not
#: been read yet. AccessReviewOverdue pages above 100.
ADMIN_ACCESS_REVIEW_AGE_DAYS = Gauge(
    "admin_access_review_age_days",
    "Age of the console access review in days (files/08 §2.7; read-only past 100).",
)
# Until a review ledger binds the gauge (the console wired), no review is
# known to exist: a process that never read the chain reports "never
# reviewed", not the zero a fresh gauge would otherwise report.
ADMIN_ACCESS_REVIEW_AGE_DAYS.set(float("inf"))

#: INT-366, files/08 §2.4: offboardings run, by what triggered them
#: (`console` — a person, `dormant` — the 60-day job) and whether every system
#: was revoked or confirmed when the run ended. Both labels are closed sets;
#: the offboarded subject is never a label (invariant 6).
ADMIN_OFFBOARDING_TOTAL = Counter(
    "admin_offboarding_total",
    "Offboardings run, by trigger and by whether every system was closed.",
    ["trigger", "complete"],
)
