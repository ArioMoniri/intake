"""INT-582 — the passkey signals files/10 §9's onboarding row asks for.

One family, ``passkey_events_total{event, reason}``. ``event`` is a closed
enumeration of what the passkey tier did; ``reason`` is a closed enumeration
too — a :class:`~intake_api.passkey.webauthn.PasskeyReason`, a challenge or
grant outcome, or ``none``. There is no tenant, patient, credential or action
label (invariant 6): a per-patient counter would let a metrics scrape tell
when one patient stepped up, and the audit chain is where that is recorded.
"""

from __future__ import annotations

import enum

from prometheus_client import Counter

__all__ = ["PASSKEY_EVENTS", "PasskeyEvent", "record_event"]


class PasskeyEvent(enum.StrEnum):
    REGISTERED = "registered"
    REGISTRATION_REFUSED = "registration_refused"
    STEP_UP_PASSED = "step_up_passed"
    STEP_UP_REFUSED = "step_up_refused"
    GATE_PASSKEY = "gate_passkey"
    GATE_OTP_TIER = "gate_otp_tier"
    GATE_REFUSED = "gate_refused"
    REMOVED = "removed"
    RECOVERY_REQUESTED = "recovery_requested"
    RECOVERY_CANCELLED = "recovery_cancelled"
    RECOVERY_COMPLETED = "recovery_completed"


PASSKEY_EVENTS = Counter(
    "passkey_events_total",
    "Patient passkey outcomes (INT-582, D36): registrations, step-ups, the gate's "
    "decision on each sensitive action, removals and recoveries. Closed event and "
    "reason enumerations; no identifying label.",
    ["event", "reason"],
)


def record_event(event: PasskeyEvent, reason: str = "none") -> None:
    PASSKEY_EVENTS.labels(event=event.value, reason=reason).inc()
