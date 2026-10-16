"""INT-515 — the voice tier's synthetic probes (CLAUDE.md invariant 15).

Two rows, two probes:

- ``voice-runtime`` → ``voice_synthetic_turn``: one scripted synthetic turn,
  run by the runtime itself on whatever lanes it has bound and reported as ids
  and timings (``POST /probe/synthetic-turn``). Its fixture-driven half is in
  ``tests/voice/test_voice_runtime_on_host.py``; here the probe reads the
  runtime's answer correctly, including the rate limit that keeps a sweep from
  running up a vendor bill;
- ``livekit-server`` → ``livekit_room_join``: LiveKit's own join validation,
  ``GET /rtc/validate`` with a probe participant's token for a probe room —
  the signalling half of a join, which needs no media and no WebRTC stack.

No socket is opened: both run against ``httpx.MockTransport``.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

import fakeredis
import httpx
import pytest
from intake_platform.room_tokens import LiveKitCredentials
from intake_probes.probes import (
    PROBE_ROOM_SESSION,
    Failed,
    Ok,
    Skipped,
    livekit_room_join,
    voice_synthetic_turn,
)
from intake_probes.registry import load_registry
from intake_probes.runner import DevProbeConfig, build_dev_clients
from test_probe_registry import REGISTRY_PATH

CREDENTIALS = LiveKitCredentials(api_key="k" * 64, api_secret="s" * 64)
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
TURN_URL = "http://voice-runtime:8100/probe/synthetic-turn"


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _report(completed: bool, stages: list[tuple[str, bool, str]]) -> dict[str, Any]:
    return {
        "completed": completed,
        "stages": [
            {"stage": stage, "ok": ok, "latency_ms": 12.5, "code": code}
            for stage, ok, code in stages
        ],
        "bound_slots": ["probe.hears_agent"] if completed else [],
    }


# --- the synthetic turn -------------------------------------------------------------------


def test_a_completed_turn_is_healthy_and_says_how_long_it_took() -> None:
    body = _report(
        True,
        [
            ("agent_speech", True, "ok"),
            ("patient_speech", True, "ok"),
            ("transcribe", True, "ok"),
            ("extract", True, "ok"),
        ],
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body)

    outcome = voice_synthetic_turn(_client(handler), TURN_URL)
    assert isinstance(outcome, Ok)
    assert outcome.detail == "turn completed in 50 ms"
    assert [(r.method, str(r.url)) for r in seen] == [("POST", TURN_URL)]


def test_an_incomplete_turn_names_its_stage_and_code() -> None:
    body = _report(False, [("agent_speech", True, "ok"), ("patient_speech", False, "unbound")])
    outcome = voice_synthetic_turn(_client(lambda r: httpx.Response(503, json=body)), TURN_URL)
    assert isinstance(outcome, Failed)
    assert outcome.detail == "turn stopped at patient_speech: unbound"


def test_a_rate_limited_turn_is_skipped_not_failed() -> None:
    outcome = voice_synthetic_turn(
        _client(lambda r: httpx.Response(429, json={"code": "probe_rate_limited"})), TURN_URL
    )
    assert isinstance(outcome, Skipped)
    assert "rate limited" in outcome.reason


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"completed": False, "stages": []}),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=["completed"]),
        httpx.Response(500, json={"detail": "boom"}),
    ],
)
def test_anything_but_a_completed_report_is_a_failure(response: httpx.Response) -> None:
    outcome = voice_synthetic_turn(_client(lambda r: response), TURN_URL)
    assert isinstance(outcome, Failed)


def test_an_unreachable_runtime_is_a_failure() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    outcome = voice_synthetic_turn(_client(refuse), TURN_URL)
    assert isinstance(outcome, Failed)
    assert outcome.detail.startswith("http request failed")


def test_a_stage_code_that_is_not_an_id_is_not_repeated() -> None:
    """The report carries closed codes; a probe repeats only id-shaped ones."""
    body = _report(False, [("transcribe", False, "Hasta: göğsüm ağrıyor")])
    outcome = voice_synthetic_turn(_client(lambda r: httpx.Response(503, json=body)), TURN_URL)
    assert isinstance(outcome, Failed)
    assert "ağrıyor" not in outcome.detail
    assert outcome.detail == "turn stopped at transcribe: unrecognised"


# --- the room join --------------------------------------------------------------------------


def _claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def test_a_validated_join_is_healthy_and_the_token_never_rides_the_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="success")

    outcome = livekit_room_join(
        _client(handler), "http://livekit:7880", CREDENTIALS, now=lambda: NOW
    )
    assert isinstance(outcome, Ok)
    (request,) = seen
    assert (request.method, request.url.path) == ("GET", "/rtc/validate")
    assert not request.url.query
    scheme, _, token = request.headers["authorization"].partition(" ")
    assert scheme == "Bearer"
    claims = _claims(token)
    assert claims["sub"] == "probe"
    assert claims["video"]["room"] == f"intake-{PROBE_ROOM_SESSION}"
    assert claims["video"]["canPublishData"] is False
    assert claims["exp"] - claims["iat"] <= 60


@pytest.mark.parametrize("status", [401, 404, 500, 503])
def test_a_refused_join_is_a_failure_naming_the_status(status: int) -> None:
    outcome = livekit_room_join(
        _client(lambda r: httpx.Response(status, text="invalid token: sk-...")),
        "http://livekit:7880",
        CREDENTIALS,
        now=lambda: NOW,
    )
    assert isinstance(outcome, Failed)
    assert outcome.detail == f"join validation answered {status}"


def test_an_unreachable_sfu_is_a_failure() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    outcome = livekit_room_join(
        _client(refuse), "http://livekit:7880", CREDENTIALS, now=lambda: NOW
    )
    assert isinstance(outcome, Failed)


# --- the runner's wiring --------------------------------------------------------------------


def test_the_runner_wires_both_rows_when_their_targets_are_named() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/probe/synthetic-turn":
            return httpx.Response(200, json=_report(True, [("extract", True, "ok")]))
        if request.url.path == "/rtc/validate":
            return httpx.Response(200, text="success")
        return httpx.Response(200, json={"sealed": False})

    config = DevProbeConfig(
        env={
            "INTAKE_VOICE_RUNTIME_URL": "http://voice-runtime:8100",
            "INTAKE_LIVEKIT_URL": "http://livekit:7880",
            "LIVEKIT_API_KEY": CREDENTIALS.api_key,
            "LIVEKIT_API_SECRET": CREDENTIALS.api_secret,
        },
        http_transport=httpx.MockTransport(handler),
        redis_client=fakeredis.FakeRedis(),
        postgres_select1=lambda: 1,
    )
    clients = build_dev_clients(load_registry(REGISTRY_PATH), config)
    assert isinstance(clients["voice-runtime"](), Ok)
    assert isinstance(clients["livekit-server"](), Ok)


def test_half_a_livekit_target_is_skipped_never_guessed() -> None:
    config = DevProbeConfig(
        env={"INTAKE_LIVEKIT_URL": "http://livekit:7880"},
        http_transport=httpx.MockTransport(lambda r: httpx.Response(200)),
        redis_client=fakeredis.FakeRedis(),
        postgres_select1=lambda: 1,
    )
    outcome = build_dev_clients(load_registry(REGISTRY_PATH), config)["livekit-server"]()
    assert isinstance(outcome, Skipped)
    assert "LIVEKIT_API_KEY" in outcome.reason
