"""The hosted ElevenLabs TTS lane (INT-443, ADR-035) — synthetic image only.

What it speaks is narrower than what any other TTS seam accepts. It refuses
before the wire, in this order:

1. **Anything a TTS may not see.** :func:`voice_clips.gateway.assert_speakable_tr`
   refuses a numeral of any kind (invariant 22) and SSML or audio-tag markup
   (INT-424). It refuses; it never rewrites.
2. **Anything off the catalogue.** ``admits`` is the server's scripted
   catalogue (the compiled clip manifests and the app's committed
   ``scriptedCatalogue.tr.json``), so a patient word cannot reach the vendor
   through this adapter, whoever calls it.
3. **RED.** A ``red`` delivery profile is refused outright: the RED script is
   pre-positioned on the device and triggered over the data channel, never
   fetched (invariant 21).
4. **A profile tuned for another model.** The v4 delivery profiles are the
   owner's cast take E04 on ``eleven_v3`` (INT-449, D20); a profile naming
   another model is refused, because changing the model is an ADR (ADR-034),
   not a profile edit.
5. **A profile that is not the served row.** The profile must be exactly
   ``voice_clips.delivery.DELIVERY_PROFILES[context]``: its version, tags,
   settings and voice. The tags therefore come from the server's table and
   from nowhere else, and a v2-era or hand-built row never reaches the wire.
6. **A voice that is not the row's.** A malformed voice id never becomes a
   path segment, and a well-formed one that is not the cast voice is refused.

Every refusal reads ``text_tr``, before any tag exists. Only then is the wire
text composed by :func:`voice_clips.gateway.wire_text`: the row's closed-table
tags (``[warmly]``, ``[calm]``, ``[softly] [reassuring]``, ``[gently]``), then
the script verbatim (invariant 10); RED and instrument rows carry no tag.

The request is the ADR-028 clip-gen request, field for field the one the
bundled E04 clips were rendered with (``scripts/voice/render_cast_clips.py``):
the wire text, the pinned model, the vendor's own text normaliser off
(``apply_text_normalization: "off"``), the profile's ``voice_settings``, raw
16-bit PCM back. It goes through
:func:`intake_platform.egress.guarded_client` under ``hosted_model_inference``
on ``NON_PERSONAL`` data, so the allow-list decides it in process, and through
the synthetic host's forward proxy, which decides it again at the network.
The host is read off the allow-list row ``elevenlabs-api`` and never written
here, so the vendor endpoint is spelled in the allow-list alone. The key comes
from OpenBao (``secret/model-lanes/providers/elevenlabs``) through the
:class:`~intake_platform.model_lanes.keys.ProviderKeyVault`; it is revealed
into one header and never into a message, a log or an exception chain.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import httpx
from intake_platform.egress import (
    AllowlistEntry,
    DataClass,
    EgressAllowlist,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    TransferLog,
    guarded_client,
)
from intake_platform.model_lanes.keys import (
    KeyVaultUnavailable,
    ProviderApiKey,
    ProviderKeyNotSet,
)
from voice_clips.audio import SynthesisedSpeech
from voice_clips.delivery import DELIVERY_PROFILES, DeliveryProfile
from voice_clips.gateway import (
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_PCM_RATE_HZ,
    DeliveryProfileMismatchError,
    TtsRefusedError,
    TtsUnavailableError,
    assert_speakable_tr,
    wire_text,
)

__all__ = [
    "ELEVENLABS_EGRESS_ROW",
    "ElevenLabsHostedTts",
    "HostedTtsRefused",
    "HostedTtsUnavailable",
    "elevenlabs_row",
]

#: The allow-list row the vendor is reached through (the owner's protected row).
ELEVENLABS_EGRESS_ROW: Final = "elevenlabs-api"
#: The text-to-speech route; the voice id is a path segment.
TTS_PATH: Final = "/v1/text-to-speech/{voice_id}"
DEFAULT_TIMEOUT_S: Final = 30.0
#: A vendor voice id is an opaque alphanumeric token; nothing else may become
#: a path segment.
_VOICE_ID: Final = re.compile(r"^[A-Za-z0-9]{8,64}$")


class HostedTtsUnavailable(TtsUnavailableError):
    """The vendor did not serve this call: no key, egress refused, unreachable,
    or a non-2xx or malformed answer. A caller may fall back to another lane.
    ``code`` is machine-shaped and carries no input, no key and no vendor body
    (invariant 6)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HostedTtsRefused(TtsRefusedError):
    """Refused before the wire: off the catalogue, RED, a profile that is not
    the served row, or a voice id that is not the row's. No lane may speak it
    on this path, so no caller falls back.
    ``code`` as above."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def elevenlabs_row(allowlist: EgressAllowlist) -> AllowlistEntry | None:
    """The vendor's allow-list row, or ``None`` while the owner has not added it.

    A row that exists but is glob-shaped, PHI-enabled, on another port or
    serving another purpose is a mis-bound provider and stops the wiring
    (``ValueError``) rather than its first call.
    """
    row = next((e for e in allowlist.tiers.dev if e.name == ELEVENLABS_EGRESS_ROW), None)
    if row is None:
        return None
    if (
        row.glob
        or row.phi_allowed
        or row.port != 443
        or row.purpose_id is not EgressPurpose.HOSTED_MODEL_INFERENCE
    ):
        raise ValueError(
            f"allow-list row {ELEVENLABS_EGRESS_ROW} must be an exact host on 443, "
            "phi_allowed: false, serving hosted_model_inference"
        )
    return row


@dataclass(frozen=True)
class ElevenLabsHostedTts:
    """A :class:`voice_clips.gateway.TtsGateway` over the hosted vendor.

    ``admits`` is required and has no default: an adapter that could be built
    without the catalogue would be an adapter that speaks anything.
    ``inner`` is the transport seam a contract test fills with
    ``httpx.MockTransport``; CI never reaches the vendor.
    """

    host: str
    key: Callable[[], ProviderApiKey]
    policy: EgressPolicy
    admits: Callable[[str], bool]
    proxy: str | None = None
    model_id: str = ELEVENLABS_MODEL_ID
    sample_rate_hz: int = ELEVENLABS_PCM_RATE_HZ
    timeout_s: float = DEFAULT_TIMEOUT_S
    inner: httpx.BaseTransport | None = None
    transfer_log: TransferLog | None = None

    def _refuse_before_the_wire(
        self, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> None:
        assert_speakable_tr(text_tr)  # invariant 22 and INT-424, before anything else
        if not self.admits(text_tr):
            raise HostedTtsRefused("hosted_tts_not_in_catalogue")
        if profile.context == "red":
            raise HostedTtsRefused("red_not_on_demand")
        if profile.model_id != self.model_id:
            raise DeliveryProfileMismatchError(
                f"delivery profile {profile.key} is tuned for model {profile.model_id!r}, "
                f"and this lane pins {self.model_id!r}; changing the model needs an ADR"
            )
        if profile != DELIVERY_PROFILES[profile.context]:
            # the tags, settings, version and voice are the served table's only
            raise HostedTtsRefused("hosted_tts_profile_not_served")
        if not _VOICE_ID.fullmatch(voice_id) or voice_id != profile.voice_id:
            raise HostedTtsRefused("hosted_tts_voice_refused")

    def _api_key(self) -> str:
        try:
            return self.key().reveal()
        except ProviderKeyNotSet:
            raise HostedTtsUnavailable("hosted_key_not_set") from None
        except KeyVaultUnavailable as err:
            raise HostedTtsUnavailable(err.code) from None

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
        self._refuse_before_the_wire(text_tr, voice_id, profile)
        # every refusal above read text_tr; the row's tags join it only here
        text = wire_text(text_tr, profile)
        headers = {"xi-api-key": self._api_key()}
        context = EgressContext(
            purpose=EgressPurpose.HOSTED_MODEL_INFERENCE, data_class=DataClass.NON_PERSONAL
        )
        client = guarded_client(
            self.policy,
            context,
            inner=self.inner,
            transfer_log=self.transfer_log,
            proxy=self.proxy,
            timeout=self.timeout_s,
        )
        response: httpx.Response | None = None
        failure = "hosted_lane_unreachable"
        with client:
            try:
                response = client.post(
                    f"https://{self.host}{TTS_PATH.format(voice_id=voice_id)}",
                    params={"output_format": f"pcm_{self.sample_rate_hz}"},
                    headers=headers,
                    json={
                        # INT-449 (D20): the served row's tags, then the script
                        # verbatim (invariant 10); the same text the bundled
                        # E04 clips were rendered from
                        "text": text,
                        "model_id": self.model_id,
                        # invariant 22: the compiler's expansion is the only
                        # normaliser that ever runs
                        "apply_text_normalization": "off",
                        # INT-415/INT-424: how the words are delivered, never which
                        "voice_settings": profile.voice_settings.as_request(),
                    },
                )
            except EgressDenied:
                failure = "hosted_lane_egress_denied"
            except httpx.TimeoutException:
                failure = "hosted_lane_timeout"
            except httpx.HTTPError:
                failure = "hosted_lane_unreachable"
        # raised outside the except blocks, so nothing chains: an httpx error
        # holds the request, and the request holds the key
        if response is None:
            raise HostedTtsUnavailable(failure)
        if not 200 <= response.status_code < 300:
            code = (
                "hosted_lane_key_rejected"
                if response.status_code in (401, 403)
                else f"hosted_lane_http_{response.status_code}"
            )
            raise HostedTtsUnavailable(code)
        pcm = response.content
        if not pcm or len(pcm) % 2:
            raise HostedTtsUnavailable("hosted_lane_bad_response")
        return SynthesisedSpeech(pcm_s16le=pcm, sample_rate_hz=self.sample_rate_hz, channels=1)
