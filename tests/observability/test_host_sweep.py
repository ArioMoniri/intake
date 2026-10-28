"""INT-560 — the probes service's sweep of the synthetic host.

Before this issue nothing probed the AWS host: the API had no results file, so
the registry page read ``no_result`` on every row. The probes service now runs
on the host (compose service ``probes``) and sweeps what the recorded
inventory (``infra/staging/inventory.yaml``) says the host runs. Pinned here,
each with its near miss, and with every client injected (no socket opens):

- every registry row gets a result each sweep: a probe for what the host runs,
  a typed ``skipped`` naming the host for what it does not — never silence;
- each probe dials the inventory's internal compose name, with the credential
  from the probe's own env variable and never from the committed file;
- a missing credential or server name is a ``skipped`` that says so, never a
  ``healthy``;
- the results file is replaced atomically, so the API never reads half a sweep;
- nothing patient-shaped or secret-shaped survives into the written file
  (invariant 6), and the two series the sweep emits are catalogued
  (invariant 13).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from intake_platform.slo import load_metrics_catalog
from intake_probes.gate import load_results
from intake_probes.host_sweep import (
    ENV_POSTGRES_PASSWORD,
    ENV_REDIS_PASSWORD,
    ENV_TLS_SERVER_NAME,
    HostProbeConfig,
    PostgresTarget,
    RedisTarget,
    build_host_clients,
    record_metrics,
    scrub_detail,
    sweep_host_once,
    write_sweep,
)
from intake_probes.inventory import HostInventory, load_host_inventory
from intake_probes.registry import load_registry
from intake_probes.runner import ProbeResult, ProbeStatus
from prometheus_client import REGISTRY as PROM_REGISTRY

REPO = Path(__file__).resolve().parents[2]
INVENTORY = REPO / "infra" / "staging" / "inventory.yaml"
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
REGISTRY = load_registry(REPO / "observability" / "registry.yaml")
SYNTHETIC = {"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

#: Probe credentials and the edge's server name, as the host env file would
#: hand them over. Test values: never a real credential.
SECRETS = {
    ENV_POSTGRES_PASSWORD: "pg-probe-test-value",
    ENV_REDIS_PASSWORD: "redis-probe-test-value",
    ENV_TLS_SERVER_NAME: "198-51-100-7.sslip.io",
}


def _inventory() -> HostInventory:
    return load_host_inventory(INVENTORY, registry=REGISTRY, env=SYNTHETIC)


class _Ping:
    def __init__(self, alive: bool = True) -> None:
        self.alive = alive

    def ping(self) -> bool:
        return self.alive


class _Calls:
    """Everything the injected clients were asked to dial."""

    def __init__(self) -> None:
        self.http: list[str] = []
        self.postgres: list[tuple[PostgresTarget, str]] = []
        self.redis: list[tuple[RedisTarget, str]] = []
        self.tcp: list[tuple[str, int]] = []
        self.tls: list[tuple[str, int, str]] = []


def _config(
    calls: _Calls,
    env: dict[str, str] | None = None,
    *,
    http_status: int = 200,
    sealed: bool = False,
    select1: Callable[[], int] = lambda: 1,
    not_after: datetime = NOW + timedelta(days=60),
) -> HostProbeConfig:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.http.append(str(request.url))
        if request.url.path == "/v1/sys/seal-status":
            return httpx.Response(http_status, json={"sealed": sealed})
        return httpx.Response(http_status, json={"status": "ok"})

    def postgres(target: PostgresTarget, password: str) -> Callable[[], int]:
        calls.postgres.append((target, password))
        return select1

    def redis(target: RedisTarget, password: str) -> _Ping:
        calls.redis.append((target, password))
        return _Ping()

    def dial(host: str, port: int) -> None:
        calls.tcp.append((host, port))

    def tls(host: str, port: int, server_name: str) -> datetime:
        calls.tls.append((host, port, server_name))
        return not_after

    return HostProbeConfig(
        env=SECRETS if env is None else env,
        http_transport=httpx.MockTransport(handler),
        postgres_select1=postgres,
        redis_client=redis,
        dial=dial,
        tls_not_after=tls,
        now=lambda: NOW,
    )


def _sweep(config: HostProbeConfig) -> dict[str, ProbeResult]:
    inventory = _inventory()
    clients = build_host_clients(REGISTRY, inventory, config)
    results = sweep_host_once(REGISTRY, clients, now=lambda: NOW)
    return {result.component: result for result in results}


# --- every row gets a result ----------------------------------------------------------


def test_every_registry_row_gets_a_result_and_none_is_silent() -> None:
    results = _sweep(_config(_Calls()))
    assert set(results) == {entry.component for entry in REGISTRY}
    assert all(result.checked_at == NOW for result in results.values())


def test_what_the_host_runs_is_probed_and_healthy_when_it_answers() -> None:
    results = _sweep(_config(_Calls()))
    probed = _inventory().deployed() - {"egress-proxy", "sms-egress"}
    for component in probed:
        assert results[component].status is ProbeStatus.HEALTHY, (
            component,
            results[component].detail,
        )


def test_a_gpu_box_model_is_skipped_as_not_on_this_host_never_probed() -> None:
    calls = _Calls()
    results = _sweep(_config(calls))
    for model in ("qwen3.5-9b", "whisper-tr-medical", "freya-tts", "voxcpm2-tts"):
        assert results[model].status is ProbeStatus.SKIPPED
        assert results[model].detail == "not deployed on synthetic-aws"
    assert not [url for url in calls.http if "880" in url], "no GPU-box port is dialled"


@pytest.mark.parametrize("proxy", ["egress-proxy", "sms-egress"])
def test_each_boundary_proxy_is_skipped_with_its_reason_never_dialled(proxy: str) -> None:
    calls = _Calls()
    result = _sweep(_config(calls))[proxy]
    assert result.status is ProbeStatus.SKIPPED
    assert result.detail == "deployed on synthetic-aws; not probed: outside_probe_networks"
    assert not [h for h, _ in calls.tcp if h == proxy]


# --- each probe dials the inventory's internal name ----------------------------------


def test_http_probes_dial_the_internal_compose_names() -> None:
    calls = _Calls()
    _sweep(_config(calls))
    assert set(calls.http) == {
        "http://api:8000/readyz",
        "http://openbao:8200/v1/sys/seal-status",
        "http://minio:9000/minio/health/ready",
        "http://keycloak:9000/health/ready",
        "http://oauth2-proxy:4180/ping",
        "http://admin-web:3000/healthz",
        "http://probes:8000/readyz",
    }


def test_postgres_is_probed_as_the_no_grant_role_with_the_env_credential() -> None:
    calls = _Calls()
    _sweep(_config(calls))
    assert calls.postgres == [
        (
            PostgresTarget(host="postgres", port=5432, user="svc_probe", dbname="intake"),
            SECRETS[ENV_POSTGRES_PASSWORD],
        )
    ]


def test_redis_is_probed_as_the_ping_only_user_with_the_env_credential() -> None:
    calls = _Calls()
    _sweep(_config(calls))
    assert calls.redis == [
        (
            RedisTarget(host="redis", port=6379, username="intake-probe", db=0),
            SECRETS[ENV_REDIS_PASSWORD],
        )
    ]


def test_the_edge_is_dialled_and_its_certificate_read_with_the_hosts_server_name() -> None:
    calls = _Calls()
    _sweep(_config(calls))
    assert calls.tcp == [("caddy", 443)]
    assert calls.tls == [("caddy", 443, SECRETS[ENV_TLS_SERVER_NAME])]


@pytest.mark.parametrize(
    ("variable", "component"),
    [
        (ENV_POSTGRES_PASSWORD, "postgres"),
        (ENV_REDIS_PASSWORD, "redis"),
        (ENV_TLS_SERVER_NAME, "edge-tls"),
    ],
)
def test_a_missing_credential_is_a_skip_that_says_so_never_healthy(
    variable: str, component: str
) -> None:
    calls = _Calls()
    env = {key: value for key, value in SECRETS.items() if key != variable}
    result = _sweep(_config(calls, env))[component]
    assert result.status is ProbeStatus.SKIPPED
    assert variable in result.detail
    # near miss: with it set, the same row is healthy
    assert _sweep(_config(_Calls()))[component].status is ProbeStatus.HEALTHY


def test_a_component_that_does_not_answer_is_unhealthy() -> None:
    results = _sweep(_config(_Calls(), http_status=503))
    assert results["api"].status is ProbeStatus.UNHEALTHY
    assert results["keycloak"].status is ProbeStatus.UNHEALTHY


def test_a_sealed_openbao_and_an_expiring_certificate_are_unhealthy() -> None:
    results = _sweep(_config(_Calls(), sealed=True, not_after=NOW + timedelta(days=3)))
    assert results["openbao"].status is ProbeStatus.UNHEALTHY
    assert results["edge-tls"].status is ProbeStatus.UNHEALTHY


def test_a_failing_select_is_unhealthy() -> None:
    def broken() -> int:
        raise OSError("connection refused")

    assert _sweep(_config(_Calls(), select1=broken))["postgres"].status is ProbeStatus.UNHEALTHY


# --- the written sweep ----------------------------------------------------------------


def _result(component: str, status: ProbeStatus, detail: str = "ok") -> ProbeResult:
    return ProbeResult(component, "http_health", status, 1.5, detail, NOW)


def test_the_sweep_file_is_the_wire_shape_the_api_reads(tmp_path: Path) -> None:
    out = tmp_path / "probe-results" / "sweep.json"
    write_sweep([_result("api", ProbeStatus.HEALTHY)], out)
    records = load_results(out)
    assert records["api"].status is ProbeStatus.HEALTHY
    assert records["api"].checked_at == NOW


def test_the_sweep_file_is_replaced_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reader between two writes sees the old sweep or the new one, whole."""
    out = tmp_path / "sweep.json"
    write_sweep([_result("api", ProbeStatus.HEALTHY)], out)
    replaced: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src: Any, dst: Any) -> None:
        # the new bytes are complete before the rename, and the old file is
        # still whole until it
        assert json.loads(Path(src).read_text(encoding="utf-8"))[0]["status"] == "unhealthy"
        assert json.loads(Path(dst).read_text(encoding="utf-8"))[0]["status"] == "healthy"
        replaced.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    write_sweep([_result("api", ProbeStatus.UNHEALTHY)], out)
    assert replaced and replaced[0][1] == str(out)
    assert [p.name for p in tmp_path.iterdir()] == ["sweep.json"], "no temp file left behind"


