"""Record the responses the admin-web overview page renders (INT-181).

``apps/admin-web/e2e/overview.spec.ts`` drives the page's server-side loader and
renders the page, and needs the responses the loader would receive. As with
``record_ops_fixture.py`` (INT-351), the ``/admin/reliability`` body is never
hand-written: it is produced by the shipped composite,
``intake_api.admin.reliability_console.build_reliability_console``, over

- the committed SLO files (``docs/slo``) and registry
  (``observability/registry.yaml``) — the real ones;
- **a real probe sweep** — ``tests/fixtures/reliability/probe_sweep.json`` is
  the runner's own output (``intake_probes.runner --once``) on the recording
  host, re-taken with ``--sweep``. On a host with no dev stack up it records
  exactly that: every store unreachable and every row without a client
  skipped, which is the honest state;
- the Prometheus answers in ``tests/fixtures/reliability/prometheus_responses.json``.
  No Prometheus runs on the recording host (container runtimes are CI-only),
  so, as in INT-351, these are constructed in the documented HTTP API shape
  and live under ``tests/`` — the client and composite that read them are the
  shipped ones.

It also records, with ``--live-api <origin>``, the live API's ``/readyz`` (the
page's API-readiness tile) and ``/version`` (which build answered) into
``overview.api.json``. Two GETs and nothing else: nothing is sent to the API.

Outputs (``apps/admin-web/e2e/fixtures``):

- ``reliability.payload.json`` — the composite as of the sweep's last probe;
- ``reliability.stale.payload.json`` — the same sources an hour later, when
  every result is past three sweeps (the stale path, never the last value);
- ``reliability.unconfigured.payload.json`` — no Prometheus and no sweep: what
  a deployment without ``INTAKE_OPS_PROMETHEUS_URL`` or
  ``INTAKE_PROBE_RESULTS_PATH`` serves.

Run: ``uv run python scripts/dev/record_reliability_fixture.py [--sweep]
[--live-api https://<host>]`` (``make admin-fixtures`` rebuilds from the
committed recordings).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from intake_api.admin.models_source import PROBE_RESULTS_ENV
from intake_api.admin.ops_prom import PromClient
from intake_api.admin.reliability_console import (
    Sweep,
    build_reliability_console,
    load_slo_files,
    load_sweep,
    reliability_queries,
)
from intake_probes.registry import load_registry
from intake_probes.runner import main as run_sweep

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
RECORDINGS = REPO / "tests" / "fixtures" / "reliability"
PROM_ANSWERS = RECORDINGS / "prometheus_responses.json"
SWEEP = RECORDINGS / "probe_sweep.json"
SLO_DIR = REPO / "docs" / "slo"
REGISTRY = REPO / "observability" / "registry.yaml"


def _recorded_prometheus(queries: dict[str, str]) -> PromClient:
    answers: dict[str, Any] = json.loads(PROM_ANSWERS.read_text(encoding="utf-8"))
    by_expr = {expr: query_id for query_id, expr in queries.items()}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answers[by_expr[request.url.params["query"]]])

    return PromClient(base_url="http://prometheus.recorded", transport=httpx.MockTransport(handler))


def _sweep_instant(sweep: Sweep) -> datetime:
    """The composite is built as of the recorded sweep's last probe."""
    stamps = [r.checked_at for r in (sweep.records or {}).values() if r.checked_at is not None]
    if not stamps:
        raise SystemExit(f"{SWEEP.relative_to(REPO)} carries no checked_at; re-record with --sweep")
    return max(stamps).astimezone(UTC)


def _live_api(origin: str) -> dict[str, Any]:
    parts = urlsplit(origin)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/"):
        raise SystemExit("--live-api takes a bare https origin")
    recorded: dict[str, Any] = {"recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with httpx.Client(timeout=10.0, follow_redirects=False) as client:
        for path in ("/readyz", "/version"):
            response = client.get(f"{parts.scheme}://{parts.netloc}{path}")
            recorded[path.strip("/")] = {"status": response.status_code, "body": response.json()}
    return recorded


def _write(name: str, payload: object) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sweep", action="store_true", help="re-take the probe sweep on this host")
    parser.add_argument("--live-api", default=None, help="record /readyz and /version from here")
    args = parser.parse_args(argv)

    if args.sweep:
        run_sweep(["--registry", str(REGISTRY), "--once", "--out", str(SWEEP)])
        print(f"wrote {SWEEP.relative_to(REPO)}")
    if args.live_api:
        _write("overview.api.json", _live_api(args.live_api))

    files = load_slo_files(SLO_DIR)
    registry = load_registry(REGISTRY)
    sweep = load_sweep({PROBE_RESULTS_ENV: str(SWEEP)})
    at = _sweep_instant(sweep)
    queries = reliability_queries(files)

    def composite(now: datetime) -> dict[str, Any]:
        return build_reliability_console(
            prom=_recorded_prometheus(queries),
            slo_files=files,
            registry=registry,
            sweep=sweep,
            now=now,
        )

    _write("reliability.payload.json", composite(at))
    _write("reliability.stale.payload.json", composite(at + timedelta(hours=1)))
    _write(
        "reliability.unconfigured.payload.json",
        build_reliability_console(
            prom=None,
            slo_files=files,
            registry=registry,
            sweep=Sweep(None, "probe_results_unconfigured"),
            now=at,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
