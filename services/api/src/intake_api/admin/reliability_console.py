"""The reliability composite behind ``GET /admin/reliability`` (INT-181).

files/08 §3 gives the **Overview** module SLO tiles and the **Reliability**
module "SLO attainment & error budgets per service, burn-rate alerts,
dependency health graph, synthetic probe matrix". One JSON document,
``intake.admin.reliability.v1``, that ``apps/admin-web``'s ``/overview`` page
renders. Four sources, all server-side and all live — nothing here is a
fixture:

- **the SLO files** (``docs/slo/*.yaml``, ``INTAKE_SLO_DIR``) — which SLOs
  exist, their objectives, windows and lanes (:mod:`.reliability_slo`);
- **Prometheus** (``INTAKE_OPS_PROMETHEUS_URL``) — the SLIs re-ranged per
  window, the ops collector's ``ops_gpu_host_up`` (the INT-351 query, reused)
  and INT-100's ``vendor_breaker_state``. Every query names catalogued series
  only (invariant 13; a test holds it) and none takes a request field
  (files/08 §0b F1);
- **the self-hosting registry** — which synthetic probes exist and which
  components run now, with their fallback edges (invariant 13: the console
  reads the registry, it does not keep one);
- **the probe runner's last sweep** (``INTAKE_PROBE_RESULTS_PATH``, the file
  ``intake_probes.runner`` writes every :data:`SWEEP_INTERVAL_S`) — each
  probe's last result and the instant it was taken.

**Unknown is a state, never a zero or a stale value (invariant 17).** Each
tile — every SLO tile, the probe matrix, and each of the four dependency
sections — has its own source and fails closed on its own, with a machine
reason and no figure. A probe result older than :data:`STALE_AFTER_S` (three
sweeps) is flagged stale in the matrix and is *unknown* as a dependency's
health: the last value is shown as the last value, never as the current one.

**Ids only (invariant 6).** Label values must be id-shaped or the tile reads
``label_not_id_shaped``; the runner's free-text ``detail`` never leaves this
module.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import yaml
from intake_platform.slo import SLOFile, load_slo_file
from intake_probes.gate import ProbeResultRecord, load_results
from intake_probes.registry import FallbackKind, Registry, load_registry
from intake_probes.runner import STALE_AFTER_S as _STALE_AFTER_S
from intake_probes.runner import SWEEP_INTERVAL_S

from intake_api.admin.models_source import PROBE_RESULTS_ENV
from intake_api.admin.ops_console import OPS_QUERIES
from intake_api.admin.ops_prom import PromClient, PromSession, TileUnknown, prom_client_from_env
from intake_api.admin.reliability_slo import (
    empty_slo_tile,
    slo_label_sets,
    slo_queries,
    slo_tile,
)

__all__ = [
    "ENV_SLO_DIR",
    "RELIABILITY_SCHEMA",
    "STALE_AFTER_S",
    "Sweep",
    "build_reliability_console",
    "load_reliability_console",
    "load_slo_files",
    "load_sweep",
    "reliability_queries",
]

RELIABILITY_SCHEMA: Final = "intake.admin.reliability.v1"
ENV_SLO_DIR: Final = "INTAKE_SLO_DIR"
_ENV_REGISTRY: Final = "INTAKE_REGISTRY_PATH"
_DEFAULT_SLO_DIR: Final = "docs/slo"
_DEFAULT_REGISTRY: Final = "observability/registry.yaml"
#: Three missed sweeps: past this a result is the last one, not the current one.
#: One constant, shared with the ops console's registry tile (INT-560).
STALE_AFTER_S: Final = _STALE_AFTER_S

_GPU_QUERY: Final = "gpu_host_up"
_VENDOR_QUERY: Final = "vendor_breaker_state"
#: INT-100's closed breaker vocabulary, worst last.
_BREAKER_HEALTH: Final[Mapping[str, str]] = {
    "closed": "healthy",
    "half_open": "degraded",
    "open": "unhealthy",
}
_BREAKER_RANK: Final[Mapping[str, int]] = {"closed": 0, "half_open": 1, "open": 2}

_FIXED_QUERIES: Final[Mapping[str, str]] = {
    _GPU_QUERY: OPS_QUERIES["gpu_host_up"],
    _VENDOR_QUERY: "max by (component, state) (vendor_breaker_state)",
}
_FIXED_LABELS: Final[Mapping[str, frozenset[str]]] = {
    _GPU_QUERY: frozenset({"host_id"}),
    _VENDOR_QUERY: frozenset({"component", "state"}),
}


@dataclass(frozen=True)
class Sweep:
    """The probe runner's last sweep, or the reason there is none to read."""

    records: Mapping[str, ProbeResultRecord] | None
    reason: str | None = None


