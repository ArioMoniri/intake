"""Shared HTTP request metrics for every FastAPI service (INT-021; inv. 13/15).

``mount_http_metrics`` is the emitter the docs/slo SLIs are written against:

- ``http_requests_total{service,method,route,status}`` — the availability SLI
  counts the 5xx share of this counter;
- ``http_request_duration_seconds{service,method,route}`` — the latency SLI
  reads this histogram's buckets.

Labels carry the ROUTE TEMPLATE (``/items/{item_id}``), never the raw path: a
path segment is free text and free text never reaches a metric label (inv. 6).
Requests that match no route collapse into the single ``unmatched`` value so
cardinality stays bounded. Both families are declared in
observability/metrics_catalog.yaml; the emit-without-catalogue gate in
tests/observability/test_slo_files.py holds that true.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram, disable_created_metrics

__all__ = ["HTTP_REQUEST_DURATION_SECONDS", "HTTP_REQUESTS_TOTAL", "mount_http_metrics"]

# The client's `_created` companion series would be emitted next to every
# counter and histogram without appearing in the catalogue; the exposition
# must equal the catalogue exactly (inv. 13), so they are off platform-wide.
disable_created_metrics()  # type: ignore[no-untyped-call]  # upstream def has no annotations

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "HTTP requests handled, by service, method, route template and status code.",
    ["service", "method", "route", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds, by service, method and route template.",
    ["service", "method", "route"],
)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path: str | None = getattr(route, "path", None)
    return path or "unmatched"


def _record(request: Request, service: str, status: str, elapsed_s: float) -> None:
    route = _route_template(request)
    HTTP_REQUESTS_TOTAL.labels(
        service=service, method=request.method, route=route, status=status
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        service=service, method=request.method, route=route
    ).observe(elapsed_s)


def mount_http_metrics(app: FastAPI, service: str) -> None:
    """Install the request-metrics middleware on ``app``.

    An unhandled exception is recorded as status 500 — the availability SLI
    must see the failure — and then re-raised for the server's error handling.
    """

    @app.middleware("http")
    async def _observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            _record(request, service, "500", time.perf_counter() - start)
            raise
        _record(request, service, str(response.status_code), time.perf_counter() - start)
        return response
