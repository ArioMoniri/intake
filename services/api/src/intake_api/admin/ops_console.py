"""The ops console composite behind ``GET /admin/ops`` (INT-351; files/08 §3 Ops).

One JSON document, ``intake.admin.ops.v1``, that ``apps/admin-web`` renders as
tiles. It is built from exactly two sources, both server-side:

- **the self-hosting registry** — the models tile is the INT-183 projection
  (:func:`intake_api.admin.models_source.load_models_module`), every row in
  registry order, narrowed to what an operator reads at a glance:
  ``self_hostable``, ``self_hosted_now``, the pin, ``probe`` and its last
  sweep result, ``licence_verified_at``. Invariant 13: the console reads the
  registry, it does not keep one.
- **this host's inventory and the probe runner's last sweep** (INT-560) —
  :func:`intake_probes.standing.standings` derives, per row, whether this
  host runs it (``deployment``), whether its stack needs it, its last probe
  result with that result's age, and a severity that is ``blocking`` only for
  what this host needs whose probe is not currently healthy. A deployment
  with no inventory (``INTAKE_HOST_INVENTORY_PATH``) keeps the registry-wide
  reading and says it has none.
- **Prometheus** — every other tile, through the fixed query table
  :data:`OPS_QUERIES`. Each query names only series catalogued in
  ``observability/metrics_catalog.yaml`` (a test holds that), so a tile cannot
  read a number nobody governs. The GPU and CI series come from the ops
  collector (``intake_probes.ops_collector``); model usage from the Backend
  Work, TTS and adapter families; the clip cache from the clip build's
  families; the wait from ``wait.checkin_to_seen_min`` (INT-163); satisfaction
  from ``csat.score`` and ``nps.monthly`` (INT-240/INT-186).

**Unknown is a state (invariant 17).** A tile whose source is unconfigured,
unreachable, erroring or silent is ``{"state": "unknown", "reason": <code>}``
with every figure ``null`` and every list empty — the page renders the word,
never a zero. One failing query blanks its own tile and no other.

**Ids only (invariant 6).** A series whose label set is not the one the query
asked for, or whose label value is not id-shaped, turns its tile unknown
(``unexpected_label`` / ``label_not_id_shaped``) rather than painting it.

**The floor and the claim (files/06 §8; invariant 20).** A CSAT or wait cohort
below k = 10 carries its count and nothing else, every figure names its window,
and no catalogue target is copied beside a figure.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from intake_platform.analytics import K_ANONYMITY_FLOOR
from intake_probes.console import ModelsModule
from intake_probes.gate import ProbeResultRecord
from intake_probes.inventory import HostReading, read_host_inventory
from intake_probes.standing import standings

from intake_api.admin.models_source import (
    PROBE_RESULTS_UNREADABLE,
    load_models_module,
    load_probe_sweep,
)
from intake_api.admin.ops_prom import (
    PromClient,
    PromSession,
    Sample,
    TileUnknown,
    prom_client_from_env,
)

__all__ = ["K_FLOOR", "OPS_QUERIES", "OPS_SCHEMA", "build_ops_console", "load_ops_console"]

OPS_SCHEMA: Final = "intake.admin.ops.v1"
K_FLOOR: Final = K_ANONYMITY_FLOOR
USAGE_WINDOW: Final = "24h"
COHORT_WINDOW: Final = "30d"
CLIP_WINDOW: Final = "last_build"

#: The only PromQL this API runs for the console. A caller cannot add to it.
OPS_QUERIES: Final[Mapping[str, str]] = {
    "gpu_host_up": "max by (host_id) (ops_gpu_host_up)",
    "gpu_utilization": "max by (host_id, gpu_index) (ops_gpu_utilization_ratio)",
    "gpu_memory_used": "max by (host_id, gpu_index) (ops_gpu_memory_used_bytes)",
    "gpu_memory_total": "max by (host_id, gpu_index) (ops_gpu_memory_total_bytes)",
    "work_requests": f"sum by (type) (increase(work_latency_ms_count[{USAGE_WINDOW}]))",
    "work_p95": (
        "histogram_quantile(0.95, sum by (le, type) "
        f"(rate(work_latency_ms_bucket[{USAGE_WINDOW}])))"
    ),
    "work_failures": f"sum by (type) (increase(work_failed_total[{USAGE_WINDOW}]))",
    "tts_requests": f"sum by (vendor) (increase(voice_tts_chars_count[{USAGE_WINDOW}]))",
    "adapter_failures": (
        f"sum by (adapter) (increase(vendor_adapter_failures_total[{USAGE_WINDOW}]))"
    ),
    "clip_lookups": "sum by (outcome) (voice_clip_cache_lookups_total)",
    "clip_syntheses": "sum by (gateway, outcome) (voice_clip_syntheses_total)",
    "clip_manifest_rows": "max by (pack, locale, voice) (voice_clip_manifest_rows)",
    "clip_manifest_present": "max by (pack, locale, voice) (voice_clip_manifest_present)",
    "wait_count": f"sum(increase(wait_checkin_to_seen_min_count[{COHORT_WINDOW}]))",
    "wait_sum": f"sum(increase(wait_checkin_to_seen_min_sum[{COHORT_WINDOW}]))",
    "csat_count": f"sum(increase(csat_score_count[{COHORT_WINDOW}]))",
    "csat_sum": f"sum(increase(csat_score_sum[{COHORT_WINDOW}]))",
    "nps": "max(nps_monthly)",
    "ci_runs": ("max by (workflow, branch, status, conclusion, head_sha) (ops_ci_last_run)"),
    "ci_updated": "max by (workflow, branch) (ops_ci_last_run_updated_seconds)",
    "collector_up": "max by (source) (ops_collector_source_up)",
}

#: The label set each query must come back with — exactly.
_LABELS: Final[Mapping[str, frozenset[str]]] = {
    "gpu_host_up": frozenset({"host_id"}),
    "gpu_utilization": frozenset({"host_id", "gpu_index"}),
    "gpu_memory_used": frozenset({"host_id", "gpu_index"}),
    "gpu_memory_total": frozenset({"host_id", "gpu_index"}),
    "work_requests": frozenset({"type"}),
    "work_p95": frozenset({"type"}),
    "work_failures": frozenset({"type"}),
    "tts_requests": frozenset({"vendor"}),
    "adapter_failures": frozenset({"adapter"}),
    "clip_lookups": frozenset({"outcome"}),
    "clip_syntheses": frozenset({"gateway", "outcome"}),
    "clip_manifest_rows": frozenset({"pack", "locale", "voice"}),
    "clip_manifest_present": frozenset({"pack", "locale", "voice"}),
    "wait_count": frozenset(),
    "wait_sum": frozenset(),
    "csat_count": frozenset(),
    "csat_sum": frozenset(),
    "nps": frozenset(),
    "ci_runs": frozenset({"workflow", "branch", "status", "conclusion", "head_sha"}),
    "ci_updated": frozenset({"workflow", "branch"}),
    "collector_up": frozenset({"source"}),
}


def _session(prom: PromClient) -> PromSession:
    """One build's view of Prometheus over :data:`OPS_QUERIES` (shared with INT-181)."""
    return PromSession(prom, OPS_QUERIES, _LABELS)


