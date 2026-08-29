"""INT-242 — when a recipient becomes due for a survey.

**Two figures live in this module and both are stated in the tree.** The
acceptance line for INT-242 reads *"monthly NPS prompt honoring quiet hours;
quarterly pulse; opt-outs respected"*, and files/08 §4 group F names the same
two: ``nps.monthly`` and ``clinician.pulse`` ("quarterly 1-5"). So
:data:`CADENCE` is sourced, and :data:`MONTHS_PER_PERIOD` is the arithmetic
those two words imply.

**Everything else a scheduler might want is absent from every file in the
tree, and absent here too.** No sampling rate, no cross-survey cool-off, no
send hour, no day-of-month anchor. Two of those would have been easy to write
and impossible to spot later: "every 90 days" reads as a decision somebody
made. The one value the mechanism genuinely cannot do without is the *first*
prompt — a recipient with no prompt history has no period to advance from —
so :class:`SurveyPolicy` carries it, unset, and :func:`due` refuses. Once a
recipient has been prompted once, the stated period answers "when next"
without any further value, which is why the gap is exactly one field wide.

**A period is a calendar span, not a number of days.** "Monthly" means the
same day next month, clamped to the month's length (31 January + 1 month is
28 February, not 3 March); "quarterly" is three of those. Thirty and ninety
days are different, invented, cadences that drift a week a year. The calendar
is read on Türkiye's fixed +03 clock — the same
:data:`~intake_platform.notifications.preferences.SCHEDULING_OFFSET` INT-141
evaluates quiet hours on, because a month boundary is a local notion and
23:30 UTC on the 31st is already the 1st in İstanbul.
"""

from __future__ import annotations

import calendar
import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final, final

from intake_platform.notifications.preferences import SCHEDULING_OFFSET

__all__ = [
    "CADENCE",
    "MONTHS_PER_PERIOD",
    "DueDecision",
    "DueStatus",
    "Period",
    "SurveyKind",
    "SurveyPolicy",
    "SurveyRecipient",
    "advance",
    "due",
    "next_due_at",
]


class SurveyKind(enum.StrEnum):
    """The two surveys this issue schedules.

    ``csat`` is deliberately absent: INT-240 records it per session, triggered
    by the session ending rather than by a clock, so it has no cadence to own.
    """

    NPS = "nps"
    CLINICIAN_PULSE = "clinician_pulse"


class Period(enum.StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


#: The calendar arithmetic each word means. Not a duration in days — see the
#: module docstring.
MONTHS_PER_PERIOD: Final[Mapping[Period, int]] = MappingProxyType(
    {Period.MONTHLY: 1, Period.QUARTERLY: 3}
)

#: Sourced: the INT-242 acceptance line, and files/08 §4 group F
#: (``nps.monthly``; ``clinician.pulse`` "quarterly 1-5"). Total over
#: :class:`SurveyKind`, so adding a kind without a stated cadence fails at the
#: first lookup rather than defaulting to something.
CADENCE: Final[Mapping[SurveyKind, Period]] = MappingProxyType(
    {SurveyKind.NPS: Period.MONTHLY, SurveyKind.CLINICIAN_PULSE: Period.QUARTERLY}
)


def _require_aware(at: datetime, what: str) -> datetime:
    if at.tzinfo is None or at.tzinfo.utcoffset(at) is None:
        raise ValueError(f"{what} must be tz-aware; a naive instant is not an instant")
    return at.astimezone(SCHEDULING_OFFSET)


def advance(at: datetime, period: Period) -> datetime:
    """One calendar period on, on the Türkiye clock, clamped to month length."""
    local = _require_aware(at, "a survey period boundary")
    total = local.month - 1 + MONTHS_PER_PERIOD[period]
    year = local.year + total // 12
    month = total % 12 + 1
    day = min(local.day, calendar.monthrange(year, month)[1])
    return local.replace(year=year, month=month, day=day)


@final
@dataclass(frozen=True, slots=True)
class SurveyPolicy:
    """The scheduling values no file in the tree states.

    :attr:`first_prompt_after` is how long after a recipient becomes eligible
    the *first* invitation falls due. Unset ships, and :func:`due` refuses
    rather than choosing — and note that the second half of the same question
    is the caller's: what event makes a recipient eligible (account created?
    first session completed? tenant go-live?) decides
    :attr:`SurveyRecipient.eligible_since`, and no file states that either.
    Both halves are one ask, recorded in docs/evidence/INT-242.md.
    """

    first_prompt_after: timedelta | None = None


@final
@dataclass(frozen=True, slots=True)
class SurveyRecipient:
    """Who might be asked, as ids and instants only (invariant 6).

    ``recipient_ref`` is the tokenized handle INT-141's transport accepts —
    never a name, a phone number or an address.
    """

    recipient_ref: str
    eligible_since: datetime
    last_prompted_at: datetime | None = None


class DueStatus(enum.StrEnum):
    DUE = "due"
    NOT_YET_DUE = "not_yet_due"
    REFUSED_FIRST_PROMPT_DELAY_UNSET = "refused_first_prompt_delay_unset"


@final
@dataclass(frozen=True, slots=True)
class DueDecision:
    status: DueStatus
    due_at: datetime | None


def next_due_at(
    kind: SurveyKind, recipient: SurveyRecipient, policy: SurveyPolicy
) -> datetime | None:
    """When the next invitation falls due, or ``None`` when nothing says."""
    if recipient.last_prompted_at is not None:
        return advance(recipient.last_prompted_at, CADENCE[kind])
    if policy.first_prompt_after is None:
        return None
    return _require_aware(recipient.eligible_since, "eligible_since") + policy.first_prompt_after


def due(
    kind: SurveyKind, recipient: SurveyRecipient, policy: SurveyPolicy, *, at: datetime
) -> DueDecision:
    """Pure: no clock is read here, so a schedule is reproducible in a test."""
    _require_aware(at, "the evaluation instant")
    due_at = next_due_at(kind, recipient, policy)
    if due_at is None:
        return DueDecision(status=DueStatus.REFUSED_FIRST_PROMPT_DELAY_UNSET, due_at=None)
    if at < due_at:
        return DueDecision(status=DueStatus.NOT_YET_DUE, due_at=due_at)
    return DueDecision(status=DueStatus.DUE, due_at=due_at)
