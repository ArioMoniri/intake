"""INT-351 — the ops console composite behind ``GET /admin/ops``.

files/08 §0b F1: every panel is server-rendered through ``services/api/admin``
and the browser never names a datasource. The composite reads exactly two
things — the self-hosting registry (through the same loader as INT-183) and
Prometheus (catalogued series only) — and answers one JSON document the
admin-web page paints.

Pinned here, each with its near-miss:

- **Unknown is a state, not a zero (invariant 17).** Prometheus unconfigured,
  unreachable, answering an error, or holding no series: every tile it feeds
  says ``unknown`` with a machine reason, and carries no figure at all.
- **Every query names only catalogued series (invariant 13)** — the query table
  is checked against ``observability/metrics_catalog.yaml``.
- **Labels are ids (invariant 6).** A series whose label value is not id-shaped
  turns its tile unknown rather than painting the value.
- **The k ≥ 10 floor holds on the console too** (files/06 §8): a CSAT or wait
  cohort below it shows its count and nothing else.
- **The route is a console route.** Audited, role-guarded to the platform
  scope, and refused to a tenant-scoped role.
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
from intake_api.admin.models_source import load_models_module
from intake_api.admin.ops_console import (
    K_FLOOR,
    OPS_QUERIES,
    OPS_SCHEMA,
    build_ops_console,
)
from intake_api.admin.ops_prom import (
    ENV_PROMETHEUS_URL,
    PromClient,
    PromUnavailable,
    prom_client_from_env,
)
from intake_platform.slo import load_metrics_catalog

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
RESPONSES: dict[str, Any] = json.loads(
    (REPO / "tests" / "fixtures" / "ops" / "prometheus_responses.json").read_text("utf-8")
)
NOW = datetime(2026, 9, 26, 16, 0, tzinfo=UTC)
PROM = "http://prometheus.test:9090"


def _by_expr() -> dict[str, str]:
    return {expr: query_id for query_id, expr in OPS_QUERIES.items()}


def _prom(overrides: dict[str, Any] | None = None, status: int = 200) -> PromClient:
    lookup = _by_expr()
    answers = {**RESPONSES, **(overrides or {})}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        query_id = lookup[request.url.params["query"]]
        return httpx.Response(status, json=answers[query_id])

    return PromClient(base_url=PROM, transport=httpx.MockTransport(handler))


def _console(prom: PromClient | None) -> dict[str, Any]:
    return build_ops_console(prom=prom, models=load_models_module(), results={}, now=NOW)


def _vector(*rows: tuple[dict[str, str], str]) -> dict[str, Any]:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": m, "value": [1790438400.0, v]} for m, v in rows],
        },
    }


PROM_TILES = ("gpu", "model_usage", "clip_cache", "wait_time", "satisfaction", "cicd")


# ---------------------------------------------------------------- the query table


class TestQueryTable:
    def test_every_query_references_only_catalogued_series(self) -> None:
        catalog = load_metrics_catalog(CATALOG)
        for query_id, expr in OPS_QUERIES.items():
            assert catalog.unknown_references(expr) == frozenset(), (
                f"{query_id}: {expr} names an uncatalogued series (invariant 13)"
            )

    def test_the_fixture_answers_every_query(self) -> None:
        assert set(OPS_QUERIES) <= set(RESPONSES)


# ------------------------------------------------------------------ Prometheus client


class TestPromClient:
    def test_it_reads_an_instant_vector_and_drops_nan(self) -> None:
        samples = _prom().vector(OPS_QUERIES["work_p95"])
        assert {s.labels["type"]: s.value for s in samples} == {
            "extract_slots": 2310.5,
            "plan_follow_ups": 1840.0,
        }

    def test_an_error_status_is_a_refusal(self) -> None:
        with pytest.raises(PromUnavailable) as refusal:
            _prom(status=503).vector(OPS_QUERIES["nps"])
        assert refusal.value.code == "prometheus_http_503"

    def test_a_query_error_body_is_a_refusal(self) -> None:
        body = {"status": "error", "errorType": "bad_data", "error": "parse error"}
        with pytest.raises(PromUnavailable) as refusal:
            _prom({"nps": body}).vector(OPS_QUERIES["nps"])
        assert refusal.value.code == "prometheus_query_error"

    def test_an_unreachable_server_is_a_refusal(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        client = PromClient(base_url=PROM, transport=httpx.MockTransport(handler))
        with pytest.raises(PromUnavailable) as refusal:
            client.vector("up")
        assert refusal.value.code == "prometheus_unreachable"

    def test_unset_env_means_no_client(self) -> None:
        assert prom_client_from_env({}) is None

    @pytest.mark.parametrize(
        "url", ["prometheus:9090", "ftp://prom:21", "http://user:pw@prom:9090", "http://"]
    )
    def test_a_url_that_is_not_plain_http_is_refused(self, url: str) -> None:
        with pytest.raises(ValueError):
            prom_client_from_env({ENV_PROMETHEUS_URL: url})


# ------------------------------------------------------------------- the composite


class TestUnconfigured:
    def test_every_prometheus_tile_is_unknown_with_a_reason(self) -> None:
        payload = _console(None)
        assert payload["schema"] == OPS_SCHEMA
        assert payload["sources"]["prometheus"] == "unconfigured"
        for tile in PROM_TILES:
            assert payload["tiles"][tile]["state"] == "unknown", tile
            assert payload["tiles"][tile]["reason"] == "prometheus_unconfigured", tile

    def test_no_unknown_tile_carries_a_figure(self) -> None:
        tiles = _console(None)["tiles"]
        assert tiles["gpu"]["hosts"] == []
        assert tiles["model_usage"]["lanes"] == []
        assert tiles["clip_cache"]["hit"] is None
        assert tiles["clip_cache"]["miss"] is None
        assert tiles["wait_time"]["n"] is None
        assert tiles["wait_time"]["mean_min"] is None
        assert tiles["satisfaction"]["csat_mean"] is None
        assert tiles["satisfaction"]["nps"] is None
        assert tiles["cicd"]["workflows"] == []

    def test_the_models_tile_still_reads_the_registry(self) -> None:
        models = _console(None)["tiles"]["models"]
        assert models["state"] == "ok"
        components = [row["component"] for row in models["rows"]]
        # every registry row, in registry order, nothing hand-kept (invariant 13)
        assert components == [row.component for row in load_models_module().rows]
        assert {"qwen3.5-9b", "whisper-tr-medical", "freya-tts"} <= set(components)
        row = next(r for r in models["rows"] if r["component"] == "whisper-tr-medical")
        assert set(row) == {
            "component",
            "pin",
            "self_hostable",
            "self_hosted_now",
            "phi_path",
            "probe",
            "probe_status",
            "licence_verified_at",
            "severity",
        }
        # no sweep ran here, so no probe result — said, not assumed healthy
        assert row["probe_status"] == "no_result"


class TestConfigured:
    def test_the_recorded_answers_fill_every_tile(self) -> None:
        tiles = _console(_prom())["tiles"]
        gpu = tiles["gpu"]
        assert gpu["state"] == "ok"
        assert gpu["hosts"] == [
            {
                "host_id": "gpu-a",
                "up": True,
                "gpus": [
                    {
                        "gpu_index": "0",
                        "utilization_ratio": 0.37,
                        "memory_used_bytes": 51200 * 1024 * 1024,
                        "memory_total_bytes": 143771 * 1024 * 1024,
                    }
                ],
            }
        ]
        lanes = {(lane["kind"], lane["lane"]): lane for lane in tiles["model_usage"]["lanes"]}
        assert lanes[("work", "extract_slots")] == {
            "kind": "work",
            "lane": "extract_slots",
            "requests": 412,
            "p95_ms": 2310.5,
            "failures": 3,
        }
        # NaN is "no latency observed", never 0 ms
        assert lanes[("work", "parse_document")]["p95_ms"] is None
        assert lanes[("tts", "freya-tts")]["requests"] == 1207
        assert lanes[("adapter", "asr")]["failures"] == 2
        assert tiles["model_usage"]["window"] == "24h"
        clip = tiles["clip_cache"]
        assert (clip["hit"], clip["miss"]) == (41, 3)
        assert clip["syntheses"] == [{"gateway": "elevenlabs", "outcome": "ok", "count": 3}]
        wait = tiles["wait_time"]
        assert wait["metric_id"] == "wait.checkin_to_seen_min"
        assert (wait["n"], wait["mean_min"], wait["window"]) == (14, 21.5, "30d")
        sat = tiles["satisfaction"]
        assert (sat["csat_n"], sat["csat_mean"], sat["nps"]) == (40, 4.4, 46.67)
        cicd = tiles["cicd"]
        assert cicd["branch"] == "main"
        assert {w["workflow"]: w["conclusion"] for w in cicd["workflows"]} == {
            "ci": "failure",
            "security": "success",
        }
        ci = next(w for w in cicd["workflows"] if w["workflow"] == "ci")
        assert ci["head_sha"] == "6dd1f2a43ac9eca765beaa42e28ec1855c2d046d"
        assert ci["updated_at"] == "2026-09-26T15:06:45Z"

    def test_every_figure_names_its_window_and_instant(self) -> None:
        payload = _console(_prom())
        assert payload["generated_at"] == "2026-09-26T16:00:00Z"
        for tile in ("model_usage", "wait_time", "satisfaction"):
            assert payload["tiles"][tile]["window"], tile

    def test_an_empty_answer_is_no_series_not_zero(self) -> None:
        empty = _vector()
        silent = {"gpu_host_up": empty, "clip_lookups": empty, "clip_syntheses": empty}
        tiles = _console(_prom({**silent, "ci_runs": empty}))["tiles"]
        assert (tiles["gpu"]["state"], tiles["gpu"]["reason"]) == ("unknown", "no_series")
        assert tiles["clip_cache"]["reason"] == "no_series"
        assert tiles["clip_cache"]["hit"] is None
        assert tiles["cicd"]["reason"] == "no_series"

    def test_a_failing_ci_collector_reads_unknown_even_with_stale_series(self) -> None:
        down = _vector(({"source": "gpu_host"}, "1"), ({"source": "ci"}, "0"))
        cicd = _console(_prom({"collector_up": down}))["tiles"]["cicd"]
        assert (cicd["state"], cicd["reason"]) == ("unknown", "collector_source_failing")
        assert cicd["workflows"] == []

    def test_a_down_host_is_down_and_carries_no_reading(self) -> None:
        down = _vector(({"host_id": "gpu-a"}, "0"))
        gpu = _console(_prom({"gpu_host_up": down}))["tiles"]["gpu"]
        assert gpu["state"] == "ok"
        assert gpu["hosts"] == [{"host_id": "gpu-a", "up": False, "gpus": []}]

    def test_one_failing_query_does_not_blank_the_other_tiles(self) -> None:
        broken = {"status": "error", "errorType": "timeout", "error": "x"}
        tiles = _console(_prom({"csat_count": broken}))["tiles"]
        assert tiles["satisfaction"]["state"] == "unknown"
        assert tiles["satisfaction"]["reason"] == "prometheus_query_error"
        assert tiles["gpu"]["state"] == "ok"


class TestPhiAndFloor:
    def test_a_label_value_that_is_not_id_shaped_turns_the_tile_unknown(self) -> None:
        leaked = _vector(({"type": "Ayşe Yılmaz"}, "4"))
        usage = _console(_prom({"work_requests": leaked}))["tiles"]["model_usage"]
        assert (usage["state"], usage["reason"]) == ("unknown", "label_not_id_shaped")
        assert usage["lanes"] == []
        assert "Ayşe" not in json.dumps(_console(_prom({"work_requests": leaked})))

    def test_an_unexpected_label_turns_the_tile_unknown(self) -> None:
        # a series re-sliced by a label the query did not ask for is a cohort
        # the tile was never designed to show (files/08 §0c F9)
        sliced = _vector(({"type": "extract_slots", "tenant": "tenant-a"}, "4"))
        usage = _console(_prom({"work_requests": sliced}))["tiles"]["model_usage"]
        assert usage["reason"] == "unexpected_label"

    def test_a_csat_cohort_below_the_floor_shows_its_count_only(self) -> None:
        sat = _console(_prom({"csat_count": _vector(({}, "4")), "csat_sum": _vector(({}, "18"))}))[
            "tiles"
        ]["satisfaction"]
        assert sat["state"] == "ok"
        assert sat["csat_n"] == 4
        assert sat["csat_suppressed"] is True
        assert sat["csat_mean"] is None
        assert sat["k_floor"] == K_FLOOR == 10

    def test_a_wait_cohort_below_the_floor_shows_its_count_only(self) -> None:
        wait = _console(_prom({"wait_count": _vector(({}, "3")), "wait_sum": _vector(({}, "95"))}))[
            "tiles"
        ]["wait_time"]
        assert (wait["n"], wait["suppressed"], wait["mean_min"]) == (3, True, None)

    def test_the_payload_carries_no_target_beside_a_figure(self) -> None:
        # invariant 20: csat.score's catalogue target is metadata, not a verdict
        text = json.dumps(_console(_prom()))
        assert "target" not in text
        assert "4.3" not in text


# ------------------------------------------------------------------------ the route


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
    monkeypatch.delenv(ENV_PROMETHEUS_URL, raising=False)
    yield from build_admin_harness(tmp_path)


class TestRoute:
    def test_the_route_serves_the_composite_to_a_platform_role(self, harness: ApiHarness) -> None:
        response = harness.client.get("/admin/ops", headers=bearer("sre_oncall"))
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema"] == OPS_SCHEMA
        assert payload["tiles"]["gpu"]["reason"] == "prometheus_unconfigured"

    def test_a_tenant_scoped_role_is_refused(self, harness: ApiHarness) -> None:
        response = harness.client.get("/admin/ops", headers=bearer("tenant_admin"))
        assert response.status_code == 403

    def test_no_token_is_refused(self, harness: ApiHarness) -> None:
        assert harness.client.get("/admin/ops").status_code == 401

    def test_an_unreachable_prometheus_reads_unknown_through_the_route(
        self, harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # .invalid never resolves (RFC 6761): no socket reaches anything real
        monkeypatch.setenv(ENV_PROMETHEUS_URL, "http://prometheus.invalid:9090")
        payload = harness.client.get("/admin/ops", headers=bearer("sre_oncall")).json()
        assert payload["sources"]["prometheus"] == "unreachable"
        assert payload["tiles"]["cicd"]["reason"] == "prometheus_unreachable"
