"""INT-091 — services/voice-runtime satisfies the monitoring contract (inv. 15).

*"every service exposes /healthz, /readyz, /metrics, /version via
packages/intake_platform/health, emits OTel through the shared setup, declares
its SLOs in docs/slo/<service>.yaml, and has a synthetic probe; a new service
without these fails make check"*.

The readiness checks are the honest part. Three bindings the Talker needs do
not exist on this branch — the clip byte store (INT-060), the self-hosted TTS
gateway (INT-095) and the room-token HTTP route (INT-103 found it absent) — so
each is a named readiness check that reports **not ready** rather than a
stand-in that reports healthy. `/readyz` is 503 on an unwired process, which
is the shape CLAUDE.md asks for: build the mechanism, wire the gate, make it
fail closed, leave the content empty.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from intake_platform.health import discover_services, verify_service_declarations
from intake_platform.slo import load_metrics_catalog, load_slo_file
from intake_probes.registry import ProbeId, load_registry
from intake_voice_runtime.app import VoiceRuntimeWiring, create_app
from intake_voice_runtime.profiles import VoiceProfile

REPO = Path(__file__).resolve().parents[2]
SERVICE_DIR = REPO / "services" / "voice-runtime"
SLO_PATH = REPO / "docs" / "slo" / "voice-runtime.yaml"
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
REGISTRY_PATH = REPO / "observability" / "registry.yaml"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


# --- the four endpoints ------------------------------------------------------------


def test_healthz_is_alive(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "alive"}


def test_version_returns_the_three_build_fields(client: TestClient) -> None:
    assert set(client.get("/version").json()) == {"git_sha", "built_at", "sbom_digest"}


def test_metrics_serves_prometheus_exposition(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_readyz_fails_closed_while_the_bindings_are_absent(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 503
    checks = response.json()["checks"]
    assert checks == {
        "clip_store": "error",
        "speech_synthesizer": "error",
        "room_token": "error",
        "voice_controls": "error",
        "safety_inbox": "error",
    }


def test_readyz_passes_once_every_binding_is_wired() -> None:
    import fakeredis
    from intake_platform.safety_inbox import RedisSafetyInboxStore
    from intake_platform.voice_control import RedisVoiceControlStore
    from talker_harness import RecordedClipStore, RecordingSynthesizer

    wiring = VoiceRuntimeWiring(
        clip_store=RecordedClipStore(),
        synthesizer=RecordingSynthesizer(),
        room_token_source=lambda session_id: "token",
        voice_controls=RedisVoiceControlStore(fakeredis.FakeRedis()),
        safety_inbox=RedisSafetyInboxStore(fakeredis.FakeRedis()),
    )
    client = TestClient(create_app(wiring), raise_server_exceptions=False)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert set(response.json()["checks"].values()) == {"ok"}


def test_http_metrics_carry_the_service_label(client: TestClient) -> None:
    client.get("/healthz")
    exposition = client.get("/metrics").text
    assert 'service="voice-runtime"' in exposition


# --- the declarations --------------------------------------------------------------


def test_the_service_declares_the_intake_contract() -> None:
    declaration = next(
        service
        for service in discover_services(REPO / "services")
        if service.name == "voice-runtime"
    )
    verify_service_declarations(declaration)
    assert declaration.health == "intake_voice_runtime.app:create_app"
    assert declaration.probe == "voice-runtime.http"


def test_the_service_is_a_workspace_member_and_a_mypy_root() -> None:
    root = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert "services/voice-runtime" in root["tool"]["uv"]["workspace"]["members"]
    assert "services/voice-runtime/src" in root["tool"]["mypy"]["files"]
    assert root["tool"]["uv"]["sources"]["intake-voice-runtime"] == {"workspace": True}


def test_check_py_type_checks_and_covers_the_new_service() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "services/voice-runtime/src" in makefile
    assert "--cov=services/voice-runtime/src --cov-branch --cov-fail-under=90" in makefile


def test_the_slo_file_exists_and_matches_its_filename() -> None:
    slo_file = load_slo_file(SLO_PATH)
    assert slo_file.service == "voice-runtime"
    assert {slo.name for slo in slo_file.slos} == {"availability"}


def test_every_slo_reference_is_catalogued() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    for slo in load_slo_file(SLO_PATH).slos:
        assert catalog.unknown_references(slo.sli) == frozenset()


def test_the_registry_still_carries_the_planned_voice_runtime_row() -> None:
    """The worker is not deployed by this issue, so the row stays planned and
    the release gate keeps seeing the true state (INT-022 header)."""
    entry = next(row for row in load_registry(REGISTRY_PATH) if row.component == "voice-runtime")
    assert entry.self_hosted_now is False
    assert entry.probe is ProbeId.LIVEKIT_ROOM_JOIN
    assert entry.phi_path is True


def test_the_three_emitted_families_are_catalogued_as_live() -> None:
    import intake_voice_runtime.metrics  # noqa: F401

    catalog = load_metrics_catalog(CATALOG_PATH)
    by_name = {metric.name: metric for metric in catalog.metrics}
    for name in (
        "talker_tool_calls_total",
        "policyguard_blocks_total",
        "delivery_insertion_wait_ms",
    ):
        assert by_name[name].status == "live", name
        assert by_name[name].owner in {"voice-runtime", "safety"}


# --- invariant 19: one production voice profile, plus typed --------------------------


def test_there_are_exactly_two_profiles() -> None:
    assert {profile.value for profile in VoiceProfile} == {"residency_tr", "typed"}


@pytest.mark.parametrize("gone", ["cascade_fast", "s2s_cloud"])
def test_the_displaced_cloud_profiles_do_not_exist(gone: str) -> None:
    with pytest.raises(ValueError):
        VoiceProfile(gone)


def test_no_code_under_the_service_names_a_displaced_profile() -> None:
    """A docstring may *name* what was displaced and why — that is the record
    files/03 §4.4 asks to keep. Code may not: no identifier, attribute or
    string literal under services/voice-runtime/src may say `cascade_fast` or
    `s2s_cloud` (CLAUDE.md invariant 19)."""
    displaced = ("cascade_fast", "s2s_cloud")
    offenders: list[str] = []
    for path in sorted((SERVICE_DIR / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        }
        for node in ast.walk(tree):
            text = None
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = None if node.value in docstrings else node.value
            elif isinstance(node, ast.Name):
                text = node.id
            elif isinstance(node, ast.Attribute):
                text = node.attr
            if text and any(token in text for token in displaced):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: {text!r}")
    assert offenders == []


# --- the SLO file's own shape ----------------------------------------------------------


def test_the_slo_file_is_valid_yaml_with_the_pinned_burn_rates() -> None:
    raw = yaml.safe_load(SLO_PATH.read_text(encoding="utf-8"))
    alerts = raw["slos"][0]["burn_rate_alerts"]
    assert alerts["fast"]["factor"] == 14.4
    assert alerts["slow"]["factor"] == 6.0
    assert alerts["ticket"]["severity"] == "ticket"
