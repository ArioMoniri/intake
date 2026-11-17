"""INT-449 — re-render the bundled dialogue clips in the cast voice (E04).

No test dials a vendor: the gateway is the real ADR-028 adapter over an
``httpx.MockTransport``, so the served request (tags on the wire only, the
normaliser off, the pinned model and voice), the quota check, the spend gates
and the stop-on-refusal rule are exercised as the live run meets them.
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
from voice_clips.delivery import CLIPGEN_VOICE_ID, delivery_profile
from voice_clips.gateway import (
    ElevenLabsClipGenGateway,
    MarkupInScriptError,
    NumeralInScriptError,
)

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts" / "voice"
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


rcc = _load("render_cast_clips")

SET = [
    {
        "context": "welcome",
        "text_tr": "Hoş geldiniz. Muayenenizden önce size bazı sorular soracağım.",
    },
    {"context": "routine", "text_tr": "Alkol kullanıyor musunuz?"},
    {"context": "sensitive", "text_tr": "Ailenizde bilinen bir hastalık var mı?"},
    {"context": "acknowledgement", "text_tr": "Anlıyorum, devam edelim."},
]


def _set_file(tmp_path: Path, entries: Any = None) -> Path:
    path = tmp_path / "bundledClipSet.json"
    path.write_text(json.dumps(SET if entries is None else entries), encoding="utf-8")
    return path


def _pcm() -> bytes:
    t = np.arange(24000 // 2) / 24000
    tone = (8000 * np.sin(2 * np.pi * 180 * t)).astype("<i2")
    pad = np.zeros(2400, dtype="<i2")
    return np.concatenate([pad, tone, pad]).tobytes()


def _vendor(
    *,
    used: int = 0,
    limit: int = 100_000,
    sub_status: int = 200,
    refuse_after: int | None = None,
    extension: int | None = None,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    served = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/user/subscription":
            if sub_status != 200:
                return httpx.Response(
                    sub_status, json={"detail": {"status": "missing_permissions"}}
                )
            body: dict[str, object] = {"character_count": used, "character_limit": limit}
            if extension is not None:
                body |= {
                    "allowed_to_extend_character_limit": True,
                    "max_character_limit_extension": extension,
                }
            return httpx.Response(200, json=body)
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json=[
                    {
                        "model_id": "eleven_v3",
                        "can_do_text_to_speech": True,
                        "languages": [{"language_id": "tr"}],
                        "model_rates": {"character_cost_multiplier": 1.0},
                    }
                ],
            )
        if refuse_after is not None and served[0] >= refuse_after:
            return httpx.Response(401, json={"detail": {"status": "quota_exceeded"}})
        served[0] += 1
        return httpx.Response(200, content=_pcm())

    return httpx.MockTransport(handler), seen


def _gateway(transport: httpx.MockTransport) -> ElevenLabsClipGenGateway:
    return ElevenLabsClipGenGateway(
        base_url="https://vendor.test", api_key=KEY, transport=transport
    )


def _synth(seen: list[httpx.Request]) -> list[httpx.Request]:
    return [r for r in seen if "/v1/text-to-speech/" in r.url.path]


# ── the set ──────────────────────────────────────────────────────────────────


def test_the_set_is_loaded_and_every_entry_checked(tmp_path: Path) -> None:
    clip_set = rcc.load_set(_set_file(tmp_path))
    assert [line.context for line in clip_set.lines] == [e["context"] for e in SET]
    assert len(clip_set.sha256) == 64


@pytest.mark.parametrize(
    ("entry", "error"),
    [
        ({"context": "red", "text_tr": "Tek başınıza kalmayın."}, "never re-rendered here"),
        ({"context": "instrument", "text_tr": "Sıradaki sorular."}, "never re-rendered here"),
        ({"context": "welcome", "text_tr": "[warmly] Hoş geldiniz."}, "markup"),
        ({"context": "cheerful", "text_tr": "Merhaba."}, "never re-rendered here"),
    ],
)
def test_an_entry_outside_the_rules_refuses_the_whole_set(
    tmp_path: Path, entry: dict[str, str], error: str
) -> None:
    # markup meets the shared gate first (INT-424), the tool's own check after
    with pytest.raises((MarkupInScriptError, rcc.RenderRefused), match=error):
        rcc.load_set(_set_file(tmp_path, [*SET, entry]))


def test_a_numeral_refuses_the_whole_set(tmp_path: Path) -> None:
    with pytest.raises(NumeralInScriptError):
        rcc.load_set(
            _set_file(tmp_path, [*SET, {"context": "routine", "text_tr": "Saat 9'da mı?"}])
        )


def test_a_duplicate_line_refuses_the_whole_set(tmp_path: Path) -> None:
    with pytest.raises(rcc.RenderRefused, match="twice"):
        rcc.load_set(_set_file(tmp_path, [*SET, SET[0]]))


def test_the_set_comes_from_the_named_ref_when_the_tree_has_none(tmp_path: Path) -> None:
    asked: list[tuple[str, str]] = []

    def read_ref(ref: str, path: str) -> str:
        asked.append((ref, path))
        return json.dumps(SET)

    clip_set = rcc.load_set(tmp_path / "absent.json", read_ref=read_ref)
    assert asked == [(rcc.SET_REF, rcc.SET_PATH)]
    assert clip_set.source == f"{rcc.SET_REF}:{rcc.SET_PATH}" and len(clip_set.lines) == 4


# ── the plan and the spend ───────────────────────────────────────────────────


def test_the_plan_counts_the_tag_characters(tmp_path: Path) -> None:
    clip_set = rcc.load_set(_set_file(tmp_path))
    plan = rcc.plan_report(clip_set.lines, tmp_path / "out")
    wire = sum(len(delivery_profile(e["context"]).wire_prefix) + len(e["text_tr"]) for e in SET)
    assert plan["lines_to_render"] == 4 and plan["wire_chars"] == wire
    assert plan["voice_id"] == CLIPGEN_VOICE_ID and plan["model_id"] == "eleven_v3"
    assert plan["estimate_usd"] == round(wire / 1000 * rcc.USD_PER_1K_CHARS, 2)


def test_the_live_run_refuses_without_a_budget_or_over_it(tmp_path: Path) -> None:
    clip_set = rcc.load_set(_set_file(tmp_path))
    transport, seen = _vendor()
    for budget in (None, 0.001):
        with pytest.raises(rcc.RenderRefused):
            rcc.render(clip_set, tmp_path / "out", _gateway(transport), budget, transport)
    assert _synth(seen) == []


# ── the quota check ──────────────────────────────────────────────────────────


def test_short_credits_stop_the_run_with_the_exact_characters_needed(tmp_path: Path) -> None:
    clip_set = rcc.load_set(_set_file(tmp_path))
    need = rcc.plan_report(clip_set.lines, tmp_path / "out")["wire_chars"]
    transport, seen = _vendor(used=100_000 - need + 1)
    with pytest.raises(rcc.RenderRefused) as raised:
        rcc.render(clip_set, tmp_path / "out", _gateway(transport), 5.0, transport)
    assert f"needs {need} characters" in str(raised.value)
    assert f"{need - 1} remain" in str(raised.value)
    assert _synth(seen) == []


def test_usage_based_billing_counts_up_to_its_owner_set_ceiling(tmp_path: Path) -> None:
    clip_set = rcc.load_set(_set_file(tmp_path))
    need = rcc.plan_report(clip_set.lines, tmp_path / "out")["wire_chars"]
    transport, _ = _vendor(used=100_000 - 12, extension=need)
    assert (
        rcc.check_quota(httpx.Client(base_url="https://vendor.test", transport=transport), need)
        == 12 + need
    )
    short, seen = _vendor(used=100_000 - 12, extension=need - 13)
    with pytest.raises(rcc.RenderRefused, match=f"{need - 1} remain"):
        rcc.render(clip_set, tmp_path / "out", _gateway(short), 5.0, short)
    assert _synth(seen) == []


def test_an_unreadable_quota_fails_closed(tmp_path: Path) -> None:
    clip_set = rcc.load_set(_set_file(tmp_path))
    transport, seen = _vendor(sub_status=401)
    with pytest.raises(rcc.RenderRefused, match="missing_permissions"):
        rcc.render(clip_set, tmp_path / "out", _gateway(transport), 5.0, transport)
    assert _synth(seen) == []


# ── the render ───────────────────────────────────────────────────────────────


def test_every_line_is_rendered_in_the_cast_voice_with_tags_on_the_wire_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clip_set = rcc.load_set(_set_file(tmp_path))
    out = tmp_path / "out"
    transport, seen = _vendor()
    index = rcc.render(clip_set, out, _gateway(transport), 5.0, transport)
    bodies = [json.loads(r.content) for r in _synth(seen)]
    assert len(bodies) == 4
    for request, body, entry in zip(_synth(seen), bodies, SET, strict=True):
        profile = delivery_profile(entry["context"])
        assert request.url.path == f"/v1/text-to-speech/{CLIPGEN_VOICE_ID}"
        assert body["model_id"] == "eleven_v3" and body["apply_text_normalization"] == "off"
        assert body["text"] == profile.wire_prefix + entry["text_tr"]
        assert body["voice_settings"] == profile.voice_settings.as_request()
        wav = out / entry["context"] / f"{clip_text_hash(entry['text_tr'])}.wav"
        assert wav.read_bytes()[:4] == b"RIFF"
    rows = {row["address"]: row for row in index["clips"]}
    assert {row["profile"] for row in rows.values()} == {
        delivery_profile(e["context"]).key for e in SET
    }
    assert all(row["profile"].endswith("@v4") for row in rows.values())
    assert index["voice_id"] == CLIPGEN_VOICE_ID and index["set_sha256"] == clip_set.sha256
    written = (out / "index.json").read_text(encoding="utf-8")
    assert KEY not in written + capsys.readouterr().out and "vendor.test" not in written


def test_a_refusal_stops_the_run_and_a_rerun_renders_only_what_is_missing(tmp_path: Path) -> None:
    clip_set = rcc.load_set(_set_file(tmp_path))
    out = tmp_path / "out"
    transport, seen = _vendor(refuse_after=2)
    with pytest.raises(rcc.RenderRefused, match="stopped"):
        rcc.render(clip_set, out, _gateway(transport), 5.0, transport)
    assert len(_synth(seen)) == 3, "two served, one refused, nothing more sent"
    first = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert len(first["clips"]) == 2

    healthy, seen2 = _vendor()
    index = rcc.render(clip_set, out, _gateway(healthy), 5.0, healthy)
    assert len(_synth(seen2)) == 2 and len(index["clips"]) == 4


def test_a_george_era_clip_on_disk_is_re_rendered(tmp_path: Path) -> None:
    clip_set = rcc.load_set(_set_file(tmp_path))
    out = tmp_path / "out"
    stale = [
        {"address": line.address, "profile": f"delivery.{line.context}@v3"}
        for line in clip_set.lines
    ]
    out.mkdir()
    (out / "index.json").write_text(json.dumps({"clips": stale}), encoding="utf-8")
    assert len(rcc.pending(clip_set.lines, out)) == 4
