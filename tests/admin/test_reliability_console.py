"""INT-181 — the reliability composite behind ``GET /admin/reliability``.

Acceptance, verbatim (docs/backlog/issues.yaml INT-181): *"SLO tiles, burn
rates, probe matrix, dependency health from live dev stack (not mock JSON)"*.

files/08 §3 names the Overview and Reliability modules; §0b F1 says every
panel is server-rendered through ``services/api/admin``. The composite reads
four live sources and nothing else — the SLO files (``docs/slo``), Prometheus
(catalogued series only), the self-hosting registry and the probe runner's
last sweep — and every tile fails closed to *unknown* on its own.

Pinned here, each with its near-miss:

- **One tile per declared SLO**, its lanes and windows taken from the SLO file
  (files/10 §6: page at 14.4x/1h+5m and 6x/6h+30m, ticket at 1x/3d+6h, over a
  28 d objective window) — never a second copy of the policy.
- **Every query names only catalogued series (invariant 13).**
- **An absent error series is zero errors only beside traffic**; no traffic is
  no SLI, never a perfect one.
- **Unknown is a state, not a zero or a stale value (invariant 17).**
- **Ids only (invariant 6)**; the probe runner's free-text ``detail`` never
  leaves the API.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from admin_harness import bearer, build_admin_harness
from api_harness import ApiHarness
from intake_api.admin.models_source import PROBE_RESULTS_ENV
from intake_api.admin.ops_prom import ENV_PROMETHEUS_URL, PromClient
from intake_api.admin.reliability_console import (
    ENV_SLO_DIR,
    RELIABILITY_SCHEMA,
    STALE_AFTER_S,
    Sweep,
    build_reliability_console,
    load_reliability_console,
    load_slo_files,
    load_sweep,
    reliability_queries,
)
from intake_api.admin.reliability_slo import SliOutsideGrammar, rerange, slo_windows
from intake_platform.slo import load_metrics_catalog, metric_references
from intake_probes.registry import load_registry
from intake_probes.runner import SWEEP_INTERVAL_S

REPO = Path(__file__).resolve().parents[2]
SLO_DIR = REPO / "docs" / "slo"
REGISTRY = REPO / "observability" / "registry.yaml"
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
FIXTURES = REPO / "tests" / "fixtures" / "reliability"
RESPONSES: dict[str, Any] = json.loads((FIXTURES / "prometheus_responses.json").read_text("utf-8"))
NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
PROM = "http://prometheus.test:9090"
UNCONFIGURED = Sweep(records=None, reason="probe_results_unconfigured")


def _files() -> tuple[Any, ...]:
    return load_slo_files(SLO_DIR)


def _vector(*rows: tuple[dict[str, str], str]) -> dict[str, Any]:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": m, "value": [1790496000.0, v]} for m, v in rows],
        },
    }


EMPTY = _vector()


def _prom(overrides: dict[str, Any] | None = None) -> PromClient:
    lookup = {expr: query_id for query_id, expr in reliability_queries(_files()).items()}
    answers = {**RESPONSES, **(overrides or {})}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        return httpx.Response(200, json=answers[lookup[request.url.params["query"]]])

    return PromClient(base_url=PROM, transport=httpx.MockTransport(handler))


def _unreachable() -> PromClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    return PromClient(base_url=PROM, transport=httpx.MockTransport(handler))


def _row(component: str, status: str, at: datetime | None, latency: float | None = 3.2) -> dict:
    row: dict[str, Any] = {
        "component": component,
        "probe": load_registry(REGISTRY).get(component).probe.value,
        "status": status,
        "latency_ms": latency if status != "skipped" else None,
        "detail": f"free text from the probe about {component} at 10.0.0.7",
    }
    if at is not None:
        row["checked_at"] = at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return row


def _sweep(tmp_path: Path, rows: list[dict[str, Any]]) -> Sweep:
    path = tmp_path / "sweep.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return load_sweep({PROBE_RESULTS_ENV: str(path)})


def _fresh(tmp_path: Path, **status: str) -> Sweep:
    at = NOW - timedelta(seconds=20)
    return _sweep(tmp_path, [_row(c, s, at) for c, s in status.items()])


def _console(
    prom: PromClient | None,
    sweep: Sweep = UNCONFIGURED,
    now: datetime = NOW,
    *,
    slo_files: tuple[Any, ...] | None = None,
    registry: bool = True,
) -> dict[str, Any]:
    return build_reliability_console(
        prom=prom,
        slo_files=_files() if slo_files is None else slo_files,
        registry=load_registry(REGISTRY) if registry else None,
        sweep=sweep,
        now=now,
    )


def _slo(payload: dict[str, Any], service: str, name: str) -> dict[str, Any]:
    return next(t for t in payload["slos"]["tiles"] if (t["service"], t["slo"]) == (service, name))


def _declared() -> list[tuple[str, str]]:
    return [(f.service, s.name) for f in _files() for s in f.slos]


# ------------------------------------------------------------------ the query table


class TestQueryTable:
    def test_every_query_references_only_catalogued_series(self) -> None:
        catalog = load_metrics_catalog(CATALOG)
        for query_id, expr in reliability_queries(_files()).items():
            assert catalog.unknown_references(expr) == frozenset(), (
                f"{query_id}: {expr} names an uncatalogued series (invariant 13)"
            )

    def test_every_declared_slo_is_queried_over_every_window_its_file_declares(self) -> None:
        queries = reliability_queries(_files())
        for slo_file in _files():
            for slo in slo_file.slos:
                declared = {slo.window} | {
                    window
                    for _, alert in slo.burn_rate_alerts.named_alerts()
                    for window in (alert.long_window, alert.short_window)
                }
                assert set(slo_windows(slo)) == declared
                for window in declared:
                    assert f"slo:{slo_file.service}:{slo.name}:{window}" in queries

    def test_the_windows_are_the_files_own_sre_workbook_windows(self) -> None:
        api = next(f for f in _files() if f.service == "api")
        availability = next(s for s in api.slos if s.name == "availability")
        assert slo_windows(availability) == ("5m", "30m", "1h", "6h", "3d", "28d")

    def test_a_reranged_sli_names_exactly_the_declared_series(self) -> None:
        for slo_file in _files():
            for slo in slo_file.slos:
                for window in slo_windows(slo):
                    assert metric_references(rerange(slo.sli, window)) == metric_references(slo.sli)

    def test_an_absent_error_series_is_zero_only_beside_traffic(self) -> None:
        # a healthy API has never answered a 5xx, so its error series does not
        # exist and a bare ratio would be EMPTY; each sum term falls back to 0,
        # and with no traffic at all 0/0 is NaN, which the client drops
        api = next(f for f in _files() if f.service == "api")
        availability = next(s for s in api.slos if s.name == "availability")
        assert rerange(availability.sli, "1h") == (
            '(sum(rate(http_requests_total{service="api",status=~"5.."}[1h])) or vector(0))'
            ' / (sum(rate(http_requests_total{service="api"}[1h])) or vector(0))'
        )

    def test_an_sli_outside_the_console_grammar_is_refused_not_guessed(self) -> None:
        with pytest.raises(SliOutsideGrammar):
            rerange("rate(http_requests_total[5m])", "1h")
        with pytest.raises(SliOutsideGrammar):
            rerange("sum(rate(http_requests_total[5m])) / sum(increase(x_total[5m]))", "1h")

    def test_the_fixture_answers_every_query(self) -> None:
        assert set(reliability_queries(_files())) <= set(RESPONSES)


class TestSloFilesAreErrorRatios:
    """docs/slo/api.yaml fixes the convention — every SLI is the ERROR ratio —
    and langfuse.yaml and siem.yaml claim to follow it. Read as a good ratio,
    a healthy boundary would burn its budget a thousand times over."""

    @pytest.mark.parametrize(
        ("service", "refusals"),
        [("langfuse", "llm_trace_fields_refused_total"), ("siem", "siem_alerts_refused_total")],
    )
    def test_the_numerator_is_the_refusal_counter(self, service: str, refusals: str) -> None:
        slo_file = next(f for f in _files() if f.service == service)
        numerator = " ".join(slo_file.slos[0].sli.split()).split(" / ")[0]
        assert metric_references(numerator) == frozenset({refusals})


# ---------------------------------------------------------------------- SLO tiles


class TestSloTiles:
    def test_one_tile_per_declared_slo_in_file_order(self) -> None:
        payload = _console(_prom())
        assert payload["schema"] == RELIABILITY_SCHEMA
        assert payload["slos"]["state"] == "ok"
        tiles = [(t["service"], t["slo"]) for t in payload["slos"]["tiles"]]
        assert tiles == _declared()
        assert len(tiles) == 8

    def test_a_tile_carries_objective_sli_budget_and_every_declared_lane(self) -> None:
        tile = _slo(_console(_prom()), "api", "availability")
        assert tile["state"] == "ok"
        assert tile["objective_percent"] == 99.9
        assert tile["slo_window"] == "28d"
        # 28 d error ratio 0.0004 against a 0.001 budget
        assert tile["sli_percent"] == pytest.approx(99.96)
        assert tile["error_budget_remaining"] == pytest.approx(0.6)
        lanes = {lane["lane"]: lane for lane in tile["burn_rates"]}
        assert lanes["fast"] == {
            "lane": "fast",
            "severity": "page",
            "factor": 14.4,
            "long_window": "1h",
            "short_window": "5m",
            "long_burn": pytest.approx(0.6),
            "short_burn": pytest.approx(0.0),
            "condition_met": False,
        }
        assert (lanes["slow"]["long_window"], lanes["slow"]["short_window"]) == ("6h", "30m")
        assert (lanes["ticket"]["long_window"], lanes["ticket"]["short_window"]) == ("3d", "6h")
        assert lanes["ticket"]["severity"] == "ticket"

    def test_the_burn_condition_is_both_windows_above_the_factor(self) -> None:
        voice = _slo(_console(_prom()), "voice-runtime", "availability")
        fast = next(lane for lane in voice["burn_rates"] if lane["lane"] == "fast")
        assert fast["long_burn"] > 14.4 and fast["short_burn"] > 14.4
        assert fast["condition_met"] is True
        # near-miss: one window over the factor is not the condition
        latency = _slo(_console(_prom()), "api", "latency")
        ticket = next(lane for lane in latency["burn_rates"] if lane["lane"] == "ticket")
        assert ticket["long_burn"] > 1.0 > ticket["short_burn"]
        assert ticket["condition_met"] is False

    def test_an_overspent_budget_reads_negative_not_clamped(self) -> None:
        overs = {"slo:api:availability:28d": _vector(({}, "0.0025"))}
        tile = _slo(_console(_prom(overs)), "api", "availability")
        assert tile["error_budget_remaining"] == pytest.approx(-1.5)

    def test_a_window_with_no_traffic_is_null_not_zero(self) -> None:
        quiet = {"slo:api:availability:5m": EMPTY}
        tile = _slo(_console(_prom(quiet)), "api", "availability")
        fast = next(lane for lane in tile["burn_rates"] if lane["lane"] == "fast")
        assert fast["short_burn"] is None
        assert fast["condition_met"] is None
        assert tile["state"] == "ok"

    def test_a_service_with_no_series_reads_unknown(self) -> None:
        tile = _slo(_console(_prom()), "langfuse", "trace_emission")
        assert (tile["state"], tile["reason"]) == ("unknown", "no_series")
        assert tile["sli_percent"] is None
        assert tile["error_budget_remaining"] is None
        assert all(lane["long_burn"] is None for lane in tile["burn_rates"])
        # the declaration is not a figure: the objective and lanes stay
        assert tile["objective_percent"] == 99.9
        assert [lane["lane"] for lane in tile["burn_rates"]] == ["fast", "slow", "ticket"]

    def test_an_error_ratio_outside_zero_to_one_is_refused(self) -> None:
        bent = {"slo:api:availability:1h": _vector(({}, "1.7"))}
        tile = _slo(_console(_prom(bent)), "api", "availability")
        assert (tile["state"], tile["reason"]) == ("unknown", "sli_out_of_range")

    def test_a_labelled_sli_answer_is_refused(self) -> None:
        # a ratio re-sliced by tenant is a cohort the tile was never designed to show
        sliced = {"slo:api:availability:1h": _vector(({"tenant": "tenant-a"}, "0.001"))}
        tile = _slo(_console(_prom(sliced)), "api", "availability")
        assert (tile["state"], tile["reason"]) == ("unknown", "unexpected_label")

    def test_one_failing_query_blanks_its_own_slo_only(self) -> None:
        broken = {"slo:api:latency:6h": {"status": "error", "errorType": "timeout", "error": "x"}}
        payload = _console(_prom(broken))
        assert _slo(payload, "api", "latency")["reason"] == "prometheus_query_error"
        assert _slo(payload, "api", "availability")["state"] == "ok"


class TestEachSloTileFailsClosed:
    @pytest.mark.parametrize(("service", "name"), _declared())
    def test_an_unreachable_prometheus_blanks_the_tile(self, service: str, name: str) -> None:
        payload = _console(_unreachable())
        tile = _slo(payload, service, name)
        assert (tile["state"], tile["reason"]) == ("unknown", "prometheus_unreachable")
        assert tile["sli_percent"] is None
        assert tile["error_budget_remaining"] is None
        for lane in tile["burn_rates"]:
            assert (lane["long_burn"], lane["short_burn"], lane["condition_met"]) == (
                None,
                None,
                None,
            )

    def test_an_unconfigured_prometheus_blanks_every_slo_tile(self) -> None:
        payload = _console(None)
        assert payload["sources"]["prometheus"] == "unconfigured"
        for tile in payload["slos"]["tiles"]:
            assert (tile["state"], tile["reason"]) == ("unknown", "prometheus_unconfigured")

    def test_an_sli_outside_the_grammar_is_its_own_unknown_tile(self) -> None:
        # a declared SLO the console cannot read is shown as such, never guessed
        api = next(f for f in _files() if f.service == "api")
        odd = api.model_copy(
            update={
                "slos": [
                    api.slos[0].model_copy(
                        update={"sli": 'rate(http_requests_total{service="api"}[5m])'}
                    )
                ]
            }
        )
        assert not any(q.startswith("slo:api:") for q in reliability_queries((odd,)))
        tile = _slo(_console(_prom(), slo_files=(odd,)), "api", "availability")
        assert (tile["state"], tile["reason"]) == ("unknown", "sli_outside_console_grammar")
        assert tile["sli_percent"] is None

    def test_an_empty_slo_directory_is_unreadable_not_zero_slos(self, tmp_path: Path) -> None:
        payload = load_reliability_console(NOW, env={ENV_SLO_DIR: str(tmp_path)})
        assert payload["slos"]["reason"] == "slo_files_unreadable"

    def test_unreadable_slo_files_blank_the_section(self, tmp_path: Path) -> None:
        (tmp_path / "broken.yaml").write_text("service: [not, a, name]\n", encoding="utf-8")
        payload = load_reliability_console(NOW, env={ENV_SLO_DIR: str(tmp_path)})
        assert payload["slos"] == {
            "state": "unknown",
            "reason": "slo_files_unreadable",
            "tiles": [],
        }
        assert payload["sources"]["slo_files"] == "unreadable"


# -------------------------------------------------------------------- probe matrix


class TestProbeMatrix:
    def test_every_registry_probe_is_a_row_with_its_last_result_and_age(
        self, tmp_path: Path
    ) -> None:
        sweep = _sweep(
            tmp_path,
            [
                _row("postgres", "healthy", NOW - timedelta(seconds=42), 4.5),
                _row("redis", "unhealthy", NOW - timedelta(seconds=42), 1.25),
                _row("voice-runtime", "skipped", NOW - timedelta(seconds=42)),
            ],
        )
        matrix = _console(None, sweep)["probe_matrix"]
        assert matrix["state"] == "ok"
        assert matrix["sweep_interval_s"] == SWEEP_INTERVAL_S == 60
        assert matrix["stale_after_s"] == STALE_AFTER_S == 180
        components = [row["component"] for row in matrix["rows"]]
        assert components == [entry.component for entry in load_registry(REGISTRY)]
        postgres = next(row for row in matrix["rows"] if row["component"] == "postgres")
        assert postgres == {
            "component": "postgres",
            "probe": "postgres_select1",
            "phi_path": True,
            "self_hosted_now": True,
            "budget_ms": load_registry(REGISTRY).get("postgres").budget_ms,
            "status": "healthy",
            "latency_ms": 4.5,
            "checked_at": "2026-09-27T09:59:18Z",
            "age_s": 42,
            "stale": False,
        }
        skipped = next(row for row in matrix["rows"] if row["component"] == "voice-runtime")
        assert (skipped["status"], skipped["latency_ms"]) == ("skipped", None)

    def test_a_registry_row_absent_from_the_sweep_reads_no_result(self, tmp_path: Path) -> None:
        matrix = _console(None, _fresh(tmp_path, postgres="healthy"))["probe_matrix"]
        redis = next(row for row in matrix["rows"] if row["component"] == "redis")
        assert (redis["status"], redis["checked_at"], redis["age_s"]) == ("no_result", None, None)
        assert redis["stale"] is True

    def test_a_result_older_than_three_sweeps_is_flagged_stale(self, tmp_path: Path) -> None:
        sweep = _sweep(
            tmp_path,
            [
                _row("postgres", "healthy", NOW - timedelta(seconds=STALE_AFTER_S)),
                _row("redis", "healthy", NOW - timedelta(seconds=STALE_AFTER_S + 1)),
            ],
        )
        rows = {row["component"]: row for row in _console(None, sweep)["probe_matrix"]["rows"]}
        # near-miss: exactly at the bound is still fresh
        assert rows["postgres"]["stale"] is False
        assert rows["redis"]["stale"] is True
        assert rows["redis"]["status"] == "healthy"  # the LAST result, flagged as such

    def test_a_result_without_an_instant_is_stale_not_fresh(self, tmp_path: Path) -> None:
        matrix = _console(None, _sweep(tmp_path, [_row("postgres", "healthy", None)]))
        postgres = next(r for r in matrix["probe_matrix"]["rows"] if r["component"] == "postgres")
        assert (postgres["age_s"], postgres["stale"]) == (None, True)

    def test_a_result_from_the_future_is_stale_not_fresh(self, tmp_path: Path) -> None:
        ahead = _sweep(tmp_path, [_row("postgres", "healthy", NOW + timedelta(minutes=5))])
        postgres = next(
            r for r in _console(None, ahead)["probe_matrix"]["rows"] if r["component"] == "postgres"
        )
        assert (postgres["age_s"], postgres["stale"]) == (None, True)

    def test_the_probe_detail_never_leaves_the_api(self, tmp_path: Path) -> None:
        text = json.dumps(_console(_prom(), _fresh(tmp_path, postgres="unhealthy")))
        assert "free text" not in text
        assert "10.0.0.7" not in text
        assert '"detail"' not in text

    def test_the_recorded_sweep_is_the_runners_own_wire_shape(self) -> None:
        # tests/fixtures/reliability/probe_sweep.json is the real runner's
        # output on the recording host (scripts/dev/record_reliability_fixture.py)
        sweep = load_sweep({PROBE_RESULTS_ENV: str(FIXTURES / "probe_sweep.json")})
        assert sweep.reason is None and sweep.records is not None
        assert set(sweep.records) == {entry.component for entry in load_registry(REGISTRY)}
        assert all(record.checked_at is not None for record in sweep.records.values())


class TestProbeMatrixFailsClosed:
    @pytest.mark.parametrize(
        ("env", "reason"),
        [
            ({}, "probe_results_unconfigured"),
            ({PROBE_RESULTS_ENV: "   "}, "probe_results_unconfigured"),
            ({PROBE_RESULTS_ENV: "/nonexistent/intake/sweep.json"}, "probe_results_missing"),
        ],
    )
    def test_an_absent_sweep_blanks_the_matrix(self, env: dict[str, str], reason: str) -> None:
        matrix = _console(None, load_sweep(env))["probe_matrix"]
        assert (matrix["state"], matrix["reason"], matrix["rows"]) == ("unknown", reason, [])

    @pytest.mark.parametrize("body", ["{not json", '[{"component": "postgres"}]', '{"a": 1}'])
    def test_an_unreadable_sweep_blanks_the_matrix(self, tmp_path: Path, body: str) -> None:
        path = tmp_path / "sweep.json"
        path.write_text(body, encoding="utf-8")
        sweep = load_sweep({PROBE_RESULTS_ENV: str(path)})
        assert sweep == Sweep(records=None, reason="probe_results_unreadable")
        matrix = _console(None, sweep)["probe_matrix"]
        assert (matrix["state"], matrix["reason"], matrix["rows"]) == (
            "unknown",
            "probe_results_unreadable",
            [],
        )

    def test_an_unreadable_registry_blanks_the_matrix(self, tmp_path: Path) -> None:
        payload = _console(None, _fresh(tmp_path, postgres="healthy"), registry=False)
        matrix = payload["probe_matrix"]
        assert (matrix["state"], matrix["reason"], matrix["rows"]) == (
            "unknown",
            "registry_unreadable",
            [],
        )
        assert payload["sources"]["registry"] == "unreadable"


# ---------------------------------------------------------------- dependency health


def _deps(payload: dict[str, Any]) -> dict[str, Any]:
    deps: dict[str, Any] = payload["dependencies"]
    return deps


class TestDependencyComponents:
    def test_every_self_hosted_component_with_its_fallback_edge(self, tmp_path: Path) -> None:
        sweep = _fresh(
            tmp_path, postgres="healthy", redis="healthy", backups="unhealthy", minio="healthy"
        )
        section = _deps(_console(None, sweep))["components"]
        assert section["state"] == "ok"
        enabled = [e.component for e in load_registry(REGISTRY) if e.self_hosted_now]
        assert [row["component"] for row in section["rows"]] == enabled
        assert {"postgres", "redis", "openbao", "minio"} <= set(enabled)
        rows = {row["component"]: row for row in section["rows"]}
        assert rows["postgres"] == {
            "component": "postgres",
            "probe": "postgres_select1",
            "health": "healthy",
            "health_reason": None,
            "checked_at": "2026-09-27T09:59:40Z",
            "fallback_kind": "component",
            "fallback": "backups",
            "fallback_health": "unhealthy",
        }
        assert (rows["redis"]["fallback_kind"], rows["redis"]["fallback"]) == ("none", None)
        assert rows["redis"]["fallback_health"] is None
        # a row the sweep did not reach is unknown, and so is a fallback it did not reach
        assert (rows["openbao"]["health"], rows["openbao"]["health_reason"]) == (
            "unknown",
            "no_result",
        )

    def test_an_in_process_fallback_is_as_healthy_as_its_host(self, tmp_path: Path) -> None:
        # deid-tr-ner-v1 falls back to intake_platform.redaction, which ships
        # inside the same artefact (the INT-022 gate's in-process semantics)
        assert load_registry(REGISTRY).get("deid-tr-ner-v1").fallback.startswith("in-process:")
        sweep = _fresh(tmp_path, **{"deid-tr-ner-v1": "healthy"})
        rows = {r["component"]: r for r in _deps(_console(None, sweep))["components"]["rows"]}
        assert rows["deid-tr-ner-v1"]["fallback_kind"] == "in_process"
        assert rows["deid-tr-ner-v1"]["fallback"] is None
        assert rows["deid-tr-ner-v1"]["fallback_health"] == "healthy"

    def test_a_stale_result_is_unknown_never_the_last_value(self, tmp_path: Path) -> None:
        old = NOW - timedelta(seconds=STALE_AFTER_S + 60)
        sweep = _sweep(tmp_path, [_row("postgres", "healthy", old)])
        rows = {r["component"]: r for r in _deps(_console(None, sweep))["components"]["rows"]}
        assert (rows["postgres"]["health"], rows["postgres"]["health_reason"]) == (
            "unknown",
            "sweep_stale",
        )
        assert rows["postgres"]["checked_at"] is None

    @pytest.mark.parametrize(
        ("sweep", "reason"),
        [
            (Sweep(None, "probe_results_unconfigured"), "probe_results_unconfigured"),
            (Sweep(None, "probe_results_unreadable"), "probe_results_unreadable"),
        ],
    )
    def test_fails_closed_without_a_sweep(self, sweep: Sweep, reason: str) -> None:
        section = _deps(_console(_prom(), sweep))["components"]
        assert (section["state"], section["reason"], section["rows"]) == ("unknown", reason, [])

    def test_fails_closed_without_a_registry(self, tmp_path: Path) -> None:
        section = _deps(_console(None, _fresh(tmp_path, postgres="healthy"), registry=False))
        assert (section["components"]["state"], section["components"]["reason"]) == (
            "unknown",
            "registry_unreadable",
        )


class TestDependencyPrometheus:
    def test_an_answering_prometheus_is_healthy(self) -> None:
        section = _deps(_console(_prom()))["prometheus"]
        assert section == {
            "state": "ok",
            "reason": None,
            "health": "healthy",
            "health_reason": None,
        }

    def test_an_unreachable_prometheus_is_unhealthy_with_its_code(self) -> None:
        section = _deps(_console(_unreachable()))["prometheus"]
        assert section == {
            "state": "ok",
            "reason": None,
            "health": "unhealthy",
            "health_reason": "prometheus_unreachable",
        }

    def test_an_unconfigured_prometheus_is_unknown(self) -> None:
        section = _deps(_console(None))["prometheus"]
        assert section == {
            "state": "unknown",
            "reason": "prometheus_unconfigured",
            "health": None,
            "health_reason": None,
        }


class TestDependencyGpuHosts:
    def test_hosts_come_from_the_collector_series(self) -> None:
        section = _deps(_console(_prom()))["gpu_hosts"]
        assert section["state"] == "ok"
        assert section["rows"] == [{"host_id": "gpu-a", "health": "healthy"}]

    def test_a_down_host_is_unhealthy(self) -> None:
        down = {"gpu_host_up": _vector(({"host_id": "gpu-a"}, "0"))}
        section = _deps(_console(_prom(down)))["gpu_hosts"]
        assert section["rows"] == [{"host_id": "gpu-a", "health": "unhealthy"}]

    @pytest.mark.parametrize(
        ("prom", "reason"),
        [
            (lambda: _prom({"gpu_host_up": EMPTY}), "no_series"),
            (_unreachable, "prometheus_unreachable"),
            (lambda: None, "prometheus_unconfigured"),
        ],
    )
    def test_fails_closed(self, prom: Any, reason: str) -> None:
        section = _deps(_console(prom()))["gpu_hosts"]
        assert (section["state"], section["reason"], section["rows"]) == ("unknown", reason, [])


class TestDependencyVendors:
    """INT-100's ``vendor_breaker_state{component,state}``, one-hot."""

    def test_breaker_states_map_to_health(self) -> None:
        section = _deps(_console(_prom()))["vendors"]
        assert section["state"] == "ok"
        assert section["rows"] == [
            {"component": "freya-tts", "breaker": "closed", "health": "healthy"},
            {"component": "voxcpm2-tts", "breaker": "half_open", "health": "degraded"},
        ]

    def test_the_worst_instance_wins(self) -> None:
        # two voice-runtime replicas disagree: an open breaker anywhere is open
        both = _vector(
            ({"component": "freya-tts", "state": "closed"}, "1"),
            ({"component": "freya-tts", "state": "open"}, "1"),
            ({"component": "freya-tts", "state": "half_open"}, "0"),
        )
        section = _deps(_console(_prom({"vendor_breaker_state": both})))["vendors"]
        assert section["rows"] == [
            {"component": "freya-tts", "breaker": "open", "health": "unhealthy"}
        ]

    def test_a_breaker_with_no_current_state_is_unknown(self) -> None:
        none = _vector(
            ({"component": "freya-tts", "state": "closed"}, "0"),
            ({"component": "freya-tts", "state": "open"}, "0"),
        )
        section = _deps(_console(_prom({"vendor_breaker_state": none})))["vendors"]
        assert section["rows"] == [{"component": "freya-tts", "breaker": None, "health": "unknown"}]

    def test_a_state_outside_the_breaker_vocabulary_is_refused(self) -> None:
        odd = _vector(({"component": "freya-tts", "state": "melting"}, "1"))
        section = _deps(_console(_prom({"vendor_breaker_state": odd})))["vendors"]
        assert (section["state"], section["reason"]) == ("unknown", "unexpected_label")

    @pytest.mark.parametrize(
        ("prom", "reason"),
        [
            (lambda: _prom({"vendor_breaker_state": EMPTY}), "no_series"),
            (_unreachable, "prometheus_unreachable"),
            (lambda: None, "prometheus_unconfigured"),
        ],
    )
    def test_fails_closed(self, prom: Any, reason: str) -> None:
        section = _deps(_console(prom()))["vendors"]
        assert (section["state"], section["reason"], section["rows"]) == ("unknown", reason, [])


