"""INT-439 — the monthly elective model-spend cap, enforced (00_STATE §3 D19).

Owner decision, 3 Oct 2026: *"make limit 80 dollars"*. ``infra/costs/
unit-prices.yaml`` carries it as a :class:`~intake_platform.cost.caps.SpendCap`.
This module is the runtime half, and it answers three questions.

**What does a call cost?** :func:`price_call` multiplies a call's usage by the
sourced price of the component its lane is charged at
(:class:`~intake_platform.cost.caps.ModelRate`). A self-hosted lane is charged
for the host seconds the call occupied, at the GPU host-hour price; that is an
upper bound under batching, which is the safe direction for a cap. A hosted lane
is charged for what the vendor meters (tokens, characters, audio seconds). A
lane with no rate has no price, and its spend is :class:`UnpricedCall`, never
zero.

**May elective work run?** :meth:`MonthlySpendLedger.admits` admits elective
work while the month-to-date spend is below the limit. It refuses once the
limit is reached, when the store cannot be read, and when no cap is configured.
**Obligatory work is always admitted** (INT-101's rule: a patient's answer that
is never extracted is a red-flag phrase nobody evaluated), and its spend is
still counted, so the month's total is honest.

**Who warns, and when?** The first record that takes the month to
``warn_ratio`` of the limit (80 %) logs a warning and increments
``model_spend_cap_events_total{event="warn"}``. The admin cost module shows the
same figure against the cap.

**One month, one total, across every process.** :class:`SpendStore` is the
seam. :class:`RedisSpendStore` keeps the month's integer micro-USD per charge
class under one key with ``INCRBY``, so N workers count one total.
:class:`InMemorySpendStore` is the single-process store. The month is the UTC
calendar month, read off an injected wall clock, because that is the period
both AWS and the vendors bill in.
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from threading import Lock
from typing import Final, Protocol

import redis
from intake_platform.cost.caps import RateRoute, SpendCap
from intake_platform.cost.config import CostConfig, Unit

from intake_voice_runtime.metering.components import ChargeClass
from intake_voice_runtime.metrics import MODEL_SPEND_CAP_EVENTS_TOTAL, MODEL_SPEND_MONTH_USD

__all__ = [
    "MICRO",
    "CallUsage",
    "InMemorySpendStore",
    "LaneRate",
    "MonthlySpendLedger",
    "RedisSpendStore",
    "SpendAdmission",
    "SpendReason",
    "SpendStore",
    "SpendStoreUnavailable",
    "UnpricedCall",
    "lane_rates",
    "month_of",
    "price_call",
]

logger = logging.getLogger("intake_voice_runtime.metering.spend")

#: Spend is stored as integer micro-USD: exact, additive, and INCRBY-able.
MICRO: Final = Decimal(1_000_000)
_SECONDS_PER_HOUR: Final = Decimal(3600)
_KEY_PREFIX: Final = "intake:spend"
#: A month's key outlives the month by long enough to be read at the next
#: month's review, and no longer.
_KEY_TTL_S: Final = 62 * 24 * 3600


class UnpricedCall(LookupError):
    """The lane has no sourced rate, so the call's cost is unknown, not zero."""


class SpendStoreUnavailable(RuntimeError):
    """The month's total cannot be read or written."""


@dataclass(frozen=True, slots=True)
class CallUsage:
    """What one model call used. Counts only; nothing a person could be read from."""

    input_tokens: int = 0
    output_tokens: int = 0
    characters: int = 0
    audio_seconds: Decimal = Decimal(0)
    busy_seconds: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "characters"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.audio_seconds < 0 or self.busy_seconds < 0:
            raise ValueError("a duration cannot be negative")


@dataclass(frozen=True, slots=True)
class LaneRate:
    """One lane's resolved rate: the unit it is charged in and the sourced price."""

    rate_id: str
    route: RateRoute
    unit: Unit
    usd_per_unit: Decimal


