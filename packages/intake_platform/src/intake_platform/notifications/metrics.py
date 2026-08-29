"""INT-141 — the two signals files/10 §9 asks the notifications row for:
delivery rates and opt-out rates.

Both label sets are closed enumerations (channel, message class, dispatch
status, preference change) — no free text, no identifier, nothing that could
carry PHI into a series (invariant 6, and the label denylist in
``intake_platform.slo`` enforces the same rule from the other side). Every
family here has an entry in ``observability/metrics_catalog.yaml``
(invariant 13).
"""

from __future__ import annotations

from typing import Final

from prometheus_client import Counter

__all__ = ["NOTIFICATION_DISPATCH_TOTAL", "NOTIFICATION_PREFERENCE_CHANGED_TOTAL"]

NOTIFICATION_DISPATCH_TOTAL: Final = Counter(
    "notification_dispatch_total",
    "Notification dispatch attempts by channel, message class and outcome.",
    ("channel", "message_class", "status"),
)

NOTIFICATION_PREFERENCE_CHANGED_TOTAL: Final = Counter(
    "notification_preference_changed_total",
    "Patient notification-preference changes, by what changed.",
    ("change",),
)
