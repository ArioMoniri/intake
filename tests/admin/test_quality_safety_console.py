"""INT-565 — `GET /admin/quality-safety`, Clinical quality & safety as a console route.

The console's view-model (apps/admin-web/src/safety, INT-185) renders this
body. Held here: every triage level is the rules engine's (invariant 1); the
false-RED queue is the INT-175 contract verbatim, annotate-only, with its
content read refused (HB-L6); PolicyGuard blocks are read from the scrape at
serve time by the sealed violation classes, and an unread or drifted scrape
paints no count — never a zero (invariant 17); a planned series promoted to
live trips the builder; and the committed fixture is the route's own builder.
"""

from __future__ import annotations

import json
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
from intake_api.admin.quality_safety_console import (
    QUALITY_SAFETY_LABELS,
    QUALITY_SAFETY_QUERIES,
    quality_safety_payload,
)
from intake_platform.admin.console_vocab import POLICYGUARD_CLASSES
from intake_platform.slo import MetricsCatalog
from protocols.taxonomy import load_taxonomy
from recorders import recorder

REPO = Path(__file__).resolve().parents[2]
TAXONOMY = REPO / "packages" / "protocols" / "taxonomy" / "branches.yaml"
FIXTURE = REPO / "apps" / "admin-web" / "e2e" / "fixtures" / "safety.payload.json"
PROM = "http://prometheus.test:9090"
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
    monkeypatch.delenv(ENV_PROMETHEUS_URL, raising=False)
    yield from build_admin_harness(tmp_path)


def _prom(result: list[dict[str, Any]], seen: list[str] | None = None) -> PromClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request.url.params["query"])
        return httpx.Response(
            200, json={"status": "success", "data": {"resultType": "vector", "result": result}}
        )

    return PromClient(base_url=PROM, transport=httpx.MockTransport(handler))


def _sample(cls: str, value: str) -> dict[str, Any]:
    return {"metric": {"class": cls}, "value": [1761800000, value]}


def _build(reading: Reading, catalog: MetricsCatalog | None = None) -> dict[str, Any]:
    return quality_safety_payload(
        catalog=catalog or load_catalog(),
        taxonomy=load_taxonomy(TAXONOMY),
        policyguard=reading,
        generated_at=NOW,
    )


def _policyguard_reading(result: list[dict[str, Any]]) -> Reading:
    return read_counts(
        _prom(result), QUALITY_SAFETY_QUERIES, QUALITY_SAFETY_LABELS, "policyguard_blocks"
    )


class TestTheRoute:
    def test_a_clinical_lead_reads_the_composite_unread_scrape_and_all(
        self, harness: ApiHarness
    ) -> None:
        response = harness.client.get("/admin/quality-safety", headers=bearer("clinical_lead"))
        assert response.status_code == 200
        body = response.json()
        assert {row["produced_by"] for row in body["triage_events"]["levels"]} == {"rules_engine"}
        assert body["triage_events"]["candidate_flag_cap"] == "YELLOW_REVIEW"
        queue = body["false_red_queue"]
        assert queue["content_read_state"] == "refused" and queue["items"] == []
        guard = body["policyguard_classes"]
        assert guard["source_available"] is False
        assert guard["source_reason"] == "prometheus_unconfigured"
        assert all(row["count"] is None for row in guard["classes"])

    def test_a_tenant_scoped_role_is_refused(self, harness: ApiHarness) -> None:
        # the counts are summed over every tenant: a one-tenant role is refused
        for role in ("tenant_clinical_responsible", "tenant_admin", "researcher"):
            response = harness.client.get("/admin/quality-safety", headers=bearer(role))
            assert response.status_code == 403, role

    def test_an_unreachable_scrape_reads_unavailable_through_the_route(
        self, harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # .invalid never resolves (RFC 6761): no socket reaches anything real
        monkeypatch.setenv(ENV_PROMETHEUS_URL, "http://prometheus.invalid:9090")
        body = harness.client.get("/admin/quality-safety", headers=bearer("auditor")).json()
        assert body["policyguard_classes"]["source_reason"] == "prometheus_unreachable"
        assert all(row["count"] is None for row in body["policyguard_classes"]["classes"])


class TestPolicyGuardBlocks:
    def test_a_read_scrape_paints_every_sealed_class_over_the_window(self) -> None:
        seen: list[str] = []
        reading = read_counts(
            _prom([_sample("diagnosis", "3.04"), _sample("register", "1")], seen),
            QUALITY_SAFETY_QUERIES,
            QUALITY_SAFETY_LABELS,
            "policyguard_blocks",
        )
        guard = _build(reading)["policyguard_classes"]
        assert seen == ["sum by (class) (increase(policyguard_blocks_total[24h]))"]
        assert guard["source_available"] is True and guard["window"] == "24h"
        counts = {row["class"]: row["count"] for row in guard["classes"]}
        assert list(counts) == list(POLICYGUARD_CLASSES)
        assert counts["diagnosis"] == 3 and counts["register"] == 1 and counts["jargon"] == 0

    def test_near_miss_a_class_off_the_sealed_set_paints_no_count(self) -> None:
        guard = _build(_policyguard_reading([_sample("made_up_class", "2")]))["policyguard_classes"]
        assert guard["source_available"] is False
        assert guard["source_reason"] == "unexpected_label"
        assert all(row["count"] is None for row in guard["classes"])

    def test_near_miss_a_label_that_is_not_an_id_paints_no_count(self) -> None:
        # a sentence where a class should be is patient text reaching a label
        guard = _build(_policyguard_reading([_sample("Hasta ağrı dedi", "1")]))[
            "policyguard_classes"
        ]
        assert guard["source_reason"] == "label_not_id_shaped"

    def test_every_query_names_only_catalogued_series(self) -> None:
        catalog = load_catalog()
        for query_id, expr in QUALITY_SAFETY_QUERIES.items():
            assert catalog.unknown_references(expr) == frozenset(), query_id


class TestPlannedSeriesTripwire:
    def test_promoting_triage_events_to_live_refuses_the_zero_skeleton(self) -> None:
        catalog = load_catalog()
        promoted = catalog.model_copy(
            update={
                "metrics": [
                    m.model_copy(update={"status": "live"})
                    if m.spec_id == "triage.events_total"
                    else m
                    for m in catalog.metrics
                ]
            }
        )
        with pytest.raises(ValueError, match="triage.events_total is catalogued live"):
            _build(Reading.unavailable("prometheus_unconfigured"), promoted)


class TestTheFixtureIsTheRoutesOwn:
    def test_the_committed_fixture_is_the_builder_with_no_scrape(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(REPO)
        built = recorder("record_safety_fixture").build_payload()
        committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for doc in (built, committed):
            doc.pop("generated_at")
        assert built == committed, "re-run scripts/dev/record_safety_fixture.py"
