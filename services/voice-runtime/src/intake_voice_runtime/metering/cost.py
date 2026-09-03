"""Turning quantities into money — and the refusal that stops it today.

files/08 §4 group J names ``cost.per_session`` *by component*, and
``observability/metrics_catalog.yaml`` carries it with ``unit: "USD"``. A
quantity is a measurement; a **cost** is a quantity multiplied by a price, and
this repository holds no price for any of the three axes:

* There is no vendor invoice to read a per-token or per-character rate off.
  CLAUDE.md invariant 19 makes every model self-hosted and files/00 §0b deletes
  the vendor socket entirely, so the rate is an amortised GPU-hour figure
  rather than a list price.
* There is no GPU-hour rate either. files/HUMAN_BLOCKERS.md **HB-I4** records
  that no card has been bought and **HB-I5** that no capacity contract naming a
  provider or an SKU exists — and it names in terms that every published
  in-country GPU price is UNVERIFIED.

So a rate written here would be the artefact files/HUMAN_BLOCKERS.md rule 1
forbids: *"a plausible invented number is worse than a missing one, because
there is no diff that makes it look wrong"*. :data:`Unpriced` therefore ships
empty and :func:`priced_cost` raises :class:`CostNotPriced` rather than
returning a zero — **zero is a claim that a session was free**, which is a
different and equally false statement.

**Consequence, stated plainly: ``cost.per_session`` is not emitted.** It stays
``status: planned`` in the catalogue, no ``Gauge`` is declared for it anywhere
in this package, and the acceptance line *"cost.per_session emitted"* is not
met. What ships is everything up to the multiplication: the per-component
quantities are metered, and the moment a rate is supplied this function turns
them into the series without any further design.
"""

from __future__ import annotations

from collections.abc import Mapping

from clinical_schemas.common import FrozenModel
from pydantic import Field, field_validator

from intake_voice_runtime.metering.components import MeteredComponent
from intake_voice_runtime.metering.ledger import SessionLedger

__all__ = ["Unpriced", "CostNotPriced", "PriceBook", "priced_cost"]


class CostNotPriced(LookupError):
    """No rate exists for a component, so its cost is unknown — not zero."""


class PriceBook(FrozenModel):
    """Rates per unit, in the currency ``cost.per_session`` is denominated in.

    ``currency`` is fixed to USD because the catalogue row is: a book in
    another currency would silently change what the series means.
    """

    rates: Mapping[MeteredComponent, float] = Field(default_factory=dict)
    source: str = Field(min_length=1, description="Who supplied these rates, and when.")
    currency: str = Field(default="USD", pattern=r"^USD$")

    @field_validator("rates")
    @classmethod
    def _no_negative_rate(
        cls, rates: Mapping[MeteredComponent, float]
    ) -> Mapping[MeteredComponent, float]:
        for component, rate in rates.items():
            if rate < 0.0:
                raise ValueError(
                    f"{component.value!r} carries a negative rate: a credit is a "
                    "correction somebody has to sign, not a price"
                )
        return rates

    def rate(self, component: MeteredComponent) -> float:
        try:
            return self.rates[component]
        except KeyError:
            raise CostNotPriced(
                f"no {self.currency} rate for {component.value!r}. Under CLAUDE.md "
                "invariant 19 there is no vendor list price, and no GPU-hour rate "
                "exists either (files/HUMAN_BLOCKERS.md HB-I4, HB-I5). A rate invented "
                "here would read as authoritative to every later reader"
            ) from None


#: The shipped book. Empty, and it stays empty until a human supplies a rate.
Unpriced: PriceBook = PriceBook(
    rates={},
    source=(
        "no rate is supplied: files/HUMAN_BLOCKERS.md HB-I4 and HB-I5 record that no "
        "GPU and no capacity contract exist, and CLAUDE.md invariant 19 leaves no "
        "vendor list price to read"
    ),
)


def priced_cost(ledger: SessionLedger, book: PriceBook) -> Mapping[MeteredComponent, float]:
    """One session's cost by component, or a refusal naming what is missing.

    Every component is priced or none is. A partial answer would be published
    as *the* cost of a session and would be wrong by exactly the components it
    left out.
    """
    return {
        component: ledger.total(component) * book.rate(component) for component in MeteredComponent
    }