# ------------------------------------------------------------------ ids only, no claims


class TestPhi:
    def test_a_label_value_that_is_not_id_shaped_turns_the_tile_unknown(self) -> None:
        leaked = _vector(({"component": "Ayşe Yılmaz", "state": "open"}, "1"))
        payload = _console(_prom({"vendor_breaker_state": leaked}))
        vendors = _deps(payload)["vendors"]
        assert (vendors["state"], vendors["reason"], vendors["rows"]) == (
            "unknown",
            "label_not_id_shaped",
            [],
        )
        assert "Ayşe" not in json.dumps(payload)

    def test_the_payload_carries_no_target_key(self, tmp_path: Path) -> None:
        text = json.dumps(_console(_prom(), _fresh(tmp_path, postgres="healthy")))
        assert '"target"' not in text
        assert "_target" not in text


# ------------------------------------------- the e2e fixtures are the composite's output


E2E = REPO / "apps" / "admin-web" / "e2e" / "fixtures"


class TestFixturesAreRecordedFromTheComposite:
    """``apps/admin-web/e2e/overview.spec.ts`` renders these; they must be what
    the shipped composite makes of the recorded sources, never a hand edit."""

    def _recorded(self, now_shift: timedelta, *, configured: bool) -> dict[str, Any]:
        sweep = load_sweep({PROBE_RESULTS_ENV: str(FIXTURES / "probe_sweep.json")})
        assert sweep.records is not None
        at = max(r.checked_at for r in sweep.records.values() if r.checked_at is not None)
        return build_reliability_console(
            prom=_prom() if configured else None,
            slo_files=_files(),
            registry=load_registry(REGISTRY),
            sweep=sweep if configured else UNCONFIGURED,
            now=at + now_shift,
        )

    @pytest.mark.parametrize(
        ("name", "shift", "configured"),
        [
            ("reliability.payload.json", timedelta(0), True),
            ("reliability.stale.payload.json", timedelta(hours=1), True),
            ("reliability.unconfigured.payload.json", timedelta(0), False),
        ],
    )
    def test_the_committed_fixture(self, name: str, shift: timedelta, configured: bool) -> None:
        recorded = json.loads((E2E / name).read_text(encoding="utf-8"))
        assert recorded == self._recorded(shift, configured=configured), (
            f"apps/admin-web/e2e/fixtures/{name} drifted from the composite; re-run "
            "uv run python scripts/dev/record_reliability_fixture.py"
        )

    def test_the_live_api_recording_is_readiness_and_version_only(self) -> None:
        recorded = json.loads((E2E / "overview.api.json").read_text(encoding="utf-8"))
        assert set(recorded) == {"recorded_at", "readyz", "version"}
        assert set(recorded["readyz"]["body"]) == {"checks"}
        assert set(recorded["version"]["body"]) == {"git_sha", "built_at", "sbom_digest"}


