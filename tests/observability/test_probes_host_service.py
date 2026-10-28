"""INT-560 — the probes app runs the host sweep, and its adapters dial what they say.

``tests/observability/test_host_sweep.py`` pins what one sweep decides. This
file pins the service around it, still without leaving this machine:

- with ``INTAKE_HOST_INVENTORY_PATH`` and ``INTAKE_PROBE_RESULTS_PATH`` set,
  the app's lifespan sweeps at once and writes the file the API reads, and
  ``/readyz`` names the inventory; an inventory that does not load starts no
  sweep and fails readiness, while ``/healthz`` stays 200 — a probes fault
  never fails a deploy;
- neither variable alone starts anything (near miss);
- the real adapters dial a local socket, read a local certificate with the
  server name they were given, and build their clients without connecting;
- a sweep that cannot be written is logged by class and the loop goes on.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import socketserver
import ssl
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from intake_probes import app as probes_app
from intake_probes import host_sweep
from intake_probes.host_sweep import HostProbeConfig, PostgresTarget, RedisTarget
from intake_probes.inventory import ENV_HOST_INVENTORY, load_host_inventory
from intake_probes.probes import Skipped
from intake_probes.registry import ProbeId, load_registry
from intake_probes.runner import ProbeResult, ProbeStatus

REPO = Path(__file__).resolve().parents[2]
INVENTORY = REPO / "infra" / "staging" / "inventory.yaml"
REGISTRY_PATH = REPO / "observability" / "registry.yaml"
REGISTRY = load_registry(REGISTRY_PATH)
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def _offline(env: object) -> HostProbeConfig:
    """Every dial answered here: HTTP 200, TCP refused, no TLS, no credentials."""

    def refused(*_: object) -> None:
        raise OSError("refused in test")

    return HostProbeConfig(
        env={},
        http_transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        dial=refused,
        tls_not_after=lambda *_: NOW,
    )


@pytest.fixture
def host_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "probe-results" / "sweep.json"
    monkeypatch.setenv(ENV_HOST_INVENTORY, str(INVENTORY))
    monkeypatch.setenv("INTAKE_PROBE_RESULTS_PATH", str(out))
    monkeypatch.setenv("INTAKE_DEPLOYMENT_DATA_CLASS", "synthetic")
    monkeypatch.setenv("INTAKE_REGISTRY_PATH", str(REGISTRY_PATH))
    monkeypatch.setattr(probes_app, "host_probe_config", _offline)
    return out


def _wait_for(path: Path, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while not path.is_file():
        assert time.monotonic() < deadline, f"{path} was never written"
        time.sleep(0.05)


# --- the app ------------------------------------------------------------------------------


def test_the_app_sweeps_the_host_at_once_and_writes_the_file_the_api_reads(
    host_env: Path,
) -> None:
    with TestClient(probes_app.create_app()) as client:
        _wait_for(host_env)
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["checks"] == {"registry": "ok", "host_inventory": "ok"}
    records = json.loads(host_env.read_text(encoding="utf-8"))
    assert {r["component"] for r in records} == {entry.component for entry in REGISTRY}
    by = {r["component"]: r for r in records}
    assert by["api"]["status"] == "healthy"
    assert by["caddy"]["status"] == "unhealthy"
    assert by["qwen3.5-9b"]["detail"] == "not deployed on synthetic-aws"


def test_an_inventory_that_does_not_load_starts_no_sweep_and_fails_readiness(
    host_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bent = tmp_path / "inventory.yaml"
    bent.write_text("host_id: x\n", encoding="utf-8")
    monkeypatch.setenv(ENV_HOST_INVENTORY, str(bent))
    with TestClient(probes_app.create_app()) as client:
        assert client.get("/healthz").status_code == 200, "a probes fault never fails a deploy"
        ready = client.get("/readyz")
        assert ready.status_code == 503
        assert ready.json()["checks"]["host_inventory"] == "error"
    assert not host_env.exists()


def test_a_process_that_is_not_synthetic_starts_no_sweep(
    host_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTAKE_DEPLOYMENT_DATA_CLASS", "real_phi")
    with TestClient(probes_app.create_app()) as client:
        assert client.get("/readyz").status_code == 503
    assert not host_env.exists()


def test_an_unreadable_registry_starts_no_sweep(
    host_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTAKE_REGISTRY_PATH", str(tmp_path / "no-registry.yaml"))
    with TestClient(probes_app.create_app()) as client:
        assert client.get("/healthz").status_code == 200
    assert not host_env.exists()


@pytest.mark.parametrize("only", [ENV_HOST_INVENTORY, "INTAKE_PROBE_RESULTS_PATH"])
def test_one_variable_alone_starts_nothing(
    host_env: Path, monkeypatch: pytest.MonkeyPatch, only: str
) -> None:
    for name in (ENV_HOST_INVENTORY, "INTAKE_PROBE_RESULTS_PATH"):
        if name != only:
            monkeypatch.delenv(name)
    assert probes_app.host_sweep_from_env(dict(os.environ)) is None
    with TestClient(probes_app.create_app()) as client:
        assert client.get("/readyz").json()["checks"] == {"registry": "ok"}
    assert not host_env.exists()


def test_the_real_config_reads_its_credentials_from_the_environment() -> None:
    config = probes_app.host_probe_config({"INTAKE_PROBE_REDIS_PASSWORD": "x"})
    assert config.env == {"INTAKE_PROBE_REDIS_PASSWORD": "x"}
    assert config.http_transport is None


# --- the loop -------------------------------------------------------------------------------


def test_the_loop_stops_when_asked(tmp_path: Path) -> None:
    out = tmp_path / "sweep.json"
    inventory = load_host_inventory(
        INVENTORY, registry=REGISTRY, env={"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}
    )
    clients = host_sweep.build_host_clients(REGISTRY, inventory, _offline(None))

    async def run() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(
            host_sweep.run_host_sweeps(REGISTRY, clients, out, stop, interval_s=0.01)
        )
        while not out.is_file():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)  # a second cycle comes round
        stop.set()
        await asyncio.wait_for(task, timeout=10)

    asyncio.run(run())
    assert out.is_file()


def test_a_sweep_that_cannot_be_written_is_logged_and_survived(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="intake_probes.host_sweep"):
        host_sweep._cycle(REGISTRY, {}, blocker / "sweep.json")
    assert "host sweep not written" in caplog.text
    assert str(blocker) not in caplog.text


def test_a_probe_the_host_cannot_run_is_a_skip_never_a_guess() -> None:
    inventory = load_host_inventory(
        INVENTORY, registry=REGISTRY, env={"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}
    )
    placement = inventory.placement("api")
    assert placement is not None and placement.probe_at is not None
    fn = host_sweep._wire(
        ProbeId.BACKUP_FRESHNESS, placement, placement.probe_at, _offline(None), httpx.Client()
    )
    outcome = fn()
    assert outcome == Skipped(reason="probe backup_freshness has no host wiring")


def test_metrics_clear_quietly_for_a_component_never_set() -> None:
    host_sweep.record_metrics(
        [ProbeResult("never-set-int560", "http_health", ProbeStatus.SKIPPED, None, "x", NOW)]
    )


# --- the real adapters ------------------------------------------------------------------------


def test_the_dial_adapter_connects_to_a_listening_socket() -> None:
    with socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler) as server:
        host, port = server.server_address[0], server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        host_sweep._dial(str(host), int(port))
        thread.join(timeout=5)
    with pytest.raises(OSError):
        host_sweep._dial("127.0.0.1", _closed_port())


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_the_tls_adapter_sends_the_server_name_it_was_given(tmp_path: Path) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    expires = datetime(2027, 1, 1, tzinfo=UTC)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "edge.example")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(expires - timedelta(days=90))
        .not_valid_after(expires)
        .sign(key, hashes.SHA256())
    )
    (tmp_path / "c.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "k.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(tmp_path / "c.pem"), str(tmp_path / "k.pem"))
    seen: list[str | None] = []
    context.sni_callback = lambda _sock, server_name, _ctx: seen.append(server_name)

    with socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler) as server:
        host, port = server.server_address[0], server.server_address[1]

        def serve_one() -> None:
            conn, _ = server.socket.accept()
            try:
                with context.wrap_socket(conn, server_side=True) as tls:
                    tls.recv(1)
            except OSError:
                conn.close()

        thread = threading.Thread(target=serve_one, daemon=True)
        thread.start()
        got = host_sweep._tls_not_after(str(host), int(port), "edge.example")
        thread.join(timeout=5)
    assert got == expires
    assert seen == ["edge.example"]


def test_the_redis_adapter_logs_in_as_the_probe_user_without_connecting() -> None:
    client = host_sweep._redis_client(RedisTarget("redis", 6379, "intake-probe", 0), "pw")
    kwargs = client.connection_pool.connection_kwargs  # type: ignore[attr-defined]
    assert (kwargs["host"], kwargs["port"], kwargs["username"], kwargs["db"]) == (
        "redis",
        6379,
        "intake-probe",
        0,
    )


def test_the_postgres_adapter_is_a_callable_that_connects_only_when_called() -> None:
    select1 = host_sweep._psycopg_select1(
        PostgresTarget("127.0.0.1", _closed_port(), "svc_probe", "intake"), "pw"
    )
    with pytest.raises(psycopg.OperationalError):
        select1()
