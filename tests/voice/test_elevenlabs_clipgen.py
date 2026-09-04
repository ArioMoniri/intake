"""INT-319 / ADR-028 — the OFFLINE cloud clip-gen adapter (ElevenLabs).

This adapter exists for exactly one job: pre-synthesising the FIXED set of
scripted, verbatim, non-patient ``text_tr`` into the clip cache at build time.
It is never a runtime lane, never on the PHI path, and never dialled by a test
or CI — these tests use an ``httpx.MockTransport`` and a spend/key gate, so no
paid call is ever made (CLAUDE.md §How we work; ADR-028).
"""

from __future__ import annotations

import httpx
import pytest
from voice_clips.audio import SynthesisedSpeech
from voice_clips.gateway import (
    ELEVENLABS_PCM_RATE_HZ,
    ENV_ELEVENLABS_BASE,
    ENV_ELEVENLABS_KEY,
    ENV_EVAL_BUDGET_USD,
    ENV_TTS_ENDPOINT,
    ENV_TTS_RECORDED_DIR,
    CloudClipGenNotBudgetedError,
    ElevenLabsClipGenGateway,
    NumeralInScriptError,
    TtsNotConfiguredError,
    TtsRefusedError,
    TtsUnavailableError,
    tts_gateway_from_env,
)

_SECRET = "sk-do-not-log-me"  # noqa: S105 - a fake key for the fixture, never a real one


def _gateway(handler) -> ElevenLabsClipGenGateway:
    return ElevenLabsClipGenGateway(
        base_url="https://tts.example.invalid",
        api_key=_SECRET,
        transport=httpx.MockTransport(handler),
    )


# --- the env selector now knows three sources -------------------------------


def _clear(monkeypatch) -> None:
    for name in (ENV_TTS_ENDPOINT, ENV_TTS_RECORDED_DIR, ENV_ELEVENLABS_BASE, ENV_ELEVENLABS_KEY):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(ENV_EVAL_BUDGET_USD, raising=False)


def test_the_cloud_pair_plus_budget_selects_the_cloud_gateway(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv(ENV_ELEVENLABS_BASE, "https://tts.example.invalid")
    monkeypatch.setenv(ENV_ELEVENLABS_KEY, _SECRET)
    monkeypatch.setenv(ENV_EVAL_BUDGET_USD, "5")
    gateway = tts_gateway_from_env()
    assert isinstance(gateway, ElevenLabsClipGenGateway)
    assert gateway.base_url == "https://tts.example.invalid"


def test_the_cloud_path_refuses_without_a_budget(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv(ENV_ELEVENLABS_BASE, "https://tts.example.invalid")
    monkeypatch.setenv(ENV_ELEVENLABS_KEY, _SECRET)
    with pytest.raises(CloudClipGenNotBudgetedError) as raised:
        tts_gateway_from_env()
    assert ENV_EVAL_BUDGET_USD in str(raised.value)


def test_a_key_without_a_base_is_not_a_cloud_source(monkeypatch) -> None:
    # A stray key alone is not a complete cloud config; with nothing else set
    # the selector fails closed on the whole set rather than half-choosing it.
    _clear(monkeypatch)
    monkeypatch.setenv(ENV_ELEVENLABS_KEY, _SECRET)
    with pytest.raises(TtsNotConfiguredError):
        tts_gateway_from_env()


def test_cloud_and_endpoint_together_are_ambiguous(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv(ENV_TTS_ENDPOINT, "http://127.0.0.1:8803")
    monkeypatch.setenv(ENV_ELEVENLABS_BASE, "https://tts.example.invalid")
    monkeypatch.setenv(ENV_ELEVENLABS_KEY, _SECRET)
    monkeypatch.setenv(ENV_EVAL_BUDGET_USD, "5")
    with pytest.raises(TtsNotConfiguredError):
        tts_gateway_from_env()


# --- the adapter itself -----------------------------------------------------


def test_it_synthesises_raw_pcm_into_speech() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("xi-api-key")
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, content=b"\x01\x00\x02\x00\x03\x00")

    speech = _gateway(handler).synthesise(text_tr="Merhaba.", voice_id="el-tr-voice")
    assert isinstance(speech, SynthesisedSpeech)
    assert speech.sample_rate_hz == ELEVENLABS_PCM_RATE_HZ
    assert speech.channels == 1
    assert speech.pcm_s16le == b"\x01\x00\x02\x00\x03\x00"
    # the voice id is in the path and the vendor normaliser is turned OFF (inv 22)
    assert "el-tr-voice" in str(captured["url"])
    assert captured["body"]["apply_text_normalization"] == "off"  # type: ignore[index]


def test_a_numeral_is_refused_before_the_wire() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
        return httpx.Response(200, content=b"\x00\x00")

    with pytest.raises(NumeralInScriptError):
        _gateway(handler).synthesise(text_tr="2 mg.", voice_id="el-tr-voice")


def test_a_non_2xx_answer_is_a_refusal_that_does_not_echo_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    with pytest.raises(TtsRefusedError) as raised:
        _gateway(handler).synthesise(text_tr="Merhaba.", voice_id="el-tr-voice")
    assert _SECRET not in str(raised.value)


def test_an_empty_body_is_a_refusal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    with pytest.raises(TtsRefusedError):
        _gateway(handler).synthesise(text_tr="Merhaba.", voice_id="el-tr-voice")


def test_a_transport_error_is_unavailable_and_does_not_echo_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(TtsUnavailableError) as raised:
        _gateway(handler).synthesise(text_tr="Merhaba.", voice_id="el-tr-voice")
    assert _SECRET not in str(raised.value)