# ---------------------------------------------------------------------- env wiring


class TestLoad:
    def test_it_reads_the_sweep_the_slo_dir_and_prometheus_from_env(self, tmp_path: Path) -> None:
        sweep = tmp_path / "sweep.json"
        sweep.write_text(json.dumps([_row("postgres", "healthy", NOW)]), encoding="utf-8")
        payload = load_reliability_console(
            NOW, env={PROBE_RESULTS_ENV: str(sweep), ENV_SLO_DIR: str(SLO_DIR)}
        )
        assert payload["sources"] == {
            "prometheus": "unconfigured",
            "slo_files": "ok",
            "registry": "ok",
            "probe_sweep": "ok",
        }
        assert payload["generated_at"] == "2026-09-27T10:00:00Z"

    def test_a_missing_registry_blanks_what_reads_it_and_nothing_else(self, tmp_path: Path) -> None:
        payload = load_reliability_console(
            NOW, env={"INTAKE_REGISTRY_PATH": str(tmp_path / "absent.yaml")}
        )
        assert payload["sources"]["registry"] == "unreadable"
        assert payload["probe_matrix"]["reason"] == "registry_unreadable"
        assert payload["slos"]["state"] == "ok"

    def test_a_malformed_prometheus_url_is_misconfigured_not_a_guess(self) -> None:
        payload = load_reliability_console(NOW, env={ENV_PROMETHEUS_URL: "prometheus:9090"})
        assert payload["sources"]["prometheus"] == "misconfigured"
        assert payload["slos"]["tiles"][0]["reason"] == "prometheus_misconfigured"
        assert _deps(payload)["vendors"]["reason"] == "prometheus_misconfigured"


