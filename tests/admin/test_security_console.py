"""INT-565 — `GET /admin/security`, the Security module as a console route.

The console's view-model (apps/admin-web/src/security, INT-192) renders this
body. Held here: an unmounted SIEM stream is *not configured*, never zero; an
egress count exists only when the scrape was read, over a stated window; the
audit-chain section is the verdict the daily verifier reaches with no anchor
(``anchor_missing``, HB-I12) — stated without reading the chain and without a
chain hash anywhere in the body, because the head is published outside the
blast radius this console sits in — and without the API importing the
verifier; the route is a console read for the security roles; and the
committed fixture is the route's own builder.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from admin_harness import bearer, build_admin_harness
from api_harness import ApiHarness
from intake_api.admin.console_sources import Reading, load_catalog, read_counts
from intake_api.admin.ops_prom import ENV_PROMETHEUS_URL, PromClient
from intake_api.admin.security_console import SECURITY_LABELS, SECURITY_QUERIES, security_payload
from intake_platform.audit import InMemoryAuditStore
from intake_platform.audit_verifier.job import run_daily_verification
from intake_platform.siem import ALERTS_PATH_ENV
from recorders import recorder

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "apps" / "admin-web" / "e2e" / "fixtures" / "security.payload.json"
PROM = "http://prometheus.test:9090"
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
    monkeypatch.delenv(ENV_PROMETHEUS_URL, raising=False)
    monkeypatch.setenv(ALERTS_PATH_ENV, str(tmp_path / "no-alert-stream.json"))
    yield from build_admin_harness(tmp_path)


def _read(harness: ApiHarness, role: str = "sre_oncall") -> Any:
    return harness.client.get("/admin/security", headers=bearer(role))


class _NoAnchor:
    def anchored_head(self) -> str | None:
        return None


def _build(egress: Reading) -> dict[str, Any]:
    return security_payload(catalog=load_catalog(), feed=None, egress=egress, generated_at=NOW)


class TestTheRoute:
    def test_an_operator_reads_the_composite(self, harness: ApiHarness) -> None:
        response = _read(harness)
        assert response.status_code == 200
        body = response.json()
        siem = body["siem"]
        assert siem["feed_configured"] is False and siem["total"] is None
        assert all(d["count"] is None for d in siem["detectors"])
        egress = body["egress_denials"]
        assert egress["source_available"] is False and egress["denied_total"] is None
        assert egress["source_reason"] == "prometheus_unconfigured"
        assert body["pentest"]["findings"] == [] and body["pentest"]["last_assessment"] is None

    def test_the_audit_chain_is_never_attested_and_carries_no_hash(
        self, harness: ApiHarness
    ) -> None:
        response = _read(harness)
        chain = response.json()["audit_chain"]
        assert chain["outcome"] == "anchor_missing" and chain["ok"] is False
        assert chain["anchor_available"] is False
        assert not {"local_head", "anchor_head", "entry_count"} & set(chain)
        # the writer's head exists and moves; the console's answer never names it
        head = harness.audit_store.entries()[-1].entry_hash
        assert head not in response.text
        assert not HEX64.search(response.text)

    def test_the_read_is_itself_audited(self, harness: ApiHarness) -> None:
        _read(harness)
        actions = [entry.action for entry in harness.audit_store.entries()]
        assert any(action.startswith("admin.security.read") for action in actions)

    def test_clinical_and_tenant_roles_are_refused(self, harness: ApiHarness) -> None:
        for role in ("clinical_lead", "tenant_admin", "researcher", "support"):
            assert _read(harness, role).status_code == 403, role


class TestEgressDenials:
    def test_a_read_scrape_shows_the_windowed_count(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.params["query"])
            result = [{"metric": {}, "value": [1761800000, "2"]}]
            return httpx.Response(
                200, json={"status": "success", "data": {"resultType": "vector", "result": result}}
            )

        prom = PromClient(base_url=PROM, transport=httpx.MockTransport(handler))
        reading = read_counts(prom, SECURITY_QUERIES, SECURITY_LABELS, "egress_denied")
        egress = _build(reading)["egress_denials"]
        assert seen == ["sum(increase(sec_egress_denied_total[24h]))"]
        assert egress["source_available"] is True
        assert egress["denied_total"] == 2 and egress["window"] == "24h"

    def test_near_miss_an_unread_scrape_is_no_count_not_zero(self) -> None:
        egress = _build(Reading.unavailable("prometheus_unreachable"))["egress_denials"]
        assert egress["denied_total"] is None
        assert egress["source_reason"] == "prometheus_unreachable"

    def test_every_query_names_only_catalogued_series(self) -> None:
        catalog = load_catalog()
        for query_id, expr in SECURITY_QUERIES.items():
            assert catalog.unknown_references(expr) == frozenset(), query_id


class TestTheVerdictIsTheVerifiers:
    def test_the_builder_states_the_verdict_the_verifier_reaches_with_no_anchor(self) -> None:
        section = _build(Reading.unavailable("prometheus_unconfigured"))["audit_chain"]
        report = run_daily_verification(InMemoryAuditStore(), anchor=_NoAnchor())
        assert section["outcome"] == report.outcome.value
        assert section["ok"] is report.ok
        assert section["anchor_available"] is (report.anchor_head is not None)
        # the verifier's report has a head; the console's section never does
        assert HEX64.fullmatch(report.local_head)
        assert not HEX64.search(json.dumps(section))


class TestTheFixtureIsTheRoutesOwn:
    def test_the_committed_fixture_is_the_builder_over_this_repositorys_sources(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(REPO)
        monkeypatch.setenv(ALERTS_PATH_ENV, str(tmp_path / "no-alert-stream.json"))
        built = recorder("record_security_fixture").build_payload()
        committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for doc in (built, committed):
            doc.pop("generated_at")
        assert built == committed, "re-run scripts/dev/record_security_fixture.py"
