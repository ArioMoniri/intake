"""The probes service's own monitoring contract (CLAUDE.md invariant 15).

Every service — this one included — mounts /healthz, /readyz, /metrics and
/version through :func:`intake_platform.health.mount_health`. Readiness here
is the one thing this service cannot work without: a registry file that
parses and validates.
"""

from __future__ import annotations

from os import environ
from pathlib import Path

from fastapi import FastAPI
from intake_platform.health import ReadinessCheck, mount_health

from intake_probes.registry import load_registry

__all__ = ["create_app", "registry_path_from_env"]


def registry_path_from_env() -> Path:
    return Path(environ.get("INTAKE_REGISTRY_PATH", "observability/registry.yaml"))


def create_app() -> FastAPI:
    app = FastAPI(title="intake-probes")

    async def registry_parses() -> bool:
        load_registry(registry_path_from_env())
        return True

    mount_health(app, readiness=[ReadinessCheck("registry", registry_parses)])
    return app
