"""The Model lanes module's composite (INT-428, ADR-035; files/08 §3).

``GET /admin/model-lanes`` — one read of everything the switch needs:

- **the deployment** — its declared, bound and effective data class, and
  whether its image carries hosted lanes at all (only the synthetic one does);
- **the control** and, per lane and per configured role, what is **serving
  right now** — provider, model (id, version, pin), the decision's reason,
  whether that exact version is qualified, and whether a run on it could
  count as clinical evidence (only a qualified self-hosted model on a real-PHI
  deployment can);
- **every selectable model per lane** — attested registry rows with their
  identity probe, and (synthetic only) each provider's dated snapshots with
  the provider's own identity probe — plus each provider's key state (set /
  not set and the last four characters; nothing more of a key ever leaves the
  server) and readiness;
- **latency and cost** from Prometheus over the catalogued ``model_lane_*``
  series (:data:`MODEL_LANES_QUERIES` — a caller cannot add PromQL), priced
  with the owner-filled unit prices in ``infra/costs/unit-prices.yaml``. A
  price nobody supplied reads ``price_not_configured``, never zero;
- **pending ceremonies** awaiting their second key.

**Unknown is a state (invariant 17).** No store wired, the store unreadable,
Prometheus unset or failing: each blanks its own part with a reason code and
nothing else. Ids only throughout (invariant 6).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from intake_platform.admin.four_eyes import PendingAction
from intake_platform.cost.config import CostConfig, load_cost_config
from intake_platform.model_lanes import (
    LANES,
    Lane,
    LaneRouter,
    LaneSetting,
    ModelLanesControl,
    ModelLanesUnavailable,
    ModelRef,
    ModelRole,
    RouteKind,
    parse_role,
)
from intake_platform.model_lanes.wiring import ModelLanesWiring

from intake_api.admin import views
from intake_api.admin.ops_prom import PromClient, PromSession, TileUnknown

__all__ = [
    "COST_CONFIG_DEFAULT",
    "MODEL_LANES_QUERIES",
    "MODEL_LANES_SCHEMA",
    "load_model_lanes_console",
]

MODEL_LANES_SCHEMA: Final = "intake.admin.model_lanes.v1"
COST_CONFIG_DEFAULT: Final = Path("infra/costs/unit-prices.yaml")
LATENCY_WINDOW: Final = "1h"
USAGE_WINDOW: Final = "24h"

_ROUTE_LABELS: Final = frozenset({"lane", "route", "provider"})

#: The only PromQL this module runs. Every series is catalogued.
MODEL_LANES_QUERIES: Final[Mapping[str, str]] = {
    "p50_ms": (
        "1000 * histogram_quantile(0.5, sum by (lane, route, provider, le) "
        f"(rate(model_lane_latency_seconds_bucket[{LATENCY_WINDOW}])))"
    ),
    "p95_ms": (
        "1000 * histogram_quantile(0.95, sum by (lane, route, provider, le) "
        f"(rate(model_lane_latency_seconds_bucket[{LATENCY_WINDOW}])))"
    ),
    "calls": (
        "sum by (lane, route, provider) "
        f'(increase(model_lane_calls_total{{outcome="ok"}}[{USAGE_WINDOW}]))'
    ),
    "tokens": (
        "sum by (lane, route, provider, direction) "
        f"(increase(model_lane_tokens_total[{USAGE_WINDOW}]))"
    ),
    "audio_seconds": (
        f"sum by (lane, route, provider) (increase(model_lane_audio_seconds_total[{USAGE_WINDOW}]))"
    ),
    "characters": (
        f"sum by (lane, route, provider) (increase(model_lane_characters_total[{USAGE_WINDOW}]))"
    ),
}
_QUERY_LABELS: Final[Mapping[str, frozenset[str]]] = {
    "p50_ms": _ROUTE_LABELS,
    "p95_ms": _ROUTE_LABELS,
    "calls": _ROUTE_LABELS,
    "tokens": _ROUTE_LABELS | {"direction"},
    "audio_seconds": _ROUTE_LABELS,
    "characters": _ROUTE_LABELS,
}
#: query id -> the catalogued series a unit price reads it from.
_USAGE_METRIC: Final[Mapping[str, str]] = {
    "tokens": "model_lane_tokens_total",
    "audio_seconds": "model_lane_audio_seconds_total",
    "characters": "model_lane_characters_total",
}

Key = tuple[str, str, str]  # (lane, route, provider)


def _control_view(control: ModelLanesControl | None, reason: str | None) -> dict[str, Any]:
    if control is None:
        return {"state": "unknown", "reason": reason}
    return {
        "state": "known",
        "reason": None,
        "revision": control.revision,
        "hosted_disabled": control.hosted_disabled,
        "changed_at": control.changed_at.isoformat() if control.changed_at else None,
        "changed_by": control.changed_by,
        "approved_by": control.approved_by,
        "last_change": control.last_change.value if control.last_change else None,
    }


def _usage(prom: PromClient | None) -> tuple[dict[str, dict[Key, list[Any]]], str | None]:
    """Every query's samples keyed by (lane, route, provider), or a reason."""
    if prom is None:
        return {}, "prometheus_unconfigured"
    session = PromSession(prom, MODEL_LANES_QUERIES, _QUERY_LABELS)
    out: dict[str, dict[Key, list[Any]]] = {}
    for query_id in MODEL_LANES_QUERIES:
        try:
            samples = session.fetch(query_id)
        except TileUnknown as unknown:
            return {}, unknown.reason
        by_key: dict[Key, list[Any]] = {}
        for sample in samples:
            key = (sample.labels["lane"], sample.labels["route"], sample.labels["provider"])
            by_key.setdefault(key, []).append(sample)
        out[query_id] = by_key
    return out, None


