"""The metrics service's own monitoring contract (CLAUDE.md invariant 15).

/healthz, /readyz, /metrics and /version come from
:func:`intake_platform.health.mount_health`; request metrics from
:func:`intake_platform.metrics.mount_http_metrics` (the ``service="metrics"``
label its SLO reads); traces from the shared ``setup_otel``.

Readiness is honest rather than convenient. The rollups read the ``events``
table, and this branch does not deploy the service or its database, so
``events_db`` is a NAMED check that reports **not ready** when no URL is
configured — ``/readyz`` answers 503 on an unwired process. Build the
mechanism, wire the gate, make it fail closed (CLAUDE.md); a check that
returned ok on a process that can roll nothing up would be the fake.
"""

from __future__ import annotations

import logging
from os import environ

from fastapi import FastAPI
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.otel import JsonLogFormatter, setup_otel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

__all__ = ["EVENTS_DB_URL_VAR", "create_app", "events_db_url"]

logger = logging.getLogger("intake_metrics")

#: The events database the rollups read. Absent → /readyz is 503.
EVENTS_DB_URL_VAR = "INTAKE_METRICS_EVENTS_DB_URL"

_otel_installed = False


def events_db_url() -> str | None:
    value = environ.get(EVENTS_DB_URL_VAR, "").strip()
    return value or None


def _setup_observability() -> None:
    """Shared OTel setup + JSON logging, once per process (invariant 15)."""
    global _otel_installed
    if _otel_installed:
        return
    setup_otel("metrics")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    _otel_installed = True


async def _events_db_ready() -> bool:
    url = events_db_url()
    if url is None:
        return False
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
    return True


def create_app() -> FastAPI:
    _setup_observability()
    app = FastAPI(title="intake-metrics")
    mount_http_metrics(app, "metrics")
    mount_health(app, readiness=[ReadinessCheck("events_db", _events_db_ready)])
    return app
