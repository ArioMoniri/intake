"""INT-022 — self-hosting registry + synthetic probes (CLAUDE.md invariants 13/15/19).

Acceptance line under test, verbatim (docs/backlog/issues.yaml INT-022):
  "registry table {component,self_hostable,self_hosted_now,host,license,probe,
   budget_ms,fallback,phi_path}; 60s runner with real dev checks (DB, Redis,
   MinIO, HAPI, OpenBao seal, LiveKit room join, cert expiry, backup freshness;
   EHRbase joins in P3 per 00 D8)"

The unit lane never needs docker: every probe takes an injected client, socket
or callable; the dev runner composes the real ones (build_dev_clients) and the
compose-backed integration lane exercises those later.
"""

from __future__ import annotations

import socket
import socketserver
import ssl
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import fakeredis
import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from intake_probes.app import create_app
from intake_probes.probes import (
    Failed,
    Ok,
    Outcome,
    Skipped,
    backup_freshness,
    cert_expiry_days,
    fetch_tls_not_after,
    http_health,
    livekit_room_join,
    minio_ready,
    openbao_seal_status,
    postgres_select1,
    redis_ping,
    tcp_connect,
)
from intake_probes.registry import ProbeId, Registry, load_registry
from intake_probes.runner import (
    DevProbeConfig,
    ProbeStatus,
    build_dev_clients,
    run_probes_once,
)
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO / "observability" / "registry.yaml"


def _entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "component": "sample",
        "self_hostable": True,
        "self_hosted_now": True,
        "host": "dev compose 127.0.0.1:5432",
        "license": "PostgreSQL Licence",
        "probe": "postgres_select1",
        "budget_ms": 500,
        "fallback": "none",
        "phi_path": False,
    }
    base.update(overrides)
    return base


def _registry(*entries: dict[str, object]) -> Registry:
    return Registry.model_validate({"components": list(entries)})


# A complete, well-formed model-provenance block (INT-243). Tests delete one
# key at a time from it to prove each half of the pin is load-bearing.
_MODEL_PROVENANCE: dict[str, object] = {
    "model_id": "openbmb/VoxCPM2",
    "revision": "32279effe8c19989596f05d353d1447f51d9e915",
    "weights_sha256": {
        "model.safetensors": "f7f964cfa9da23653baec6e6f7750719977ad944ed9f95fe52fe3a620506891d"
    },
    "licence_verified_at": date(2026, 8, 29),
    "licence_blob_url": "https://example.invalid/LICENSE",
    "licence_blob_sha256": "4f10acc209addacfad28293315c74c4cd648f771ee1263a748f1781d1e0265e4",
}


# --- the shipped registry ---------------------------------------------------------


def test_shipped_registry_loads_and_validates() -> None:
    registry = load_registry(REGISTRY_PATH)
    names = {e.component for e in registry}
    assert {
        "postgres",
        "redis",
        "minio",
        "hapi",
        "openbao",
        "api",
        "probes",
        "voice-runtime",
        "edge-tls",
        "backups",
        "qwen3.5-9b",
        "whisper-tr-medical",
        "freya-tts",
        "deid-tr-ner-v1",
    } <= names


def test_shipped_registry_has_exactly_the_acceptance_schema() -> None:
    raw = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    required = {
        "component",
        "self_hostable",
        "self_hosted_now",
        "host",
        "license",
        "probe",
        "budget_ms",
        "fallback",
        "phi_path",
    }
    # INT-243 extends the row with an OPTIONAL model-provenance block, so an
    # auditor can see the pin and the exact licence blob that was read rather
    # than a prose claim inside `host` (files/03 §4.9.0 rule 3, invariant 19).
    optional = {
        "model_id",
        "revision",
        "weights_sha256",
        "licence_verified_at",
        "licence_blob_url",
        "licence_blob_sha256",
        "licence_note",
        # INT-347: the digest-pinned container image, kept out of `host`
        # because the console serves `host` (tests/infra/test_object_store_image.py)
        "image",
    }
    for row in raw["components"]:
        keys = set(row)
        assert required <= keys, f"row {row.get('component')} is missing required keys"
        assert keys <= required | optional, f"row {row.get('component')} has unknown keys"


