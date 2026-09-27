"""Dev-lane on-demand George (ElevenLabs) clip synthesis — the ON-DEMAND
variant of ADR-028, for SCRIPTED question text only.

These tests INJECT a fake gateway and never dial the live vendor (CLAUDE.md
§How we work; ADR-028): a counting gateway proves the vendor is called at most
once per distinct scripted text, a boom gateway proves the failure path, and a
missing wiring proves fail-closed. The sha256(text_tr) addressing is
``protocols.dsl.clip_text_hash`` — the same the offline ADR-028 manifest uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from george_harness import budget, catalogue_of, compiled_dist, router_client
from intake_api.dev_voice import (
    ENV_DEV_GEORGE,
    GEORGE_CLIP_PATH,
    GEORGE_VOICE_ID,
    GeorgeClipCache,
    GeorgeWiring,
    george_wiring_from_env,
)
from intake_api.dev_voice_guard import ScriptedCatalogue, load_scripted_catalogue
from protocols.dsl import clip_text_hash
from voice_clips.audio import SynthesisedSpeech
from voice_clips.delivery import DELIVERY_CONTEXTS, DeliveryProfile, delivery_profile
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
        self.profiles: list[DeliveryProfile] = []
        self._pcm = pcm

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
        self.calls += 1
        self.seen.append((text_tr, voice_id))
        self.profiles.append(profile)
        return SynthesisedSpeech(pcm_s16le=self._pcm, sample_rate_hz=24000, channels=1)


class BoomGateway:
    """The vendor is unreachable; the key must never reach the response."""

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
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
    # The api names no audio content type (invariant 3's audio-retention guard);
    # the client reads the bytes opaquely and plays them by file URI. Still a real
    # WAV — the RIFF/WAVE magic bytes prove the framing survived the move to
    # voice_clips.audio.wav_bytes.
    assert res.headers["content-type"] == "application/octet-stream"
    assert res.headers["x-george-cache"] == "miss"
    assert res.content[:4] == b"RIFF" and res.content[8:12] == b"WAVE"
    assert gateway.calls == 1
    # George's voice id, not a client-chosen one
    assert gateway.seen[0][1] == GEORGE_VOICE_ID
    # addressed on disk by the delivery profile (INT-415) and sha256(text_tr),
    # with no audio-typed file extension; no context sent means routine
    routine = delivery_profile("routine")
    assert gateway.profiles == [routine]
    assert [p.name for p in tmp_path.iterdir()] == [routine.key]
    assert [p.name for p in (tmp_path / routine.key).iterdir()] == [
        clip_text_hash("Sizi dinliyorum.")
    ]


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
    assert not list(tmp_path.iterdir())


# (e) INT-415: the delivery context picks a server-side profile ---------------


def test_every_context_but_red_is_served_under_its_own_profile(tmp_path: Path) -> None:
    gateway = CountingGateway()
    client = _client(_wiring(gateway, tmp_path))
    served = [context for context in DELIVERY_CONTEXTS if context != "red"]
    for context in served:
        res = client.post(
            GEORGE_CLIP_PATH, json={"text_tr": "Merhaba.", "delivery_context": context}
        )
        assert res.status_code == 200, context
        assert res.headers["x-george-cache"] == "miss"
    # one dial per (text, profile): the same words in six contexts are six clips
    assert gateway.calls == len(served)
    assert [profile.context for profile in gateway.profiles] == served
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        delivery_profile(context).key for context in served
    )


def test_the_profile_changes_the_cache_key_and_a_repeat_is_a_hit(tmp_path: Path) -> None:
    gateway = CountingGateway()
    client = _client(_wiring(gateway, tmp_path))
    routine = client.post(GEORGE_CLIP_PATH, json={"text_tr": "Merhaba."})
    welcome = client.post(
        GEORGE_CLIP_PATH, json={"text_tr": "Merhaba.", "delivery_context": "welcome"}
    )
    again = client.post(
        GEORGE_CLIP_PATH, json={"text_tr": "Merhaba.", "delivery_context": "welcome"}
    )
    assert [r.headers["x-george-cache"] for r in (routine, welcome, again)] == [
        "miss",
        "miss",
        "hit",
    ]
    assert gateway.calls == 2
    text_hash = clip_text_hash("Merhaba.")
    assert (tmp_path / delivery_profile("routine").key / text_hash).is_file()
    assert (tmp_path / delivery_profile("welcome").key / text_hash).is_file()


def test_red_is_never_synthesised_on_demand(tmp_path: Path) -> None:
    """Invariant 21: the RED script is pre-positioned on the device and
    triggered over the data channel; the on-demand route never serves it."""
    gateway = CountingGateway()
    client = _client(_wiring(gateway, tmp_path))
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": "Merhaba.", "delivery_context": "red"})
    assert res.status_code == 422
    assert res.json()["error"] == "red_not_on_demand"
    assert gateway.calls == 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("near_miss", ["Red", "RED", "cheerful", "routine ", "", "urgent"])
def test_a_context_outside_the_seven_is_refused_before_the_vendor(
    tmp_path: Path, near_miss: str
) -> None:
    gateway = CountingGateway()
    client = _client(_wiring(gateway, tmp_path))
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": "Merhaba.", "delivery_context": near_miss})
    assert res.status_code == 422
    assert gateway.calls == 0


def test_the_client_cannot_send_voice_settings(tmp_path: Path) -> None:
    """The profile table is server-side only: a body carrying its own voice
    settings or model is refused, never merged."""
    gateway = CountingGateway()
    client = _client(_wiring(gateway, tmp_path))
    for extra in (
        {"voice_settings": {"style": 1.0}},
        {"model_id": "eleven_v3"},
        {"delivery_profile": "delivery.welcome@v1"},
    ):
        res = client.post(GEORGE_CLIP_PATH, json={"text_tr": "Merhaba.", **extra})
        assert res.status_code == 422, extra
    assert gateway.calls == 0


def _pinned(tmp_path: Path, pins: dict[str, str]) -> tuple[CountingGateway, TestClient]:
    gateway = CountingGateway()
    catalogue = ScriptedCatalogue(
        text_hashes=frozenset(clip_text_hash(text) for text in (*_SCRIPTED, *pins)),
        pinned_contexts={clip_text_hash(text): context for text, context in pins.items()},  # type: ignore[misc]
    )
    wiring = GeorgeWiring(
        cache=GeorgeClipCache(gateway=gateway, cache_dir=tmp_path),  # type: ignore[arg-type]
        catalogue=catalogue,
        budget=budget(),
    )
    return gateway, _client(wiring)


@pytest.mark.parametrize("claimed", [c for c in DELIVERY_CONTEXTS if c != "red"])
def test_a_red_script_is_refused_whatever_context_the_client_claims(
    tmp_path: Path, claimed: str
) -> None:
    """The label is not trusted: a compiled rule script is RED delivery, so
    calling it routine does not buy it an on-demand clip."""
    gateway, client = _pinned(tmp_path, {"Hemen yardım isteyin.": "red"})
    res = client.post(
        GEORGE_CLIP_PATH,
        json={"text_tr": "Hemen yardım isteyin.", "delivery_context": claimed},
    )
    assert res.status_code == 422
    assert res.json()["error"] == "red_not_on_demand"
    assert "Hemen" not in res.text  # invariant 6: the text is never echoed
    assert gateway.calls == 0


def test_an_instrument_item_is_spoken_only_in_the_instrument_profile(tmp_path: Path) -> None:
    gateway, client = _pinned(tmp_path, {"Son iki haftada ne sıklıkla?": "instrument"})
    wrong = client.post(
        GEORGE_CLIP_PATH,
        json={"text_tr": "Son iki haftada ne sıklıkla?", "delivery_context": "welcome"},
    )
    assert wrong.status_code == 422
    assert wrong.json()["error"] == "delivery_context_mismatch"
    assert gateway.calls == 0
    right = client.post(
        GEORGE_CLIP_PATH,
        json={"text_tr": "Son iki haftada ne sıklıkla?", "delivery_context": "instrument"},
    )
    assert right.status_code == 200
    assert [profile.context for profile in gateway.profiles] == ["instrument"]


def test_an_unpinned_text_is_served_in_any_context_but_red(tmp_path: Path) -> None:
    """The negative control for the pins: an ordinary scripted question is not
    held to one context."""
    gateway, client = _pinned(tmp_path, {"Hemen yardım isteyin.": "red"})
    res = client.post(
        GEORGE_CLIP_PATH, json={"text_tr": "Sizi dinliyorum.", "delivery_context": "sensitive"}
    )
    assert res.status_code == 200
    assert [profile.context for profile in gateway.profiles] == ["sensitive"]


def test_the_compiled_catalogue_pins_every_rule_script_to_red(tmp_path: Path) -> None:
    """Against a bundle the REAL compiler wrote: the pins are derived from the
    manifest rows' subjects, server-side, and every rule row is pinned red."""
    dist = compiled_dist(tmp_path, voice="george-test")
    catalogue = load_scripted_catalogue(dist)
    manifest_path = next(dist.glob("*/clips.*.json"))
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))["entries"]
    red = {row["text_hash"] for row in rows if row["subject"].startswith("rf.")}
    assert red, "the fixture pack must carry a rule script for this to mean anything"
    assert {h for h, c in catalogue.pinned_contexts.items() if c == "red"} == red
    for row in rows:
        expected = "red" if row["subject"].startswith("rf.") else None
        assert catalogue.pinned_contexts.get(row["text_hash"]) == expected
