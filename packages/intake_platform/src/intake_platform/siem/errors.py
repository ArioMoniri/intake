"""INT-205 — the three refusals this tier can make, as types."""

from __future__ import annotations

__all__ = ["AlertRefused", "RetentionNotConfiguredError", "SiemConfigError"]


class SiemConfigError(ValueError):
    """A committed SIEM configuration file does not hold. Never repaired."""


class AlertRefused(ValueError):
    """An alert could not be reduced to :class:`SecurityAlert` safely.

    Refusing is the correct outcome: an alert we cannot scrub is an alert we
    cannot show, and showing it anyway is the PHI leak invariant 6 forbids. The
    refusal is counted (``siem_alerts_refused_total``) so a rising rate is
    visible rather than silent.
    """


class RetentionNotConfiguredError(ValueError):
    """No retention window for the alert store, and none may be invented."""
