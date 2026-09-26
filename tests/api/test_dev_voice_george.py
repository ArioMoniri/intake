"""Dev-lane on-demand George (ElevenLabs) clip synthesis — the ON-DEMAND
variant of ADR-028, for SCRIPTED question text only.

These tests INJECT a fake gateway and never dial the live vendor (CLAUDE.md
§How we work; ADR-028): a counting gateway proves the vendor is called at most
once per distinct scripted text, a boom gateway proves the failure path, and a
missing wiring proves fail-closed. The sha256(text_tr) addressing is
``protocols.dsl.clip_text_hash`` — the same the offline ADR-028 manifest uses.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from george_harness import budget, catalogue_of, router_client
from intake_api.dev_voice import (
    ENV_DEV_GEORGE,
    GEORGE_CLIP_PATH,
    GEORGE_VOICE_ID,
    GeorgeClipCache,
    GeorgeWiring,
    george_wiring_from_env,
)
from voice_clips.audio import SynthesisedSpeech
from voice_clips.gateway import (
    ENV_ELEVENLABS_BASE,
    ENV_ELEVENLABS_KEY,
    TtsUnavailableError,
)

_SECRET = "sk-do-not-log-me"  # noqa: S105 - a fake key for the fixture


class CountingGateway:
    """Counts synthesise calls so the cache-hit path can prove no second dial."""

    def __init__(self, pcm: bytes = b"\x01\x00\x02\x00\x03\x00") -> None:
        self.calls = 0
        self.seen: list[tuple[str, str]] = []
        self._pcm = pcm

    def synthesise(self, *, text_tr: str, voice_id: str) -> SynthesisedSpeech:
        self.calls += 1
        self.seen.append((text_tr, voice_id))
        return SynthesisedSpeech(pcm_s16le=self._pcm, sample_rate_hz=24000, channels=1)


class BoomGateway:
    """The vendor is unreachable; the key must never reach the response."""

    def synthesise(self, *, text_tr: str, voice_id: str) -> SynthesisedSpeech:
        raise TtsUnavailableError(f"unreachable; {_SECRET} is never echoed")


#: The scripted texts this suite speaks, standing in for compiled catalogue rows
#: (INT-326: the route admits only a compiled clip-manifest text; the catalogue
#: itself is proven against the real compiler in test_dev_voice_hardening.py).
_SCRIPTED = ("Sizi dinliyorum.", "Şikayetiniz nedir?", "Merhaba.")


def _client(wiring: GeorgeWiring | None) -> TestClient:
    # INT-326: the route needs a patient principal; the door itself is proven
    # in test_dev_voice_hardening.py, so this suite resolves one directly
    return router_client(wiring)


def _wiring(gateway: object, cache_dir: Path) -> GeorgeWiring:
    return GeorgeWiring(
        cache=GeorgeClipCache(gateway=gateway, cache_dir=cache_dir),  # type: ignore[arg-type]
        catalogue=catalogue_of(*_SCRIPTED),
        budget=budget(),
    )


# (a) cache miss → generator called once → clip cached + played -----------------


def test_cache_miss_calls_gateway_once_and_returns_playable_wav(tmp_path: Path) -> None:
    gateway = CountingGateway()
    client = _client(_wiring(gateway, tmp_path))
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": "Sizi dinliyorum."})
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/wav"
    assert res.headers["x-george-cache"] == "miss"
    assert res.content[:4] == b"RIFF" and res.content[8:12] == b"WAVE"
    assert gateway.calls == 1
    # George's voice id, not a client-chosen one
    assert gateway.seen[0][1] == GEORGE_VOICE_ID
    # addressed on disk by sha256(text_tr)
    assert list(tmp_path.glob("*.wav"))


# (b) cache hit → generator NOT called ------------------------------------------


def test_cache_hit_does_not_call_gateway_again(tmp_path: Path) -> None:
    gateway = CountingGateway()
    client = _client(_wiring(gateway, tmp_path))
    body = {"text_tr": "Şikayetiniz nedir?"}
    first = client.post(GEORGE_CLIP_PATH, json=body)
    second = client.post(GEORGE_CLIP_PATH, json=body)
    assert first.status_code == second.status_code == 200
    assert first.headers["x-george-cache"] == "miss"
    assert second.headers["x-george-cache"] == "hit"
    assert second.content == first.content
    assert gateway.calls == 1  # the vendor is dialled at most once per distinct text


# (c) key absent → fail-closed fallback, no crash -------------------------------


def test_unconfigured_wiring_fails_closed_503(tmp_path: Path) -> None:
    client = _client(None)  # no key / dev flag off → no wiring
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": "Merhaba."})
    assert res.status_code == 503
    assert res.json()["error"] == "george_unconfigured"


def test_env_wiring_is_off_without_the_dev_flag(monkeypatch) -> None:
    monkeypatch.delenv(ENV_DEV_GEORGE, raising=False)
    monkeypatch.setenv(ENV_ELEVENLABS_BASE, "https://tts.example.invalid")
    monkeypatch.setenv(ENV_ELEVENLABS_KEY, _SECRET)
    assert george_wiring_from_env() is None


def test_env_wiring_is_off_without_a_key(monkeypatch) -> None:
    monkeypatch.setenv(ENV_DEV_GEORGE, "explicit-yes")
    monkeypatch.setenv(ENV_ELEVENLABS_BASE, "https://tts.example.invalid")
    monkeypatch.delenv(ENV_ELEVENLABS_KEY, raising=False)
    assert george_wiring_from_env() is None


def test_vendor_error_is_502_and_never_echoes_the_key(tmp_path: Path) -> None:
    client = _client(_wiring(BoomGateway(), tmp_path))
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": "Merhaba."})
    assert res.status_code == 502
    assert res.json()["error"] == "george_unavailable"
    assert _SECRET not in res.text


# (d) the numeral/invariant-22 guard REFUSES text before the vendor -------------


def test_numeral_bearing_text_is_refused_before_the_vendor(tmp_path: Path) -> None:
    gateway = CountingGateway()
    client = _client(_wiring(gateway, tmp_path))
    # a patient-shaped answer carrying a numeral: refused before any dial
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": "2 gün önce başladı."})
    assert res.status_code == 422
    assert res.json()["error"] == "not_speakable"
    assert gateway.calls == 0
    assert not list(tmp_path.glob("*.wav"))
