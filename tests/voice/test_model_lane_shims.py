"""INT-428 — the routed gateways keep the existing adapter interfaces.

``LaneRoutedExtractionGateway`` is an ``ExtractionGateway``,
``LaneRoutedTranscriber`` a ``Transcriber`` and ``LaneRoutedTtsGateway`` a
``TtsGateway``; each routes through the model lanes and refuses with the
interface's own "unavailable" error and a routing code.

- **Invariant 22 runs first:** a numeral is refused before a lane is chosen —
  no TTS, hosted or self-hosted, is reached.
- **Invariant 14:** the hosted extraction call carries the instructions and the
  delimited transcript in separate roles, and asks for the dated snapshot.
- **The per-call model check** refuses an answer from another model.
- **Invariant 1:** the extraction output still goes through the unchanged
  parser — the gateway returns the completion's text, nothing else.
"""

from __future__ import annotations

from typing import Any

import pytest
from intake_platform.model_lanes import Lane, LaneSetting, ModelLanesControl
from intake_voice_runtime.adapters.lanes import LaneRoutedTranscriber
from intake_voice_runtime.adapters.speech import SpeechUnavailable
from intake_voice_runtime.extraction.boundary import wrap_patient_data
from intake_voice_runtime.extraction.errors import ExtractionUnavailable
from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall
from intake_voice_runtime.extraction.lanes import LaneRoutedExtractionGateway
from model_lanes_kit import build_lanes
from voice_clips.delivery import DEFAULT_DELIVERY_CONTEXT, delivery_profile
from voice_clips.gateway import NumeralInScriptError, TtsUnavailableError
from voice_clips.lanes import LaneRoutedTtsGateway


def _hosted(lane: Lane) -> ModelLanesControl:
    settings = {name: LaneSetting() for name in Lane}
    settings[lane] = LaneSetting(route="hosted:openai")
    return ModelLanesControl(lanes=settings)


@pytest.fixture()
def extraction_call() -> ExtractionCall:
    return ExtractionCall(
        instructions="Extract the declared slots.",
        data=wrap_patient_data("sentetik hasta: başım ağrıyor"),
        json_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )


class RecordingSelfHosted:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, call: ExtractionCall) -> Completion:
        self.calls += 1
        return Completion(text='{"slots": []}', input_tokens=1, output_tokens=1)


class TestTheExtractionGateway:
    def _gateway(self, lanes: Any, self_hosted: Any = None) -> LaneRoutedExtractionGateway:
        return LaneRoutedExtractionGateway(
            lanes.router,
            tenant_id=None,
            self_hosted=self_hosted,
            hosted={lanes.backend.provider: lanes.backend},
        )

    def test_hosted_extraction_asks_for_the_snapshot_on_non_personal_egress(
        self, extraction_call: ExtractionCall
    ) -> None:
        lanes = build_lanes(control=_hosted(Lane.LLM), served=False)
        completion = self._gateway(lanes).complete(extraction_call)
        assert completion.text == '{"slots": []}'
        kind, model, data_class = lanes.backend.calls[0]
        assert (kind, model, data_class.value) == ("chat", "gpt-4o-mini-2024-07-18", "non_personal")

    def test_an_answer_from_another_model_is_refused(self, extraction_call: ExtractionCall) -> None:
        lanes = build_lanes(control=_hosted(Lane.LLM), served=False)
        lanes.backend.served = "gpt-4o-2024-08-06"
        with pytest.raises(ExtractionUnavailable, match="model_identity_mismatch"):
            self._gateway(lanes).complete(extraction_call)

    def test_near_miss_the_self_hosted_lane_uses_the_configured_gateway(
        self, extraction_call: ExtractionCall
    ) -> None:
        lanes = build_lanes()
        self_hosted = RecordingSelfHosted()
        assert self._gateway(lanes, self_hosted).complete(extraction_call).text == '{"slots": []}'
        assert self_hosted.calls == 1 and lanes.backend.calls == []

    def test_a_refused_lane_is_the_interfaces_own_error(
        self, extraction_call: ExtractionCall
    ) -> None:
        lanes = build_lanes(served=False)
        with pytest.raises(ExtractionUnavailable, match="self_hosted_unhealthy"):
            self._gateway(lanes, RecordingSelfHosted()).complete(extraction_call)


