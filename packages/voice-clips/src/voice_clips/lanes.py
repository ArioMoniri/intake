"""``TtsGateway`` over the model lanes (INT-428, ADR-035).

:class:`LaneRoutedTtsGateway` is a :class:`~voice_clips.gateway.TtsGateway`:
one scripted Turkish string in, one :class:`~voice_clips.audio.SynthesisedSpeech`
out, routed by :func:`intake_platform.model_lanes.dispatch` — once per session
when a :class:`~intake_platform.model_lanes.SessionLanes` is given.

**Invariant 22 runs first, on every lane.** :func:`assert_speakable_tr` refuses
any numeral before a route is even decided, so no TTS — self-hosted or hosted
— ever receives a digit; the compiler's Turkish expansion is the only
normaliser, and the provider is never asked to read a number.

- ``self_hosted`` — the configured :class:`HttpTtsGateway` (or the recorded
  one in CI);
- ``hosted:<provider>`` — a :class:`~intake_platform.model_lanes.HostedBackend`
  (synthetic image only): raw 16-bit mono PCM in the catalogue's voice, from
  the resolved dated snapshot. The caller's ``voice_id`` names a voice in
  *our* clip catalogue, not one the provider knows, so it is not forwarded.
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

from voice_clips.audio import SynthesisedSpeech
from voice_clips.delivery import DeliveryProfile
from voice_clips.gateway import (
    RecordedSpeechMissingError,
    TtsGateway,
    TtsUnavailableError,
    assert_speakable_tr,
)

__all__ = ["LaneRoutedTtsGateway"]


class LaneRoutedTtsGateway:
    """One ``synthesise`` per call, routed through the model lanes."""

    def __init__(
        self,
        router: LaneRouter,
        *,
        tenant_id: str | None,
        self_hosted: TtsGateway | None,
        hosted: Mapping[ProviderId, HostedBackend],
        session: SessionLanes | None = None,
        role: str = Lane.TTS.value,
    ) -> None:
        self._router = router
        self._tenant_id = tenant_id
        self._self_hosted = self_hosted
        self._hosted = hosted
        self._session = session
        self._role = role

    def _run(
        self,
        text_tr: str,
        voice_id: str,
        profile: DeliveryProfile,
        assignment: ModelAssignment,
    ) -> LaneResult[SynthesisedSpeech]:
        route = assignment.route
        if route is not None and route.kind is RouteKind.SELF_HOSTED:
            if self._self_hosted is None:
                raise TtsUnavailableError("no self-hosted TTS endpoint is configured")
            speech = self._self_hosted.synthesise(
                text_tr=text_tr, voice_id=voice_id, profile=profile
            )
            return LaneResult(speech, HostedUsage(characters=len(text_tr)))
        provider = self._hosted.get(route.provider) if route and route.provider else None
        data_class = assignment.egress_data_class
        if provider is None or data_class is None or assignment.model is None:
            raise HostedLaneUnavailable("hosted_lane_unconfigured")
        hosted = provider.speech(text_tr, data_class=data_class, model=assignment.model.wire)
        speech = SynthesisedSpeech(
            pcm_s16le=hosted.pcm_s16le,
            sample_rate_hz=hosted.sample_rate_hz,
            channels=hosted.channels,
        )
        return LaneResult(speech, hosted.usage)

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
        assert_speakable_tr(text_tr)  # invariant 22, before any lane is chosen
        try:
            return dispatch(
                self._router,
                self._role,
                tenant_id=self._tenant_id,
                call=lambda assignment: self._run(text_tr, voice_id, profile, assignment),
                failures=(TtsUnavailableError, RecordedSpeechMissingError),
                session=self._session,
            )
        except LaneRefused as refused:
            raise TtsUnavailableError(f"the tts lane refused the call: {refused.code}") from None