def load_sweep(env: Mapping[str, str]) -> Sweep:
    """Read the sweep ``INTAKE_PROBE_RESULTS_PATH`` names; never raise."""
    raw = env.get(PROBE_RESULTS_ENV, "").strip()
    if not raw:
        return Sweep(None, "probe_results_unconfigured")
    path = Path(raw)
    if not path.is_file():
        return Sweep(None, "probe_results_missing")
    try:
        return Sweep(load_results(path))
    except (OSError, ValueError):
        return Sweep(None, "probe_results_unreadable")


def load_slo_files(directory: Path) -> tuple[SLOFile, ...]:
    """Every ``*.yaml`` in the SLO directory, in file order. Raises if any fails."""
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        raise FileNotFoundError(f"no SLO files under {directory}")
    return tuple(load_slo_file(path) for path in paths)


def reliability_queries(files: Sequence[SLOFile]) -> dict[str, str]:
    """The only PromQL this composite runs: derived from the files, never a request."""
    return {**slo_queries(files), **_FIXED_QUERIES}


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- probe results: freshness ---------------------------------------------------------


def _age(record: ProbeResultRecord | None, now: datetime) -> int | None:
    """Seconds since the probe ran; ``None`` when that cannot be known."""
    if record is None or record.checked_at is None or record.checked_at.tzinfo is None:
        return None
    age = int((now - record.checked_at).total_seconds())
    return age if age >= 0 else None


def _health(record: ProbeResultRecord | None, now: datetime) -> tuple[str, str | None, str | None]:
    """(health, reason, checked_at) — a stale or absent result is unknown."""
    if record is None:
        return "unknown", "no_result", None
    age = _age(record, now)
    if age is None or age > STALE_AFTER_S or record.checked_at is None:
        return "unknown", "sweep_stale", None
    return record.status.value, None, _iso(record.checked_at)


# --- tiles ----------------------------------------------------------------------------


