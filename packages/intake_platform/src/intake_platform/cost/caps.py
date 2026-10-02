"""INT-439 — the monthly spend cap and the model rates it is counted in.

Owner decision, 3 Oct 2026, in chat: *"make limit 80 dollars"* — the answer to
files/HUMAN_BLOCKERS.md HB-O8, recorded as 00_STATE §3 D19. Two pieces of
``infra/costs/unit-prices.yaml`` carry it:

- :class:`SpendCap` — a calendar-month USD limit on **elective** model spend
  (council verifier members and hosted model lanes), with the ratio at which it
  warns. Elective work is refused once the month-to-date spend reaches the
  limit; obligatory work — the first extraction of an answer the patient has
  just given — is counted toward the month and never refused (INT-101's rule).
- :class:`ModelRate` — which priced component each *measure* of a model lane's
  use is charged at. A rate holds no number of its own: every measure points at
  a component whose ``price`` is already sourced (url, source, as_of), so one
  figure lives in one place and the console, the alert rules and the runtime
  ledger cannot disagree about it. A self-hosted lane is charged per GPU
  host-hour for the seconds it occupied; a hosted lane per what the vendor
  meters — input and output tokens at their own prices, characters, audio.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ["CapPeriod", "Measure", "ModelRate", "RateRoute", "SpendCap", "SpendCapLimit"]


class CapPeriod(enum.StrEnum):
    """A calendar month in UTC — the period both AWS and the vendors bill in."""

    CALENDAR_MONTH_UTC = "calendar_month_utc"


class RateRoute(enum.StrEnum):
    SELF_HOSTED = "self_hosted"
    HOSTED = "hosted"


class Measure(enum.StrEnum):
    """One thing a model call uses that a price can be a price of."""

    INPUT_TOKENS = "input_tokens"
    OUTPUT_TOKENS = "output_tokens"
    CHARACTERS = "characters"
    AUDIO_SECONDS = "audio_seconds"
    #: Wall seconds a self-hosted call occupied its GPU host — priced per host-hour.
    BUSY_SECONDS = "busy_seconds"


class SpendCapLimit(BaseModel):
    """The limit, who set it, and when. All three are required: a cap with no
    provenance is a number nobody can be asked about."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    usd: Decimal = Field(gt=0)
    source: str = Field(min_length=1)
    as_of: date


class SpendCap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cap_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")
    covers: Literal["elective_model_spend"]
    period: CapPeriod
    limit: SpendCapLimit
    #: Warn at this fraction of the limit. Strictly inside (0, 1): a warning at
    #: the limit itself is the refusal, and one at zero is noise.
    warn_ratio: Decimal = Field(gt=0, lt=1)

    @property
    def warn_at_usd(self) -> Decimal:
        return self.limit.usd * self.warn_ratio


class ModelRate(BaseModel):
    """A model lane, and the priced component each measure of its use is charged at."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")
    route: RateRoute
    provider: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")
    #: The model id for a hosted lane (the family the list price is a price of);
    #: for a self-hosted lane, the instance type the models run on.
    model: str = Field(min_length=1, max_length=128)
    charges: Mapping[Measure, str] = Field(min_length=1)
    note: str = Field(min_length=1)

    @field_validator("model")
    @classmethod
    def _model_is_an_id(cls, value: str) -> str:
        if any(ch.isspace() for ch in value):
            raise ValueError("a model id carries no whitespace")
        return value
