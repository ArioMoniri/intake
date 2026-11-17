"""The owner-filled price and budget file, as a schema (INT-190).

``infra/costs/unit-prices.yaml`` is the cost module's only source of money.
This module decides what that file may say, and it is strict in one direction
above all: **a value never travels without its provenance.** A price or a
budget limit is refused unless it names a ``source`` and an ``as_of`` date,
and a ``source`` with no value is refused too, because a half-filled row is a
claim nobody made. With nothing filled in, every price and every limit is
``None`` — and ``None`` is carried to the console as "not configured", never
coerced to a zero (files/HUMAN_BLOCKERS.md rule 1; HB-O8).

The file names *what* is priced; :mod:`intake_platform.cost.resolve` binds each
row to the metrics catalogue, so a row that meters nothing real is refused
before any arithmetic happens (CLAUDE.md invariant 13).
"""

from __future__ import annotations

import enum
import hashlib
import math
import re
from datetime import date
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "PERIOD_HOURS",
    "PERIOD_WINDOW",
    "Aggregation",
    "Budget",
    "BudgetScope",
    "CostComponent",
    "CostConfig",
    "Limit",
    "Period",
    "Price",
    "Profile",
    "Unit",
    "UsageSeries",
    "config_identity",
    "is_id",
    "load_cost_config",
]

#: An identifier the console may show: lowercase, no spaces, no prose. A
#: component, vendor, budget or label value that is not id-shaped is refused,
#: because free text on an operator surface is where content leaks (inv. 6).
_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_LABEL_NAME_RE: Final = re.compile(r"^[a-z_][a-z0-9_]*$")
_METRIC_NAME_RE: Final = re.compile(r"^[a-z_][a-z0-9_]*$")


def is_id(value: str) -> bool:
    """Whether ``value`` is id-shaped (see ``_ID_RE``)."""
    return _ID_RE.match(value) is not None


def _require_id(value: str, what: str) -> str:
    if not is_id(value):
        raise ValueError(f"{what} {value!r} is not id-shaped (lowercase id, no prose)")
    return value


class Profile(enum.StrEnum):
    """The voice profiles a session can run under — CLAUDE.md invariant 19."""

    RESIDENCY_TR = "residency_tr"
    TYPED = "typed"


class Unit(enum.StrEnum):
    """What one unit of a price buys. Each is read off one catalogued unit."""

    AUDIO_SECOND = "audio_second"
    CHARACTER = "character"
    TOKEN = "token"  # noqa: S105 — a unit of model usage, not a credential
    MESSAGE = "message"
    CLIP = "clip"
    HOST_HOUR = "host_hour"


class Aggregation(enum.StrEnum):
    """How a window's quantity is read off a catalogued series."""

    #: ``increase(<histogram>_sum[w])`` — the quantity the observations add up to.
    HISTOGRAM_SUM = "histogram_sum"
    #: ``increase(<counter>[w])`` — events in the window.
    COUNTER_INCREASE = "counter_increase"
    #: ``avg_over_time(<0/1 gauge>[w]) * hours(w)`` — hours up in the window.
    GAUGE_HOURS = "gauge_hours"


class Period(enum.StrEnum):
    """The two budget periods. Both are rolling windows, not calendar ones."""

    DAY = "day"
    MONTH = "month"


#: The Prometheus window each period is evaluated over. The month is 30 days,
#: which files/06 §3's "30 d hot" telemetry retention keeps whole.
PERIOD_WINDOW: Final[dict[Period, str]] = {Period.DAY: "1d", Period.MONTH: "30d"}
PERIOD_HOURS: Final[dict[Period, int]] = {Period.DAY: 24, Period.MONTH: 720}


class BudgetScope(enum.StrEnum):
    ALL_VENDORS = "all_vendors"
    VENDOR = "vendor"


class _Sourced(BaseModel):
    """A value, who supplied it, and when — all three, or none of them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str | None = None
    as_of: date | None = None

    def _check(self, value: float | None, what: str) -> None:
        if value is None:
            if self.source is not None or self.as_of is not None:
                raise ValueError(
                    f"{what} names a source or a date but has no value: a provenance "
                    "with nothing to attach to is a claim nobody made"
                )
            return
        if not math.isfinite(value):
            raise ValueError(f"{what} must be a finite number")
        if value < 0:
            raise ValueError(
                f"{what} is negative: a credit is a correction somebody signs, not a price"
            )
        if not (self.source and self.source.strip()) or self.as_of is None:
            raise ValueError(
                f"{what} carries a value with no source and as_of date — a number "
                "nobody can trace is the invented value files/HUMAN_BLOCKERS.md rule 1 "
                "forbids"
            )


class Price(_Sourced):
    usd_per_unit: float | None = None

    @model_validator(mode="after")
    def _provenance(self) -> Price:
        self._check(self.usd_per_unit, "price.usd_per_unit")
        return self


class Limit(_Sourced):
    usd: float | None = None

    @model_validator(mode="after")
    def _provenance(self) -> Limit:
        self._check(self.usd, "limit.usd")
        return self


class UsageSeries(BaseModel):
    """Which catalogued series meters a component, and how."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str
    aggregation: Aggregation
    selector: dict[str, str] = Field(default_factory=dict)

    @field_validator("metric")
    @classmethod
    def _metric_shape(cls, value: str) -> str:
        if _METRIC_NAME_RE.match(value) is None:
            raise ValueError(f"not a Prometheus series name: {value!r}")
        return value

    @field_validator("selector")
    @classmethod
    def _selector_ids(cls, value: dict[str, str]) -> dict[str, str]:
        for name, matched in value.items():
            if _LABEL_NAME_RE.match(name) is None:
                raise ValueError(f"not a Prometheus label name: {name!r}")
            _require_id(matched, f"selector value for {name!r}")
        return value


