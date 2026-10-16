"""INT-497 — `make voice-experience`: the harness that measures the seams.

The harness reads a rendered clip set (the gitignored E04 render in practice)
and reports per-clip edges and loudness, the lead-in → question joins before
and after, and level traces for the endpointer replay. These tests build a
synthetic clip set of tones in a temporary directory — no vendor, no voice,
nothing committed — and pin what each report says, so the numbers in
docs/evidence/INT-497.md come from code that is itself under test.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from voice_clips.audio import Pcm, SynthesisedSpeech, wav_bytes

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "voice"))

import voice_experience as harness  # noqa: E402

RATE = 24_000


def tone(
    seconds: float, amplitude: float, lead_ms: int = 20, trail_ms: int = 40
) -> NDArray[np.int16]:
    t = np.arange(round(RATE * seconds)) / RATE
    body = amplitude * 32767 * np.sin(2 * np.pi * 220 * t)
    # a dip in the middle, so a short answer can be cut at a syllable boundary
    body[len(body) // 3 : len(body) // 3 + RATE // 50] *= 0.01
    return np.concatenate(
        [
            np.zeros(RATE * lead_ms // 1000),
            body,
            np.zeros(RATE * trail_ms // 1000),
        ]
    ).astype(np.int16)


def clip_set(root: Path, rows: list[tuple[str, NDArray[np.int16]]]) -> Path:
    clips = []
    for at, (context, samples) in enumerate(rows):
        address = f"{context}/{hashlib.sha256(f'{context}{at}'.encode()).hexdigest()}"
        target = root / f"{address}.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            wav_bytes(
                SynthesisedSpeech(
                    pcm_s16le=samples.astype("<i2").tobytes(), sample_rate_hz=RATE, channels=1
                )
            )
        )
        clips.append({"address": address, "context": context})
    (root / "index.json").write_text(json.dumps({"clips": clips}), encoding="utf-8")
    return root


@pytest.fixture
def clips(tmp_path: Path) -> Path:
    return clip_set(
        tmp_path / "set",
        [
            ("acknowledgement", tone(1.0, 0.05)),
            ("acknowledgement", tone(1.2, 0.08)),
            ("routine", tone(2.0, 0.6)),
            ("routine", tone(2.4, 0.4)),
            ("routine", tone(1.8, 0.5)),
        ],
    )


class TestJoins:
    def test_it_reports_every_clip_and_every_lead_in_to_question_pair(self, clips: Path) -> None:
        report = harness.joins(clips, None)
        assert report["clips"] == 5
        joins = report["joins"]
        assert isinstance(joins, dict)
        assert joins["pairs"] == 2 * 3

    def test_quiet_acknowledgements_and_loud_questions_step_before_and_not_after(
        self, clips: Path
    ) -> None:
        report = harness.joins(clips, None)
        spread = report["loudness_spread_lu"]
        assert isinstance(spread, dict)
        assert spread["before"] > 10.0
        assert spread["after"] < 0.6
        joins = report["joins"]
        assert isinstance(joins, dict)
        assert joins["before"]["loudness_step_lu"]["p50"] > 10.0
        assert joins["after"]["loudness_step_lu"]["max"] < 0.6

    def test_the_designed_pause_is_the_devices_own_sentence_boundary(self, clips: Path) -> None:
        source = harness.SHAPING_TS
        expected = sum(
            harness.ts_constant(source, name)
            for name in ("KEEP_TAIL_MS", "SENTENCE_GAP_MS", "KEEP_HEAD_MS")
        )
        joins = harness.joins(clips, None)["joins"]
        assert isinstance(joins, dict)
        assert joins["after"]["designed_pause_ms"] == expected

    def test_the_player_switch_is_said_to_be_unmeasured_unless_a_measurement_is_given(
        self, clips: Path, tmp_path: Path
    ) -> None:
        joins = harness.joins(clips, None)["joins"]
        assert isinstance(joins, dict)
        assert "not measured" in str(joins["before"]["player_switch"])
        measured = tmp_path / "playback.json"
        measured.write_text(
            json.dumps({"chain_ms": {"p50": 120.0}, "queue_ms": {"p50": 0.0}}), encoding="utf-8"
        )
        joins = harness.joins(clips, measured)["joins"]
        assert isinstance(joins, dict)
        assert joins["before"]["player_switch"] == {"p50": 120.0}
        assert joins["after"]["player_switch"] == {"p50": 0.0}


class TestTraces:
    def test_every_trace_records_where_speech_really_ended(self, clips: Path) -> None:
        payload = harness.traces(clips, 50.0, 10)
        traces = payload["traces"]
        assert isinstance(traces, list)
        assert traces
        for trace in traces:
            assert trace["speech_end_ms"] > harness.PREROLL_MS
            assert len(trace["levels"]) * 50.0 > trace["speech_end_ms"]

    def test_it_renders_each_kind_over_both_rooms_with_its_question_shape(
        self, clips: Path
    ) -> None:
        traces = harness.traces(clips, 50.0, 10)["traces"]
        assert isinstance(traces, list)
        kinds = {trace["kind"] for trace in traces}
        assert {"short", "long", "narrative"} <= kinds
        assert {trace["room"] for trace in traces} == set(harness.ROOMS_DBFS)
        shapes = {trace["kind"]: trace["shape"] for trace in traces}
        assert shapes["narrative"] == "narrative"
        assert shapes["short"] == "short"

    def test_a_short_answer_is_cut_inside_its_window(self) -> None:
        pcm = Pcm(samples=tone(2.0, 0.5), sample_rate_hz=RATE)
        words = harness.first_words(pcm)
        assert words is not None
        low, high = harness.SHORT_ANSWER_WINDOW_MS
        duration_ms = 1000 * words.samples.size / RATE
        assert low - 20 <= duration_ms <= high + 20

    def test_the_trace_holds_levels_never_samples(self, clips: Path) -> None:
        trace = harness.traces(clips, 50.0, 10)["traces"][0]  # type: ignore[index]
        assert all(-200.0 < level <= 0.0 for level in trace["levels"])


def test_a_directory_without_an_index_is_refused(tmp_path: Path) -> None:
    assert harness.main(["joins", "--clips", str(tmp_path)]) == 2