class TestTheTranscriber:
    def test_hosted_transcription_names_provider_and_snapshot(self) -> None:
        lanes = build_lanes(control=_hosted(Lane.ASR), served=False)
        transcriber = LaneRoutedTranscriber(
            lanes.router,
            tenant_id=None,
            audio_format="wav",
            self_hosted=None,
            hosted={lanes.backend.provider: lanes.backend},
        )
        result = transcriber.transcribe(b"\x00\x00" * 16)
        assert result.model == "openai/gpt-4o-mini-transcribe-2025-12-15"
        assert transcriber.pin is None  # a hosted provider names no §4.9.1 row

    def test_a_refused_lane_is_speech_unavailable(self) -> None:
        lanes = build_lanes(served=False)
        transcriber = LaneRoutedTranscriber(
            lanes.router, tenant_id=None, audio_format="wav", self_hosted=None, hosted={}
        )
        with pytest.raises(SpeechUnavailable, match="self_hosted_unhealthy"):
            transcriber.transcribe(b"\x00\x00")


class TestTheTtsGateway:
    def _gateway(self, lanes: Any) -> LaneRoutedTtsGateway:
        return LaneRoutedTtsGateway(
            lanes.router,
            tenant_id=None,
            self_hosted=None,
            hosted={lanes.backend.provider: lanes.backend},
        )

    def test_a_numeral_is_refused_before_any_lane_is_chosen(self) -> None:
        lanes = build_lanes(control=_hosted(Lane.TTS), served=False)
        with pytest.raises(NumeralInScriptError):
            self._gateway(lanes).synthesise(
                text_tr="Günde 2 tablet",
                voice_id="voice",
                profile=delivery_profile(DEFAULT_DELIVERY_CONTEXT),
            )
        assert lanes.backend.calls == []

    def test_near_miss_expanded_turkish_reaches_the_hosted_snapshot(self) -> None:
        lanes = build_lanes(control=_hosted(Lane.TTS), served=False)
        speech = self._gateway(lanes).synthesise(
            text_tr="Günde iki tablet",
            voice_id="voice",
            profile=delivery_profile(DEFAULT_DELIVERY_CONTEXT),
        )
        assert speech.sample_rate_hz == 24000
        assert lanes.backend.calls[0][:2] == ("tts", "gpt-4o-mini-tts-2025-12-15")

    def test_a_refused_lane_is_tts_unavailable(self) -> None:
        lanes = build_lanes(served=False)
        with pytest.raises(TtsUnavailableError, match="self_hosted_unhealthy"):
            self._gateway(lanes).synthesise(
                text_tr="Merhaba",
                voice_id="voice",
                profile=delivery_profile(DEFAULT_DELIVERY_CONTEXT),
            )


class RecordingTts:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def synthesise(self, *, text_tr: str, voice_id: str, profile: Any) -> Any:
        from voice_clips.audio import SynthesisedSpeech

        self.texts.append(text_tr)
        return SynthesisedSpeech(pcm_s16le=b"\x00\x00" * 4, sample_rate_hz=16000, channels=1)


class TestTheSelfHostedTtsLane:
    def test_the_self_hosted_lane_uses_the_configured_gateway(self) -> None:
        lanes = build_lanes()
        self_hosted = RecordingTts()
        gateway = LaneRoutedTtsGateway(
            lanes.router, tenant_id=None, self_hosted=self_hosted, hosted={}
        )
        speech = gateway.synthesise(
            text_tr="Merhaba", voice_id="voice", profile=delivery_profile(DEFAULT_DELIVERY_CONTEXT)
        )
        assert speech.sample_rate_hz == 16000 and self_hosted.texts == ["Merhaba"]

    def test_no_self_hosted_gateway_is_unavailable_not_a_crash(self) -> None:
        lanes = build_lanes()
        gateway = LaneRoutedTtsGateway(lanes.router, tenant_id=None, self_hosted=None, hosted={})
        with pytest.raises(TtsUnavailableError, match="self_hosted_failed"):
            gateway.synthesise(
                text_tr="Merhaba",
                voice_id="voice",
                profile=delivery_profile(DEFAULT_DELIVERY_CONTEXT),
            )
