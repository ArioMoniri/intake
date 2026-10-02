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
from voice_clips.delivery import DELIVERY_PROFILES, MAX_STYLE
from voice_clips.gateway import ElevenLabsClipGenGateway, HttpTtsGateway, NumeralInScriptError

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


def test_the_committed_set_loads_with_a_v3_row_for_every_context_it_uses() -> None:
    lines = rbc.load_clip_set()
    assert lines
    assert {line.context for line in lines} <= set(rbc.V3_EXPRESSIVE)


def test_the_v3_expressive_table_is_the_owner_request_and_leaves_red_and_instrument_alone() -> None:
    assert dict(rbc.V3_EXPRESSIVE) == {
        "welcome": (0.32, 0.40, 0.97),
        "acknowledgement": (0.38, 0.35, 1.00),
        "routine": (0.40, 0.30, 0.98),
        "sensitive": (0.50, 0.20, 0.92),
        "closing": (0.35, 0.40, 0.96),
    }
    assert "red" not in rbc.V3_EXPRESSIVE and "instrument" not in rbc.V3_EXPRESSIVE
    # The style ceiling was lifted from 0.3 to 0.4 for exactly this table (owner
    # request, 3 Oct 2026); pinned so a further lift is a reviewed change.
    assert MAX_STYLE == 0.4
    assert max(style for _, style, _ in rbc.V3_EXPRESSIVE.values()) == MAX_STYLE
    for context in ("red", "instrument"):
        assert DELIVERY_PROFILES[context].voice_settings.style == 0.0  # untouched
    welcome = rbc.v3_profile("welcome")
    assert welcome.key == "delivery.welcome@v3"
    assert welcome.voice_settings.as_request() == {
        "stability": 0.32,
        "similarity_boost": 0.75,
        "style": 0.40,
        "use_speaker_boost": True,
        "speed": 0.97,
    }


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
    assert [call["text"] for call in calls] == [line.text_tr for line in lines]
    assert all(call["model_id"] == "eleven_multilingual_v2" for call in calls)
    assert all(call["apply_text_normalization"] == "off" for call in calls)
    assert calls[0]["voice_settings"]["style"] == 0.40  # welcome
    assert calls[1]["voice_settings"]["style"] == 0.30  # routine
    rows = {row["address"]: row for row in index["clips"]}
    assert rows[lines[0].address]["profile"] == "delivery.welcome@v3"
    assert all(row["lead_silence_ms"] < 200 for row in rows.values())  # dead air trimmed
    assert json.loads((tmp_path / "index.json").read_text())["voice_id"] == rbc.GEORGE_VOICE_ID


def test_a_rerun_spends_only_on_what_is_missing(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    first, second = _line("Sizi bugün hekime getiren nedir?"), _line("Teşekkürler.", "closing")
    rbc.render([first], tmp_path, _gateway(calls), budget_usd=1.0)
    rbc.render([first, second], tmp_path, _gateway(calls), budget_usd=1.0)
    assert [call["text"] for call in calls] == [first.text_tr, second.text_tr]
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
    with pytest.raises(rbc.RenderRefused):
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
