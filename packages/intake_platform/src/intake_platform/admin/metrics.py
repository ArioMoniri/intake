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

from prometheus_client import Counter

__all__ = [
    "ADMIN_BREAK_GLASS_OPENED_TOTAL",
    "ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL",
    "ADMIN_MODEL_BENCHMARK_REQUESTED_TOTAL",
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