def _count(value: float | None) -> int | None:
    return None if value is None else int(round(value))


def _by(samples: tuple[Sample, ...], *names: str) -> dict[tuple[str, ...], float]:
    return {tuple(s.labels[name] for name in names): s.value for s in samples}


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- tiles -------------------------------------------------------------------------


def _gpu(session: PromSession) -> dict[str, Any]:
    up = session.fetch("gpu_host_up")
    if not up:
        raise TileUnknown("no_series")
    util = _by(session.fetch("gpu_utilization"), "host_id", "gpu_index")
    used = _by(session.fetch("gpu_memory_used"), "host_id", "gpu_index")
    total = _by(session.fetch("gpu_memory_total"), "host_id", "gpu_index")
    hosts: list[dict[str, Any]] = []
    for sample in sorted(up, key=lambda s: s.labels["host_id"]):
        host = sample.labels["host_id"]
        is_up = sample.value >= 1
        indexes = sorted(
            {idx for (h, idx) in (*util, *used, *total) if h == host}, key=lambda i: (len(i), i)
        )
        gpus = [
            {
                "gpu_index": idx,
                "utilization_ratio": util.get((host, idx)),
                "memory_used_bytes": _count(used.get((host, idx))),
                "memory_total_bytes": _count(total.get((host, idx))),
            }
            for idx in indexes
        ]
        hosts.append({"host_id": host, "up": is_up, "gpus": gpus if is_up else []})
    return {"hosts": hosts}


def _usage(session: PromSession) -> dict[str, Any]:
    served = _by(session.fetch("work_requests"), "type")
    p95 = _by(session.fetch("work_p95"), "type")
    failures = _by(session.fetch("work_failures"), "type")
    tts = _by(session.fetch("tts_requests"), "vendor")
    adapters = _by(session.fetch("adapter_failures"), "adapter")
    lanes: list[dict[str, Any]] = []
    for (lane,) in sorted({*served, *p95, *failures}):
        lanes.append(
            {
                "kind": "work",
                "lane": lane,
                "requests": _count(served.get((lane,))),
                "p95_ms": p95.get((lane,)),
                "failures": _count(failures.get((lane,))),
            }
        )
    for (lane,), value in sorted(tts.items()):
        lanes.append(
            {
                "kind": "tts",
                "lane": lane,
                "requests": _count(value),
                "p95_ms": None,
                "failures": None,
            }
        )
    for (lane,), value in sorted(adapters.items()):
        lanes.append(
            {
                "kind": "adapter",
                "lane": lane,
                "requests": None,
                "p95_ms": None,
                "failures": _count(value),
            }
        )
    if not lanes:
        raise TileUnknown("no_series")
    return {"lanes": lanes}


