"""The cost module's fixed PromQL table, and how an answer to it is read (INT-190).

Every query here is *derived* from the price file and the catalogue — there is
no request field that reaches a query string, and every series a query names
is catalogued (CLAUDE.md invariant 13). Two shapes only:

- a **direct** component is summed ``by (profile)``, so each profile's usage
  is its own;
- an **allocated** component, and nothing else, is summed to one number.

Every query aggregates tenant, branch and every other label away. So a
response that carries any label the query did not group by is not an answer
to the query this module sent, and it is refused — the same stance as an
identifier appearing where only ids were expected (invariant 6). A profile
outside the closed set (invariant 19), a value that is not a finite,
non-negative number, and a result that is not an instant vector are refused
the same way. A refusal is a *source error*, which the console shows as such;
it is never read as zero.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any, Final

from intake_platform.cost.config import (
    PERIOD_HOURS,
    PERIOD_WINDOW,
    Aggregation,
    Period,
    Profile,
    UsageSeries,
)
from intake_platform.cost.resolve import Attribution, ResolvedComponent

__all__ = [
    "SESSIONS_METRIC",
    "QueryRefused",
    "QueryRunner",
    "component_query",
    "parse_by_profile",
    "parse_scalar",
    "run_query",
    "sessions_query",
    "usage_term",
]

#: The per-session divisor (catalogued live; emitted by the INT-101 meter).
SESSIONS_METRIC: Final = "voice_sessions_metered_total"

#: Whatever answers a PromQL instant query with the Prometheus HTTP API body
#: (``/api/v1/query``). ``None`` in its place means no source is configured.
QueryRunner = Callable[[str], Mapping[str, Any]]


class QueryRefused(ValueError):
    """The source did not answer the query this module sent."""


def _selector(labels: Mapping[str, str]) -> str:
    if not labels:
        return ""
    # values are id-shaped by schema, so no quoting or escaping is ever needed
    inner = ",".join(f'{name}="{labels[name]}"' for name in sorted(labels))
    return "{" + inner + "}"


def usage_term(usage: UsageSeries, period: Period) -> str:
    """One window's quantity of a series, summed over every label (a scalar)."""
    window = PERIOD_WINDOW[period]
    selector = _selector(usage.selector)
    if usage.aggregation is Aggregation.HISTOGRAM_SUM:
        return f"sum(increase({usage.metric}_sum{selector}[{window}]))"
    if usage.aggregation is Aggregation.COUNTER_INCREASE:
        return f"sum(increase({usage.metric}{selector}[{window}]))"
    return f"sum(avg_over_time({usage.metric}{selector}[{window}])) * {PERIOD_HOURS[period]}"


def component_query(resolved: ResolvedComponent, period: Period) -> str:
    """The query the console sends for one component and one window."""
    usage = resolved.component.usage
    if usage is None:
        raise ValueError(f"{resolved.component.component} has no usage series to query")
    term = usage_term(usage, period)
    if resolved.attribution is Attribution.DIRECT:
        # direct series are histograms or counters labelled by profile
        return term.replace("sum(", "sum by (profile) (", 1)
    return term


def sessions_query(period: Period) -> str:
    return f"sum by (profile) (increase({SESSIONS_METRIC}[{PERIOD_WINDOW[period]}]))"


def run_query(runner: QueryRunner, promql: str) -> list[tuple[dict[str, str], float]]:
    """Send one query and return its samples, or raise :class:`QueryRefused`."""
    try:
        response = runner(promql)
    except Exception as exc:  # the source is outside this process: any failure is its own
        raise QueryRefused(f"the source did not answer ({type(exc).__name__})") from None
    if response.get("status") != "success":
        raise QueryRefused(f"the source answered status {response.get('status')!r}")
    data = response.get("data")
    if not isinstance(data, Mapping) or data.get("resultType") != "vector":
        raise QueryRefused("the answer is not an instant vector")
    result = data.get("result")
    if not isinstance(result, list):
        raise QueryRefused("the answer carries no result list")
    samples: list[tuple[dict[str, str], float]] = []
    for item in result:
        if not isinstance(item, Mapping):
            raise QueryRefused("a result entry is not an object")
        metric = item.get("metric")
        value = item.get("value")
        if not isinstance(metric, Mapping) or not isinstance(value, list) or len(value) != 2:
            raise QueryRefused("a result entry is not a labelled sample")
        try:
            number = float(value[1])
        except (TypeError, ValueError):
            raise QueryRefused("a sample value is not a number") from None
        if not math.isfinite(number) or number < 0:
            raise QueryRefused("a sample value is not a finite, non-negative quantity")
        samples.append(({str(k): str(v) for k, v in metric.items()}, number))
    return samples


def parse_by_profile(samples: list[tuple[dict[str, str], float]]) -> dict[Profile, float]:
    """Samples of a ``sum by (profile)`` query, keyed by the closed profile set."""
    known = {p.value: p for p in Profile}
    out: dict[Profile, float] = {}
    for labels, number in samples:
        if set(labels) != {"profile"}:
            raise QueryRefused(
                f"a sample carries label(s) {sorted(labels)} where only profile was grouped"
            )
        profile = known.get(labels["profile"])
        if profile is None:
            raise QueryRefused("a sample names a profile outside the closed set")
        if profile in out:
            raise QueryRefused("a profile appears twice in one answer")
        out[profile] = number
    return out


def parse_scalar(samples: list[tuple[dict[str, str], float]]) -> float | None:
    """The one sample of a ``sum(...)`` query; ``None`` when there is none."""
    if not samples:
        return None
    if len(samples) != 1 or samples[0][0]:
        raise QueryRefused("a summed query answered with labelled or repeated samples")
    return samples[0][1]
