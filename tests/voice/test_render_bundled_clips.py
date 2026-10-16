"""INT-440 — the bundled-clip renderer (ADR-028 offline clip-gen fast path).

No test dials a vendor: the gateway is the real ElevenLabs adapter over an
``httpx.MockTransport``, so the request shape, the spend gates and the corpus
gates are exercised exactly as the live run will meet them.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import numpy as np
import pytest
from protocols.dsl import clip_text_hash
from voice_clips.delivery import CLIPGEN_VOICE_ID, DELIVERY_PROFILES
from voice_clips.gateway import (
    ELEVENLABS_MODEL_ID,
    ElevenLabsClipGenGateway,
    HttpTtsGateway,
    MarkupInScriptError,
    NumeralInScriptError,
    wire_text,
)

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "voice" / "render_bundled_clips.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_bundled_clips", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_bundled_clips"] = module
    spec.loader.exec_module(module)
    return module


rbc = _load()


def _pcm(ms: int = 400, rate: int = 24000) -> bytes:
    t = np.arange(int(rate * ms / 1000))
    tone = (8000 * np.sin(2 * np.pi * 220 * t / rate)).astype("<i2")
    pad = np.zeros(int(rate * 0.2), dtype="<i2")  # 200 ms of lead and trail air
    return np.concatenate([pad, tone, pad]).tobytes()


def _gateway(calls: list[dict[str, Any]]) -> ElevenLabsClipGenGateway:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, content=_pcm())

    return ElevenLabsClipGenGateway(
        base_url="https://vendor.invalid",
        api_key="test-key-not-real",
        transport=httpx.MockTransport(handler),
    )


def _line(text: str, context: str = "routine") -> Any:
    return rbc.ClipLine(context=context, text_tr=text)


def test_the_committed_set_loads_and_uses_only_bundled_contexts() -> None:
    lines = rbc.load_clip_set()
    assert lines
    assert {line.context for line in lines} <= rbc.BUNDLED_CONTEXTS


def test_bundled_clips_render_under_the_served_table_and_never_red_or_instrument() -> None:
    # D20: the cast voice E04 on eleven_v3, v4 of every row, replaced the
    # George "v3 expressive" proposal; the bundled set renders what is served.
    assert rbc.BUNDLED_CONTEXTS == {"welcome", "acknowledgement", "routine", "sensitive", "closing"}
    for context in rbc.BUNDLED_CONTEXTS:
        profile = rbc.bundled_profile(context)
        assert profile is DELIVERY_PROFILES[context]
        assert profile.voice_id == CLIPGEN_VOICE_ID
        assert profile.model_id == ELEVENLABS_MODEL_ID
    for context in ("red", "instrument"):
        with pytest.raises(rbc.RenderRefused):
            rbc.bundled_profile(context)


def test_plan_reports_chars_and_estimate_and_dials_nothing(tmp_path: Path) -> None:
    lines = [_line("Sizi bugün hekime getiren nedir?"), _line("Teşekkürler.", "acknowledgement")]
    report = rbc.plan_report(lines, tmp_path)
    chars = sum(len(line.text_tr) for line in lines)
    assert report["to_render"] == 2
    assert report["chars_to_send"] == chars
    assert report["by_context"] == {"acknowledgement": 1, "routine": 1}
    assert report["estimate_usd"] == round(chars / 1000 * rbc.USD_PER_1K_CHARS, 2)
    assert list(tmp_path.iterdir()) == []


def test_live_renders_each_line_under_its_context_profile_into_its_context_dir(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    lines = [_line("Hoş geldiniz.", "welcome"), _line("Sizi bugün hekime getiren nedir?")]
    index = rbc.render(lines, tmp_path, _gateway(calls), budget_usd=1.0)
    for line in lines:
        clip = tmp_path / f"{line.context}/{clip_text_hash(line.text_tr)}.wav"
        assert clip.read_bytes()[:4] == b"RIFF"
    served = [DELIVERY_PROFILES[line.context] for line in lines]
    # the tags ride on the wire only; the words are the script's, verbatim
    assert [call["text"] for call in calls] == [
        wire_text(line.text_tr, profile) for line, profile in zip(lines, served, strict=True)
    ]
    assert all(call["text"].endswith(line.text_tr) for call, line in zip(calls, lines, strict=True))
    assert all(call["model_id"] == ELEVENLABS_MODEL_ID for call in calls)
    assert all(call["apply_text_normalization"] == "off" for call in calls)
    assert [call["voice_settings"] for call in calls] == [
        profile.voice_settings.as_request() for profile in served
    ]
    rows = {row["address"]: row for row in index["clips"]}
    assert rows[lines[0].address]["profile"] == DELIVERY_PROFILES["welcome"].key
    assert all(row["lead_silence_ms"] < 200 for row in rows.values())  # dead air trimmed
    assert json.loads((tmp_path / "index.json").read_text())["voice_id"] == CLIPGEN_VOICE_ID


def test_a_rerun_spends_only_on_what_is_missing(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    first, second = _line("Sizi bugün hekime getiren nedir?"), _line("Teşekkürler.", "closing")
    rbc.render([first], tmp_path, _gateway(calls), budget_usd=1.0)
    rbc.render([first, second], tmp_path, _gateway(calls), budget_usd=1.0)
    assert [call["text"] for call in calls] == [
        wire_text(first.text_tr, DELIVERY_PROFILES["routine"]),
        wire_text(second.text_tr, DELIVERY_PROFILES["closing"]),
    ]
    index = json.loads((tmp_path / "index.json").read_text())
    assert {row["address"] for row in index["clips"]} == {first.address, second.address}


def test_a_clip_made_under_another_profile_is_rendered_again(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    line = _line("Sizi bugün hekime getiren nedir?")
    rbc.render([line], tmp_path, _gateway(calls), budget_usd=1.0)
    index_path = tmp_path / "index.json"
    index = json.loads(index_path.read_text())
    index["clips"][0]["profile"] = "delivery.routine@v1"
    index_path.write_text(json.dumps(index))
    assert rbc.pending([line], tmp_path) == [line]


def test_refuses_over_budget_and_over_the_ceiling_before_the_wire(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    with pytest.raises(rbc.RenderRefused):
        rbc.render([_line("Sizi bugün hekime getiren nedir?")], tmp_path, _gateway(calls), 0.0)
    assert calls == []
    assert rbc.SPEND_CEILING_USD == 10.0


def test_refuses_any_gateway_that_is_not_the_offline_adapter(tmp_path: Path) -> None:
    with pytest.raises(rbc.RenderRefused):
        rbc.render(
            [_line("Sizi bugün hekime getiren nedir?")],
            tmp_path,
            HttpTtsGateway(endpoint="http://127.0.0.1:9"),
            budget_usd=1.0,
        )


def _write_set(tmp_path: Path, entries: list[dict[str, str]]) -> Path:
    path = tmp_path / "set.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_a_numeral_or_markup_refuses_the_whole_set(tmp_path: Path) -> None:
    with pytest.raises(NumeralInScriptError):
        rbc.load_clip_set(
            _write_set(tmp_path, [{"context": "routine", "text_tr": "Ağrı 3 gündür mü?"}])
        )
    # main's gate (INT-424) refuses markup before this tool's own backstop
    with pytest.raises(MarkupInScriptError):
        rbc.load_clip_set(
            _write_set(tmp_path, [{"context": "routine", "text_tr": "Ağrı [whispers] nerede?"}])
        )


def test_a_red_or_instrument_context_is_never_rendered_from_this_set(tmp_path: Path) -> None:
    for context in ("red", "instrument"):
        with pytest.raises(rbc.RenderRefused):
            rbc.load_clip_set(
                _write_set(tmp_path, [{"context": context, "text_tr": "Hemen arayın."}])
            )


def test_the_same_line_twice_in_one_context_refuses_the_set(tmp_path: Path) -> None:
    entry = {"context": "routine", "text_tr": "Sizi bugün hekime getiren nedir?"}
    with pytest.raises(rbc.RenderRefused):
        rbc.load_clip_set(_write_set(tmp_path, [entry, entry]))