class CostComponent(BaseModel):
    """One thing that costs money, and the series that says how much of it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component: str
    vendor: str | None
    vendor_note: str | None = None
    unit: Unit
    profiles: tuple[Profile, ...] = ()
    usage: UsageSeries | None
    usage_note: str | None = None
    price: Price

    @field_validator("component")
    @classmethod
    def _component_id(cls, value: str) -> str:
        return _require_id(value, "component")

    @field_validator("vendor")
    @classmethod
    def _vendor_id(cls, value: str | None) -> str | None:
        return value if value is None else _require_id(value, "vendor")

    @model_validator(mode="after")
    def _reasons_for_absences(self) -> CostComponent:
        if self.vendor is None and not (self.vendor_note and self.vendor_note.strip()):
            raise ValueError(
                f"{self.component}: vendor is null, so vendor_note must say why no vendor is chosen"
            )
        if self.usage is None and not (self.usage_note and self.usage_note.strip()):
            raise ValueError(
                f"{self.component}: usage is null, so usage_note must say why nothing meters it"
            )
        if len(set(self.profiles)) != len(self.profiles):
            raise ValueError(f"{self.component}: duplicate profiles {list(self.profiles)}")
        return self


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    budget_id: str
    scope: BudgetScope
    vendor: str | None = None
    period: Period
    limit: Limit

    @field_validator("budget_id")
    @classmethod
    def _budget_id(cls, value: str) -> str:
        return _require_id(value, "budget_id")

    @model_validator(mode="after")
    def _scope_and_vendor_agree(self) -> Budget:
        if self.scope is BudgetScope.ALL_VENDORS and self.vendor is not None:
            raise ValueError(f"{self.budget_id}: an all_vendors budget cannot name a vendor")
        if self.scope is BudgetScope.VENDOR and self.vendor is None:
            raise ValueError(f"{self.budget_id}: a vendor budget must name its vendor")
        return self


class CostConfig(BaseModel):
    """``infra/costs/unit-prices.yaml``, validated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    #: observability/metrics_catalog.yaml denominates cost_per_session in USD;
    #: a file in another currency would silently change what every figure means.
    currency: Literal["USD"]
    components: tuple[CostComponent, ...] = Field(min_length=1)
    budgets: tuple[Budget, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _closed_and_covered(self) -> CostConfig:
        ids = [c.component for c in self.components]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate component ids: {ids}")
        budget_ids = [b.budget_id for b in self.budgets]
        if len(set(budget_ids)) != len(budget_ids):
            raise ValueError(f"duplicate budget ids: {budget_ids}")

        vendors = {c.vendor for c in self.components if c.vendor is not None}
        slots: dict[tuple[str | None, Period], str] = {}
        for budget in self.budgets:
            if budget.vendor is not None and budget.vendor not in vendors:
                raise ValueError(
                    f"budget {budget.budget_id} names vendor {budget.vendor!r}, which no "
                    "component has"
                )
            slot = (budget.vendor, budget.period)
            if slot in slots:
                raise ValueError(f"budgets {slots[slot]} and {budget.budget_id} cover one slot")
            slots[slot] = budget.budget_id
        # every vendor, and all of them together, has a budget for every period:
        # a spend nobody can set a limit for is a spend nobody watches
        candidates: list[str | None] = [*sorted(vendors), None]
        for vendor in candidates:
            for period in Period:
                if (vendor, period) not in slots:
                    who = vendor if vendor is not None else "all_vendors"
                    raise ValueError(f"no {period.value} budget for {who}")
        return self


def load_cost_config(path: Path) -> CostConfig:
    return CostConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def config_identity(path: Path, repo_root: Path) -> tuple[str, str]:
    """The repo-relative path and sha256 of a config, as the console shows them."""
    relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    return relative, hashlib.sha256(path.read_bytes()).hexdigest()
