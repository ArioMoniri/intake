"""``Transcriber`` over the model lanes (INT-428, ADR-035).

:class:`LaneRoutedTranscriber` is a
:class:`~intake_voice_runtime.adapters.asr.Transcriber`: audio in, one
:class:`~intake_voice_runtime.adapters.asr.Transcription` out, routed by
:func:`intake_platform.model_lanes.dispatch` — once per session when a
:class:`~intake_platform.model_lanes.SessionLanes` is given:

- ``self_hosted`` — the configured :class:`HttpTranscriber` (its public-host
  refusal and its PHI-path pin rule unchanged), or the recorded one in CI;
- ``hosted:<provider>`` — a :class:`~intake_platform.model_lanes.HostedBackend`
  (synthetic image only), Turkish, asked for the resolved dated snapshot. The
  model id the answer carries names the provider and the snapshot, so a
  transcript never passes for the self-hosted model's.

``pin`` is the self-hosted lane's: a hosted provider names no files/03 §4.9.1
row, and the router never builds a hosted assignment for a real PHI
deployment (ADR-035). Nothing here keeps the audio.
"""

from __future__ import annotations

from collections.abc import Mapping

from intake_platform.model_lanes import (
    HostedBackend,
    HostedLaneUnavailable,
    HostedUsage,
    Lane,
    LaneRefused,
    LaneResult,
    LaneRouter,
    ModelAssignment,
    ProviderId,
    RouteKind,
    SessionLanes,
    dispatch,
)

from intake_voice_runtime.adapters.asr import (
    RecordedTranscriptMissing,
    Transcriber,
    Transcription,
)
from intake_voice_runtime.adapters.pins import ModelPin
from intake_voice_runtime.adapters.speech import SpeechUnavailable

__all__ = ["LaneRoutedTranscriber"]


class LaneRoutedTranscriber:
    """One ``transcribe`` per call, routed through the model lanes.

    ``audio_format`` is the container's short name the hosted route needs to
    recognise the encoding (``wav``, ``m4a`` …). It has no default: the caller
    knows what its media plane hands over, and a guess is a garbled transcript.
    """

    pin: ModelPin | None

    def __init__(
        self,
        router: LaneRouter,
        *,
        tenant_id: str | None,
        audio_format: str,
        self_hosted: Transcriber | None,
        hosted: Mapping[ProviderId, HostedBackend],
        session: SessionLanes | None = None,
        role: str = Lane.ASR.value,
    ) -> None:
        self._router = router
        self._tenant_id = tenant_id
        self._audio_format = audio_format
        self._self_hosted = self_hosted
        self._hosted = hosted
        self._session = session
        self._role = role
        self.pin = self_hosted.pin if self_hosted is not None else None

    def _run(self, audio: bytes, assignment: ModelAssignment) -> LaneResult[Transcription]:
        route = assignment.route
        if route is not None and route.kind is RouteKind.SELF_HOSTED:
            if self._self_hosted is None:
                raise SpeechUnavailable("no self-hosted ASR endpoint is configured")
            return LaneResult(self._self_hosted.transcribe(audio))
        provider = self._hosted.get(route.provider) if route and route.provider else None
        data_class = assignment.egress_data_class
        if provider is None or data_class is None or assignment.model is None:
            raise HostedLaneUnavailable("hosted_lane_unconfigured")
        result = provider.transcribe(
            audio,
            audio_format=self._audio_format,
            data_class=data_class,
            model=assignment.model.wire,
        )
        transcription = Transcription(
            text=result.text, model=f"{provider.provider_id.value}/{result.model}"
        )
        return LaneResult(
            transcription,
            HostedUsage(
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                audio_seconds=result.usage.audio_seconds,
            ),
        )

    def transcribe(self, audio: bytes) -> Transcription:
        try:
            return dispatch(
                self._router,
                self._role,
                tenant_id=self._tenant_id,
                call=lambda assignment: self._run(audio, assignment),
                failures=(SpeechUnavailable, RecordedTranscriptMissing),
                session=self._session,
            )
        except LaneRefused as refused:
            raise SpeechUnavailable(f"the asr lane refused the call: {refused.code}") from None
