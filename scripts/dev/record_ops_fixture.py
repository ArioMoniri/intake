"""Record the responses the admin-web ops page renders (INT-351).

``apps/admin-web/e2e/ops.spec.ts`` drives the page's server-side loader and
renders the page, and needs the responses the loader would receive. As with
``record_models_fixture.py`` and its siblings, there are two ways to give it
them and only one is honest: hand-write the ``/admin/ops`` body in TypeScript —
a second, hand-kept copy of the composite that keeps passing on the day the
composite changes — or produce it with the composite itself. This script does
the second, three times:

- ``ops.payload.json`` — ``intake_api.admin.ops_console.build_ops_console`` over
  the real registry (``observability/registry.yaml`` through the INT-183
  loader) and the recorded Prometheus answers in
  ``tests/fixtures/ops/prometheus_responses.json``. No Prometheus runs on this
  host (container runtimes are CI-only), so those answers are constructed in
  the documented HTTP API shape and live under ``tests/`` — the composite that
  reads them is the shipped one.
- ``ops.unconfigured.payload.json`` — the same composite with no Prometheus at
  all: the platform's own unknown state, which is what a deployment without
  ``INTAKE_OPS_PROMETHEUS_URL`` serves.
- ``ops.health.json`` — ``/healthz``, ``/readyz`` and ``/version`` as the shared
  ``intake_platform.health.mount_health`` contract serves them (every service
  mounts the same four endpoints, invariant 15), from the probes service's app
  with the build stamp set to this checkout's HEAD.

Run: ``uv run python scripts/dev/record_ops_fixture.py`` (also ``make
admin-fixtures``).
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 — `git rev-parse HEAD` only
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient
from intake_api.admin.models_source import load_models_module
from intake_api.admin.ops_console import OPS_QUERIES, build_ops_console
from intake_api.admin.ops_prom import PromClient

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
PROM_ANSWERS = REPO / "tests" / "fixtures" / "ops" / "prometheus_responses.json"
#: The instant the recorded Prometheus answers were taken at.
RECORDED_AT = datetime(2026, 9, 26, 16, 0, tzinfo=UTC)


def _recorded_prometheus() -> PromClient:
    answers: dict[str, Any] = json.loads(PROM_ANSWERS.read_text(encoding="utf-8"))
    by_expr = {expr: query_id for query_id, expr in OPS_QUERIES.items()}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answers[by_expr[request.url.params["query"]]])

    return PromClient(base_url="http://prometheus.recorded", transport=httpx.MockTransport(handler))


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


def main() -> int:
    models = load_models_module()
    _write(
        "ops.payload.json",
        build_ops_console(prom=_recorded_prometheus(), models=models, results={}, now=RECORDED_AT),
    )
    _write(
        "ops.unconfigured.payload.json",
        build_ops_console(prom=None, models=models, results={}, now=RECORDED_AT),
    )
    _write("ops.health.json", _health())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