#: Planted in a probe's failure text. A valid TCKN (checksum holds), a TR
#: mobile number, an IBAN, an email and a URL with credentials in it.
PLANTED = (
    "upstream said 10000000146 / 05321234567 / TR330006100519786457841326 / "
    "ayse@example.com via http://svc:hunter2@api:8000/x"
)


def test_no_patient_or_secret_shaped_text_reaches_the_written_file(tmp_path: Path) -> None:
    out = tmp_path / "sweep.json"
    results = sweep_host_once(
        REGISTRY,
        {"api": lambda: (_ for _ in ()).throw(RuntimeError(PLANTED))},
        now=lambda: NOW,
    )
    write_sweep(results, out)
    text = out.read_text(encoding="utf-8")
    for leaked in (
        "10000000146",
        "05321234567",
        "TR330006100519786457841326",
        "ayse@example.com",
        "hunter2",
    ):
        assert leaked not in text, leaked
    # near miss: the failure itself is still reported, as unhealthy
    assert load_results(out)["api"].status is ProbeStatus.UNHEALTHY


def test_scrub_detail_keeps_an_operational_message_readable() -> None:
    assert scrub_detail("expected 200, got 503") == "expected 200, got 503"
    assert len(scrub_detail("x" * 5000)) <= 240


# --- metrics: catalogued, ids only -----------------------------------------------------


