"""The probes service's own monitoring contract (CLAUDE.md invariant 15).

Every service — this one included — mounts /healthz, /readyz, /metrics and
/version through :func:`intake_platform.health.mount_health`, and emits OTel
and JSON logs through the shared :func:`intake_platform.otel.setup_otel`.
Readiness here is what this service cannot work without: a registry file
that parses and validates, and — where it sweeps a host — that host's
inventory.

INT-351: the same service hosts the **ops collector**
(:mod:`intake_probes.ops_collector`) when its environment configures one — a
background loop that turns GPU-host, CI and clip-build facts into catalogued
series on this service's ``/metrics``. Unconfigured, no loop starts and the
families are served empty (help and type lines only), which the admin console
reads as *unknown*.

INT-560: it also hosts the **host sweep** (:mod:`intake_probes.host_sweep`)
when ``INTAKE_HOST_INVENTORY_PATH`` and ``INTAKE_PROBE_RESULTS_PATH`` are both
set — on the synthetic AWS host, compose service ``probes``. Every 60 s it
probes what the inventory says the host runs and replaces the results file
the API's registry page reads. An inventory that does not load starts no
sweep: ``/readyz`` names it and the page reads *no result*, never a guess.
The process stays alive either way, so a probes fault never fails a deploy.

INT-021 close-out: docs/slo/probes.yaml is written against
``http_requests_total{service="probes"}``, and until the close-out nothing here
emitted it — an objective nobody could breach. The shared request middleware
is mounted like every other service's.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from os import environ
from pathlib import Path

from fastapi import FastAPI
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.otel import JsonLogFormatter, setup_otel
from prometheus_client import REGISTRY

from intake_probes.host_sweep import HostProbeConfig, build_host_clients, run_host_sweeps
from intake_probes.inventory import ENV_HOST_INVENTORY, InventoryError, load_host_inventory
from intake_probes.ops_collector import interval_from_env, ops_collector_from_env, run_collector
from intake_probes.registry import load_registry

__all__ = [
    "HostSweepSetting",
    "create_app",
    "host_probe_config",
    "host_sweep_from_env",
    "registry_path_from_env",
]

logger = logging.getLogger("intake_probes")

#: Where the host sweep writes; the same variable the API's console reads.
ENV_PROBE_RESULTS = "INTAKE_PROBE_RESULTS_PATH"

_otel_installed = False


def registry_path_from_env() -> Path:
    return Path(environ.get("INTAKE_REGISTRY_PATH", "observability/registry.yaml"))


@dataclass(frozen=True)
class HostSweepSetting:
    """The two paths the host sweep needs; both or neither."""

    inventory: Path
    out: Path


def host_sweep_from_env(env: Mapping[str, str]) -> HostSweepSetting | None:
    """The sweep the environment asks for, or ``None`` when it asks for none."""
    inventory = env.get(ENV_HOST_INVENTORY, "").strip()
    out = env.get(ENV_PROBE_RESULTS, "").strip()
    if not (inventory and out):
        return None
    return HostSweepSetting(Path(inventory), Path(out))


def host_probe_config(env: Mapping[str, str]) -> HostProbeConfig:
    """The real dialling clients for the host sweep (tests substitute this)."""
    return HostProbeConfig(env=dict(env))


def _setup_observability() -> None:
    """Shared OTel setup + JSON logging, once per process (invariant 15)."""
    global _otel_installed
    if _otel_installed:
        return
    setup_otel("probes")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    _otel_installed = True


@contextlib.asynccontextmanager
async def _ops_collector() -> AsyncIterator[None]:
    collector = ops_collector_from_env(environ)
    if not collector.configured:
        yield
        return
    collector.register_clip_textfile(REGISTRY)
    stop = asyncio.Event()
    task = asyncio.create_task(run_collector(collector, interval_from_env(environ), stop))
    try:
        yield
    finally:
        stop.set()
        await task


@contextlib.asynccontextmanager
async def _host_sweep() -> AsyncIterator[None]:
    setting = host_sweep_from_env(environ)
    if setting is None:
        yield
        return
    try:
        registry = load_registry(registry_path_from_env())
        inventory = load_host_inventory(setting.inventory, registry=registry, env=environ)
    except InventoryError as refused:
        logger.warning("host sweep not started: %s", refused.code)
        yield
        return
    except (OSError, ValueError) as exc:
        logger.warning("host sweep not started: registry unreadable (%s)", type(exc).__name__)
        yield
        return
    clients = build_host_clients(registry, inventory, host_probe_config(environ))
    stop = asyncio.Event()
    task = asyncio.create_task(run_host_sweeps(registry, clients, setting.out, stop))
    try:
        yield
    finally:
        stop.set()
        await task


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with _ops_collector(), _host_sweep():
        yield


def create_app() -> FastAPI:
    _setup_observability()
    app = FastAPI(title="intake-probes", lifespan=_lifespan)
    mount_http_metrics(app, "probes")

    async def registry_parses() -> bool:
        load_registry(registry_path_from_env())
        return True

    checks = [ReadinessCheck("registry", registry_parses)]
    setting = host_sweep_from_env(environ)
    if setting is not None:
        inventory_path = setting.inventory

        async def host_inventory_loads() -> bool:
            registry = load_registry(registry_path_from_env())
            load_host_inventory(inventory_path, registry=registry, env=environ)
            return True

        checks.append(ReadinessCheck("host_inventory", host_inventory_loads))
    mount_health(app, readiness=checks)
    return app
