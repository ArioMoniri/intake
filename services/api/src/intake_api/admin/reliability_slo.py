"""SLO tiles for the reliability console (INT-181; files/08 §3 Overview, Reliability).

One tile per SLO declared in ``docs/slo/<service>.yaml`` — the files are the
only source of objectives, windows and burn-rate lanes, so the console cannot
hold a second copy of the policy that could disagree with the alerts.

**What a tile shows** (Google SRE workbook, *Alerting on SLOs*, multiwindow
multi-burn-rate — the shape files/10 §6 pins):

- the objective and the SLO window the file declares (28 d today);
- the SLI over that window, as attainment ``1 - error_ratio``;
- the error budget remaining, ``1 - error_ratio / budget`` — it goes negative
  when the budget is overspent and is never clamped;
- per declared lane (fast 14.4x on 1 h + 5 m, slow 6x on 6 h + 30 m, ticket
  1x on 3 d + 6 h), the burn rate on each window (``error_ratio / budget``)
  and whether the alert condition holds — both windows above the factor,
  exactly the expression :func:`intake_platform.slo.prometheus_rule_groups`
  emits.

**The query is the file's SLI, re-ranged — plus one correction.** Every SLI is
an error ratio written over ``[5m]`` (the schema enforces it). The recording
rules re-range it per window; the console does the same, and additionally
turns each ``sum(rate(<series>[w]))`` term into ``(... or vector(0))``. A
healthy service that has never answered a 5xx has no error series at all, so
the bare ratio is EMPTY and the tile would read *unknown* forever; with the
fallback it reads 0 errors — but only beside traffic, because with no traffic
at all the ratio is 0/0, NaN, which the client drops (*no observation*, never
a perfect SLI). An SLI written in any other shape is refused
(:class:`SliOutsideGrammar`) and its tile says so rather than guessing.

**Unknown is a state (invariant 17).** A tile whose queries cannot be answered
carries its reason and no figure; its objective and lanes stay, because they
are declarations, not measurements.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Final

from intake_platform.slo import BASE_RANGE, SLO, SLOFile, error_budget, window_seconds

from intake_api.admin.ops_prom import PromSession, TileUnknown

__all__ = [
    "SliOutsideGrammar",
    "empty_slo_tile",
    "rerange",
    "slo_label_sets",
    "slo_queries",
    "slo_query_id",
    "slo_tile",
    "slo_windows",
]

#: ``sum(rate(<series>{<selector>}[5m]))`` — the one term shape our SLIs use.
_TERM: Final = re.compile(r"sum\(rate\(([a-z_][a-z0-9_]*(?:\{[^{}]*\})?)\[5m\]\)\)")
#: Float noise tolerated either side of [0, 1] before a ratio is refused.
_EPSILON: Final = 1e-9
_DIGITS: Final = 6


class SliOutsideGrammar(ValueError):
    """The SLI is not built from ``sum(rate(<series>[5m]))`` terms."""


def rerange(sli: str, window: str) -> str:
    """The SLI over ``window``, each sum term falling back to 0 when absent."""
    window_seconds(window)
    normal = " ".join(sli.split())
    terms = len(_TERM.findall(normal))
    if terms == 0 or normal.count(BASE_RANGE) != terms:
        raise SliOutsideGrammar(f"not a ratio of sum(rate(<series>[5m])) terms: {normal!r}")
    return _TERM.sub(lambda m: f"(sum(rate({m.group(1)}[{window}])) or vector(0))", normal)


def slo_windows(slo: SLO) -> tuple[str, ...]:
    """Every window the file declares for this SLO, shortest first."""
    windows = {slo.window}
    for _, alert in slo.burn_rate_alerts.named_alerts():
        windows.update((alert.long_window, alert.short_window))
    return tuple(sorted(windows, key=window_seconds))


def slo_query_id(service: str, name: str, window: str) -> str:
    return f"slo:{service}:{name}:{window}"


def slo_queries(files: Iterable[SLOFile]) -> dict[str, str]:
    """Every SLO query the console runs; an SLI outside the grammar has none."""
    queries: dict[str, str] = {}
    for slo_file in files:
        for slo in slo_file.slos:
            try:
                ranged = {window: rerange(slo.sli, window) for window in slo_windows(slo)}
            except SliOutsideGrammar:
                continue
            for window, expr in ranged.items():
                queries[slo_query_id(slo_file.service, slo.name, window)] = expr
    return queries


def slo_label_sets(queries: Mapping[str, str]) -> dict[str, frozenset[str]]:
    """Every SLO answer is one unlabelled sample; a label is a re-sliced cohort."""
    return {query_id: frozenset() for query_id in queries}


def _lanes(slo: SLO) -> list[dict[str, Any]]:
    return [
        {
            "lane": kind,
            "severity": alert.severity,
            "factor": alert.factor,
            "long_window": alert.long_window,
            "short_window": alert.short_window,
            "long_burn": None,
            "short_burn": None,
            "condition_met": None,
        }
        for kind, alert in slo.burn_rate_alerts.named_alerts()
    ]


def empty_slo_tile(slo_file: SLOFile, slo: SLO, reason: str) -> dict[str, Any]:
    """The tile's unknown shape: the declaration, every measured figure ``None``."""
    return {
        "service": slo_file.service,
        "slo": slo.name,
        "state": "unknown",
        "reason": reason,
        "objective_percent": slo.objective,
        "slo_window": slo.window,
        "sli_percent": None,
        "error_budget_remaining": None,
        "burn_rates": _lanes(slo),
    }


def _ratio(session: PromSession, query_id: str) -> float | None:
    value = session.scalar(query_id)
    if value is None:
        return None
    if value < -_EPSILON or value > 1 + _EPSILON:
        raise TileUnknown("sli_out_of_range")
    return min(max(value, 0.0), 1.0)


def _burn(ratio: float | None, budget: float) -> float | None:
    return None if ratio is None else round(ratio / budget, _DIGITS)


def slo_tile(session: PromSession, slo_file: SLOFile, slo: SLO) -> dict[str, Any]:
    """One SLO's tile; raises :class:`TileUnknown` when its source cannot answer."""
    try:
        windows = {w: rerange(slo.sli, w) for w in slo_windows(slo)}
    except SliOutsideGrammar:
        raise TileUnknown("sli_outside_console_grammar") from None
    ratios = {w: _ratio(session, slo_query_id(slo_file.service, slo.name, w)) for w in windows}
    if all(value is None for value in ratios.values()):
        raise TileUnknown("no_series")
    budget = error_budget(slo.objective)
    overall = ratios[slo.window]
    lanes = _lanes(slo)
    for lane in lanes:
        long_burn = _burn(ratios[lane["long_window"]], budget)
        short_burn = _burn(ratios[lane["short_window"]], budget)
        lane["long_burn"] = long_burn
        lane["short_burn"] = short_burn
        if long_burn is not None and short_burn is not None:
            lane["condition_met"] = long_burn > lane["factor"] and short_burn > lane["factor"]
    return {
        **empty_slo_tile(slo_file, slo, "no_series"),
        "state": "ok",
        "reason": None,
        "sli_percent": None if overall is None else round((1.0 - overall) * 100.0, _DIGITS),
        "error_budget_remaining": None
        if overall is None
        else round(1.0 - overall / budget, _DIGITS),
        "burn_rates": lanes,
    }
