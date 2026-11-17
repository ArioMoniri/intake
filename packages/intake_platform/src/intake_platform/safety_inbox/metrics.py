"""The signals invariant 49 pages on (INT-406; files/08 §4 E, §5; files/10 §9).

files/08 §4 E: *"``triage.events_total`` counts REDs that fired; these two
count REDs nobody answered, which is the number that decides an outcome."*
The first two families are those two; the other two are the ones this issue
adds so the 60 s half of files/02 §8.2 is paged too, not only the SLA half — an
entry waiting too long for the store, and a RED whose route never made one. Those
four are catalogued in observability/metrics_catalog.yaml (invariant 13) and
alerted in infra/observability/safety-rules.yaml. INT-475 adds a fifth, catalogued
too: a notification the API raised whose audit row could not be appended.

Label discipline (invariant 6): ``tenant`` is a tenant id and ``age_band`` a
closed :class:`~intake_platform.safety_inbox.sla.AgeBand` member. No session,
visit, rule or person is ever a label — who answered is on the audit chain.
"""

from __future__ import annotations

from typing import Final

from prometheus_client import Counter, Gauge, Histogram

from intake_platform.safety_inbox.sla import DEFAULT_ACK_SLA, AgeBand

__all__ = [
    "CLINIC_RED_ACK_LATENCY_MIN",
    "CLINIC_RED_INBOX_PENDING_AGE_S",
    "CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL",
    "CLINIC_RED_NOTIFICATION_UNAUDITED_TOTAL",
    "CLINIC_RED_UNACKNOWLEDGED_TOTAL",
    "UNREADABLE_TENANT",
    "mark_inbox_unreadable",
]

_SLA_MIN: Final = DEFAULT_ACK_SLA.total_seconds() / 60.0

#: Minutes from the entry to its acknowledgement. The bucket edges are
#: measurement resolution, not targets; the default SLA is one of them so
#: "answered inside the default" is read off a bucket rather than estimated
#: between two.
CLINIC_RED_ACK_LATENCY_MIN = Histogram(
    "clinic_red_ack_latency_min",
    "Safety inbox entry to human acknowledgement, in minutes (files/02 §8.2).",
    buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, _SLA_MIN, 480.0, 1440.0, float("inf")),
)

#: Open entries by tenant and by where they stand against the tenant SLA.
#: Recomputed whole by every sweep, so an acknowledged entry leaves the series
#: rather than lingering at its last value.
CLINIC_RED_UNACKNOWLEDGED_TOTAL = Gauge(
    "clinic_red_unacknowledged_total",
    "Safety inbox entries nobody has acknowledged, by tenant and SLA age band.",
    ["tenant", "age_band"],
)

#: Seconds the oldest RED entry has waited in this process for the shared
#: inbox store; 0 when none waits. Above 60 the files/02 §8.2 inbox budget is
#: broken for that RED, and the alert says so.
CLINIC_RED_INBOX_PENDING_AGE_S = Gauge(
    "clinic_red_inbox_pending_age_s",
    "Age of the oldest RED entry not yet written to the shared Safety inbox, in seconds.",
)

#: A RED whose clinician route raised before any entry existed. The RED is
#: still delivered (the route never costs it that); but no entry means no
#: clock and no page from the inbox, so this counter is the page instead.
CLINIC_RED_INBOX_ROUTE_FAILURES_TOTAL = Counter(
    "clinic_red_inbox_route_failures_total",
    "REDs whose clinician route into the Safety inbox raised, so no entry was made.",
)

#: INT-475: an audit row (invariant 4) the API owed for a RED's clinic route —
#: a RED or on-site staff notification it put in the inbox, or a RED it could
#: not route — that could not be appended. The notification is never held back
#: for its paperwork (a RED answer does not wait on the audit chain), so the
#: missing row is counted here instead of passing silently.
CLINIC_RED_NOTIFICATION_UNAUDITED_TOTAL = Counter(
    "clinic_red_notification_unaudited_total",
    "Audit rows the API owed for a RED's clinic route (a RED or on-site staff "
    "notification raised, or a RED it could not route) that could not be written.",
)

#: The ``tenant`` value that means "the inbox could not be read". A sweep that
#: cannot see the inbox cannot say nobody is waiting, so it reports the
#: unreadable inbox as past the SLA, with the value +Inf, and the page fires.
UNREADABLE_TENANT: Final = "inbox_unreadable"


def mark_inbox_unreadable() -> None:
    """Fail closed: replace every series with the one that pages."""
    CLINIC_RED_UNACKNOWLEDGED_TOTAL.clear()
    CLINIC_RED_UNACKNOWLEDGED_TOTAL.labels(
        tenant=UNREADABLE_TENANT, age_band=AgeBand.PAST_SLA.value
    ).set(float("inf"))
