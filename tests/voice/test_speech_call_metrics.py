"""INT-182 — ASR and TTS calls are counted, so the Voice module has an error rate.

The Voice module's per-profile tiles (files/08 §3 "Voice runtime") ask for an
ASR/TTS error figure, and until this issue nothing counted a speech call at
all: INT-100 counted breaker *transitions* and lane *failovers*, which say a
lane gave up, not how often it failed. ``voice_speech_calls_total`` counts
every call that reached a wire, by registry component, kind and outcome.

Two places dial a speech model and each counts where the component is known:

- **TTS** — the INT-100 failover ladder, which holds the registry order and
  therefore the component name of every lane it tries. A lane skipped behind
  an open breaker, or one the budget left no time for, dialled nothing and is
  not a call (a skip is already ``vendor_failovers_total``).
- **ASR** — :class:`HttpTranscriber`, whose §4.9.1 row names its component
  (``COMPONENT_OF``); a dev lane with no row is ``unregistered``.

Labels are a registry component, a closed kind and a closed outcome — never a
session id and never the text or audio (invariant 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pytest
from intake_voice_runtime.adapters.asr import HttpTranscriber
from intake_voice_runtime.adapters.pins import COMPONENT_OF, ModelStackRow
from intake_voice_runtime.adapters.speech import SpeechUnavailable
from intake_voice_runtime.resilience import (
    BreakerBoard,
    BreakerPolicy,
    FailoverSynthesizer,
    LaneRow,
    SpeechLanesExhausted,
    build_failover_order,
)
from prometheus_client import REGISTRY
from talker_harness import FakeClock

ENDPOINT = "http://127.0.0.1:8802"


def _calls(component: str, kind: str, outcome: str) -> float:
    labels = {"component": component, "kind": kind, "outcome": outcome}
    return REGISTRY.get_sample_value("voice_speech_calls_total", labels) or 0.0


@dataclass
class Lane:
    clock: FakeClock
    fail: bool = False
    calls: list[str] = field(default_factory=list)

    def synthesize(self, text_tr: str, voice_id: str, *, timeout_s: float | None = None) -> bytes:
        self.calls.append(text_tr)
        if self.fail:
            raise SpeechUnavailable("the TTS endpoint did not answer (ConnectError)")
        return b"frames"


def _row(component: str, fallback: str = "none") -> LaneRow:
    return LaneRow(
        component=component,
        self_hostable=True,
        self_hosted_now=True,
        phi_path=True,
        fallback=fallback,
    )


def _ladder(
    clock: FakeClock, primary: Lane, secondary: Lane, *, board: BreakerBoard
) -> FailoverSynthesizer:
    order = build_failover_order(
        "int182-tts-a",
        {
            "int182-tts-a": _row("int182-tts-a", "component:int182-tts-b"),
            "int182-tts-b": _row("int182-tts-b"),
        },
        phi_path=True,
    )
    return FailoverSynthesizer(
        order,
        {"int182-tts-a": primary, "int182-tts-b": secondary},
        board=board,
        clock=clock,
    )


class TestTtsCalls:
    def test_a_served_call_counts_ok_for_its_component(self) -> None:
        clock = FakeClock()
        before = _calls("int182-tts-a", "tts", "ok")
        ladder = _ladder(clock, Lane(clock), Lane(clock), board=BreakerBoard(clock=clock))
        ladder.synthesize("Sentetik soru.", "voice-a")
        assert _calls("int182-tts-a", "tts", "ok") == before + 1

    def test_a_failed_call_counts_failed_and_the_next_lane_counts_ok(self) -> None:
        clock = FakeClock()
        a_failed = _calls("int182-tts-a", "tts", "failed")
        b_ok = _calls("int182-tts-b", "tts", "ok")
        ladder = _ladder(
            clock, Lane(clock, fail=True), Lane(clock), board=BreakerBoard(clock=clock)
        )
        ladder.synthesize("Sentetik soru.", "voice-a")
        assert _calls("int182-tts-a", "tts", "failed") == a_failed + 1
        assert _calls("int182-tts-b", "tts", "ok") == b_ok + 1

    def test_a_lane_skipped_behind_an_open_breaker_dialled_nothing_and_is_not_a_call(
        self,
    ) -> None:
        clock = FakeClock()
        board = BreakerBoard(clock=clock, policy=BreakerPolicy(failure_threshold=1))
        board.breaker("int182-tts-a").record_failure()  # opened by an earlier session
        primary = Lane(clock)
        before = {outcome: _calls("int182-tts-a", "tts", outcome) for outcome in ("ok", "failed")}
        _ladder(clock, primary, Lane(clock), board=board).synthesize("Sentetik soru.", "voice-a")
        assert primary.calls == []
        assert {
            outcome: _calls("int182-tts-a", "tts", outcome) for outcome in ("ok", "failed")
        } == before

    def test_exhaustion_counts_every_failed_dial(self) -> None:
        clock = FakeClock()
        before_a = _calls("int182-tts-a", "tts", "failed")
        before_b = _calls("int182-tts-b", "tts", "failed")
        ladder = _ladder(
            clock,
            Lane(clock, fail=True),
            Lane(clock, fail=True),
            board=BreakerBoard(clock=clock),
        )
        with pytest.raises(SpeechLanesExhausted):
            ladder.synthesize("Sentetik soru.", "voice-a")
        assert _calls("int182-tts-a", "tts", "failed") == before_a + 1
        assert _calls("int182-tts-b", "tts", "failed") == before_b + 1


class TestAsrCalls:
    def _transcriber(self, handler: httpx.MockTransport) -> HttpTranscriber:
        return HttpTranscriber(ENDPOINT, row=ModelStackRow.ASR_SHADOW, transport=handler)

    def test_an_answered_transcription_counts_ok_for_its_row_component(self) -> None:
        component = COMPONENT_OF[ModelStackRow.ASR_SHADOW]
        assert component is not None
        before = _calls(component, "asr", "ok")
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"text": "sentetik", "model": "m"})
        )
        self._transcriber(transport).transcribe(b"\x00\x01")
        assert _calls(component, "asr", "ok") == before + 1

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(503, json={}),
            httpx.Response(200, json={"no_text": True}),
        ],
    )
    def test_a_failed_transcription_counts_failed(self, response: httpx.Response) -> None:
        component = COMPONENT_OF[ModelStackRow.ASR_SHADOW]
        assert component is not None
        before = _calls(component, "asr", "failed")
        transport = httpx.MockTransport(lambda request: response)
        with pytest.raises(SpeechUnavailable):
            self._transcriber(transport).transcribe(b"\x00\x01")
        assert _calls(component, "asr", "failed") == before + 1

    def test_an_unreachable_endpoint_counts_failed(self) -> None:
        component = COMPONENT_OF[ModelStackRow.ASR_SHADOW]
        assert component is not None
        before = _calls(component, "asr", "failed")

        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        with pytest.raises(SpeechUnavailable):
            self._transcriber(httpx.MockTransport(refuse)).transcribe(b"\x00\x01")
        assert _calls(component, "asr", "failed") == before + 1

    def test_a_dev_lane_with_no_row_is_counted_as_unregistered(self) -> None:
        before = _calls("unregistered", "asr", "ok")
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"text": "sentetik"})
        )
        HttpTranscriber(ENDPOINT, transport=transport).transcribe(b"\x00")
        assert _calls("unregistered", "asr", "ok") == before + 1