def test_every_phi_path_component_is_self_hostable() -> None:
    # invariant 19 across the shipped data, not only the validator
    for e in load_registry(REGISTRY_PATH):
        if e.phi_path:
            assert e.self_hostable, f"{e.component} is on the PHI path but not self-hostable"


def test_ehrbase_joined_with_int032_and_is_not_enabled() -> None:
    """Until INT-032 this row had to be absent, and the test said so. The row
    exists now (the P3 export tier landed), and what must stay true is
    narrower: D8 is still cited, and the CDR is NOT enabled — it lives behind
    the compose `export` profile and no deployment serves from it, so the
    release gate must not treat it as a live PHI-path dependency."""
    registry = load_registry(REGISTRY_PATH)
    rows = [e for e in registry if "ehrbase" in e.component.lower()]
    assert [e.component for e in rows] == ["ehrbase"]
    row = rows[0]
    assert row.self_hosted_now is False, (
        "an enabled EHRbase row would make the P3 export tier look like a running "
        "dependency; nothing serves from it (00 §3 D8)"
    )
    assert row.phi_path is True and row.self_hostable is True
    assert row.license == "Apache-2.0"
    assert row.licence_verified_at == date(2026, 8, 29)
    assert row.licence_blob_url == (
        "https://raw.githubusercontent.com/ehrbase/ehrbase/v2.35.1/LICENSE"
    )
    assert row.licence_blob_sha256 == (
        "58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd"
    )
    assert "2.35.1" in row.host, "the registry host must pin the image tag the compose runs"
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    assert "D8" in text and "00_STATE" in text, "the EHRbase row must cite files/00_STATE.md §3 D8"


def test_model_rows_mirror_the_03_491_pins() -> None:
    registry = load_registry(REGISTRY_PATH)
    by_name = {e.component: e for e in registry}

    qwen = by_name["qwen3.5-9b"]
    assert "Qwen/Qwen3.5-9B@c202236" in qwen.host
    assert "Apache-2.0" in qwen.license

    whisper = by_name["whisper-tr-medical"]
    assert "0e74ec8" in whisper.host
    # the licence finding is carried verbatim — card tag only, no LICENSE blob
    assert whisper.license == "UNVERIFIED (card tag apache-2.0, no blob)"

    freya = by_name["freya-tts"]
    assert "d124e07" in freya.host
    assert "Apache-2.0" in freya.license
    # INT-243 closed the open finding this row used to carry ("VoxCPM2 VAE
    # weights @32279eff have NO licence blob"): VoxCPM2 has its own row now,
    # with the blob url and sha it was verified from. Freya's licence line
    # must no longer speak for another model.
    assert "32279eff" not in freya.license
    assert "NO licence blob" not in freya.license

    deid = by_name["deid-tr-ner-v1"]
    assert "MIT" in deid.license and "CC-BY-4.0" in deid.license


# --- INT-243: VoxCPM2 (files/03 §4.9.1 rows 10-11) ---------------------------------


def test_voxcpm2_row_pins_the_model_and_falls_back_to_freya() -> None:
    entry = load_registry(REGISTRY_PATH).get("voxcpm2-tts")
    assert entry.model_id == "openbmb/VoxCPM2"
    assert entry.revision == "32279effe8c19989596f05d353d1447f51d9e915"
    assert entry.phi_path is True
    assert entry.self_hostable is True
    assert entry.probe is ProbeId.HTTP_HEALTH
    # row 12 is the whole-session fallback and it stays serving (8803)
    assert entry.fallback == "component:freya-tts"
    assert entry.weights_sha256["model.safetensors"] == (
        "f7f964cfa9da23653baec6e6f7750719977ad944ed9f95fe52fe3a620506891d"
    )
    assert entry.weights_sha256["audiovae.pth"] == (
        "94b5d51e107e0507d4acc976cfdadb64edd6fd06d1f751dadbf2fd1594274bf1"
    )