def _clips(session: PromSession) -> dict[str, Any]:
    lookups = _by(session.fetch("clip_lookups"), "outcome")
    syntheses = session.fetch("clip_syntheses")
    rows = _by(session.fetch("clip_manifest_rows"), "pack", "locale", "voice")
    present = _by(session.fetch("clip_manifest_present"), "pack", "locale", "voice")
    if not lookups and not syntheses and not rows:
        raise TileUnknown("no_series")
    return {
        "manifests": [
            {
                "pack": pack,
                "locale": locale,
                "voice": voice,
                "rows": _count(value),
                "present": _count(present.get((pack, locale, voice))),
            }
            for (pack, locale, voice), value in sorted(rows.items())
        ],
        # a family that answered without a child for an outcome counted none
        "hit": _count(lookups.get(("hit",), 0.0)) if lookups else None,
        "miss": _count(lookups.get(("miss",), 0.0)) if lookups else None,
        "syntheses": [
            {
                "gateway": s.labels["gateway"],
                "outcome": s.labels["outcome"],
                "count": _count(s.value),
            }
            for s in sorted(syntheses, key=lambda s: (s.labels["gateway"], s.labels["outcome"]))
        ],
    }


def _cohort(count: float | None, total: float | None) -> tuple[int | None, bool, float | None]:
    """(n, suppressed, mean) for one cohort — the mean only at or above k."""
    n = _count(count)
    suppressed = n is None or n < K_FLOOR
    mean = None
    if not suppressed and count and total is not None:
        mean = round(total / count, 2)
    return n, suppressed, mean


def _wait(session: PromSession) -> dict[str, Any]:
    count = session.scalar("wait_count")
    if count is None:
        raise TileUnknown("no_series")
    n, suppressed, mean = _cohort(count, session.scalar("wait_sum"))
    return {"n": n, "suppressed": suppressed, "mean_min": mean}


def _satisfaction(session: PromSession) -> dict[str, Any]:
    count = session.scalar("csat_count")
    total = session.scalar("csat_sum")
    nps = session.scalar("nps")
    if count is None and nps is None:
        raise TileUnknown("no_series")
    n, suppressed, mean = _cohort(count, total)
    return {
        "csat_n": n,
        "csat_suppressed": suppressed,
        "csat_mean": mean,
        "nps": None if nps is None else round(nps, 2),
    }


def _cicd(session: PromSession) -> dict[str, Any]:
    sources = _by(session.fetch("collector_up"), "source")
    if sources.get(("ci",)) == 0:
        raise TileUnknown("collector_source_failing")
    runs = session.fetch("ci_runs")
    if not runs:
        raise TileUnknown("no_series")
    updated = _by(session.fetch("ci_updated"), "workflow", "branch")
    branches = {s.labels["branch"] for s in runs}
    if len(branches) != 1:
        raise TileUnknown("unexpected_label")
    workflows = [
        {
            "workflow": s.labels["workflow"],
            "status": s.labels["status"],
            "conclusion": s.labels["conclusion"],
            "head_sha": s.labels["head_sha"],
            "updated_at": _iso(updated.get((s.labels["workflow"], s.labels["branch"]))),
        }
        for s in sorted(runs, key=lambda s: s.labels["workflow"])
        if s.value >= 1
    ]
    return {"branch": branches.pop(), "workflows": workflows}


#: Every tile's shape when it is unknown: the same keys, no figure.
_EMPTY: Final[Mapping[str, Mapping[str, Any]]] = {
    "gpu": {"hosts": []},
    "model_usage": {"window": USAGE_WINDOW, "lanes": []},
    "clip_cache": {
        "window": CLIP_WINDOW,
        "hit": None,
        "miss": None,
        "syntheses": [],
        "manifests": [],
    },
    "wait_time": {
        "metric_id": "wait.checkin_to_seen_min",
        "window": COHORT_WINDOW,
        "k_floor": K_FLOOR,
        "n": None,
        "suppressed": None,
        "mean_min": None,
    },
    "satisfaction": {
        "csat_metric_id": "csat.score",
        "nps_metric_id": "nps.monthly",
        "window": COHORT_WINDOW,
        "k_floor": K_FLOOR,
        "csat_n": None,
        "csat_suppressed": None,
        "csat_mean": None,
        "nps": None,
    },
    "cicd": {"branch": None, "workflows": []},
}