def _price(cost: CostConfig | None, metric: str, selector: Mapping[str, str]) -> float | None:
    if cost is None:
        return None
    for component in cost.components:
        usage = component.usage
        if usage is None or usage.metric != metric:
            continue
        if all(selector.get(name) == value for name, value in usage.selector.items()):
            return component.price.usd_per_unit
    return None


def _cost_row(
    key: Key, usage: Mapping[str, Mapping[Key, list[Any]]], cost: CostConfig | None
) -> dict[str, Any]:
    lane, route, provider = key
    if route != RouteKind.HOSTED.value:
        # a GPU host is billed by the hour, not per call: the Cost module
        # allocates it; a per-call figure here would be invented
        return {"state": "not_metered", "usd": None}
    total = 0.0
    seen = False
    for query_id, metric in _USAGE_METRIC.items():
        for sample in usage.get(query_id, {}).get(key, []):
            if sample.value is None or sample.value == 0:
                continue
            seen = True
            selector = {"lane": lane, "provider": provider, **dict(sample.labels)}
            price = _price(cost, metric, selector)
            if price is None:
                return {"state": "price_not_configured", "usd": None}
            total += sample.value * price
    return {"state": "known", "usd": round(total, 6)} if seen else {"state": "known", "usd": 0.0}


def _lane_usage(
    lane: Lane, usage: Mapping[str, Mapping[Key, list[Any]]], cost: CostConfig | None
) -> list[dict[str, Any]]:
    keys = sorted({k for by_key in usage.values() for k in by_key if k[0] == lane.value})
    rows = []
    for key in keys:

        def first(query_id: str, key: Key = key) -> float | None:
            samples = usage.get(query_id, {}).get(key, [])
            value = samples[0].value if samples else None
            return round(value, 3) if isinstance(value, float) else value

        rows.append(
            {
                "route": key[1],
                "provider": key[2],
                "p50_ms": first("p50_ms"),
                "p95_ms": first("p95_ms"),
                "calls": first("calls"),
                "cost": _cost_row(key, usage, cost),
            }
        )
    return rows


def _ref_view(ref: ModelRef | None) -> dict[str, Any] | None:
    if ref is None:
        return None
    return {
        "source": ref.source,
        "provider": ref.provider,
        "model_id": ref.model_id,
        "version": ref.version,
        "wire": ref.wire,
        "sha256": ref.sha256,
        "component": ref.component,
        "key": ref.key,
    }


def _setting_view(setting: LaneSetting | None) -> dict[str, Any] | None:
    if setting is None:
        return None
    return {
        "route": setting.route,
        "model": setting.model,
        "fallback": setting.fallback.value if setting.fallback else None,
        "fallback_model": setting.fallback_model,
    }


def _role_view(
    role: ModelRole, router: LaneRouter, control: ModelLanesControl | None, own: bool
) -> dict[str, Any]:
    assignment = router.assign(role, tenant_id=None)
    setting = control.setting_for(role) if control is not None else None
    data_class = router.data_class(control)
    expected = (
        router.expected_self_hosted(role, setting, data_class) if setting is not None else None
    )
    return {
        "role": role.id,
        "lane": role.lane.value,
        "inherits": not own,
        "setting": _setting_view(setting),
        "serving": {
            "available": assignment.available,
            "reason": assignment.reason,
            "provider": assignment.provider,
            "route": assignment.route.wire if assignment.route else None,
            "fallback": assignment.fallback,
            "model": _ref_view(assignment.model),
            "qualified": assignment.qualified,
            "clinical_evidence": assignment.clinical_evidence,
        },
        "self_hosted": {
            "identity": router.health.state(role.lane, expected),
            "expected": _ref_view(expected),
        },
    }