def test_voxcpm2_licence_is_verified_from_a_named_blob_not_a_card_tag() -> None:
    # files/03 §4.9.0 rule 3 + invariant 19: the auditor must be able to see
    # WHAT WAS READ. The HF weights repo has no LICENSE file at all, so the
    # url must point at the vendor source repo, pinned to a commit.
    entry = load_registry(REGISTRY_PATH).get("voxcpm2-tts")
    assert entry.licence_verified_at == date(2026, 8, 29)
    assert entry.licence_blob_url == (
        "https://raw.githubusercontent.com/OpenBMB/VoxCPM/"
        "272b8ffbf660b0cfd07e20fdef538f335a4f92ca/LICENSE"
    )
    assert entry.licence_blob_sha256 == (
        "4f10acc209addacfad28293315c74c4cd648f771ee1263a748f1781d1e0265e4"
    )
    assert entry.licence_note is not None
    note = entry.licence_note.lower()
    assert "no license" in note, "the note must say plainly that the HF repo carries no LICENSE"
    assert "openbmb/voxcpm" in note, "the note must say where the blob came from"


def test_declaring_a_model_id_requires_the_full_pin() -> None:
    # a half-pinned model row is worse than none: it looks verified
    for missing in ("revision", "weights_sha256", "licence_verified_at"):
        row = _entry(**_MODEL_PROVENANCE)
        del row[missing]
        with pytest.raises(ValidationError, match="model_id"):
            _registry(row)


def test_claiming_licence_verification_requires_naming_the_blob() -> None:
    # you cannot assert `licence_verified_at` without saying which blob you
    # read and what it hashed to — that is the whole point of §4.9.0 rule 3
    for missing in ("licence_blob_url", "licence_blob_sha256"):
        row = _entry(**_MODEL_PROVENANCE)
        del row[missing]
        with pytest.raises(ValidationError, match="licence_verified_at"):
            _registry(row)


def test_provenance_hashes_and_revision_must_be_well_formed() -> None:
    with pytest.raises(ValidationError):
        _registry(_entry(**{**_MODEL_PROVENANCE, "revision": "32279ef"}))  # short sha
    with pytest.raises(ValidationError):
        _registry(_entry(**{**_MODEL_PROVENANCE, "licence_blob_sha256": "NOTAHASH"}))
    with pytest.raises(ValidationError):
        _registry(_entry(**{**_MODEL_PROVENANCE, "weights_sha256": {"w.bin": "cafe"}}))
    with pytest.raises(ValidationError):
        _registry(_entry(**{**_MODEL_PROVENANCE, "weights_sha256": {}}))


def test_licence_blob_url_must_be_https() -> None:
    # a http:// blob url is not evidence of anything
    with pytest.raises(ValidationError):
        _registry(
            _entry(**{**_MODEL_PROVENANCE, "licence_blob_url": "http://example.invalid/LICENSE"})
        )


def test_rows_without_a_model_id_stay_valid_untouched() -> None:
    # the provenance block is additive: the ten service rows do not carry a
    # model pin and must not be forced to invent one
    assert _registry(_entry()).get("sample").model_id is None


def test_voice_runtime_is_marked_planned_with_the_livekit_probe() -> None:
    registry = load_registry(REGISTRY_PATH)
    vr = next(e for e in registry if e.component == "voice-runtime")
    assert vr.self_hosted_now is False
    assert vr.probe is ProbeId.LIVEKIT_ROOM_JOIN
    assert vr.phi_path is True


# --- schema validation ------------------------------------------------------------


def test_phi_path_requires_self_hostable() -> None:
    # invariant 19: a PHI-path component that cannot be self-hosted is a defect
    with pytest.raises(ValidationError, match="invariant 19"):
        _registry(_entry(phi_path=True, self_hostable=False))