def lane_rates(config: CostConfig) -> dict[tuple[RateRoute, str, str], LaneRate]:
    """``(route, provider, model) -> LaneRate`` for every configured model rate."""
    components = {component.component: component for component in config.components}
    rates: dict[tuple[RateRoute, str, str], LaneRate] = {}
    for rate in config.model_rates:
        component = components[rate.priced_by]
        price = component.price.usd_per_unit
        if price is None:  # CostConfig refuses this; re-checked so a type never lies
            raise UnpricedCall(rate.rate_id)
        rates[(rate.route, rate.provider, rate.model)] = LaneRate(
            rate_id=rate.rate_id,
            route=rate.route,
            unit=component.unit,
            usd_per_unit=Decimal(str(price)),
        )
    return rates


def _quantity(unit: Unit, usage: CallUsage) -> Decimal:
    if unit is Unit.HOST_HOUR:
        return usage.busy_seconds / _SECONDS_PER_HOUR
    if unit is Unit.TOKEN:
        return Decimal(usage.input_tokens + usage.output_tokens)
    if unit is Unit.CHARACTER:
        return Decimal(usage.characters)
    if unit is Unit.AUDIO_SECOND:
        return usage.audio_seconds
    raise UnpricedCall(f"a model lane is never charged per {unit.value}")


def price_call(rate: LaneRate | None, usage: CallUsage) -> Decimal:
    """The call's cost in USD, or :class:`UnpricedCall`. Never a guessed zero."""
    if rate is None:
        raise UnpricedCall("this lane has no model rate in infra/costs/unit-prices.yaml")
    return _quantity(rate.unit, usage) * rate.usd_per_unit


def month_of(moment: datetime) -> str:
    """``YYYY-MM`` of the UTC calendar month. A naive datetime is refused."""
    if moment.tzinfo is None:
        raise ValueError("the spend month is read off an aware datetime")
    return moment.astimezone(UTC).strftime("%Y-%m")


class SpendStore(Protocol):
    def add(self, month: str, charge_class: ChargeClass, micro_usd: int) -> int:
        """Add to the month, return the month's total over every class."""
        ...

    def total(self, month: str) -> int:
        """The month's total micro-USD over every class."""
        ...


