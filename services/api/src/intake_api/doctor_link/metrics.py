"""INT-150 — the Doctor Link signals files/10 §9 names for this row.

The §9 `doctor-link` row asks for four: *opens, failed OTPs, revocations,
time-to-open*. Three of them are counts of things this service does and are
emitted here as ONE family with a closed ``event`` label; the fourth
(time-to-open, ``wait.doctor_link_first_open_h``) is an interval whose
publisher does not exist and stays ``planned`` in the catalogue, which
``intake_platform.wait_times`` records rather than this module papering over.

Invariant 6 governs the label set: ``event`` is a closed enumeration of
outcomes, and there is no tenant, patient, link, clinic or recipient label —
a per-link counter would let a Prometheus scrape reconstruct one clinician's
reading behaviour from a metrics endpoint that is not consent-scoped.
"""

from __future__ import annotations

import enum

from prometheus_client import Counter

__all__ = ["DOCTOR_LINK_EVENTS", "DoctorLinkEvent", "record_event"]


class DoctorLinkEvent(enum.StrEnum):
    """Closed outcome vocabulary. A refusal reason is a system fact, not a
    patient fact, so it may be a label; a link id may not."""

    ISSUED = "issued"
    REVOKED = "revoked"
    OTP_REQUESTED = "otp_requested"
    OTP_FAILED = "otp_failed"
    OTP_LIMITED = "otp_limited"
    OPENED = "opened"
    REFUSED_EXPIRED = "refused_expired"
    REFUSED_REVOKED = "refused_revoked"
    REFUSED_VIEW_LIMIT = "refused_view_limit"
    REFUSED_UNKNOWN_TOKEN = "refused_unknown_token"  # noqa: S105 — an outcome label


DOCTOR_LINK_EVENTS = Counter(
    "doctor_link_events_total",
    "Doctor Link lifecycle outcomes (files/10 §9 doctor-link row: opens, "
    "failed OTPs, revocations). Closed event enumeration; no identifying label.",
    ["event"],
)


def record_event(event: DoctorLinkEvent) -> None:
    DOCTOR_LINK_EVENTS.labels(event=event.value).inc()
