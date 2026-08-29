"""INT-141 — quiet hours and opt-out: the patient's own controls.

**No quiet-hours window is shipped, and that is deliberate.** files/10 §9
names the control ("content-free pushes, quiet hours, opt-out") and no file in
the tree names an hour. Writing 22:00–08:00 here would be a value chosen once
by an engineer for every future patient with no diff that makes it look wrong
— the thing rule 1 of HUMAN_BLOCKERS forbids. So an unset baseline **refuses**
(``REFUSED_QUIET_HOURS_UNSET``): a reminder is a convenience, and not sending
one is the safe direction. The ask is recorded in docs/evidence/INT-141.md.

Two windows can apply and they **union**, never intersect: the tenant's
baseline plus the patient's own. A patient who adds a quiet afternoon gets it;
a patient whose window says nothing about the night does not thereby unlock
the night.

The clock is Türkiye's. Evaluating a local window in UTC would wake a third
of the country three hours early, and this product encodes exactly one
jurisdiction (the same posture INT-223 takes with ``jurisdiction_tr_only``) —
so the offset is a fixed +03 constant rather than a per-patient timezone
column, which also keeps a location signal out of the row. A second
jurisdiction is a data-model change with a real timezone database behind it,
not a second constant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final, final

__all__ = [
    "MINUTES_PER_DAY",
    "SCHEDULING_OFFSET",
    "NotificationPreferences",
    "QuietWindow",
    "local_minute_of_day",
]

MINUTES_PER_DAY: Final = 24 * 60

#: Türkiye keeps a single year-round UTC+03 offset with no daylight change,
#: so a fixed offset is exact here and needs no timezone database on the
#: image. See the module docstring for why this is one constant and not a
#: per-patient column.
SCHEDULING_OFFSET: Final = timezone(timedelta(hours=3), "Türkiye (UTC+03)")

_TIME_OF_DAY = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


def local_minute_of_day(at: datetime) -> int:
    """Minutes since local midnight for a tz-aware instant."""
    if at.tzinfo is None or at.tzinfo.utcoffset(at) is None:
        raise ValueError("quiet hours need a tz-aware instant; a naive one is not a time")
    local = at.astimezone(SCHEDULING_OFFSET)
    return local.hour * 60 + local.minute


@final
@dataclass(frozen=True, slots=True)
class QuietWindow:
    """A local window during which nothing is delivered. Wraps midnight when
    ``end`` is earlier than ``start``, which is the normal case."""

    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        for name, value in (("start_minute", self.start_minute), ("end_minute", self.end_minute)):
            if not 0 <= value < MINUTES_PER_DAY:
                raise ValueError(f"{name} must be a minute of the day (0–1439), got {value}")
        if self.start_minute == self.end_minute:
            raise ValueError("a quiet window of zero width is not a window; clear it instead")

    @classmethod
    def parse(cls, start: str, end: str) -> QuietWindow:
        """From the wire form ``HH:MM``. Anything else is refused rather than
        coerced — "8:00" is a typo, not eight o'clock."""
        return cls(start_minute=_minute_of(start), end_minute=_minute_of(end))

    def covers(self, minute_of_day: int) -> bool:
        """Half-open: the start minute is quiet, the end minute is awake."""
        if self.start_minute < self.end_minute:
            return self.start_minute <= minute_of_day < self.end_minute
        return minute_of_day >= self.start_minute or minute_of_day < self.end_minute

    def as_text(self) -> tuple[str, str]:
        return _text_of(self.start_minute), _text_of(self.end_minute)


@final
@dataclass(frozen=True, slots=True)
class NotificationPreferences:
    """What the patient has said. ``quiet is None`` means she has said
    nothing about hours — never "she is happy to be woken"."""

    opted_out: bool
    quiet: QuietWindow | None


def _minute_of(value: str) -> int:
    match = _TIME_OF_DAY.match(value)
    if match is None:
        raise ValueError("a time of day must be written HH:MM on the 24-hour clock")
    return int(match.group(1)) * 60 + int(match.group(2))


def _text_of(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"
