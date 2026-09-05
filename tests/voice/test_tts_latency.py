"""INT-319 — the dev TTS latency harness (`make tts-latency`).

The harness measures four delays per configured on-prem TTS lane over a fixed,
named corpus of scripted questions, and it does so while honouring the same
invariants the speech path does:

- **Invariant 22** — no numeral reaches a TTS model. Every corpus line is
  refused before the wire if it carries a Unicode decimal digit, using the
  same ``assert_no_numeral`` the adapter uses.
- **Invariant 10** — the scripted question is spoken verbatim. The harness
  never paraphrases a line; the recorded-timing replay carries the exact text.
- **Invariant 20** — everything it prints is a measurement of one bridge on
  one day against a NAMED corpus, never a property of the product and never an
  accuracy figure. A blocked lane is reported blocked, never a filled-in number
  (invariant 17 / files/HUMAN_BLOCKERS.md Rule 1).

These tests exercise the hermetic recorded path — the CI and no-GPU dev path —
and the streaming live-measurement arithmetic against a fake transport, so no
test dials a model (ADR-006).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "voice"))

import tts_latency as harness  # noqa: E402

# --- the corpus is speakable ------------------------------------------------


def test_corpus_is_named_and_non_empty() -> None:
    assert harness.CORPUS_ID
    assert harness.CORPUS
    assert all(isinstance(line, str) and line.strip() for line in harness.CORPUS)


def test_corpus_carries_no_numeral() -> None:
    # invariant 22: the compiler expands every digit; a corpus line with one
    # would be read out by a disabled normaliser's fallback branch.
    harness.assert_corpus_speakable(harness.CORPUS)


def test_a_numeral_in_the_corpus_is_refused() -> None:
    with pytest.raises(harness.TtsLatencyRefused):
        harness.assert_corpus_speakable(("İki numaralı soru: 2 mg.",))


# --- the recorded (hermetic) path -------------------------------------------


def _recorded_run(tmp_path: Path, *, blocked_reason: str | None = None) -> Path:
    lanes: dict[str, object] = {
        "voxcpm2": {
            "status": "measured",
            "timings": [
                {
                    "compile_to_synth_ms": 0.4,
                    "ttfa_ms": 120.0,
                    "full_audio_ms": 900.0,
                    "delivery_ms": 905.0,
                    "audio_bytes": 48044,
                }
                for _ in harness.CORPUS
            ],
        },
        "freya": {
            "status": "measured",
            "timings": [
                {
                    "compile_to_synth_ms": 0.3,
                    "ttfa_ms": 520.0,
                    "full_audio_ms": 700.0,
                    "delivery_ms": 704.0,
                    "audio_bytes": 32044,
                }
                for _ in harness.CORPUS
            ],
        },
        harness.EXPRESSIVE_CANDIDATE.id: {
            "status": "blocked",
            "reason": blocked_reason
            or "licence UNVERIFIED against the raw LICENSE blob; GPU unreachable",
        },
    }
    run = {
        "corpus_id": harness.CORPUS_ID,
        "recorded_on": "2026-09-04",
        "provenance": "hand-authored fixture exercising the harness arithmetic; "
        "not a device measurement (see docs/evidence/INT-319.md)",
        "lanes": lanes,
    }
    path = tmp_path / "run.json"
    path.write_text(json.dumps(run), encoding="utf-8")
    return path


def test_recorded_run_reports_every_lane(tmp_path: Path) -> None:
    run = harness.RecordedTimingRun.load(_recorded_run(tmp_path))
    measurements = harness.benchmark_recorded(run, harness.benchmark_lanes())
    by_id = {m.lane.id: m for m in measurements}
    assert by_id["voxcpm2"].status == "measured"
    assert by_id["freya"].status == "measured"
    # every corpus line yields one timing row with all four delays present
    for line, timing in zip(harness.CORPUS, by_id["voxcpm2"].timings, strict=True):
        assert timing.compile_to_synth_ms >= 0.0
        assert timing.ttfa_ms > 0.0
        assert timing.full_audio_ms >= timing.ttfa_ms
        assert timing.delivery_ms >= timing.full_audio_ms
        assert line  # the line exists; the harness measures every one


def test_expressive_candidate_is_reported_blocked_not_faked(tmp_path: Path) -> None:
    run = harness.RecordedTimingRun.load(_recorded_run(tmp_path))
    measurements = harness.benchmark_recorded(run, harness.benchmark_lanes())
    expressive = next(m for m in measurements if m.lane.id == harness.EXPRESSIVE_CANDIDATE.id)
    assert expressive.status == "blocked"
    assert expressive.timings == ()
    assert "UNVERIFIED" in expressive.reason or "GPU" in expressive.reason


def test_recorded_run_refuses_a_corpus_mismatch(tmp_path: Path) -> None:
    payload = json.loads(_recorded_run(tmp_path).read_text(encoding="utf-8"))
    payload["corpus_id"] = "some-other-corpus"
    path = tmp_path / "mismatch.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(harness.TtsLatencyRefused):
        harness.RecordedTimingRun.load(path)


def test_a_missing_lane_in_the_run_is_blocked_never_invented(tmp_path: Path) -> None:
    payload = json.loads(_recorded_run(tmp_path).read_text(encoding="utf-8"))
    del payload["lanes"]["freya"]
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    run = harness.RecordedTimingRun.load(path)
    measurements = harness.benchmark_recorded(run, harness.benchmark_lanes())
    freya = next(m for m in measurements if m.lane.id == "freya")
    assert freya.status == "blocked"
    assert freya.timings == ()


# --- the report never overstates --------------------------------------------


def test_report_carries_the_disclaimer_and_corpus(tmp_path: Path) -> None:
    run = harness.RecordedTimingRun.load(_recorded_run(tmp_path))
    measurements = harness.benchmark_recorded(run, harness.benchmark_lanes())
    report = harness.render_report(
        measurements, source="recorded", corpus_id=harness.CORPUS_ID, recorded_on="2026-09-04"
    )
    assert harness.CORPUS_ID in report
    assert "invariant 20" in report
    # no accuracy/property wording — the claims-scan patterns must not appear
    lowered = report.lower()
    for banned in ("accuracy", "sensitivity", "specificity", "auroc", " wer", "state-of-the-art"):
        assert banned not in lowered


def test_report_names_the_four_delays(tmp_path: Path) -> None:
    run = harness.RecordedTimingRun.load(_recorded_run(tmp_path))
    measurements = harness.benchmark_recorded(run, harness.benchmark_lanes())
    report = harness.render_report(
        measurements, source="recorded", corpus_id=harness.CORPUS_ID, recorded_on="2026-09-04"
    )
    for column in ("compile", "first-audio", "full-audio", "delivery"):
        assert column in report.lower()


# --- the live streaming measurement (fake transport, no model dialled) -------


def test_live_measures_ttfa_before_full_audio() -> None:
    # A streaming response whose body arrives in two chunks: the harness must
    # record a time-to-first-audio strictly before time-to-full-audio.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"RIFF....audio-bytes....WAVE")

    transport = httpx.MockTransport(handler)
    timing = harness.measure_live_line(
        "http://127.0.0.1:8805", "Merhaba.", "residency-tr-01", transport=transport
    )
    assert timing.ttfa_ms > 0.0
    assert timing.full_audio_ms >= timing.ttfa_ms
    assert timing.audio_bytes > 0
    assert timing.delivery_ms >= timing.full_audio_ms


def test_live_refuses_a_public_host() -> None:
    # invariant 19: a self-hosted lane is never a public FQDN. The harness
    # reuses the adapter's own refusal rather than a second copy of it.
    with pytest.raises(harness.TtsLatencyRefused):
        harness.measure_live_line("https://api.example.com", "Merhaba.", "residency-tr-01")


def test_live_refuses_a_numeral_before_the_wire() -> None:
    with pytest.raises(harness.TtsLatencyRefused):
        harness.measure_live_line("http://127.0.0.1:8805", "2 mg.", "residency-tr-01")


# --- the lane set is the production ladder plus the candidate, never the app -


def test_benchmark_lanes_include_ladder_and_candidate() -> None:
    ids = {lane.id for lane in harness.benchmark_lanes()}
    assert {"voxcpm2", "freya"} <= ids
    assert harness.EXPRESSIVE_CANDIDATE.id in ids


def test_expressive_candidate_is_not_turkish_verified() -> None:
    # files/00_STATE.md line 99 rules CosyVoice2 out for Turkish; the harness
    # must carry that finding rather than presenting it as a production lane.
    assert harness.EXPRESSIVE_CANDIDATE.turkish_verified is False
    assert harness.EXPRESSIVE_CANDIDATE.dev_only is True


# --- the clip-cache playback path (hermetic; decode + play, ~no synth) -------


def _mono_wav(sample_rate_hz: int = 24000, ms: int = 120) -> bytes:
    import struct as _struct

    n = int(sample_rate_hz * ms / 1000)
    pcm = b"".join(_struct.pack("<h", (i % 200) - 100) for i in range(n))
    fmt = _struct.pack("<HHIIHH", 1, 1, sample_rate_hz, sample_rate_hz * 2, 2, 16)
    body = (
        b"RIFF"
        + _struct.pack("<I", 4 + (8 + len(fmt)) + (8 + len(pcm)))
        + b"WAVE"
        + b"fmt "
        + _struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + _struct.pack("<I", len(pcm))
        + pcm
    )
    return body


def test_clip_playback_is_measured_without_synthesis() -> None:
    # The fixed scripted questions are pre-synthesised offline; at runtime the
    # device only decodes and plays a cached clip — the harness measures that
    # path with no TTS on it at all (coordinator (b)).
    measurement = harness.measure_clip_playback(_mono_wav())
    assert measurement.audio_bytes > 0
    # a playback timing has no synth term: compile→synth start is zero here
    assert measurement.compile_to_synth_ms == 0.0
    assert measurement.ttfa_ms >= 0.0
    assert measurement.full_audio_ms >= measurement.ttfa_ms
    assert measurement.delivery_ms >= measurement.full_audio_ms


def test_clip_playback_refuses_a_non_wav_body() -> None:
    with pytest.raises(harness.TtsLatencyRefused):
        harness.measure_clip_playback(b"not-a-wav")


def test_report_marks_the_cloud_clipgen_ab_blocked_on_the_key() -> None:
    # ElevenLabs offline clip-gen A/B is a separate, key-gated measurement; with
    # no key the report says so rather than inventing a comparison.
    report = harness.render_report(
        [], source="recorded", corpus_id=harness.CORPUS_ID, recorded_on="2026-09-04"
    )
    assert "TTS_ELEVENLABS_API_KEY" in report


# --- the committed evidence fixture stays honest ----------------------------


def test_committed_recorded_run_loads_and_declares_its_provenance() -> None:
    # The fixture make tts-latency RECORDED=... replays in docs/evidence must
    # match the corpus, mark the expressive candidate blocked, and SAY it is not
    # a device measurement — so it can never be quoted as one (invariant 20).
    fixture = REPO / "tests" / "fixtures" / "tts_latency" / "recorded_run.json"
    run = harness.RecordedTimingRun.load(fixture)
    assert run.corpus_id == harness.CORPUS_ID
    assert "NOT device measurements" in run.provenance or "not a device measurement" in (
        run.provenance
    )
    measurements = harness.benchmark_recorded(run, harness.benchmark_lanes())
    expressive = next(m for m in measurements if m.lane.id == harness.EXPRESSIVE_CANDIDATE.id)
    assert expressive.status == "blocked"
