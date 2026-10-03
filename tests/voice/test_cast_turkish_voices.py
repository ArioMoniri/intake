"""INT-449 — the Turkish voice-casting tool (ADR-028 offline clip-gen lane).

No test dials a vendor. The library, the model list and the timestamped
synthesis are an ``httpx.MockTransport``; the gateway is the real ADR-028
adapter where the request body is compared. The measurements run on synthetic
signals whose gaps and pitch steps are known.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import numpy as np
import pytest
from voice_clips.delivery import delivery_profile
from voice_clips.gateway import ElevenLabsClipGenGateway, NumeralInScriptError

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts" / "voice"
RATE = 24000
KEY = "k-test-never-printed"


def _load(name: str) -> ModuleType:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    if name in sys.modules:  # one module object per session, shared with round 2's tests
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lib = _load("voice_cast_library")
rep = _load("voice_cast_report")
cast = _load("cast_turkish_voices")


# ── synthetic speech ─────────────────────────────────────────────────────────


def _tone(seconds: float, hz: float) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    return 0.3 * np.sin(2 * np.pi * hz * t) + 0.1 * np.sin(2 * np.pi * 2 * hz * t)


def _speak(
    text: str, *, gap_s: float = 0.0, hz: Callable[[int], float] = lambda i: 150.0
) -> tuple[bytes, dict[str, list[Any]]]:
    """A take of ``text``: each letter 60 ms of tone, each space ``gap_s`` of silence."""
    parts: list[np.ndarray] = [np.zeros(int(RATE * 0.2))]
    chars, starts, ends = [], [], []
    now, word = 0.2, 0
    for char in text:
        length = gap_s if char.isspace() else (0.0 if not char.isalpha() else 0.06)
        if char.isspace():
            word += 1
        chars.append(char)
        starts.append(now)
        ends.append(now + length)
        if length:
            parts.append(
                _tone(length, hz(word)) if char.isalpha() else np.zeros(int(RATE * length))
            )
        now += length
    parts.append(np.zeros(int(RATE * 0.2)))
    pcm = (np.concatenate(parts) * 32767).astype("<i2").tobytes()
    alignment = {
        "characters": chars,
        "character_start_times_seconds": starts,
        "character_end_times_seconds": ends,
    }
    return pcm, alignment


def _metrics(text: str, **kwargs: Any) -> Any:
    pcm, alignment = _speak(text, **kwargs)
    samples = np.frombuffer(pcm, dtype="<i2")
    return rep.clip_metrics(samples, RATE, text, rep.Alignment.from_json(alignment))


# ── catalogue lines ──────────────────────────────────────────────────────────


def test_six_lines_one_per_named_context() -> None:
    keys = [line.key for line in cast.LINES]
    assert keys == ["welcome", "routine", "sensitive", "acknowledgement", "instrument", "red"]


def test_lines_on_main_are_verbatim_in_their_sources() -> None:
    on_main = [line for line in cast.LINES if line.ref is None]
    assert on_main, "at least the protocol, i18n and RED lines are on main"
    cast.verify_lines(on_main, read_ref=lambda ref, path: None)


def test_branch_lines_verify_against_the_named_ref_only() -> None:
    branch = [line for line in cast.LINES if line.ref is not None]
    seen: list[tuple[str, str]] = []

    def read_ref(ref: str, path: str) -> str:
        seen.append((ref, path))
        return "\n".join(line.text_tr for line in branch)

    cast.verify_lines(branch, repo=REPO / "nowhere", read_ref=read_ref)
    assert {ref for ref, _ in seen} == {cast.INT414_REF}


def test_a_line_not_in_its_source_refuses_the_whole_run() -> None:
    near_miss = cast.CatalogueLine("welcome", "Hoş geldiniz, muayeneden önce.", cast.TR_TS)
    with pytest.raises(cast.CastRefused, match="not verbatim"):
        cast.verify_lines([near_miss], read_ref=lambda ref, path: None)


def test_numerals_and_markup_are_refused_before_anything_is_sent() -> None:
    with pytest.raises(NumeralInScriptError):
        cast.verify_lines([cast.CatalogueLine("red", "Hemen 112'yi arayın.", cast.TR_TS)])
    with pytest.raises(cast.CastRefused, match="markup"):
        cast.verify_lines([cast.CatalogueLine("welcome", "[warmly] Hoş geldiniz.", cast.TR_TS)])


def test_george_is_the_voice_dev_voice_pins() -> None:
    source = (REPO / "services/api/src/intake_api/dev_voice.py").read_text(encoding="utf-8")
    pinned = re.search(r'GEORGE_VOICE_ID: Final = "([^"]+)"', source)
    assert pinned is not None and pinned.group(1) == lib.GEORGE_VOICE_ID


# ── the wire ─────────────────────────────────────────────────────────────────


def test_request_body_is_the_gateways_body() -> None:
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=b"\x00\x01" * 400)

    gateway = ElevenLabsClipGenGateway(
        base_url="https://vendor.test", api_key=KEY, transport=httpx.MockTransport(handler)
    )
    profile = delivery_profile("welcome")
    gateway.synthesise(text_tr=cast.LINES[0].text_tr, voice_id="v1", profile=profile)
    assert captured == [cast.request_body(cast.LINES[0].text_tr, profile)]
    assert captured[0]["apply_text_normalization"] == "off"


def test_aligned_synthesis_hits_with_timestamps_and_returns_the_alignment() -> None:
    seen: list[httpx.Request] = []
    pcm, alignment = _speak("Teşekkür ederim.")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {"audio_base64": base64.b64encode(pcm).decode(), "alignment": alignment}
        return httpx.Response(200, json=body)

    with lib.vendor_client("https://vendor.test", KEY, httpx.MockTransport(handler)) as client:
        speech, got = cast.synthesise_aligned(
            client, text_tr="Teşekkür ederim.", voice_id="v1", profile=delivery_profile("routine")
        )
    request = seen[0]
    assert request.url.path == "/v1/text-to-speech/v1/with-timestamps"
    assert request.url.params["output_format"] == "pcm_24000"
    assert request.headers["xi-api-key"] == KEY
    assert speech.pcm_s16le == pcm and got is not None and "".join(got.chars) == "Teşekkür ederim."


def test_a_model_outside_the_casting_pair_is_refused() -> None:
    profile = delivery_profile("routine")
    other = type(profile)(
        context="routine",
        version=1,
        model_id="eleven_flash_v2_5",
        voice_settings=profile.voice_settings,
    )
    with lib.vendor_client("https://vendor.test", KEY) as client, pytest.raises(cast.CastRefused):
        cast.synthesise_aligned(client, text_tr="Teşekkürler.", voice_id="v1", profile=other)


# ── library and shortlist ────────────────────────────────────────────────────


def _raw(name: str, **over: Any) -> dict[str, Any]:
    base = {
        "voice_id": f"id-{name}",
        "name": name,
        "public_owner_id": "o",
        "gender": "female",
        "age": "middle_aged",
        "accent": "standard",
        "language": "tr",
        "category": "professional",
        "descriptive": "calm",
        "use_case": "conversational",
        "description": "Sakin ve sıcak.",
        "usage_character_count_1y": 10_000_000,
        "cloned_by_count": 500,
        "notice_period": 730,
        "live_moderation_enabled": False,
        "free_users_allowed": True,
        "featured": False,
        "verified_languages": [
            {"language": "tr", "model_id": "eleven_multilingual_v2", "accent": "standard"}
        ],
    }
    return {**base, **over}


@pytest.mark.parametrize(
    ("over", "why"),
    [
        ({"category": "famous"}, "iconic"),
        ({"rate": 2.0}, "custom rate"),
        ({"fiat_rate": 0.5}, "custom rate"),
        ({"accent": "american"}, "native"),
        ({"language": "en"}, "native"),
        ({"age": "child"}, "adult"),
    ],
)
def test_ineligible_voices_are_excluded(over: dict[str, Any], why: str) -> None:
    reason = lib.exclusion(lib.parse_library_voice(_raw("x", **over)))
    assert reason is not None and why in reason
    assert lib.exclusion(lib.parse_library_voice(_raw("ok"))) is None


def test_score_prefers_calm_professional_standard_turkish() -> None:
    calm = lib.parse_library_voice(_raw("calm"))
    loud = lib.parse_library_voice(
        _raw(
            "loud",
            accent="karadeniz",
            descriptive="excited",
            use_case="characters_animation",
            description="Komik çizgi film sesi.",
        )
    )
    assert lib.accent_kind(loud) == "regional"
    assert lib.score(calm) > lib.score(loud)


def test_shortlist_is_gender_balanced_and_never_includes_the_control() -> None:
    raws = [_raw(f"f{i}", cloned_by_count=1000 * (9 - i)) for i in range(6)]
    raws += [_raw(f"m{i}", gender="male", cloned_by_count=10 * (9 - i)) for i in range(6)]
    raws.append(_raw("george", voice_id=lib.GEORGE_VOICE_ID))
    picked = lib.shortlist([lib.parse_library_voice(r) for r in raws], 8)
    assert sorted(v.gender for v in picked) == ["female"] * 4 + ["male"] * 4
    assert lib.GEORGE_VOICE_ID not in {v.voice_id for v in picked}


def _vendor(
    *, refuse_v3: bool = False, refuse_voice: str = "", v3_listed: bool = True, gap_s: float = 0.0
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    library = [_raw(f"f{i}") for i in range(5)] + [_raw(f"m{i}", gender="male") for i in range(5)]
    library.append(_raw("famous", category="famous"))

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/v1/shared-voices":
            return httpx.Response(200, json={"voices": library, "has_more": False})
        if path == "/v2/voices":
            return httpx.Response(200, json={"voices": [], "has_more": False})
        if path == "/v1/models":
            models = [
                {
                    "model_id": "eleven_multilingual_v2",
                    "can_do_text_to_speech": True,
                    "languages": [{"language_id": "tr"}],
                }
            ]
            if v3_listed:
                models.append(
                    {
                        "model_id": "eleven_v3",
                        "can_do_text_to_speech": True,
                        "languages": [{"language_id": "tr"}],
                        "model_rates": {"character_cost_multiplier": 1.0},
                    }
                )
            return httpx.Response(200, json=models)
        body = json.loads(request.content)
        if (refuse_v3 and body["model_id"] == "eleven_v3") or (
            refuse_voice and f"/{refuse_voice}/" in path
        ):
            return httpx.Response(400, json={"detail": "refused"})
        pcm, alignment = _speak(body["text"], gap_s=gap_s)
        return httpx.Response(
            200, json={"audio_base64": base64.b64encode(pcm).decode(), "alignment": alignment}
        )

    return httpx.MockTransport(handler), seen


def test_library_query_sends_only_filters_and_dedups_across_sorts() -> None:
    transport, seen = _vendor()
    with lib.vendor_client("https://vendor.test", KEY, transport) as client:
        voices = lib.fetch_library(client)
    assert len(voices) == 11
    for request in seen:
        assert set(request.url.params) == {"language", "page_size", "page", "sort"}
        assert request.url.params["language"] == "tr" and not request.content


def test_v3_is_compared_only_when_listed_for_turkish() -> None:
    assert list(cast.cast_models({"eleven_multilingual_v2": 1.0}, True)) == [
        "eleven_multilingual_v2"
    ]
    assert list(cast.cast_models(None, True)) == ["eleven_multilingual_v2", "eleven_v3"]
    assert list(cast.cast_models(None, False)) == ["eleven_multilingual_v2"]


# ── spend ────────────────────────────────────────────────────────────────────


def test_estimate_is_chars_times_voices_times_models_at_the_planning_rate() -> None:
    chars = cast.chars_per_voice()
    expected = round(9 * chars * 2 / 1000 * cast.USD_PER_1K_CHARS, 2)
    assert cast.estimate_usd(9, {"a": 1.0, "b": 1.0}) == expected
    assert expected <= cast.SPEND_CEILING_USD


def _args(tmp_path: Path, **over: Any) -> argparse.Namespace:
    base = {
        "live": True,
        "estimate": False,
        "analyse": None,
        "out": tmp_path,
        "shortlist": 8,
        "no_v3": False,
    }
    return argparse.Namespace(**{**base, **over})


@pytest.fixture
def live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("INTAKE_TTS_ENDPOINT", "INTAKE_TTS_RECORDED_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TTS_ELEVENLABS_BASE_URL", "https://vendor.test")
    monkeypatch.setenv("TTS_ELEVENLABS_API_KEY", KEY)
    monkeypatch.setenv("EVAL_BUDGET_USD", "5")


def test_live_refuses_without_a_budget(
    live_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("EVAL_BUDGET_USD")
    transport, seen = _vendor()
    with pytest.raises(cast.CastRefused, match="EVAL_BUDGET_USD"):
        cast.run(_args(tmp_path), transport)
    assert seen == []


def test_live_refuses_when_the_estimate_exceeds_the_budget(
    live_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EVAL_BUDGET_USD", "0.5")
    transport, seen = _vendor()
    with pytest.raises(cast.CastRefused, match="exceeds the budget"):
        cast.run(_args(tmp_path), transport)
    assert not any("text-to-speech" in r.url.path for r in seen)


def test_plan_without_credentials_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TTS_ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(cast.CastRefused, match="--estimate"):
        cast.run(_args(tmp_path, live=False))


# ── a full offline run ───────────────────────────────────────────────────────


def _run_dir(tmp_path: Path) -> Path:
    (run_dir,) = [p for p in tmp_path.iterdir() if p.is_dir()]
    return run_dir


def test_live_run_writes_blind_and_labelled_pages_and_never_the_key(
    live_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    transport, seen = _vendor()
    assert cast.run(_args(tmp_path), transport) == 0
    run_dir = _run_dir(tmp_path)
    index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
    assert len(index["combos"]) == 18 and len(index["ranking"]) == 18
    voices = {c["voice"]["voice_id"] for c in index["combos"].values()}
    assert lib.GEORGE_VOICE_ID in voices and "id-famous" not in voices
    sent = [json.loads(r.content)["text"] for r in seen if "text-to-speech" in r.url.path]
    assert set(sent) == {line.text_tr for line in cast.LINES}
    blind = (run_dir / "blind.html").read_text(encoding="utf-8")
    labelled = (run_dir / "labelled.html").read_text(encoding="utf-8")
    for combo in index["combos"].values():
        assert combo["voice"]["voice_id"] not in blind and combo["voice"]["name"] not in blind
        assert combo["voice"]["voice_id"] in labelled
    assert "eleven_" not in blind
    out = capsys.readouterr()
    written = "".join(p.read_text(encoding="utf-8") for p in run_dir.glob("*.*"))
    assert KEY not in out.out + out.err + written
    assert "vendor.test" not in written


def test_v3_refusal_drops_v3_and_keeps_every_v2_take(live_env: None, tmp_path: Path) -> None:
    transport, seen = _vendor(refuse_v3=True)
    cast.run(_args(tmp_path), transport)
    index = json.loads((_run_dir(tmp_path) / "index.json").read_text(encoding="utf-8"))
    v3_calls = [r for r in seen if r.content and json.loads(r.content)["model_id"] == "eleven_v3"]
    assert len(v3_calls) == 1, "v3 is tried once, then dropped for the run"
    for combo in index["combos"].values():
        assert (len(combo["clips"]) == 6) == (combo["model_id"] == "eleven_multilingual_v2")


def test_a_refused_voice_is_dropped_after_one_call(live_env: None, tmp_path: Path) -> None:
    transport, seen = _vendor(refuse_voice="id-f0", v3_listed=False)
    cast.run(_args(tmp_path), transport)
    calls = [r for r in seen if "/id-f0/" in r.url.path]
    assert len(calls) == 1


def test_analyse_reproduces_the_ranking_offline(live_env: None, tmp_path: Path) -> None:
    transport, _ = _vendor(v3_listed=False)
    cast.run(_args(tmp_path), transport)
    run_dir = _run_dir(tmp_path)
    first = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))["ranking"]
    assert cast.main(["--analyse", str(run_dir)]) == 0
    again = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))["ranking"]
    assert again == first


# ── measurements ─────────────────────────────────────────────────────────────


def test_a_gap_between_words_is_measured_and_a_joined_phrase_has_none() -> None:
    text = "bir iki üç dört beş"
    joined = _metrics(text, gap_s=0.0)
    broken = _metrics(text, gap_s=0.25)
    assert joined.aligned and len(joined.mid_gaps_ms) == 4
    assert max(joined.mid_gaps_ms) < 50
    assert min(broken.mid_gaps_ms) >= 200
    assert rep.aggregate([broken])["break_share"] == 1.0


def test_a_pitch_step_at_the_boundary_is_measured_in_semitones() -> None:
    text = "bir iki üç dört"
    flat = _metrics(text, hz=lambda word: 150.0)
    stepped = _metrics(text, hz=lambda word: 150.0 if word % 2 == 0 else 300.0)
    assert max(flat.mid_jumps_st) < 1.0
    assert min(stepped.mid_jumps_st) == pytest.approx(12.0, abs=1.0)


def test_punctuation_boundaries_are_kept_out_of_the_continuity_figures() -> None:
    m = _metrics("bir, iki üç. dört beş", gap_s=0.25)
    assert len(m.punct_gaps_ms) == 2 and len(m.mid_gaps_ms) == 2


def test_an_unaligned_take_still_reports_rate_but_no_boundary_figure() -> None:
    pcm, _ = _speak("bir iki üç")
    m = rep.clip_metrics(np.frombuffer(pcm, dtype="<i2"), RATE, "bir iki üç", None)
    assert not m.aligned and m.mid_gaps_ms == () and m.rate_sps is not None


def test_rank_puts_the_steadiest_first_and_missing_figures_last() -> None:
    combos = {
        "S01": {"gap_ms": 40.0, "jump_st": 1.0, "rate_cv": 0.2},
        "S02": {"gap_ms": 10.0, "jump_st": 0.5, "rate_cv": 0.1},
        "S03": {"gap_ms": None, "jump_st": None, "rate_cv": None},
    }
    assert [code for code, _ in rep.rank(combos)] == ["S02", "S01", "S03"]


def test_pages_escape_vendor_supplied_names() -> None:
    combos = {
        "S01": {
            "voice": {"name": "<b>x</b>", "voice_id": "id", "source": "library"},
            "model_id": "eleven_multilingual_v2",
            "metrics": {},
        }
    }
    page = rep.labelled_page([("S01", 1.0)], combos, [("welcome", "Hoş geldiniz.")], {})
    assert "<b>x</b>" not in page and "&lt;b&gt;x&lt;/b&gt;" in page
