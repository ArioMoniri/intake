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
    "ADMIN_PENDING_ACTION_EXPIRED_TOTAL",
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