def _probe_matrix(
    registry: Registry, records: Mapping[str, ProbeResultRecord], now: datetime
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for entry in registry:
        record = records.get(entry.component)
        age = _age(record, now)
        rows.append(
            {
                "component": entry.component,
                "probe": entry.probe.value,
                "phi_path": entry.phi_path,
                "self_hosted_now": entry.self_hosted_now,
                "budget_ms": entry.budget_ms,
                "status": record.status.value if record is not None else "no_result",
                "latency_ms": record.latency_ms if record is not None else None,
                "checked_at": (
                    _iso(record.checked_at)
                    if record is not None and record.checked_at is not None
                    else None
                ),
                "age_s": age,
                "stale": age is None or age > STALE_AFTER_S,
            }
        )
    return {"rows": rows}


def _components(
    registry: Registry, records: Mapping[str, ProbeResultRecord], now: datetime
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for entry in registry:
        if not entry.self_hosted_now:
            continue
        health, reason, checked_at = _health(records.get(entry.component), now)
        kind = entry.fallback_kind
        fallback: str | None = None
        fallback_health: str | None = None
        if kind is FallbackKind.COMPONENT:
            fallback = entry.fallback_target
            fallback_health = _health(records.get(fallback), now)[0]
        elif kind is FallbackKind.IN_PROCESS:
            # the fallback ships inside the component's own artefact (INT-022)
            fallback_health = health
        rows.append(
            {
                "component": entry.component,
                "probe": entry.probe.value,
                "health": health,
                "health_reason": reason,
                "checked_at": checked_at,
                "fallback_kind": kind.value.replace("-", "_"),
                "fallback": fallback,
                "fallback_health": fallback_health,
            }
        )
    return {"rows": rows}


def _gpu_hosts(session: PromSession) -> dict[str, Any]:
    samples = session.fetch(_GPU_QUERY)
    if not samples:
        raise TileUnknown("no_series")
    return {
        "rows": [
            {"host_id": s.labels["host_id"], "health": "healthy" if s.value >= 1 else "unhealthy"}
            for s in sorted(samples, key=lambda s: s.labels["host_id"])
        ]
    }


def _vendors(session: PromSession) -> dict[str, Any]:
    samples = session.fetch(_VENDOR_QUERY)
    if not samples:
        raise TileUnknown("no_series")
    current: dict[str, str | None] = {}
    for sample in samples:
        state = sample.labels["state"]
        if state not in _BREAKER_RANK:
            raise TileUnknown("unexpected_label")
        component = sample.labels["component"]
        current.setdefault(component, None)
        held = current[component]
        # one-hot per instance; across replicas the worst instance wins
        if sample.value >= 1 and (held is None or _BREAKER_RANK[state] > _BREAKER_RANK[held]):
            current[component] = state
    return {
        "rows": [
            {
                "component": component,
                "breaker": state,
                "health": "unknown" if state is None else _BREAKER_HEALTH[state],
            }
            for component, state in sorted(current.items())
        ]
    }


def _section(state: str, reason: str | None, **body: Any) -> dict[str, Any]:
    return {"state": state, "reason": reason, **body}


def build_reliability_console(
    *,
    prom: PromClient | None,
    slo_files: Sequence[SLOFile] | None,
    registry: Registry | None,
    sweep: Sweep,
    now: datetime,
    prom_misconfigured: bool = False,
) -> dict[str, Any]:
    """The whole ``intake.admin.reliability.v1`` document."""
    files = tuple(slo_files or ())
    queries = reliability_queries(files)
    labels = {**slo_label_sets(slo_queries(files)), **_FIXED_LABELS}
    session = PromSession(prom, queries, labels) if prom is not None else None
    no_prom = "prometheus_misconfigured" if prom_misconfigured else "prometheus_unconfigured"

    # SLO tiles — one per declared SLO, in file order
    tiles: list[dict[str, Any]] = []
    for slo_file in files:
        for slo in slo_file.slos:
            if session is None:
                tiles.append(empty_slo_tile(slo_file, slo, no_prom))
                continue
            try:
                tiles.append(slo_tile(session, slo_file, slo))
            except TileUnknown as unknown:
                tiles.append(empty_slo_tile(slo_file, slo, unknown.reason))
    slos = (
        _section("ok", None, tiles=tiles)
        if slo_files is not None
        else _section("unknown", "slo_files_unreadable", tiles=[])
    )

    # the probe matrix and the component graph share one source: the sweep
    source_reason = "registry_unreadable" if registry is None else sweep.reason
    if registry is None or sweep.records is None:
        matrix = _section("unknown", source_reason, rows=[])
        components = _section("unknown", source_reason, rows=[])
    else:
        matrix = _section("ok", None, **_probe_matrix(registry, sweep.records, now))
        components = _section("ok", None, **_components(registry, sweep.records, now))

    # Prometheus-fed dependency sections
    fed: dict[str, dict[str, Any]] = {}
    for name, builder in (("gpu_hosts", _gpu_hosts), ("vendors", _vendors)):
        if session is None:
            fed[name] = _section("unknown", no_prom, rows=[])
            continue
        try:
            fed[name] = _section("ok", None, **builder(session))
        except TileUnknown as unknown:
            fed[name] = _section("unknown", unknown.reason, rows=[])

    # Prometheus itself, as the API sees it after every query above
    if session is None:
        prometheus = _section("unknown", no_prom, health=None, health_reason=None)
        prom_source = "misconfigured" if prom_misconfigured else "unconfigured"
    elif session.unreachable or session.answered == 0:
        failure = "prometheus_unreachable" if session.unreachable else session.failure
        prometheus = _section("ok", None, health="unhealthy", health_reason=failure)
        prom_source = "unreachable" if session.unreachable else "erroring"
    else:
        prometheus = _section("ok", None, health="healthy", health_reason=None)
        prom_source = "ok"

    return {
        "schema": RELIABILITY_SCHEMA,
        "generated_at": _iso(now),
        "sources": {
            "prometheus": prom_source,
            "slo_files": "ok" if slo_files is not None else "unreadable",
            "registry": "ok" if registry is not None else "unreadable",
            "probe_sweep": "ok" if sweep.records is not None else sweep.reason,
        },
        "slos": slos,
        "probe_matrix": {
            **matrix,
            "sweep_interval_s": SWEEP_INTERVAL_S,
            "stale_after_s": STALE_AFTER_S,
        },
        "dependencies": {
            "components": components,
            "prometheus": prometheus,
            "gpu_hosts": fed["gpu_hosts"],
            "vendors": fed["vendors"],
        },
    }


def load_reliability_console(now: datetime, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Wire the composite from the process environment.

    A malformed Prometheus URL is ``misconfigured`` rather than a crash or a
    guess; an unreadable SLO directory or registry blanks the tiles that read
    it and nothing else.
    """
    env = os.environ if env is None else env
    try:
        prom, misconfigured = prom_client_from_env(env), False
    except ValueError:
        prom, misconfigured = None, True
    try:
        files: tuple[SLOFile, ...] | None = load_slo_files(
            Path(env.get(ENV_SLO_DIR, "").strip() or _DEFAULT_SLO_DIR)
        )
    except (OSError, ValueError, yaml.YAMLError):
        files = None
    try:
        registry: Registry | None = load_registry(
            Path(env.get(_ENV_REGISTRY, "").strip() or _DEFAULT_REGISTRY)
        )
    except (OSError, ValueError, yaml.YAMLError):
        registry = None
    return build_reliability_console(
        prom=prom,
        slo_files=files,
        registry=registry,
        sweep=load_sweep(env),
        now=now,
        prom_misconfigured=misconfigured,
    )