def _sample(name: str, component: str) -> float | None:
    return PROM_REGISTRY.get_sample_value(name, {"component": component})


def test_the_sweep_sets_probe_status_for_what_it_probed_and_clears_what_it_skipped() -> None:
    record_metrics(
        [
            _result("api", ProbeStatus.HEALTHY),
            _result("keycloak", ProbeStatus.UNHEALTHY, "expected 200, got 503"),
            ProbeResult("qwen3.5-9b", "http_health", ProbeStatus.SKIPPED, None, "not here", NOW),
        ]
    )
    assert _sample("probe_status", "api") == 1.0
    assert _sample("probe_status", "keycloak") == 0.0
    assert _sample("probe_status", "qwen3.5-9b") is None, "a skip is no observation"
    assert (_sample("probe_latency_ms_count", "api") or 0) >= 1
    # a component that later stops being probed loses its series
    record_metrics([ProbeResult("keycloak", "http_health", ProbeStatus.SKIPPED, None, "gone", NOW)])
    assert _sample("probe_status", "keycloak") is None


def test_the_two_series_are_catalogued_live_with_id_labels_only() -> None:
    catalog = load_metrics_catalog(CATALOG)
    by_name = {metric.name: metric for metric in catalog.metrics}
    for name in ("probe_status", "probe_latency_ms"):
        metric = by_name[name]
        assert metric.status == "live", name
        assert list(metric.labels) == ["component"], name


def test_a_failed_write_leaves_the_old_sweep_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "sweep.json"
    write_sweep([_result("api", ProbeStatus.HEALTHY)], out)

    def refuse(src: Any, dst: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError):
        write_sweep([_result("api", ProbeStatus.UNHEALTHY)], out)
    assert load_results(out)["api"].status is ProbeStatus.HEALTHY
    assert [p.name for p in tmp_path.iterdir()] == ["sweep.json"]
