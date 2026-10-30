"""Serve-time sources shared by the INT-565 console composites.

**The metrics catalogue.** Every composite resolves the metric ids it names
through ``observability/metrics_catalog.yaml`` and raises on a miss: naming a
series nobody governs would be a claim about a series that does not exist
(invariant 15).

**Scrape readings.** The Clinical quality & safety and Security composites
each show one figure that only a metrics scrape can supply (PolicyGuard blocks
by class, egress denials). They read it the way the ops console does
(INT-351): through the API's own Prometheus reader
(``INTAKE_OPS_PROMETHEUS_URL``), running only a query from the composite's
fixed table, holding every answer to the label set that query asked for (ids
only, invariant 6).

A figure that could not be read is a :class:`Reading` with a machine reason —
``prometheus_unconfigured``, ``prometheus_misconfigured``, the reader's own
failure codes — and no values. A composite renders that as not available,
never as zero (invariant 17).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from intake_platform.slo import MetricDef, MetricsCatalog, load_metrics_catalog

from intake_api.admin.ops_prom import PromClient, PromSession, TileUnknown, prom_client_from_env

__all__ = [
    "METRICS_CATALOG",
    "REPO",
    "WINDOW",
    "Reading",
    "catalogued",
    "load_catalog",
    "prom_from_env",
    "read_counts",
]

REPO: Final = Path(__file__).resolve().parents[5]
METRICS_CATALOG: Final = REPO / "observability" / "metrics_catalog.yaml"

#: The window every INT-565 scrape reads over, named beside the figure.
WINDOW: Final = "24h"


def load_catalog(path: Path = METRICS_CATALOG) -> MetricsCatalog:
    return load_metrics_catalog(path)


def catalogued(catalog: MetricsCatalog, metric_id: str) -> MetricDef:
    """The catalogue entry a composite names, by spec id or series name."""
    for metric in catalog.metrics:
        if metric_id in (metric.spec_id, metric.name):
            return metric
    raise KeyError(f"{metric_id} is not catalogued (invariant 15)")


@dataclass(frozen=True)
class Reading:
    """One query's answer: counts by label value, or why there are none."""

    reason: str | None
    values: Mapping[str, int] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.reason is None

    @classmethod
    def unavailable(cls, reason: str) -> Reading:
        return cls(reason=reason)


def prom_from_env(env: Mapping[str, str]) -> PromClient | Reading:
    """The configured reader, or the reading every figure gets without one."""
    try:
        prom = prom_client_from_env(env)
    except ValueError:
        return Reading.unavailable("prometheus_misconfigured")
    return prom if prom is not None else Reading.unavailable("prometheus_unconfigured")


def read_counts(
    source: PromClient | Reading,
    queries: Mapping[str, str],
    labels: Mapping[str, frozenset[str]],
    query_id: str,
) -> Reading:
    """Run one query from the fixed table; counts are rounded increases.

    A query whose label set is empty answers one scalar, held under ``""``.
    """
    names = sorted(labels[query_id])
    if len(names) > 1:
        raise ValueError(f"{query_id}: a console count is keyed by at most one label")
    if isinstance(source, Reading):
        return source
    try:
        samples = PromSession(source, queries, labels).fetch(query_id)
    except TileUnknown as unknown:
        return Reading.unavailable(unknown.reason)
    values: dict[str, int] = {}
    for sample in samples:
        key = sample.labels[names[0]] if names else ""
        values[key] = values.get(key, 0) + int(round(sample.value))
    return Reading(reason=None, values=values)
