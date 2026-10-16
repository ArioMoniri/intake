"""The OpenAI-compatible hosted adapter (INT-428, ADR-035) — synthetic image only.

It speaks four routes and nothing else:

- ``POST /v1/chat/completions`` — instructions in the ``system`` role, the
  delimited data block in the ``user`` role (speech and documents are data,
  never instructions — invariant 14), ``temperature: 0`` and a strict JSON
  Schema ``response_format``, so decoding is constrained to the contract and
  the caller's parser refuses anything else anyway;
- ``POST /v1/audio/transcriptions`` — Turkish, JSON out;
- ``POST /v1/audio/speech`` — raw 16-bit PCM out, never a container;
- ``GET /v1/models/{snapshot}`` — the identity probe: the provider confirms
  it serves that exact dated snapshot.

Every call names a resolved dated snapshot (the adapter never picks one) and
goes through :func:`intake_platform.egress.guarded_client` under the
``hosted_model_inference`` purpose and the data class the ADR-035 guard
admitted, so the allow-list decides it a second time. A refusal, a truncation,
a content filter or an empty output is one outcome — ``hosted_lane_no_answer``.
Any other failure is a code and an HTTP status at most: the provider's error
body can echo the input, so it is never read into a message, a log or an
exception chain (invariant 6). Nothing here imports a vendor SDK.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Final

import httpx
from intake_platform.egress import (
    DataClass,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    TransferLog,
    guarded_client,
)
from intake_platform.model_lanes.hosted import (
    NO_ANSWER,
    HostedChat,
    HostedLaneUnavailable,
    HostedSpeech,
    HostedTranscript,
    HostedUsage,
)
from intake_platform.model_lanes.keys import ProviderApiKey, ProviderKeyNotSet
from intake_platform.model_lanes.model import ProviderId

from intake_hosted_lanes.catalogue import ResolvedProvider

__all__ = ["OpenAICompatibleProvider"]

CHAT_PATH: Final = "/v1/chat/completions"
TRANSCRIPTION_PATH: Final = "/v1/audio/transcriptions"
SPEECH_PATH: Final = "/v1/audio/speech"
MODELS_PATH: Final = "/v1/models"
DEFAULT_TIMEOUT_S: Final = 30.0
PROBE_TIMEOUT_S: Final = 3.0
#: The speech route's raw-PCM response format: 24 kHz, 16-bit, mono.
_SPEECH_FORMAT: Final = "pcm"
#: Finish reasons that are not a complete answer.
_NOT_AN_ANSWER: Final = frozenset({"length", "content_filter"})


def _int(raw: object) -> int:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0 else 0


def _status_code(status: int) -> str:
    if status in (401, 403):
        return "hosted_lane_key_rejected"
    if status == 429:
        return "hosted_lane_rate_limited"
    return f"hosted_lane_http_{status}"


class OpenAICompatibleProvider:
    """One hosted provider over the OpenAI v1 wire shape.

    ``policy_for`` maps the call's data class to the egress policy for its
    tier; ``inner`` is the transport seam a contract test fills with
    ``httpx.MockTransport`` (CI never reaches a provider); ``proxy`` is the
    deployment's forward proxy, which the egress module refuses for any
    personal data class (ADR-025, INT-203).
    """

    def __init__(
        self,
        provider: ResolvedProvider,
        *,
        key: Callable[[], ProviderApiKey],
        policy_for: Callable[[DataClass], EgressPolicy],
        transfer_log: TransferLog | None = None,
        proxy: str | None = None,
        inner: httpx.BaseTransport | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._provider = provider
        self._key = key
        self._policy_for = policy_for
        self._transfer_log = transfer_log
        self._proxy = proxy
        self._inner = inner
        self._timeout_s = timeout_s

    @property
    def provider_id(self) -> ProviderId:
        return self._provider.spec.id

    # -- the wire ----------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        try:
            key = self._key()
        except ProviderKeyNotSet:
            raise HostedLaneUnavailable("hosted_key_not_set") from None
        return {"Authorization": f"Bearer {key.reveal()}"}

    def _send(
        self,
        data_class: DataClass,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
        form: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> httpx.Response:
        headers = self._headers()
        context = EgressContext(purpose=EgressPurpose.HOSTED_MODEL_INFERENCE, data_class=data_class)
        try:
            client = guarded_client(
                self._policy_for(data_class),
                context,
                inner=self._inner,
                transfer_log=self._transfer_log,
                proxy=self._proxy,
                timeout=timeout_s if timeout_s is not None else self._timeout_s,
            )
        except ValueError:
            # a personal data class may not delegate its pin to the proxy
            raise HostedLaneUnavailable("hosted_lane_egress_refused") from None
        response: httpx.Response | None = None
        failure: str | None = None
        with client:
            try:
                response = client.request(
                    method,
                    f"{self._provider.base_url}{path}",
                    headers=headers,
                    json=json_body,
                    files=files,
                    data=form,
                )
            except EgressDenied:
                failure = "hosted_lane_egress_denied"
            except httpx.TimeoutException:
                failure = "hosted_lane_timeout"
            except httpx.HTTPError:
                failure = "hosted_lane_unreachable"
        # Raised after the except blocks close, so nothing is chained: an
        # httpx error holds the request, and the request holds the key.
        if response is None:
            raise HostedLaneUnavailable(failure or "hosted_lane_unreachable")
        if not 200 <= response.status_code < 300:
            raise HostedLaneUnavailable(
                _status_code(response.status_code), status=response.status_code
            )
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Mapping[str, Any]:
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HostedLaneUnavailable("hosted_lane_bad_response") from None
        if not isinstance(body, dict):
            raise HostedLaneUnavailable("hosted_lane_bad_response")
        return body

    # -- the three lanes ---------------------------------------------------------------

    def chat_json(
        self,
        *,
        instructions: str,
        data_block: str,
        schema_name: str,
        json_schema: Mapping[str, Any],
        data_class: DataClass,
        model: str,
    ) -> HostedChat:
        """One schema-constrained completion; instructions and data never share
        a message. A refusal, a truncation or an empty answer is ``NO_ANSWER``."""
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": data_block},
            ],
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": dict(json_schema), "strict": True},
            },
        }
        payload = self._json(self._send(data_class, "POST", CHAT_PATH, json_body=body))
        try:
            choice = payload["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError):
            raise HostedLaneUnavailable("hosted_lane_bad_response") from None
        if not isinstance(message, dict) or not isinstance(choice, dict):
            raise HostedLaneUnavailable("hosted_lane_bad_response")
        text = message.get("content")
        if (
            message.get("refusal")
            or choice.get("finish_reason") in _NOT_AN_ANSWER
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise HostedLaneUnavailable(NO_ANSWER)
        served = payload.get("model")
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return HostedChat(
            text=text,
            model=served if isinstance(served, str) else "",
            usage=HostedUsage(
                input_tokens=_int(usage.get("prompt_tokens")),
                output_tokens=_int(usage.get("completion_tokens")),
            ),
        )

    def transcribe(
        self, audio: bytes, *, audio_format: str, data_class: DataClass, model: str
    ) -> HostedTranscript:
        """Turkish transcription. ``audio_format`` is the container's short name
        (the upload part's file extension, which is how the route recognises
        the encoding); the bytes are sent and not kept."""
        if not audio_format.isalnum() or len(audio_format) > 8:
            raise HostedLaneUnavailable("hosted_lane_audio_format_refused")
        response = self._send(
            data_class,
            "POST",
            TRANSCRIPTION_PATH,
            files={"file": (f"speech.{audio_format}", audio, "application/octet-stream")},
            form={"model": model, "language": "tr", "response_format": "json"},
        )
        payload = self._json(response)
        text = payload.get("text")
        if not isinstance(text, str):
            raise HostedLaneUnavailable("hosted_lane_bad_response")
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        seconds = usage.get("seconds") if usage.get("type") == "duration" else None
        audio_seconds = (
            float(seconds)
            if isinstance(seconds, int | float) and not isinstance(seconds, bool) and seconds >= 0
            else 0.0
        )
        return HostedTranscript(
            text=text,
            model=model,
            usage=HostedUsage(
                input_tokens=_int(usage.get("input_tokens")),
                output_tokens=_int(usage.get("output_tokens")),
                audio_seconds=audio_seconds,
            ),
        )

    def speech(self, text_tr: str, *, data_class: DataClass, model: str) -> HostedSpeech:
        """Synthesise already-normalised Turkish (the caller has refused every
        numeral — invariant 22); raw PCM back, never a container."""
        spec = self._provider.spec
        response = self._send(
            data_class,
            "POST",
            SPEECH_PATH,
            json_body={
                "model": model,
                "input": text_tr,
                "voice": spec.tts_voice,
                "response_format": _SPEECH_FORMAT,
            },
        )
        pcm = response.content
        if not pcm:
            raise HostedLaneUnavailable(NO_ANSWER)
        if len(pcm) % 2:
            raise HostedLaneUnavailable("hosted_lane_bad_response")
        return HostedSpeech(
            pcm_s16le=pcm,
            sample_rate_hz=spec.tts_sample_rate_hz,
            channels=1,
            model=model,
            usage=HostedUsage(characters=len(text_tr)),
        )

    def probe(self, model: str) -> bool:
        """The identity probe: the provider answers for this exact snapshot.
        No inference, no payload, no cost — and False on any failure."""
        try:
            response = self._send(
                DataClass.NON_PERSONAL, "GET", f"{MODELS_PATH}/{model}", timeout_s=PROBE_TIMEOUT_S
            )
            body = self._json(response)
        except HostedLaneUnavailable:
            return False
        return body.get("id") == model