# ------------------------------------------------------------------------ the route


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
    monkeypatch.delenv(ENV_PROMETHEUS_URL, raising=False)
    monkeypatch.delenv(PROBE_RESULTS_ENV, raising=False)
    yield from build_admin_harness(tmp_path)


class TestRoute:
    def test_the_route_serves_the_composite_to_a_platform_role(self, harness: ApiHarness) -> None:
        response = harness.client.get("/admin/reliability", headers=bearer("sre_oncall"))
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema"] == RELIABILITY_SCHEMA
        assert payload["probe_matrix"]["reason"] == "probe_results_unconfigured"

    def test_a_tenant_scoped_role_is_refused(self, harness: ApiHarness) -> None:
        response = harness.client.get("/admin/reliability", headers=bearer("tenant_admin"))
        assert response.status_code == 403

    def test_no_token_is_refused(self, harness: ApiHarness) -> None:
        assert harness.client.get("/admin/reliability").status_code == 401

    def test_an_unreachable_prometheus_reads_unknown_through_the_route(
        self, harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # .invalid never resolves (RFC 6761): no socket reaches anything real
        monkeypatch.setenv(ENV_PROMETHEUS_URL, "http://prometheus.invalid:9090")
        payload = harness.client.get("/admin/reliability", headers=bearer("sre_oncall")).json()
        assert payload["sources"]["prometheus"] == "unreachable"
        assert payload["dependencies"]["prometheus"]["health"] == "unhealthy"