@dataclass
class InMemorySpendStore:
    """One process's month totals. Correct for exactly one worker."""

    _totals: dict[tuple[str, ChargeClass], int] = field(default_factory=dict, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def add(self, month: str, charge_class: ChargeClass, micro_usd: int) -> int:
        with self._lock:
            key = (month, charge_class)
            self._totals[key] = self._totals.get(key, 0) + micro_usd
            return self._sum(month)

    def total(self, month: str) -> int:
        with self._lock:
            return self._sum(month)

    def _sum(self, month: str) -> int:
        return sum(value for (m, _), value in self._totals.items() if m == month)


class RedisSpendStore:
    """The deployment's month totals, shared by every worker."""

    def __init__(self, client: redis.Redis, *, deployment: str) -> None:
        if not deployment or any(ch in deployment for ch in ": \t\n"):
            raise ValueError("deployment must be a non-empty id with no separator")
        self._r = client
        self._deployment = deployment

    def _key(self, month: str, charge_class: ChargeClass) -> str:
        return f"{_KEY_PREFIX}:{self._deployment}:{month}:{charge_class.value}"

    def add(self, month: str, charge_class: ChargeClass, micro_usd: int) -> int:
        key = self._key(month, charge_class)
        try:
            with self._r.pipeline() as pipe:
                pipe.incrby(key, micro_usd)
                pipe.expire(key, _KEY_TTL_S)
                pipe.execute()
        except redis.RedisError:
            raise SpendStoreUnavailable("spend_store_unreachable") from None
        return self.total(month)

    def total(self, month: str) -> int:
        keys = [self._key(month, charge_class) for charge_class in ChargeClass]
        try:
            values: list[object] = list(self._r.mget(keys))
        except redis.RedisError:
            raise SpendStoreUnavailable("spend_store_unreachable") from None
        return sum(_micro(raw) for raw in values)


def _micro(raw: object) -> int:
    """One stored counter. Absent reads 0; anything but an integer is refused."""
    if raw is None:
        return 0
    text = raw.decode("ascii", "replace") if isinstance(raw, bytes) else raw
    if not isinstance(text, str) or not text.lstrip("-").isdigit():
        raise SpendStoreUnavailable("spend_store_malformed")
    return int(text)


class SpendReason(enum.StrEnum):
    OBLIGATORY = "obligatory"
    WITHIN_CAP = "within_cap"
    CAP_REACHED = "cap_reached"
    CAP_NOT_CONFIGURED = "cap_not_configured"
    STORE_UNAVAILABLE = "store_unavailable"


@dataclass(frozen=True, slots=True)
class SpendAdmission:
    admitted: bool
    reason: SpendReason
    month: str
    spent_usd: Decimal | None
    limit_usd: Decimal | None


def _usd(micro: int) -> Decimal:
    return Decimal(micro) / MICRO


@dataclass
class MonthlySpendLedger:
    """The deployment's month of elective model spend, against its one cap."""

    cap: SpendCap | None
    store: SpendStore
    wall_clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    _warned: set[str] = field(default_factory=set, init=False, repr=False)

    @classmethod
    def from_config(
        cls,
        config: CostConfig,
        store: SpendStore,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> MonthlySpendLedger:
        caps = [cap for cap in config.spend_caps if cap.covers == "elective_model_spend"]
        clock = wall_clock or (lambda: datetime.now(UTC))
        return cls(cap=caps[0] if caps else None, store=store, wall_clock=clock)

    def admits(self, charge_class: ChargeClass) -> SpendAdmission:
        """May this work run? A query: it records nothing."""
        month = month_of(self.wall_clock())
        limit = self.cap.limit.usd if self.cap is not None else None
        if charge_class is ChargeClass.OBLIGATORY:
            return SpendAdmission(True, SpendReason.OBLIGATORY, month, None, limit)
        if self.cap is None or limit is None:
            return self._refuse(SpendReason.CAP_NOT_CONFIGURED, month, None, None)
        try:
            spent = _usd(self.store.total(month))
        except SpendStoreUnavailable:
            return self._refuse(SpendReason.STORE_UNAVAILABLE, month, None, limit)
        if spent >= limit:
            return self._refuse(SpendReason.CAP_REACHED, month, spent, limit)
        return SpendAdmission(True, SpendReason.WITHIN_CAP, month, spent, limit)

    def record(self, usd: Decimal, charge_class: ChargeClass) -> Decimal | None:
        """Count spend that happened. Never refuses; returns the month's total.

        Returns ``None`` when the store cannot be written: the spend still
        happened, and an obligatory call must not fail because a counter did.
        The miss is counted so it is visible, never silently dropped.
        """
        if usd < 0:
            raise ValueError("a negative spend nets cost off against itself")
        month = month_of(self.wall_clock())
        micro = int((usd * MICRO).to_integral_value(rounding=ROUND_CEILING))
        try:
            total = _usd(self.store.add(month, charge_class, micro))
        except SpendStoreUnavailable:
            MODEL_SPEND_CAP_EVENTS_TOTAL.labels(event="store_unavailable").inc()
            return None
        MODEL_SPEND_MONTH_USD.set(float(total))
        self._maybe_warn(month, total)
        return total

    def _maybe_warn(self, month: str, total: Decimal) -> None:
        if self.cap is None or month in self._warned or total < self.cap.warn_at_usd:
            return
        self._warned.add(month)
        MODEL_SPEND_CAP_EVENTS_TOTAL.labels(event="warn").inc()
        logger.warning(
            "model spend reached the warning ratio of the monthly cap",
            extra={"cap_id": self.cap.cap_id, "month": month},
        )

    def _refuse(
        self,
        reason: SpendReason,
        month: str,
        spent: Decimal | None,
        limit: Decimal | None,
    ) -> SpendAdmission:
        MODEL_SPEND_CAP_EVENTS_TOTAL.labels(event=f"refused_{reason.value}").inc()
        return SpendAdmission(False, reason, month, spent, limit)
