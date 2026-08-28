"""INT-197 — invariant 15 (monitoring contract) + baseline security headers.

The four health endpoints come from intake_platform.health.mount_health, the
request metrics from intake_platform.metrics.mount_http_metrics (both series
already catalogued in observability/metrics_catalog.yaml), and every response
carries the INT-012 security headers plus the dev-tier marker.
"""

from __future__ import annotations

from api_harness import ApiHarness


def test_health_surface_is_mounted(harness: ApiHarness) -> None:
    assert harness.client.get("/healthz").json() == {"status": "alive"}
    version = harness.client.get("/version").json()
    assert set(version) == {"git_sha", "built_at", "sbom_digest"}


def test_readyz_reports_db_audit_and_dev_auth(harness: ApiHarness) -> None:
    response = harness.client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"] == {"db": "ok", "audit_store": "ok", "dev_auth": "ok"}


def test_http_metrics_carry_the_api_service_label(harness: ApiHarness) -> None:
    harness.client.get("/v1/visits", headers=harness.patient())
    exposition = harness.client.get("/metrics").text
    assert "http_requests_total{" in exposition
    assert 'service="api"' in exposition
    assert 'route="/v1/visits"' in exposition


def test_security_headers_and_tier_marker_on_every_response(harness: ApiHarness) -> None:
    for path, headers in (("/healthz", {}), ("/v1/visits", harness.patient())):
        response = harness.client.get(path, headers=headers)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["x-intake-auth-tier"] == "dev"