def test_unknown_probe_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _registry(_entry(probe="quantum_entanglement"))


def test_duplicate_component_names_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        _registry(_entry(component="twin"), _entry(component="twin"))


def test_component_fallback_must_resolve_in_the_registry() -> None:
    with pytest.raises(ValidationError, match="fallback"):
        _registry(_entry(fallback="component:ghost"))


def test_component_may_not_be_its_own_fallback() -> None:
    with pytest.raises(ValidationError, match="itself"):
        _registry(_entry(component="ouro", fallback="component:ouro"))


def test_malformed_fallback_shape_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _registry(_entry(fallback="restore it somehow"))


def test_budget_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _registry(_entry(budget_ms=0))


def test_extra_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _registry(_entry(comment="the schema is exact"))


def test_registry_file_must_hold_a_components_list(tmp_path: Path) -> None:
    bad = tmp_path / "registry.yaml"
    bad.write_text("just a string\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_registry(bad)


# --- probe functions against fakes -------------------------------------------------


def test_tcp_connect_ok_against_a_real_listening_socket() -> None:
    with socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler) as server:
        host, port = server.server_address[0], server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        def dial() -> None:
            sock = socket.create_connection((str(host), int(port)), timeout=2)
            sock.close()

        assert isinstance(tcp_connect(dial), Ok)
        thread.join(timeout=5)


def test_tcp_connect_failure_is_reported_not_raised() -> None:
    def dial() -> None:
        raise OSError("connection refused")

    outcome = tcp_connect(dial)
    assert isinstance(outcome, Failed)
    assert "refused" in outcome.detail


def _http_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_http_health_200_is_ok() -> None:
    client = _http_client(lambda request: httpx.Response(200))
    assert isinstance(http_health(client, "http://127.0.0.1:8091/fhir/metadata"), Ok)


def test_http_health_non_200_fails_with_the_status() -> None:
    client = _http_client(lambda request: httpx.Response(503))
    outcome = http_health(client, "http://127.0.0.1:8091/fhir/metadata")
    assert isinstance(outcome, Failed)
    assert "503" in outcome.detail


def test_http_health_transport_error_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    outcome = http_health(_http_client(handler), "http://127.0.0.1:9/x")
    assert isinstance(outcome, Failed)


def test_postgres_select1_ok_with_injected_callable() -> None:
    assert isinstance(postgres_select1(lambda: 1), Ok)


def test_postgres_select1_wrong_scalar_fails() -> None:
    outcome = postgres_select1(lambda: 0)
    assert isinstance(outcome, Failed)


def test_postgres_select1_raising_callable_fails() -> None:
    def select1() -> int:
        raise ConnectionError("server closed the connection")

    outcome = postgres_select1(select1)
    assert isinstance(outcome, Failed)
    assert "closed" in outcome.detail


def test_redis_ping_against_fakeredis() -> None:
    assert isinstance(redis_ping(fakeredis.FakeRedis()), Ok)


def test_redis_ping_failure_is_reported() -> None:
    class Down:
        def ping(self) -> bool:
            raise ConnectionError("redis is down")

    outcome = redis_ping(Down())
    assert isinstance(outcome, Failed)


def test_minio_ready_hits_the_health_ready_endpoint() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    assert isinstance(minio_ready(_http_client(handler), "http://127.0.0.1:9000"), Ok)
    assert seen == ["http://127.0.0.1:9000/minio/health/ready"]


def test_minio_ready_non_200_fails() -> None:
    client = _http_client(lambda request: httpx.Response(503))
    assert isinstance(minio_ready(client, "http://127.0.0.1:9000"), Failed)


def test_openbao_unsealed_is_ok() -> None:
    client = _http_client(lambda request: httpx.Response(200, json={"sealed": False}))
    assert isinstance(openbao_seal_status(client, "http://127.0.0.1:8200"), Ok)


