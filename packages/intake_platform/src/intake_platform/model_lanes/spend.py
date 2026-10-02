"""INT-439 — every hosted model-lane call is charged against the monthly cap.

Owner decision, 3 Oct 2026: *"make limit 80 dollars"* (00_STATE §3 D19). A hosted
lane exists only on the synthetic deployment (ADR-035), where no real patient is
owed the call, so every hosted call is **elective** spend. :func:`~intake_platform.
model_lanes.dispatch.dispatch` asks :class:`HostedSpendGate` before each hosted
attempt and charges it after:

- **before**, the call is refused with a closed code when the lane has no model
  rate (``hosted_lane_unpriced`` — spend nobody can price cannot be bounded),
  when the month has reached the cap (``spend_cap_reached``), when the month
  cannot be read (``spend_store_unavailable``) or when no cap is configured
  (``spend_cap_not_configured``);
- **after**, what the provider reported using is priced at the lane's sourced
  rates and added to the deployment's month.

A router composed with **no** gate refuses every hosted call
(``hosted_spend_unmetered``): an unmetered hosted lane is exactly the unbounded
spend the cap exists to stop. Self-hosted calls are not gated here; their
elective use is gated by the voice runtime's ``SessionLedger``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from intake_platform.cost.caps import RateRoute
from intake_platform.cost.config import CostConfig
from intake_platform.cost.spend import (
    MODEL_SPEND_CAP_EVENTS_TOTAL,
    CallUsage,
    ChargeClass,
    LaneRate,
    MonthlySpendLedger,
    SpendReason,
    SpendStore,
    UnpricedCall,
    lane_rates,
    price_call,
)
from intake_platform.model_lanes.hosted import HostedUsage

__all__ = [
    "CODE_UNMETERED",
    "CODE_UNPRICED",
    "HostedSpendGate",
    "SpendGateRefused",
]

CODE_UNMETERED: Final = "hosted_spend_unmetered"
CODE_UNPRICED: Final = "hosted_lane_unpriced"
_CODE_OF: Final[Mapping[SpendReason, str]] = {
    SpendReason.CAP_REACHED: "spend_cap_reached",
    SpendReason.STORE_UNAVAILABLE: "spend_store_unavailable",
    SpendReason.CAP_NOT_CONFIGURED: "spend_cap_not_configured",
}


class SpendGateRefused(Exception):
    """A hosted call the cap will not admit. Carries a closed code only."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _lane_key(provider: str | None, model_id: str | None) -> tuple[RateRoute, str, str] | None:
    if provider is None or model_id is None:
        return None
    return (RateRoute.HOSTED, provider, model_id)


@dataclass(frozen=True)
class HostedSpendGate:
    """The deployment's monthly ledger and the hosted lanes' sourced rates."""

    ledger: MonthlySpendLedger
    rates: Mapping[tuple[RateRoute, str, str], LaneRate]

    @classmethod
    def from_config(cls, config: CostConfig, store: SpendStore) -> HostedSpendGate:
        return cls(ledger=MonthlySpendLedger.from_config(config, store), rates=lane_rates(config))

    def _rate(self, provider: str | None, model_id: str | None) -> LaneRate | None:
        key = _lane_key(provider, model_id)
        return None if key is None else self.rates.get(key)

    def admit(self, provider: str | None, model_id: str | None) -> None:
        """Raise :class:`SpendGateRefused` unless this hosted call may run."""
        if self._rate(provider, model_id) is None:
            MODEL_SPEND_CAP_EVENTS_TOTAL.labels(event="refused_hosted_unpriced").inc()
            raise SpendGateRefused(CODE_UNPRICED)
        verdict = self.ledger.admits(ChargeClass.ELECTIVE)
        if not verdict.admitted:
            raise SpendGateRefused(_CODE_OF[verdict.reason])

    def charge(
        self, provider: str | None, model_id: str | None, usage: HostedUsage
    ) -> Decimal | None:
        """Count a finished hosted call against the month; the month's total."""
        rate = self._rate(provider, model_id)
        call = CallUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            characters=usage.characters,
            audio_seconds=Decimal(str(usage.audio_seconds)),
        )
        try:
            usd = price_call(rate, call)
        except UnpricedCall:
            # the call ran and reported a measure its rate has no price for:
            # it is counted as a miss, visibly, and the next call is still gated
            MODEL_SPEND_CAP_EVENTS_TOTAL.labels(event="unpriced_hosted_usage").inc()
            return None
        return self.ledger.record(usd, ChargeClass.ELECTIVE)
