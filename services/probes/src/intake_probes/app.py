"""The probes service's own monitoring contract (CLAUDE.md invariant 15).

Every service — this one included — mounts /healthz, /readyz, /metrics and
/version through :func:`intake_platform.health.mount_health`. Readiness here
is the one thing this service cannot work without: a registry file that
parses and validates.

INT-351: the same service hosts the **ops collector**
(:mod:`intake_probes.ops_collector`) when its environment configures one — a
background loop that turns GPU-host, CI and clip-build facts into catalogued
series on this service's ``/metrics``. Unconfigured, no loop starts and the
families are served empty (help and type lines only), which the admin console
reads as *unknown*.

INT-202: it also serves ``sec_backup_age_min`` and
``sec_restore_drill_age_days``, computed at scrape time from the PHI-free
records in ``INTAKE_BACKUP_DIR`` — the directory its ``backup_freshness``
probe already watches (:mod:`intake_platform.backup.metrics`).

INT-021 close-out: docs/slo/probes.yaml is written against
``http_requests_total{service="probes"}``, and until the close-out nothing here
emitted it — an objective nobody could breach. The shared request middleware
is mounted like every other service's.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from os import environ
from pathlib import Path

from fastapi import FastAPI
from intake_platform.backup.metrics import bind_from_env as bind_backup_gauges
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from prometheus_client import REGISTRY

from intake_probes.ops_collector import interval_from_env, ops_collector_from_env, run_collector
from intake_probes.registry import load_registry

__all__ = ["create_app", "registry_path_from_env"]


def registry_path_from_env() -> Path:
    return Path(environ.get("INTAKE_REGISTRY_PATH", "observability/registry.yaml"))


@contextlib.asynccontextmanager
async def _ops_collector(app: FastAPI) -> AsyncIterator[None]:
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


def create_app() -> FastAPI:
    app = FastAPI(title="intake-probes", lifespan=_ops_collector)
    mount_http_metrics(app, "probes")

    async def registry_parses() -> bool:
        load_registry(registry_path_from_env())
        return True

    mount_health(app, readiness=[ReadinessCheck("registry", registry_parses)])
    bind_backup_gauges(environ)
    return app
