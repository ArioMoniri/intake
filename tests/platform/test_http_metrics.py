"""INT-021 — the shared HTTP metrics middleware every service mounts.

``mount_http_metrics`` is the emitter behind docs/slo SLIs
(``http_requests_total`` / ``http_request_duration_seconds``). Pinned here:

- labels carry the ROUTE TEMPLATE, never the raw path — a path segment is
  free text and free text never reaches a metric label (inv. 6);
- an unhandled exception is counted as status 500 (the availability SLI sees
  the failure) and still propagates;
- unmatched requests collapse into the single ``unmatched`` route label
  (bounded cardinality).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from intake_platform.metrics import mount_http_metrics
from prometheus_client import REGISTRY


def _client(service: str) -> TestClient:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def read_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("unhandled failure")

    mount_http_metrics(app, service)
    return TestClient(app, raise_server_exceptions=False)


def test_counts_by_route_template_and_status() -> None:
    client = _client("msvc_route")
    assert client.get("/items/123").status_code == 200
    assert client.get("/items/456").status_code == 200
    assert (
        REGISTRY.get_sample_value(
            "http_requests_total",
            {
                "service": "msvc_route",
                "method": "GET",
                "route": "/items/{item_id}",
                "status": "200",
            },
        )
        == 2.0
    )
    assert (
        REGISTRY.get_sample_value(
            "http_request_duration_seconds_count",
            {"service": "msvc_route", "method": "GET", "route": "/items/{item_id}"},
        )
        == 2.0
    )


def test_raw_path_never_reaches_a_label() -> None:
    marker = "58-rheumatology-maslak"
    client = _client("msvc_phi")
    assert client.get(f"/items/{marker}").status_code == 200
    for family in REGISTRY.collect():
        if not family.name.startswith("http_request"):
            continue
        for sample in family.samples:
            for value in sample.labels.values():
                assert marker not in value, f"raw path leaked into label: {sample.labels}"


def test_unhandled_exception_counts_as_500_and_propagates() -> None:
    client = _client("msvc_err")
    assert client.get("/boom").status_code == 500
    assert (
        REGISTRY.get_sample_value(
            "http_requests_total",
            {"service": "msvc_err", "method": "GET", "route": "/boom", "status": "500"},
        )
        == 1.0
    )


def test_unmatched_route_is_one_bounded_label_value() -> None:
    client = _client("msvc_404")
    assert client.get("/definitely/not/here").status_code == 404
    assert (
        REGISTRY.get_sample_value(
            "http_requests_total",
            {"service": "msvc_404", "method": "GET", "route": "unmatched", "status": "404"},
        )
        == 1.0
    )
