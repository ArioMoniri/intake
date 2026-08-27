"""The monitoring-contract entry points (INT-010; files/10 §6, CLAUDE.md inv. 15).

Every service mounts the same four endpoints via :func:`mount_health`:

- ``/healthz`` — 200 whenever the process is alive.
- ``/readyz``  — 200 with ``{"checks": {...}}`` when every readiness check
  passes; 503 naming each check's state (``ok`` / ``error`` / ``timeout``)
  otherwise. A check can fail loudly or hang — both are reported, never raised
  into the transport.
- ``/metrics`` — Prometheus exposition (the shared registry; the OTel pipeline
  arrives with INT-011).
- ``/version`` — ``{git_sha, built_at, sbom_digest}`` stamped at build time
  (``INTAKE_GIT_SHA`` / ``INTAKE_BUILT_AT`` / ``INTAKE_SBOM_DIGEST``).

Service enumeration: :func:`discover_services` walks a directory of service
packages and reads each ``pyproject.toml``'s ``[tool.intake]`` table;
:func:`verify_service_declarations` is the contract — a service must declare
its ``health`` app factory and its ``probe`` id (consumed by services/probes,
INT-022). A new service without these fails ``make check`` via
tests/platform/test_health_contract.py.
"""

from __future__ import annotations

import asyncio
import os
import tomllib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

__all__ = [
    "ReadinessCheck",
    "ServiceContractError",
    "ServiceDeclaration",
    "VersionInfo",
    "discover_services",
    "mount_health",
    "verify_service_declarations",
]

_DEFAULT_CHECK_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class ReadinessCheck:
    """A named readiness probe: an async callable returning True when ready."""

    name: str
    check: Callable[[], Awaitable[bool]]
    timeout_s: float = _DEFAULT_CHECK_TIMEOUT_S


@dataclass(frozen=True)
class VersionInfo:
    git_sha: str
    built_at: str
    sbom_digest: str

    @classmethod
    def from_env(cls) -> VersionInfo:
        return cls(
            git_sha=os.environ.get("INTAKE_GIT_SHA", "dev"),
            built_at=os.environ.get("INTAKE_BUILT_AT", "dev"),
            sbom_digest=os.environ.get("INTAKE_SBOM_DIGEST", "dev"),
        )


async def _run_check(check: ReadinessCheck) -> str:
    try:
        ok = await asyncio.wait_for(check.check(), timeout=check.timeout_s)
    except TimeoutError:
        return "timeout"
    except Exception:  # noqa: BLE001 — a readiness probe reports, never raises
        return "error"
    return "ok" if ok else "error"


def mount_health(
    app: FastAPI,
    readiness: list[ReadinessCheck] | None = None,
    version_info: VersionInfo | None = None,
) -> None:
    """Mount /healthz, /readyz, /metrics and /version on ``app``."""
    checks: list[ReadinessCheck] = list(readiness or [])
    version = version_info or VersionInfo.from_env()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/readyz")
    async def readyz(response: Response) -> dict[str, dict[str, str]]:
        results = dict(
            zip(
                (c.name for c in checks),
                await asyncio.gather(*(_run_check(c) for c in checks)),
                strict=True,
            )
        )
        if any(state != "ok" for state in results.values()):
            response.status_code = 503
        return {"checks": results}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    @app.get("/version")
    async def version_endpoint() -> dict[str, str]:
        return {
            "git_sha": version.git_sha,
            "built_at": version.built_at,
            "sbom_digest": version.sbom_digest,
        }


class ServiceContractError(Exception):
    """A service directory violates the monitoring contract."""


@dataclass(frozen=True)
class ServiceDeclaration:
    name: str
    path: Path
    health: str | None = None
    probe: str | None = None
    raw: dict[str, object] = field(default_factory=dict)


def discover_services(root: Path) -> list[ServiceDeclaration]:
    """Enumerate service packages: every child directory holding a pyproject.toml."""
    services: list[ServiceDeclaration] = []
    if not root.is_dir():
        return services
    for pyproject in sorted(root.glob("*/pyproject.toml")):
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        intake_table = data.get("tool", {}).get("intake", {})
        services.append(
            ServiceDeclaration(
                name=pyproject.parent.name,
                path=pyproject.parent,
                health=intake_table.get("health"),
                probe=intake_table.get("probe"),
                raw=intake_table,
            )
        )
    return services


def verify_service_declarations(service: ServiceDeclaration) -> None:
    """The contract: a service declares its health app factory and its probe id.

    Raises :class:`ServiceContractError` naming the service and the missing
    declaration — the test that calls this over ``services/`` is what makes
    "a new service without these fails make check" true (inv. 15).
    """
    missing = [
        key for key, value in (("health", service.health), ("probe", service.probe)) if not value
    ]
    if missing:
        raise ServiceContractError(
            f"service {service.name!r} ({service.path}) is missing "
            f"[tool.intake] declaration(s): {', '.join(missing)} — every service "
            "must mount the four health endpoints via intake_platform.health."
            "mount_health and register a synthetic probe (files/10 §6)"
        )