def _model_options(router: LaneRouter, probe_hosted: bool) -> dict[str, Any]:
    """Every selectable model per lane, with its identity probe and
    qualification. In a PHI deployment the hosted lists are empty and only
    rows attested ``jurisdiction: TR`` + ``phi_path`` are selectable."""
    data_class = router.data_class()
    out: dict[str, Any] = {}
    for lane in LANES:
        self_hosted = []
        for option in router.models.self_hosted_options(lane):
            ref = option.ref()
            attested = option.attested_for(data_class)
            self_hosted.append(
                {
                    "component": option.component,
                    "pinned": option.pinned,
                    "attested": attested,
                    "jurisdiction": option.jurisdiction,
                    "model": _ref_view(ref),
                    "identity": router.health.state(lane, ref if attested else None),
                    "qualified": router.qualifications.qualified(lane, ref),
                }
            )
        hosted = []
        for provider in router.hosted.providers:
            block = router.provider_block(provider)
            backend = router.hosted.backends.get(provider)
            defaults = router.models.hosted_defaults.get(provider, {})
            for model in router.models.hosted_options(provider, lane):
                ref = model.ref(provider)
                probe: dict[str, str | None]
                if not probe_hosted or block is not None or backend is None:
                    probe = {"state": "skipped", "reason": block or "probe_not_requested"}
                else:
                    healthy = backend.probe(model.wire)
                    probe = {"state": "healthy" if healthy else "unhealthy", "reason": None}
                hosted.append(
                    {
                        "provider": provider.value,
                        "model": _ref_view(ref),
                        "default": defaults.get(lane) == model.id,
                        "probe": probe,
                        "qualified": router.qualifications.qualified(lane, ref),
                    }
                )
        out[lane.value] = {
            "gated": router.qualifications.gated(lane),
            "self_hosted": self_hosted,
            "hosted": hosted,
        }
    return out


def _providers_view(router: LaneRouter) -> list[dict[str, Any]]:
    rows = []
    for provider, info in router.hosted.providers.items():
        key = router.keys.status(provider) if router.keys is not None else None
        block = router.provider_block(provider)
        rows.append(
            {
                "provider": provider.value,
                "egress_row": info.egress_row,
                "listed": info.listed,
                "self_hostable": False,
                "phi_path": False,
                "key": {
                    "state": key.state if key is not None else "unconfigured",
                    "last4": key.last4 if key is not None else None,
                    "set_at": key.set_at if key is not None else None,
                },
                "ready": {"state": "ready" if block is None else "blocked", "reason": block},
            }
        )
    return rows


def load_model_lanes_console(
    now: datetime,
    *,
    wiring: ModelLanesWiring | None,
    pending: tuple[PendingAction, ...],
    prom: PromClient | None,
    cost_loader: Callable[[], CostConfig | None] | None = None,
    probe_hosted: bool = True,
) -> dict[str, Any]:
    base: dict[str, Any] = {"schema": MODEL_LANES_SCHEMA, "generated_at": now.isoformat()}
    if wiring is None:
        return {
            **base,
            "state": "unknown",
            "reason": "model_lanes_unconfigured",
            "deployment": None,
            "control": _control_view(None, "model_lanes_unconfigured"),
            "lanes": [],
            "roles": [],
            "models": {},
            "providers": [],
            "usage_window": USAGE_WINDOW,
            "usage_reason": "model_lanes_unconfigured",
            "pending": [],
        }
    router = wiring.router
    try:
        control: ModelLanesControl | None = wiring.store.read()
        control_reason = None
    except ModelLanesUnavailable as failure:
        control, control_reason = None, failure.code
    usage, usage_reason = _usage(prom)
    cost = cost_loader() if cost_loader is not None else _load_cost()
    lanes = []
    for lane in LANES:
        row = _role_view(ModelRole.of(lane), router, control, own=True)
        row["usage"] = _lane_usage(lane, usage, cost)
        lanes.append(row)
    roles = [
        _role_view(parse_role(role_id), router, control, own=True)
        for role_id in sorted(control.roles if control is not None else {})
    ]
    effective = router.data_class(control)
    return {
        **base,
        "state": "known" if control is not None else "unknown",
        "reason": control_reason,
        "deployment": {
            "declared": router.declared.value,
            "bound": control.data_class.value if control and control.data_class else None,
            "effective": effective.value,
            "hosted_lanes": bool(router.hosted.providers),
            "data_class_mismatch": bool(
                control and control.data_class and control.data_class is not router.declared
            ),
        },
        "control": _control_view(control, control_reason),
        "lanes": lanes,
        "roles": roles,
        "models": _model_options(router, probe_hosted),
        "providers": _providers_view(router),
        "usage_window": USAGE_WINDOW,
        "usage_reason": usage_reason,
        "pending": [views.pending_view(p) for p in pending],
    }


def _load_cost() -> CostConfig | None:
    try:
        return load_cost_config(COST_CONFIG_DEFAULT)
    except (OSError, ValueError):
        return None
