"""The Cost module's console composite (INT-565; files/08 §3 "Cost", §4 J).

``GET /admin/cost`` is the body ``apps/admin-web/src/cost`` renders (INT-190):
per-session cost by component, vendor and profile, and budgets with their
alerts. The arithmetic and every refusal behind it are
``intake_platform.cost.compose_cost_payload``; this module only names the
inputs the API serves it from:

- the owner-filled price file, ``infra/costs/unit-prices.yaml`` (HB-O8: every
  price and budget is empty until the owner fills them, so every figure reads
  *price not configured*, never 0);
- the metrics catalogue, which says which usage series exist;
- the API's own Prometheus reader (``INTAKE_OPS_PROMETHEUS_URL``) as the query
  runner. The queries come from the committed price file and catalogue; nothing
  in the request reaches one. Unset or malformed, there is no runner and every
  quantity reads *source unavailable*.

No session identifier exists anywhere in the body: per-session cost is a mean
(invariant 6). :func:`cost_payload` is what ``scripts/dev/record_cost_fixture.py``
records the e2e fixtures through.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from intake_platform.admin import AdminRole, AdminWiring
from intake_platform.cost import (
    QueryRunner,
    compose_cost_payload,
    config_identity,
    load_cost_config,
)

from intake_api.admin.console_sources import REPO, load_catalog, prom_from_env
from intake_api.admin.deps import AdminCaller
from intake_api.admin.ops_prom import PromClient

__all__ = ["COST_CONFIG", "cost_payload", "cost_read"]

COST_CONFIG: Final = REPO / "infra" / "costs" / "unit-prices.yaml"


def cost_payload(
    *, config_path: Path, runner: QueryRunner | None, repo: Path = REPO
) -> dict[str, Any]:
    """The composite over one price file and one runner (``None``: no source)."""
    ref, digest = config_identity(config_path, repo)
    return compose_cost_payload(
        load_cost_config(config_path),
        config_ref=ref,
        config_digest=digest,
        catalog=load_catalog(),
        runner=runner,
    )


def _runner() -> QueryRunner | None:
    source = prom_from_env(os.environ)
    return source.query if isinstance(source, PromClient) else None


async def cost_read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    # synchronous httpx, off the event loop
    return await run_in_threadpool(lambda: cost_payload(config_path=COST_CONFIG, runner=_runner()))