def test_openbao_sealed_fails_loudly() -> None:
    client = _http_client(lambda request: httpx.Response(200, json={"sealed": True}))
    outcome = openbao_seal_status(client, "http://127.0.0.1:8200")
    assert isinstance(outcome, Failed)
    assert "sealed" in outcome.detail


def test_openbao_error_status_fails() -> None:
    client = _http_client(lambda request: httpx.Response(500, json={}))
    assert isinstance(openbao_seal_status(client, "http://127.0.0.1:8200"), Failed)


def test_cert_expiry_with_a_synthetic_date_ok_and_failing() -> None:
    now = datetime(2026, 8, 28, tzinfo=UTC)
    fresh = cert_expiry_days(lambda: now + timedelta(days=90), min_days=14, now=lambda: now)
    assert isinstance(fresh, Ok)
    assert "90" in fresh.detail

    closing = cert_expiry_days(lambda: now + timedelta(days=3), min_days=14, now=lambda: now)
    assert isinstance(closing, Failed)


def test_cert_expiry_fetch_error_is_reported() -> None:
    def fetch() -> datetime:
        raise OSError("handshake refused")

    assert isinstance(cert_expiry_days(fetch, min_days=14), Failed)


def _selfsigned_cert(tmp_path: Path, not_after: datetime) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_after - timedelta(days=365))
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "probe.crt"
    key_path = tmp_path / "probe.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


def test_fetch_tls_not_after_reads_the_peer_certificate(tmp_path: Path) -> None:
    expected = datetime(2027, 3, 1, 12, 0, tzinfo=UTC)
    cert_path, key_path = _selfsigned_cert(tmp_path, expected)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

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
        got = fetch_tls_not_after(str(host), int(port), timeout_s=5)
        thread.join(timeout=5)

    assert got == expected


def test_backup_freshness_fresh_stale_and_missing(tmp_path: Path) -> None:
    target = tmp_path / "backups"
    target.mkdir()
    artefact = target / "intake-2026-08-28.dump"
    artefact.write_bytes(b"backup bytes")

    now = artefact.stat().st_mtime
    assert isinstance(backup_freshness(target, max_age_s=3600, now=lambda: now + 60), Ok)

    stale = backup_freshness(target, max_age_s=3600, now=lambda: now + 7200)
    assert isinstance(stale, Failed)

    empty = tmp_path / "empty"
    empty.mkdir()
    assert isinstance(backup_freshness(empty, max_age_s=3600, now=lambda: now), Failed)
    assert isinstance(backup_freshness(tmp_path / "absent", max_age_s=3600), Failed)


def test_backup_freshness_without_age_bound_is_a_presence_check(tmp_path: Path) -> None:
    # the deid artefact row: pinned model, presence matters, age does not
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    old = (tmp_path / "config.json").stat().st_mtime
    assert isinstance(backup_freshness(tmp_path, max_age_s=None, now=lambda: old + 1e9), Ok)


def test_livekit_room_join_is_a_typed_skipped_result() -> None:
    outcome = livekit_room_join()
    assert isinstance(outcome, Skipped)
    assert outcome.reason == "livekit lands with INT-090"


# --- the runner ---------------------------------------------------------------------


class _StepClock:
    def __init__(self, *times: float) -> None:
        self._times = list(times)

    def __call__(self) -> float:
        return self._times.pop(0)


def test_run_probes_once_maps_outcomes_and_latency() -> None:
    registry = _registry(
        _entry(component="up", probe="redis_ping", budget_ms=1000),
        _entry(component="down", probe="redis_ping", budget_ms=1000),
        _entry(component="later", probe="livekit_room_join", budget_ms=1000),
        _entry(component="unwired", probe="http_health", budget_ms=1000),
    )
    clients: dict[str, Callable[[], Outcome]] = {
        "up": lambda: Ok("pong"),
        "down": lambda: Failed("no pong"),
        "later": livekit_room_join,
    }
    results = {r.component: r for r in run_probes_once(registry, clients)}

    assert results["up"].status is ProbeStatus.HEALTHY
    assert results["up"].latency_ms is not None and results["up"].latency_ms >= 0
    assert results["down"].status is ProbeStatus.UNHEALTHY
    assert results["later"].status is ProbeStatus.SKIPPED
    assert results["later"].detail == "livekit lands with INT-090"
    assert results["unwired"].status is ProbeStatus.SKIPPED
    assert "no probe client" in results["unwired"].detail


