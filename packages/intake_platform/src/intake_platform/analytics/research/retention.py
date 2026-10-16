"""INT-490 — LD-06's two undecided retention periods, as configuration.

LD-06 ``retention.aggregates`` and ``retention.raw_telemetry`` are both
``not decided`` (value_status ``draft``), and CLAUDE.md makes data retention a
stop-and-ask for the owner. So both are configuration with **no default**: the
variables below are read from the environment, an absent or empty one is
UNDECIDED, and a value that is not a positive whole number of days is refused
(:class:`RetentionConfigRefused`) rather than read as undecided — a typo must
not look like a decision either way.

**The fail-closed reading, recorded once.** A retention period governs
something that is KEPT. While a period is undecided, nothing of that kind is
kept:

- ``aggregates`` undecided — no aggregate is kept anywhere: the Analytics read
  computes its release per request from source rows that sit inside their own
  files/06 §3 clocks, answers ``Cache-Control: no-store``, and writes no table,
  file, cache or export; and a Loop-2 evidence bundle, which rides a pull
  request and is therefore kept, is refused with :class:`RetentionUndecided`.
  The live read is NOT refused: LD-06's own ``fail_closed_while_draft`` lets
  aggregates that pass the gate reach the panel while retention is draft, and
  "serve nothing until the owner decides" would be stricter than the decision
  it implements while keeping nothing more safely.
- ``raw_telemetry`` undecided — no per-person telemetry is recorded; the views
  that need it (per question, and the device platform) are reported
  ``raw_telemetry_retention_undecided``. Once a period is set they report
  ``raw_telemetry_not_recorded`` until a producer and a store land: setting a
  period does not invent the recording.

Nothing here proposes a number. LD-06 records the statutory outer bound of the
destruction CYCLE (Yönetmelik m.11(2), six months) and files/06 §3's current
telemetry wording; neither is a retention period, and neither is used as one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

__all__ = [
    "ENV_AGGREGATE_RETENTION_DAYS",
    "ENV_RAW_TELEMETRY_RETENTION_DAYS",
    "AnalyticsRetention",
    "RetentionConfigRefused",
    "RetentionUndecided",
]

ENV_AGGREGATE_RETENTION_DAYS: Final = "INTAKE_ANALYTICS_AGGREGATE_RETENTION_DAYS"
ENV_RAW_TELEMETRY_RETENTION_DAYS: Final = "INTAKE_ANALYTICS_RAW_TELEMETRY_RETENTION_DAYS"

_DAYS: Final = re.compile(r"^[1-9][0-9]*$")


class RetentionConfigRefused(ValueError):
    """A retention variable is set to something that is not a whole number of
    days. Names the variable, never its value (invariant 6)."""

    def __init__(self, variable: str) -> None:
        super().__init__(f"{variable} must be a positive whole number of days")
        self.variable = variable


class RetentionUndecided(Exception):
    """Something would be kept, and the owner has not set how long (LD-06)."""

    def __init__(self, which: str) -> None:
        super().__init__(
            f"the {which} retention period is undecided (LD-06 retention.{which}, draft); "
            "nothing of that kind is kept until the owner sets it"
        )
        self.which = which


def _days(env: Mapping[str, str], variable: str) -> timedelta | None:
    raw = env.get(variable, "").strip()
    if not raw:
        return None
    if _DAYS.fullmatch(raw) is None:
        raise RetentionConfigRefused(variable)
    return timedelta(days=int(raw))


@dataclass(frozen=True)
class AnalyticsRetention:
    """Both periods, each ``None`` while undecided. No field has a default."""

    aggregates: timedelta | None
    raw_telemetry: timedelta | None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> AnalyticsRetention:
        return cls(
            aggregates=_days(env, ENV_AGGREGATE_RETENTION_DAYS),
            raw_telemetry=_days(env, ENV_RAW_TELEMETRY_RETENTION_DAYS),
        )

    def require_keeping(self) -> timedelta:
        """How long a kept aggregate may live — or :class:`RetentionUndecided`."""
        if self.aggregates is None:
            raise RetentionUndecided("aggregates")
        return self.aggregates

    def raw_telemetry_reason(self) -> str:
        """Why the raw-telemetry views carry no data, as a reason class."""
        if self.raw_telemetry is None:
            return "raw_telemetry_retention_undecided"
        return "raw_telemetry_not_recorded"

    def as_payload(self) -> dict[str, dict[str, object]]:
        def state(period: timedelta | None) -> dict[str, object]:
            if period is None:
                return {"state": "undecided"}
            return {"state": "set", "days": period.days}

        return {"aggregates": state(self.aggregates), "raw_telemetry": state(self.raw_telemetry)}
