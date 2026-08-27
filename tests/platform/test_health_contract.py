"""INT-010 — the monitoring-contract entry points (CLAUDE.md invariant 15).

Acceptance, verbatim:
  "mount_health(app, readiness=[...]) for FastAPI, workers, voice-runtime;
   /version returns git_sha, built_at, sbom_digest"
  "health_contract test enumerates every service in the repo and fails on a
   missing endpoint or missing probe registration"

The enumeration is exercised against fixture services (tests/fixtures/services)
so the contract's ability to FAIL is proven — a compliant fixture passes, a
fixture missing the declaration is reported. Real services under services/
are enumerated by the same code the moment they exist.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from intake_platform.health import (
    ReadinessCheck,
    ServiceContractError,
    VersionInfo,
    discover_services,
    mount_health,
    verify_service_declarations,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "services"


def _app(readiness: list[ReadinessCheck] | None = None) -> TestClient:
    app = FastAPI()
    mount_health(
        app,
        readiness=readiness or [],
        version_info=VersionInfo(
            git_sha="abc1234", built_at="2026-08-27T00:00:00Z", sbom_digest="sha256:feed"
        ),
    )
    return TestClient(app, raise_server_exceptions=False)


# --- /healthz -------------------------------------------------------------------


def test_healthz_is_alive_even_when_readiness_fails() -> None:
    async def db() -> bool:
        raise RuntimeError("down")

    client = _app([ReadinessCheck("db", db)])
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


# --- /readyz --------------------------------------------------------------------


def test_readyz_ok_when_all_checks_pass() -> None:
    async def db() -> bool:
        return True

    async def redis() -> bool:
        return True

    client = _app([ReadinessCheck("db", db), ReadinessCheck("redis", redis)])
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"checks": {"db": "ok", "redis": "ok"}}


def test_readyz_503_names_the_failing_check() -> None:
    async def db() -> bool:
        return True

    async def redis() -> bool:
        raise ConnectionError("boom")

    client = _app([ReadinessCheck("db", db), ReadinessCheck("redis", redis)])
    r = client.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["redis"] == "error"


def test_readyz_reports_timeout_as_timeout() -> None:
    async def slow() -> bool:
        await asyncio.sleep(5)
        return True

    client = _app([ReadinessCheck("redis", slow, timeout_s=0.1)])
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["redis"] == "timeout"


# --- /version -------------------------------------------------------------------


def test_version_returns_the_three_build_fields() -> None:
    client = _app()
    body = client.get("/version").json()
    assert body == {
        "git_sha": "abc1234",
        "built_at": "2026-08-27T00:00:00Z",
        "sbom_digest": "sha256:feed",
    }


def test_version_info_reads_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("INTAKE_GIT_SHA", "cafe999")
    monkeypatch.setenv("INTAKE_BUILT_AT", "2026-08-27T10:00:00Z")
    monkeypatch.setenv("INTAKE_SBOM_DIGEST", "sha256:beef")
    info = VersionInfo.from_env()
    assert (info.git_sha, info.built_at, info.sbom_digest) == (
        "cafe999",
        "2026-08-27T10:00:00Z",
        "sha256:beef",
    )


# --- /metrics -------------------------------------------------------------------


def test_metrics_serves_prometheus_exposition() -> None:
    client = _app()
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "# HELP" in r.text or "# TYPE" in r.text


# --- service enumeration ---------------------------------------------------------


def test_discovers_fixture_services() -> None:
    services = discover_services(FIXTURES)
    names = {s.name for s in services}
    assert "good_service" in names
    assert "bad_service" in names


def test_compliant_service_passes_contract() -> None:
    good = next(s for s in discover_services(FIXTURES) if s.name == "good_service")
    verify_service_declarations(good)  # must not raise
    assert good.probe == "good_service.http"


def test_service_without_declaration_fails_contract() -> None:
    bad = next(s for s in discover_services(FIXTURES) if s.name == "bad_service")
    try:
        verify_service_declarations(bad)
    except ServiceContractError as err:
        assert "bad_service" in str(err)
    else:
        raise AssertionError("a service without [tool.intake] health/probe must fail the contract")


def test_every_real_service_in_repo_satisfies_the_contract() -> None:
    # Enumerates services/ — zero today; every future service is bound by this
    # test the moment its directory lands, which is the point of the contract.
    for service in discover_services(REPO / "services"):
        verify_service_declarations(service)