def test_run_probes_once_flags_a_budget_breach_as_unhealthy() -> None:
    registry = _registry(_entry(component="slow", probe="redis_ping", budget_ms=100))
    results = run_probes_once(
        registry,
        {"slow": lambda: Ok("pong")},
        clock=_StepClock(0.0, 0.5),  # 500 ms measured against a 100 ms budget
    )
    assert results[0].status is ProbeStatus.UNHEALTHY
    assert "budget" in results[0].detail
    assert results[0].latency_ms == pytest.approx(500.0)


def test_run_probes_once_survives_a_raising_client() -> None:
    def explode() -> Outcome:
        raise RuntimeError("client blew up")

    registry = _registry(_entry(component="volatile", probe="redis_ping"))
    results = run_probes_once(registry, {"volatile": explode})
    assert results[0].status is ProbeStatus.UNHEALTHY
    assert "client blew up" in results[0].detail


def test_probe_result_serialises_to_the_gate_wire_shape() -> None:
    registry = _registry(_entry(component="up", probe="redis_ping"))
    record = run_probes_once(registry, {"up": lambda: Ok("pong")})[0].to_json()
    assert set(record) == {"component", "probe", "status", "latency_ms", "detail"}
    assert record["status"] == "healthy"


# --- dev client composition ---------------------------------------------------------


def test_build_dev_clients_wires_the_real_dev_checks(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY_PATH)
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "intake.dump").write_bytes(b"backup bytes")
    deid = tmp_path / "deid"
    deid.mkdir()
    (deid / "config.json").write_text("{}", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/sys/seal-status":
            return httpx.Response(200, json={"sealed": False})
        return httpx.Response(200)

    config = DevProbeConfig(
        env={
            "INTAKE_BACKUP_DIR": str(backups),
            "INTAKE_DEID_MODEL_DIR": str(deid),
            "INTAKE_LLM_HEALTH_URL": "http://127.0.0.1:8801/health",
        },
        http_transport=httpx.MockTransport(handler),
        redis_client=fakeredis.FakeRedis(),
        postgres_select1=lambda: 1,
    )
    clients = build_dev_clients(registry, config)

    # the acceptance's dev-check list: DB, Redis, MinIO, HAPI, OpenBao seal,
    # LiveKit room join, cert expiry (via env target), backup freshness
    for component in ("postgres", "redis", "minio", "hapi", "openbao", "voice-runtime"):
        assert component in clients, f"{component} has no dev client"
    assert isinstance(clients["postgres"](), Ok)
    assert isinstance(clients["redis"](), Ok)
    assert isinstance(clients["minio"](), Ok)
    assert isinstance(clients["hapi"](), Ok)
    assert isinstance(clients["openbao"](), Ok)
    assert isinstance(clients["voice-runtime"](), Skipped)
    assert isinstance(clients["backups"](), Ok)
    assert isinstance(clients["deid-tr-ner-v1"](), Ok)
    assert isinstance(clients["qwen3.5-9b"](), Ok)

    # not wireable today: no daemon (whisper), not deployed (freya), no service
    # yet (api); no TLS edge without INTAKE_TLS_PROBE_TARGET
    for absent in ("whisper-tr-medical", "freya-tts", "api", "edge-tls"):
        assert absent not in clients

    results = {r.component: r for r in run_probes_once(registry, clients)}
    assert results["postgres"].status is ProbeStatus.HEALTHY
    assert results["whisper-tr-medical"].status is ProbeStatus.SKIPPED


def test_build_dev_clients_without_optional_targets(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY_PATH)
    config = DevProbeConfig(
        env={"INTAKE_BACKUP_DIR": str(tmp_path)},
        http_transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        redis_client=fakeredis.FakeRedis(),
        postgres_select1=lambda: 1,
    )
    clients = build_dev_clients(registry, config)
    assert "qwen3.5-9b" not in clients  # no INTAKE_LLM_HEALTH_URL in this environment


# --- the service's own health app (invariant 15) ------------------------------------


def test_probes_service_mounts_the_four_health_endpoints() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    assert client.get("/healthz").status_code == 200
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["checks"]["registry"] == "ok"
    assert client.get("/metrics").status_code == 200
    assert client.get("/version").status_code == 200


def test_probes_service_declares_the_intake_contract() -> None:
    import tomllib

    from intake_platform.health import discover_services, verify_service_declarations

    declaration = next(s for s in discover_services(REPO / "services") if s.name == "probes")
    verify_service_declarations(declaration)  # must not raise

    data = tomllib.loads((REPO / "services" / "probes" / "pyproject.toml").read_text("utf-8"))
    assert data["tool"]["intake"]["probe"] == "probes.http"


# --- remaining probe edges -----------------------------------------------------------


def test_redis_ping_falsy_reply_fails() -> None:
    class Mute:
        def ping(self) -> bool:
            return False

    assert isinstance(redis_ping(Mute()), Failed)


def test_openbao_body_without_sealed_key_fails() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"other": 1}))
    )
    outcome = openbao_seal_status(client, "http://127.0.0.1:8200")
    assert isinstance(outcome, Failed)
    assert "unreadable" in outcome.detail


