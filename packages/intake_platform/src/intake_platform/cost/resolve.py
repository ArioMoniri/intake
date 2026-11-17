"""Bind every priced component to the catalogued series that meters it (INT-190).

A cost is a quantity times a price, and the quantity has to be a real series:
CLAUDE.md invariant 13 closes the set of series the platform emits, and a
price attached to a name that is not in ``observability/metrics_catalog.yaml``
would be a price for nothing. So before any arithmetic, each usage row is held
to the catalogue:

- the series exists, and the aggregation reads it as the type it is (a
  histogram's ``_sum``, a counter's increase, a 0/1 gauge's hours up);
- the priced unit is the unit the series counts — characters priced per token
  would multiply the right quantity by the wrong rate;
- the selector only names labels the series carries, and a series carrying a
  ``vendor`` label is read for the component's own vendor, never summed across;
- attribution follows the labels. A series labelled by ``profile`` is spent
  *directly* by the profiles the component declares; one without that label
  is *allocated* evenly across every session metered in the window, and may
  not pretend to belong to a profile.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

from intake_platform.cost.config import Aggregation, CostComponent, CostConfig, Unit
from intake_platform.slo import MetricDef, MetricsCatalog

__all__ = ["Attribution", "CostConfigError", "ResolvedComponent", "resolve_components"]

#: The catalogue type each aggregation can read.
_AGGREGATION_TYPE: Final[dict[Aggregation, str]] = {
    Aggregation.HISTOGRAM_SUM: "histogram",
    Aggregation.COUNTER_INCREASE: "counter",
    Aggregation.GAUGE_HOURS: "gauge",
}

#: The catalogued unit each priced unit may be read off.
_CATALOG_UNIT: Final[dict[Unit, frozenset[str]]] = {
    Unit.AUDIO_SECOND: frozenset({"s"}),
    Unit.CHARACTER: frozenset({"chars"}),
    Unit.TOKEN: frozenset({"tokens"}),
    Unit.MESSAGE: frozenset({"count"}),
    Unit.CLIP: frozenset({"count"}),
    Unit.HOST_HOUR: frozenset({"bool (0/1)"}),
}


class CostConfigError(ValueError):
    """A price row that does not meter a real, catalogued quantity."""


class Attribution(enum.StrEnum):
    #: The series is labelled by profile; each profile pays for its own.
    DIRECT = "direct"
    #: The series has no profile; the window's total is split evenly across
    #: every metered session.
    ALLOCATED = "allocated"


@dataclass(frozen=True)
class ResolvedComponent:
    component: CostComponent
    attribution: Attribution
    #: ``live`` / ``planned`` from the catalogue, or ``None`` when nothing meters it.
    catalog_status: str | None


def _metric(catalog: MetricsCatalog, name: str) -> MetricDef | None:
    return next((m for m in catalog.metrics if m.name == name), None)


def _resolve(component: CostComponent, catalog: MetricsCatalog) -> ResolvedComponent:
    who = component.component
    usage = component.usage
    if usage is None:
        attribution = Attribution.DIRECT if component.profiles else Attribution.ALLOCATED
        return ResolvedComponent(component, attribution, None)

    metric = _metric(catalog, usage.metric)
    if metric is None:
        raise CostConfigError(
            f"{who}: usage series {usage.metric!r} is not catalogued in "
            "observability/metrics_catalog.yaml (CLAUDE.md invariant 13)"
        )
    expected_type = _AGGREGATION_TYPE[usage.aggregation]
    if metric.type != expected_type:
        raise CostConfigError(
            f"{who}: {usage.metric} is a {metric.type}; {usage.aggregation.value} reads a "
            f"{expected_type}"
        )
    if metric.unit not in _CATALOG_UNIT[component.unit]:
        raise CostConfigError(
            f"{who}: priced per {component.unit.value}, but {usage.metric} is catalogued in "
            f"unit {metric.unit!r} — a rate must be per the unit the series counts"
        )
    labels = set(metric.labels)
    stray = sorted(set(usage.selector) - labels)
    if stray:
        raise CostConfigError(f"{who}: {usage.metric} carries no label(s) {stray}")
    if "vendor" in labels and usage.selector.get("vendor") != component.vendor:
        raise CostConfigError(
            f"{who}: {usage.metric} is labelled by vendor, so the selector must read "
            f"vendor={component.vendor!r} rather than sum every vendor's usage"
        )
    has_profile = "profile" in labels
    if has_profile and not component.profiles:
        raise CostConfigError(
            f"{who}: {usage.metric} is labelled by profile, so the component must declare "
            "the profiles it spends in"
        )
    if not has_profile and component.profiles:
        raise CostConfigError(
            f"{who}: {usage.metric} carries no profile label, so it cannot be attributed to "
            f"profiles {[p.value for p in component.profiles]} — leave profiles empty and it "
            "is allocated across all sessions"
        )
    attribution = Attribution.DIRECT if has_profile else Attribution.ALLOCATED
    return ResolvedComponent(component, attribution, metric.status)


def resolve_components(
    config: CostConfig, catalog: MetricsCatalog
) -> tuple[ResolvedComponent, ...]:
    """Every component, bound to its catalogued series, in config order.

    :raises CostConfigError: for the first row that meters nothing real.
    """
    return tuple(_resolve(component, catalog) for component in config.components)
