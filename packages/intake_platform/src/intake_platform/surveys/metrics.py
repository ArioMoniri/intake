"""INT-242 — the one signal a survey scheduler owes.

Every label is a closed enumeration (survey kind, invitation channel, message
class, outcome): nothing free-text, no recipient, no tenant, no clinician
(invariant 6, and the ``PHI_RISK_LABEL_NAMES`` schema check from the other
side). The family has an entry in ``observability/metrics_catalog.yaml``
(invariant 13).

What it is for: the ``status`` label is the honest record of why nothing is
being sent. ``blocked_iys_consent_absent`` accumulating is the İYS gate doing
its job, and ``refused_schedule_unset`` accumulating is the missing
first-prompt value — both are asks with a counter behind them rather than
silence.
"""

from __future__ import annotations

from typing import Final

from prometheus_client import Counter

__all__ = ["SURVEY_INVITATION_TOTAL"]

SURVEY_INVITATION_TOTAL: Final = Counter(
    "survey_invitation_total",
    "Survey invitation decisions by kind, channel, message class and outcome.",
    ("kind", "channel", "message_class", "status"),
)