def test_openbao_non_json_body_fails() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not json"))
    )
    assert isinstance(openbao_seal_status(client, "http://127.0.0.1:8200"), Failed)


def test_registry_get_raises_keyerror_for_unknown_component() -> None:
    registry = _registry(_entry(component="only"))
    with pytest.raises(KeyError):
        registry.get("other")


def test_build_dev_clients_wires_the_tls_edge_when_a_target_is_set() -> None:
    registry = load_registry(REGISTRY_PATH)
    config = DevProbeConfig(
        env={"INTAKE_TLS_PROBE_TARGET": "127.0.0.1:1", "INTAKE_TLS_MIN_DAYS": "7"},
        http_transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        redis_client=fakeredis.FakeRedis(),
        postgres_select1=lambda: 1,
    )
    clients = build_dev_clients(registry, config)
    assert "edge-tls" in clients
    # nothing listens on port 1 — the real TLS fetch fails and the probe reports it
    outcome = clients["edge-tls"]()
    assert isinstance(outcome, Failed)


# --- the runner CLI (the release gate's producer) -------------------------------------


def test_runner_main_once_writes_the_wire_shape(tmp_path: Path) -> None:
    """`main --once` sweeps the real dev wiring and writes the gate's input.

    Statuses are whatever this machine can reach (compose up or down — both
    are truthful sweeps); the contract under test is shape and coverage of
    every registry row, not health.
    """
    from intake_probes.runner import main

    out = tmp_path / "probe-results.json"
    rc = main(["--registry", str(REGISTRY_PATH), "--once", "--out", str(out)])
    assert rc == 0

    import json

    records = json.loads(out.read_text(encoding="utf-8"))
    assert {r["component"] for r in records} == {e.component for e in load_registry(REGISTRY_PATH)}
    for record in records:
        assert set(record) == {"component", "probe", "status", "latency_ms", "detail"}
        assert record["status"] in {"healthy", "unhealthy", "skipped"}


def test_runner_main_once_prints_to_stdout_without_out(capsys: pytest.CaptureFixture[str]) -> None:
    from intake_probes.runner import main

    rc = main(["--registry", str(REGISTRY_PATH), "--once"])
    assert rc == 0
    payload = capsys.readouterr().out
    assert '"component"' in payload and '"status"' in payload
