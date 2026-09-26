"""The probes service's own monitoring contract (CLAUDE.md invariant 15).

Every service — this one included — mounts /healthz, /readyz, /metrics and
/version through :func:`intake_platform.health.mount_health`, takes its request
metrics from :func:`intake_platform.metrics.mount_http_metrics` (the
``service="probes"`` label docs/slo/probes.yaml reads) and its traces and logs
from the shared ``setup_otel``. Readiness here is the one thing this service
cannot work without: a registry file that parses and validates.

The middleware and the OTel setup were absent until INT-021 closed the
invariant-15 gate, and the consequence was not cosmetic: docs/slo/probes.yaml
declared an availability budget over ``http_requests_total{service="probes"}``,
the family was catalogued, and **no code anywhere emitted that label value** —
an error budget that could never burn. The service that watches everything else
was the one nothing watched.
"""

from __future__ import annotations

import logging
from os import environ
from pathlib import Path

from fastapi import FastAPI
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.otel import JsonLogFormatter, setup_otel

from intake_probes.registry import load_registry

__all__ = ["create_app", "registry_path_from_env"]

logger = logging.getLogger("intake_probes")

_otel_installed = False


def registry_path_from_env() -> Path:
    return Path(environ.get("INTAKE_REGISTRY_PATH", "observability/registry.yaml"))


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


def create_app() -> FastAPI:
    _setup_observability()
    app = FastAPI(title="intake-probes")

    async def registry_parses() -> bool:
        load_registry(registry_path_from_env())
        return True

    mount_http_metrics(app, "probes")
    mount_health(app, readiness=[ReadinessCheck("registry", registry_parses)])
    return app
