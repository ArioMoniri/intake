"""The quarterly KEK rotation cadence (INT-367; files/10 §3).

files/10 §3 states the cadence in three words — "key rotation quarterly" — and
this module is the arithmetic those words imply, nothing more:

- **A quarter is three calendar months, not ninety days.** The same day of the
  month three months on, clamped to the month's length (30 November + one
  quarter is 28 February, or 29 in a leap year). Ninety or ninety-one days is a
  different, invented cadence that drifts.
- **Counted in UTC from the last rotation.** The last rotation is the creation
  time of the key's latest Transit version, which OpenBao records itself
  (:mod:`intake_platform.key_rotation.transit`). A key is due once that instant
  plus one quarter has passed; the countdown goes negative when it is overdue.
- **Pure.** No clock is read here, so a test can move time freely.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
from typing import Final

__all__ = ["ROTATION_PERIOD_MONTHS", "next_rotation_due", "rotation_due_days"]

#: files/10 §3: "key rotation quarterly". Three calendar months.
ROTATION_PERIOD_MONTHS: Final = 3

_ONE_DAY: Final = timedelta(days=1)


def _utc(at: datetime, what: str) -> datetime:
    if at.tzinfo is None or at.tzinfo.utcoffset(at) is None:
        raise ValueError(f"{what} must be tz-aware; a naive instant is not an instant")
    return at.astimezone(UTC)


def next_rotation_due(last_rotated_at: datetime) -> datetime:
    """One quarter after the last rotation, in UTC, clamped to month length."""
    last = _utc(last_rotated_at, "the last rotation time")
    total = last.month - 1 + ROTATION_PERIOD_MONTHS
    year = last.year + total // 12
    month = total % 12 + 1
    day = min(last.day, calendar.monthrange(year, month)[1])
    return last.replace(year=year, month=month, day=day)


def rotation_due_days(last_rotated_at: datetime, now: datetime) -> float:
    """Days until the next rotation is due; zero when due, negative when overdue."""
    return (next_rotation_due(last_rotated_at) - _utc(now, "now")) / _ONE_DAY
