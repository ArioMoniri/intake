"""Record the responses the admin-web ops page renders (INT-351, INT-560).

``apps/admin-web/e2e/ops.spec.ts`` drives the page's server-side loader and
renders the page, and needs the responses the loader would receive. As with
``record_models_fixture.py`` and its siblings, there are two ways to give it
them and only one is honest: hand-write the ``/admin/ops`` body in TypeScript —
a second, hand-kept copy of the composite that keeps passing on the day the
composite changes — or produce it with the composite itself. This script does
the second, three times:

- ``ops.payload.json`` — ``intake_api.admin.ops_console.build_ops_console`` over
  the real registry (``observability/registry.yaml`` through the INT-183
  loader), the synthetic host's recorded inventory
  (``infra/staging/inventory.yaml``), the host sweep recorded in
  ``tests/fixtures/ops/host_sweep.json`` and the recorded Prometheus answers in
  ``tests/fixtures/ops/prometheus_responses.json``. The payload is dated at
  the sweep's last probe, so every row's age reads as it did then. No
  Prometheus runs on this host (container runtimes are CI-only), so those
  answers are constructed in the documented HTTP API shape and live under
  ``tests/`` — the composite that reads them is the shipped one.
- ``ops.unconfigured.payload.json`` — the same composite with no Prometheus,
  no inventory and no sweep at all: the platform's own unknown state, which is
  what a deployment without ``INTAKE_OPS_PROMETHEUS_URL``,
  ``INTAKE_HOST_INVENTORY_PATH`` and ``INTAKE_PROBE_RESULTS_PATH`` serves.
- ``ops.health.json`` — ``/healthz``, ``/readyz`` and ``/version`` as the shared
  ``intake_platform.health.mount_health`` contract serves them (every service
  mounts the same four endpoints, invariant 15), from the probes service's app
  with the build stamp set to this checkout's HEAD.

``--sweep`` re-takes the host sweep: the shipped wiring
(``intake_probes.host_sweep.build_host_clients`` over the recorded inventory)
on the recording machine, which is not on the host's compose networks. Every
dial is refused rather than sent — so nothing here resolves a compose name on
whatever network the laptop is on — and no probe credential is set, so the
sweep records what such a run is: what the host does not run skipped as
``not deployed on synthetic-aws``, the credentialled probes skipped for their
missing variable, and everything else unreachable.

Run: ``uv run python scripts/dev/record_ops_fixture.py [--sweep]`` (also
``make admin-fixtures``, which rebuilds from the committed recordings).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 — `git rev-parse HEAD` only
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

import httpx
from fastapi.testclient import TestClient
from intake_api.admin.models_source import ProbeSweep, load_models_module
from intake_api.admin.ops_console import OPS_QUERIES, build_ops_console
from intake_api.admin.ops_prom import PromClient
from intake_probes.gate import load_results
from intake_probes.host_sweep import (
    HostProbeConfig,
    build_host_clients,
    sweep_host_once,
    write_sweep,
)
from intake_probes.inventory import HostReading, load_host_inventory
from intake_probes.registry import load_registry

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
RECORDINGS = REPO / "tests" / "fixtures" / "ops"
PROM_ANSWERS = RECORDINGS / "prometheus_responses.json"
HOST_SWEEP = RECORDINGS / "host_sweep.json"
INVENTORY = REPO / "infra" / "staging" / "inventory.yaml"
REGISTRY = REPO / "observability" / "registry.yaml"
#: The synthetic image bakes this; the recorder plays that host.
SYNTHETIC = {"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}
#: The instant the recorded Prometheus answers were taken at.
RECORDED_AT = datetime(2026, 9, 26, 16, 0, tzinfo=UTC)


def _recorded_prometheus() -> PromClient:
    answers: dict[str, Any] = json.loads(PROM_ANSWERS.read_text(encoding="utf-8"))
    by_expr = {expr: query_id for query_id, expr in OPS_QUERIES.items()}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answers[by_expr[request.url.params["query"]]])

    return PromClient(base_url="http://prometheus.recorded", transport=httpx.MockTransport(handler))


def _off_the_compose_network(*_: object) -> NoReturn:
    raise OSError("not on the host's compose network")


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("not on the host's compose network", request=request)


def _take_host_sweep() -> None:
    registry = load_registry(REGISTRY)
    inventory = load_host_inventory(INVENTORY, registry=registry, env=SYNTHETIC)
    config = HostProbeConfig(
        env={},
        http_transport=httpx.MockTransport(_refuse),
        dial=_off_the_compose_network,
        tls_not_after=_off_the_compose_network,
    )
    write_sweep(
        sweep_host_once(registry, build_host_clients(registry, inventory, config)), HOST_SWEEP
    )
    print(f"wrote {HOST_SWEEP.relative_to(REPO)}")


def _head() -> str:
    return subprocess.run(  # noqa: S603  # nosec B603 B607 — fixed argv
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        check=True,
        text=True,
        cwd=REPO,
    ).stdout.strip()


def _health() -> dict[str, dict[str, Any]]:
    os.environ["INTAKE_GIT_SHA"] = _head()
    os.environ["INTAKE_BUILT_AT"] = RECORDED_AT.strftime("%Y-%m-%dT%H:%M:%SZ")
    from intake_probes.app import create_app

    with TestClient(create_app()) as client:
        return {
            path.strip("/"): {"status": response.status_code, "body": response.json()}
            for path in ("/healthz", "/readyz", "/version")
            for response in (client.get(path),)
        }


def _write(name: str, payload: object) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--sweep", action="store_true", help="re-take the recorded host sweep")
    args = parser.parse_args(argv)
    if args.sweep:
        _take_host_sweep()

    registry = load_registry(REGISTRY)
    inventory = load_host_inventory(INVENTORY, registry=registry, env=SYNTHETIC)
    sweep = load_results(HOST_SWEEP)
    swept_at = max(r.checked_at for r in sweep.values() if r.checked_at is not None)
    _write(
        "ops.payload.json",
        build_ops_console(
            prom=_recorded_prometheus(),
            models=load_models_module(ProbeSweep(records=sweep)),
            results=sweep,
            now=swept_at,
            host=HostReading(inventory, None),
        ),
    )
    _write(
        "ops.unconfigured.payload.json",
        build_ops_console(
            prom=None, models=load_models_module(ProbeSweep()), results={}, now=RECORDED_AT
        ),
    )
    _write("ops.health.json", _health())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
