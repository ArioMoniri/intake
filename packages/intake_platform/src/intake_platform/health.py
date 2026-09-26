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

import ast
import asyncio
import os
import tomllib
from collections.abc import Awaitable, Callable, Container
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

__all__ = [
    "ContractFindings",
    "ReadinessCheck",
    "ServiceContractError",
    "ServiceDeclaration",
    "VersionInfo",
    "discover_services",
    "mount_health",
    "scan_service_sources",
    "verify_service_contract",
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


# --- invariant 15, all four requirements in one place -----------------------------

#: The shared modules invariant 15 names. A service that re-implements any of
#: these has left the shared setup and, with it, the redaction and the label
#: hygiene the setup carries.
_HEALTH_MODULE = "intake_platform.health"
_OTEL_MODULE = "intake_platform.otel"
_METRICS_MODULE = "intake_platform.metrics"


@dataclass(frozen=True)
class ContractFindings:
    """What a static read of one service's sources found.

    Static rather than live on purpose: several services refuse to construct
    without their secrets backend, and a gate that a new service can pass by
    being unimportable is not a gate.
    """

    mounts_health: bool
    calls_setup_otel: bool
    http_metric_service_labels: frozenset[str]


def _imported_from(tree: ast.Module, module: str) -> set[str]:
    """Names imported out of ``module`` in one parsed file."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _called_names(tree: ast.Module) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` bindings, so a named constant resolves.

    services/voice-runtime passes ``SERVICE_NAME`` rather than the string, and a
    gate that only understood literals would have called it non-conformant.
    """
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value.value
    return constants


def _http_metric_labels(tree: ast.Module) -> set[str]:
    """The service labels passed to ``mount_http_metrics(app, "...")``."""
    constants = _module_string_constants(tree)
    labels: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else None
        )
        if name != "mount_http_metrics" or len(node.args) < 2:
            continue
        label = node.args[1]
        if isinstance(label, ast.Constant) and isinstance(label.value, str):
            labels.add(label.value)
        elif isinstance(label, ast.Name) and label.id in constants:
            labels.add(constants[label.id])
    return labels


def scan_service_sources(service: ServiceDeclaration) -> ContractFindings:
    """Read a service's Python sources for its use of the shared platform modules."""
    root = service.path / "src"
    if not root.is_dir():
        root = service.path
    mounts_health = False
    calls_setup_otel = False
    labels: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        called = _called_names(tree)
        if "mount_health" in _imported_from(tree, _HEALTH_MODULE) and "mount_health" in called:
            mounts_health = True
        if "setup_otel" in _imported_from(tree, _OTEL_MODULE) and "setup_otel" in called:
            calls_setup_otel = True
        if "mount_http_metrics" in _imported_from(tree, _METRICS_MODULE):
            labels |= _http_metric_labels(tree)
    return ContractFindings(
        mounts_health=mounts_health,
        calls_setup_otel=calls_setup_otel,
        http_metric_service_labels=frozenset(labels),
    )


def verify_service_contract(
    service: ServiceDeclaration,
    *,
    slo_dir: Path,
    probe_components: Container[str],
) -> None:
    """CLAUDE.md invariant 15 for one service, all four requirements at once.

    Raises :class:`ServiceContractError` listing **every** requirement the
    service fails — an operator adding a service should learn all four gaps in
    one run, not one per re-run. The four:

    1. the endpoints come from :func:`mount_health` (and the ``[tool.intake]``
       declaration names the app factory and the probe id);
    2. spans and logs go through :func:`intake_platform.otel.setup_otel`;
    3. ``docs/slo/<service>.yaml`` exists;
    4. a component of the same name has a row in the probe registry, so
       something actually calls the service every 60 s.

    ``probe_components`` is the registry's component names — passed in rather
    than read here, because intake_platform must not import services/probes.
    """
    failures: list[str] = []
    try:
        verify_service_declarations(service)
    except ServiceContractError as err:
        failures.append(str(err))

    findings = scan_service_sources(service)
    if not findings.mounts_health:
        failures.append(
            f"no call to {_HEALTH_MODULE}.mount_health — /healthz, /readyz, /metrics and "
            "/version must come from the shared module"
        )
    if not findings.calls_setup_otel:
        failures.append(
            f"no call to {_OTEL_MODULE}.setup_otel — telemetry that skips the shared setup "
            "skips its redaction (inv. 6)"
        )
    if not (slo_dir / f"{service.name}.yaml").is_file():
        failures.append(
            f"no {slo_dir.name}/{service.name}.yaml — a service without a declared error "
            "budget cannot be on call for anything (docs/slo)"
        )
    if service.name not in probe_components:
        failures.append(
            f"no {service.name!r} row in the probe registry — declaring a probe id in "
            "pyproject.toml is not the same as having a synthetic probe"
        )
    if failures:
        joined = "\n  - ".join(failures)
        raise ServiceContractError(
            f"service {service.name!r} ({service.path}) fails CLAUDE.md invariant 15:\n  - {joined}"
        )
