"""INT-242 — NPS scheduling and clinician pulse survey cadence.

Acceptance: *"monthly NPS prompt honoring quiet hours; quarterly pulse;
opt-outs respected"*. legal: ``6563-IYS``; sec_row: ``experience``.

Read the module docstrings in this order — each states the argument its part
of the design rests on:

- ``cadence`` — the two figures that are stated, the one that is not, and why
  a period is a calendar span rather than a number of days.
- ``classification`` — **the determination**: a survey invitation carried as
  an electronic message is commercial under 6563, so it needs an İYS consent,
  so today it cannot be sent at all.
- ``planner`` — the order of refusal, and why sending is not this module's
  job.
- ``metrics`` — the single signal, and why its ``status`` label is the honest
  record of the two open asks.

**What this package does not contain**, deliberately: a sampling rate, a
cross-survey cool-off, a send hour, a day-of-period anchor, a survey
invitation template, a store of who was invited when. No file in the tree
states any of them, and 6563 keeps *sender records* whose shape depends on the
İYS integration nobody has specified — so an invitation history table would be
inventing that shape for rows that cannot lawfully exist yet. The asks and
their named humans are in docs/evidence/INT-242.md.
"""

from __future__ import annotations

from intake_platform.surveys.cadence import (
    CADENCE,
    MONTHS_PER_PERIOD,
    DueDecision,
    DueStatus,
    Period,
    SurveyKind,
    SurveyPolicy,
    SurveyRecipient,
    advance,
    due,
    next_due_at,
)
from intake_platform.surveys.classification import (
    SATISFACTION_PROMPTS_FLAG,
    SURVEY_MESSAGE_CLASS,
    InvitationChannel,
    requires_iys_consent,
)
from intake_platform.surveys.metrics import SURVEY_INVITATION_TOTAL
from intake_platform.surveys.planner import (
    InvitationOutcome,
    InvitationStatus,
    SurveyInvitationPlanner,
)

__all__ = [
    "CADENCE",
    "MONTHS_PER_PERIOD",
    "SATISFACTION_PROMPTS_FLAG",
    "SURVEY_INVITATION_TOTAL",
    "SURVEY_MESSAGE_CLASS",
    "DueDecision",
    "DueStatus",
    "InvitationChannel",
    "InvitationOutcome",
    "InvitationStatus",
    "Period",
    "SurveyInvitationPlanner",
    "SurveyKind",
    "SurveyPolicy",
    "SurveyRecipient",
    "advance",
    "due",
    "next_due_at",
    "requires_iys_consent",
]