_BUILDERS: Final[Mapping[str, Callable[[PromSession], dict[str, Any]]]] = {
    "gpu": _gpu,
    "model_usage": _usage,
    "clip_cache": _clips,
    "wait_time": _wait,
    "satisfaction": _satisfaction,
    "cicd": _cicd,
}


def _models_tile(
    models: ModelsModule | None,
    results: Mapping[str, ProbeResultRecord] | None,
    host: HostReading,
    now: datetime,
) -> dict[str, Any]:
    if models is None or results is None:
        # a tile built from two sources is unknown when either is unreadable:
        # a refused sweep painted as "no_result" would claim a sweep ran
        return {
            "state": "unknown",
            "reason": "registry_unreadable" if models is None else PROBE_RESULTS_UNREADABLE,
            "release_blocked": None,
            "host": None,
            "host_reason": None,
            "rows": [],
        }
    inventory = host.inventory
    standing = {s.component: s for s in standings(models, inventory, results, now)}
    rows = []
    for row in models.rows:
        here = standing[row.component]
        checked_at = here.probe.checked_at
        rows.append(
            {
                "component": row.component,
                "pin": row.pin,
                "self_hostable": row.self_hostable,
                "self_hosted_now": row.self_hosted_now,
                "phi_path": row.phi_path,
                "probe": row.probe,
                "deployment": here.deployment.value,
                "needed": here.needed,
                "not_needed_reason": here.not_needed_reason,
                "probe_status": here.probe.status,
                "probe_checked_at": _iso(None if checked_at is None else checked_at.timestamp()),
                "probe_age_s": here.probe.age_s,
                "probe_stale": here.probe.stale,
                "licence_verified_at": (
                    row.licence_verified_at.isoformat() if row.licence_verified_at else None
                ),
                "severity": here.severity.value,
                "severity_reason": here.reason.value,
            }
        )
    return {
        "state": "ok",
        "reason": None,
        "release_blocked": models.release.blocked,
        "host": (
            None
            if inventory is None
            else {"host_id": inventory.host_id, "data_class": inventory.data_class}
        ),
        "host_reason": host.reason,
        "rows": rows,
    }


#: The reading a caller that names no host gets: no inventory, said so.
_NO_HOST: Final = HostReading(None, "host_inventory_unconfigured")


def build_ops_console(
    *,
    prom: PromClient | None,
    models: ModelsModule | None,
    results: Mapping[str, ProbeResultRecord] | None,
    now: datetime,
    host: HostReading = _NO_HOST,
    prom_misconfigured: bool = False,
) -> dict[str, Any]:
    """The whole ``intake.admin.ops.v1`` document.

    ``results`` is ``None`` when the probe runner's file was present and
    refused (INT-377); an unset or absent file is an empty mapping. ``host``
    is this deployment's inventory, or the code for why there is none
    (INT-560).
    """
    tiles: dict[str, Any] = {"models": _models_tile(models, results, host, now)}
    session = _session(prom) if prom is not None else None
    for tile_id, builder in _BUILDERS.items():
        empty = dict(_EMPTY[tile_id])
        if session is None:
            reason = "prometheus_misconfigured" if prom_misconfigured else "prometheus_unconfigured"
            tiles[tile_id] = {"state": "unknown", "reason": reason, **empty}
            continue
        try:
            tiles[tile_id] = {"state": "ok", "reason": None, **empty, **builder(session)}
        except TileUnknown as unknown:
            tiles[tile_id] = {"state": "unknown", "reason": unknown.reason, **empty}
    if session is None:
        prometheus = "misconfigured" if prom_misconfigured else "unconfigured"
    else:
        prometheus = "unreachable" if session.unreachable else "ok"
    return {
        "schema": OPS_SCHEMA,
        "generated_at": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "prometheus": prometheus,
            "registry": "ok" if models is not None else "unreadable",
        },
        "tiles": tiles,
    }


def load_ops_console(now: datetime, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Wire the composite from the process environment and the committed registry.

    A malformed ``INTAKE_OPS_PROMETHEUS_URL`` is not a crash and not a guess:
    the Prometheus tiles read ``prometheus_misconfigured``. An unreadable
    registry turns the models tile unknown rather than taking the page down,
    and so does a probe-results file that is present and not a sweep (INT-377).
    An inventory that is unset, absent or refused leaves the tile known, with
    the registry-wide reading and ``host_reason`` saying why (INT-560).
    """
    env = os.environ if env is None else env
    try:
        prom, misconfigured = prom_client_from_env(env), False
    except ValueError:
        prom, misconfigured = None, True
    sweep = load_probe_sweep()
    try:
        models: ModelsModule | None = load_models_module(sweep)
    except (OSError, ValueError):
        models = None
    return build_ops_console(
        prom=prom,
        models=models,
        results=None if sweep.refused else sweep.records,
        now=now,
        host=read_host_inventory(env),
        prom_misconfigured=misconfigured,
    )
