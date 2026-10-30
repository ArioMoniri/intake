"""INT-565 — `GET /admin/cost`, the Cost module as a console route.

``intake_platform.cost.compose_cost_payload`` (INT-190) is the arithmetic and
``tests/admin/test_cost_module.py`` holds it; this suite holds the route: it
serves exactly the committed fixture when no Prometheus is configured (every
price unconfigured, HB-O8; every quantity source-unavailable, never 0), it
reads usage through the API's own Prometheus reader when one is, it carries
no session identifier, and only the roles that run the platform read it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from admin_harness import bearer, build_admin_harness
from api_harness import ApiHarness
from intake_api.admin.cost_console import COST_CONFIG, cost_payload
from intake_api.admin.ops_prom import ENV_PROMETHEUS_URL, PromClient

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
PROM = "http://prometheus.test:9090"


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
    monkeypatch.delenv(ENV_PROMETHEUS_URL, raising=False)
    yield from build_admin_harness(tmp_path)


def _read(harness: ApiHarness, role: str = "platform_admin") -> Any:
    return harness.client.get("/admin/cost", headers=bearer(role))


class TestTheRoute:
    def test_with_no_source_the_route_serves_the_committed_fixture(
        self, harness: ApiHarness
    ) -> None:
        response = _read(harness)
        assert response.status_code == 200
        committed = json.loads((FIXTURES / "cost.payload.json").read_text(encoding="utf-8"))
        assert response.json() == committed
        assert response.json()["source"]["configured"] is False

    def test_no_session_identifier_reaches_the_body(self, harness: ApiHarness) -> None:
        text = json.dumps(_read(harness).json())
        for forbidden in ('"session_id"', '"patient', '"tenant_id"', '"clinician'):
            assert forbidden not in text

    def test_clinical_and_tenant_roles_are_refused(self, harness: ApiHarness) -> None:
        for role in ("clinical_lead", "tenant_admin", "compliance_officer", "researcher"):
            assert _read(harness, role).status_code == 403, role


class TestTheRunner:
    def test_a_configured_reader_answers_the_composers_queries(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.params["query"])
            return httpx.Response(
                200, json={"status": "success", "data": {"resultType": "vector", "result": []}}
            )

        prom = PromClient(base_url=PROM, transport=httpx.MockTransport(handler))
        body = cost_payload(config_path=COST_CONFIG, runner=prom.query)
        assert body["source"]["configured"] is True
        assert seen, "the composer ran its queries through the reader"

    def test_near_miss_an_erroring_reader_is_a_source_error_not_a_zero(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"status": "error", "error": "down"})

        prom = PromClient(base_url=PROM, transport=httpx.MockTransport(handler))
        body = cost_payload(config_path=COST_CONFIG, runner=prom.query)
        sessions = [window["sessions"] for window in body["windows"]]
        assert sessions and all(s["state"] == "source_error" for s in sessions)
        assert all(
            row["usd_per_session"] is None for w in body["windows"] for row in w["per_session"]
        )
