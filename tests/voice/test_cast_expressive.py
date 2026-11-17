"""INT-449 round 2 — expressive casting on eleven_v3 with render-time tags.

What this file pins: a tag comes only from the closed per-context table, exists
only on the wire (``text_tr`` and the catalogue are untouched, invariant 10),
never reaches RED or an instrument, and never reaches v2. The round renders the
kept voices plus two expressive extras at two v3 stability levels, within the
5 USD ceiling. No test dials a vendor: everything is an ``httpx.MockTransport``.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import numpy as np
import pytest
from voice_clips.delivery import DeliveryProfileError, delivery_profile
from voice_clips.gateway import MarkupInScriptError

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts" / "voice"
RATE = 24000
KEY = "k-test-never-printed"


def _load(name: str) -> ModuleType:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lib = _load("voice_cast_library")
rep = _load("voice_cast_report")
tags = _load("voice_cast_tags")
cast = _load("cast_turkish_voices")
r2 = _load("cast_expressive")


def _speak(wire: str, line: str, *, align_tags: bool) -> tuple[bytes, dict[str, list[Any]]]:
    """60 ms of tone per letter of ``line``; the tag characters take no audio."""
    lead = wire[: len(wire) - len(line)]
    chars, starts, ends, parts = [], [], [], [np.zeros(int(RATE * 0.2))]
    now = 0.2
    if align_tags:
        for char in lead:
            chars.append(char)
            starts.append(now)
            ends.append(now)
    for char in line:
        length = 0.06 if char.isalpha() else 0.0
        chars.append(char)
        starts.append(now)
        ends.append(now + length)
        if length:
            t = np.arange(int(RATE * length)) / RATE
            parts.append(0.3 * np.sin(2 * np.pi * 150 * t))
        now += length
    parts.append(np.zeros(int(RATE * 0.2)))
    pcm = (np.concatenate(parts) * 32767).astype("<i2").tobytes()
    return pcm, {
        "characters": chars,
        "character_start_times_seconds": starts,
        "character_end_times_seconds": ends,
    }


# ── the closed table ─────────────────────────────────────────────────────────


def test_the_table_is_closed_and_red_and_instrument_carry_nothing() -> None:
    tags.check_table()
    assert tags.TAGS["red"] == () and tags.TAGS["instrument"] == ()
    assert tags.tag_prefix("red") == "" and tags.tag_prefix("instrument") == ""
    assert tags.tag_prefix("sensitive") == "[softly] [reassuring] "


@pytest.mark.parametrize(
    "change",
    [
        {"red": ("[calm]",)},
        {"instrument": ("[gently]",)},
        {"welcome": ("[pause]",)},
        {"welcome": ("[Warmly]",)},
        {"welcome": ("[warmly] extra",)},
    ],
)
def test_a_table_that_breaks_a_rule_is_refused(change: dict[str, tuple[str, ...]]) -> None:
    with pytest.raises(tags.TagRefused):
        tags.check_table({**tags.TAGS, **change})


def test_the_casting_table_is_the_served_table() -> None:
    for context in tags.TAGS:
        assert tags.TAGS[context] == delivery_profile(context).tags
        assert tags.tag_prefix(context) == delivery_profile(context).wire_prefix


# ── the words stay verbatim ──────────────────────────────────────────────────


def test_no_tag_is_in_the_catalogue_and_a_tagged_line_is_still_refused() -> None:
    assert not any("[" in line.text_tr for line in cast.LINES)
    tagged = cast.CatalogueLine("welcome", "[warmly] " + cast.LINES[0].text_tr, cast.TR_TS)
    # the shared gate refuses markup first (INT-424), the tool's own check after
    with pytest.raises((MarkupInScriptError, cast.CastRefused), match="markup"):
        cast.verify_lines([tagged], read_ref=lambda ref, path: None)


def test_the_tag_exists_only_in_the_request_text() -> None:
    line = cast.LINES[0]
    profile = r2.expressive_profile(line.key, 0.0)
    body = cast.request_body(line.text_tr, profile)
    assert body["text"] == "[warmly] " + line.text_tr == tags.tag_prefix(line.key) + line.text_tr
    assert line.text_tr == cast.LINES[0].text_tr and "[" not in line.text_tr
    assert body["model_id"] == "eleven_v3" and body["apply_text_normalization"] == "off"
    assert body["voice_settings"]["stability"] == 0.0


def _never(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"no request may be sent: {request.url}")


@pytest.mark.parametrize(
    ("context", "tag_set", "model"),
    [
        ("welcome", ("[warmly]",), "eleven_multilingual_v2"),
        ("welcome", ("[sad]",), "eleven_v3"),
        ("sensitive", ("[softly]",), "eleven_v3"),
    ],
)
def test_a_tag_off_the_table_or_on_v2_is_refused_before_the_wire(
    context: str, tag_set: tuple[str, ...], model: str
) -> None:
    profile = dataclasses.replace(delivery_profile(context), model_id=model, tags=tag_set)
    with (
        lib.vendor_client("https://vendor.test", KEY, httpx.MockTransport(_never)) as client,
        pytest.raises(cast.CastRefused),
    ):
        cast.synthesise_aligned(client, text_tr="Teşekkürler.", voice_id="v1", profile=profile)


def test_a_tag_on_red_cannot_even_be_built() -> None:
    with pytest.raises(DeliveryProfileError):
        dataclasses.replace(delivery_profile("red"), tags=("[calm]",))


# ── the cast and the spend ───────────────────────────────────────────────────


def _raw(name: str, **over: Any) -> dict[str, Any]:
    base = {
        "voice_id": f"id-{name}",
        "name": name,
        "gender": "female",
        "age": "middle_aged",
        "accent": "istanbul",
        "language": "tr",
        "category": "professional",
        "descriptive": "calm",
        "use_case": "conversational",
        "description": "A warm and expressive Turkish voice.",
        "cloned_by_count": 100,
        "notice_period": 730,
    }
    return {**base, **over}


def test_the_extras_are_new_middle_aged_expressive_voices_one_per_gender() -> None:
    raws = [
        _raw("f-best", cloned_by_count=9000),
        _raw("f-next"),
        _raw("f-young", age="young", cloned_by_count=99999),
        _raw("f-flat", description="A clear voice.", cloned_by_count=99999),
        _raw("f-loud", descriptive="excited", cloned_by_count=99999),
        _raw("m-best", gender="male", description="Duygusal ve sıcak bir ses."),
        _raw("kept", cloned_by_count=99999),
    ]
    voices = [lib.parse_library_voice(r) for r in raws]
    picked = lib.expressive_extras(voices, frozenset({"id-kept"}))
    assert [v.name for v in picked] == ["f-best", "m-best"]


def test_the_round_casts_the_four_kept_voices_first(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = [lib.parse_library_voice(_raw("x", gender="male"))]
    cast_list = r2.round2_cast(pool)
    assert [v.voice_id for v in cast_list[:4]] == [vid for vid, _ in r2.CORE]
    assert len(cast_list) == 5 and cast_list[4].voice_id == "id-x"


def test_estimate_counts_the_tag_characters() -> None:
    lines = sum(len(line.text_tr) for line in cast.LINES)
    tag_chars = sum(len(tags.tag_prefix(line.key)) for line in cast.LINES)
    assert r2.wire_chars() == lines + tag_chars
    expected = round(6 * 2 * (lines + tag_chars) / 1000 * cast.USD_PER_1K_CHARS, 2)
    assert r2.estimate_usd(6) == expected <= cast.SPEND_CEILING_USD


# ── a full offline round ─────────────────────────────────────────────────────


@pytest.fixture
def live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("INTAKE_TTS_ENDPOINT", "INTAKE_TTS_RECORDED_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TTS_ELEVENLABS_BASE_URL", "https://vendor.test")
    monkeypatch.setenv("TTS_ELEVENLABS_API_KEY", KEY)
    monkeypatch.setenv("EVAL_BUDGET_USD", "5")


def _vendor(
    *, v3_listed: bool = True, align_tags: bool = True, quota: int | None = None
) -> tuple[Any, list[Any]]:
    """``quota``: successful syntheses before every later one is HTTP 401 quota_exceeded."""
    seen: list[httpx.Request] = []
    served = [0]
    library = [_raw(name, voice_id=vid, description="calm") for vid, name in r2.CORE]
    library += [_raw("f-extra"), _raw("m-extra", gender="male")]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/v1/shared-voices":
            return httpx.Response(200, json={"voices": library, "has_more": False})
        if path == "/v1/models":
            ids = ["eleven_multilingual_v2"] + (["eleven_v3"] if v3_listed else [])
            return httpx.Response(
                200,
                json=[
                    {
                        "model_id": m,
                        "can_do_text_to_speech": True,
                        "languages": [{"language_id": "tr"}],
                    }
                    for m in ids
                ],
            )
        if quota is not None and served[0] >= quota:
            detail = {"status": "quota_exceeded", "message": f"echo {KEY} and the text"}
            return httpx.Response(401, json={"detail": detail})
        served[0] += 1
        wire = json.loads(request.content)["text"]
        line = next(x.text_tr for x in cast.LINES if wire.endswith(x.text_tr))
        pcm, alignment = _speak(wire, line, align_tags=align_tags)
        body = {"audio_base64": base64.b64encode(pcm).decode(), "alignment": alignment}
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler), seen


def _args(tmp_path: Path, **over: Any) -> argparse.Namespace:
    base = {"live": True, "estimate": False, "resume": None, "out": tmp_path}
    return argparse.Namespace(**{**base, **over})


def _synth(seen: list[httpx.Request]) -> list[httpx.Request]:
    return [r for r in seen if "text-to-speech" in r.url.path]


def test_a_401_stops_the_run_and_resume_renders_only_the_missing_takes(
    live_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    transport, seen = _vendor(quota=20)
    assert r2.run(_args(tmp_path), transport) == 0
    (run_dir,) = list(tmp_path.iterdir())
    first = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
    assert len(_synth(seen)) == 21, "twenty served, one refused, then nothing more is sent"
    errors = [e for v in first["combos"].values() for e in v["errors"]]
    assert any("HTTP 401 (quota_exceeded" in e for e in errors)
    assert any("stopped the run" in e for e in errors)
    assert KEY not in json.dumps(first) and "the text" not in json.dumps(first)
    kept = {(c, k): p for c, v in first["combos"].items() for k, p in v["clips"].items()}
    assert len(kept) == 20
    incomplete = {v["voice"]["voice_id"] for v in first["combos"].values() if len(v["clips"]) < 6}

    healthy, seen2 = _vendor()
    assert r2.run(_args(tmp_path, live=False, resume=run_dir), healthy) == 0
    again = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
    assert again["blind_order"] == first["blind_order"]
    assert all(len(v["clips"]) == 6 for v in again["combos"].values())
    assert len(_synth(seen2)) == 12 * 6 - 20, "only the missing takes are sent"
    assert {r.url.path.split("/")[3] for r in _synth(seen2)} <= incomplete
    assert all(again["combos"][c]["clips"][k] == p for (c, k), p in kept.items())
    assert again["chars_sent"] > first["chars_sent"] and len(again["resumed_at"]) == 1
    assert KEY not in capsys.readouterr().out


def test_resume_refuses_a_round_one_run(live_env: None, tmp_path: Path) -> None:
    (tmp_path / "index.json").write_text(json.dumps({"round": 1, "combos": {}}), encoding="utf-8")
    transport, seen = _vendor()
    with pytest.raises(lib.CastRefused, match="not a round-2 run"):
        r2.run(_args(tmp_path, live=False, resume=tmp_path), transport)
    assert _synth(seen) == []


def test_vendor_status_keeps_only_a_snake_case_token() -> None:
    def resp(body: Any) -> httpx.Response:
        return httpx.Response(401, json=body)

    assert lib.vendor_status(resp({"detail": {"status": "quota_exceeded"}})) == "quota_exceeded"
    assert lib.vendor_status(resp({"detail": {"status": f"leak {KEY}"}})) == "unknown"
    assert lib.vendor_status(resp({"detail": "plain message"})) == "unknown"
    assert lib.vendor_status(httpx.Response(500, content=b"not json")) == "unknown"


@pytest.mark.parametrize("align_tags", [True, False])
def test_a_round_renders_twelve_tagged_v3_combinations(
    live_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str], align_tags: bool
) -> None:
    transport, seen = _vendor(align_tags=align_tags)
    assert r2.run(_args(tmp_path), transport) == 0
    (run_dir,) = list(tmp_path.iterdir())
    assert run_dir.name.endswith("-r2")
    index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
    assert sorted(index["combos"]) == [f"E{i:02d}" for i in range(1, 13)]
    synth = [json.loads(r.content) for r in seen if "text-to-speech" in r.url.path]
    assert len(synth) == 72
    by_line = {line.text_tr: line.key for line in cast.LINES}
    for body in synth:
        assert body["model_id"] == "eleven_v3"
        assert body["voice_settings"]["stability"] in (0.0, 0.5)
        line = next(t for t in by_line if body["text"].endswith(t))
        assert body["text"] == tags.tag_prefix(by_line[line]) + line
        if by_line[line] in ("red", "instrument"):
            assert "[" not in body["text"]
    for combo in index["combos"].values():
        assert len(combo["clips"]) == 6 and combo["metrics"]["aligned_takes"] == 6
        assert combo["metrics"]["tag_ms_max"] == (0.0 if align_tags else None)
    blind = (run_dir / "blind.html").read_text(encoding="utf-8")
    assert "stability" not in blind and "Cavit" not in blind and "eleven_" not in blind
    out = capsys.readouterr()
    assert KEY not in out.out + out.err + (run_dir / "index.json").read_text(encoding="utf-8")


def test_a_round_refuses_when_v3_is_not_listed_for_turkish(live_env: None, tmp_path: Path) -> None:
    transport, seen = _vendor(v3_listed=False)
    with pytest.raises(lib.CastRefused, match="v3 only"):
        r2.run(_args(tmp_path), transport)
    assert not any("text-to-speech" in r.url.path for r in seen)


# ── the tag span measurement ─────────────────────────────────────────────────


def test_split_prefix_separates_the_tag_and_measures_its_span() -> None:
    text = "Teşekkürler."
    plain = rep.Alignment(tuple(text), (0.0,) * len(text), (0.1,) * len(text))
    assert rep.split_prefix(plain, text) == (plain, None)
    lead = "[calm] "
    tagged = rep.Alignment(
        tuple(lead + text),
        (0.0,) * len(lead) + (0.5,) * len(text),
        (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.5) + (0.6,) * len(text),
    )
    tail, span = rep.split_prefix(tagged, text)
    assert tail is not None and "".join(tail.chars) == text
    assert span == pytest.approx(500.0)
    assert rep.split_prefix(plain, "Başka.") == (None, None)
