"""The worker as the deployment runs it: environment in, wired app out (INT-515).

``uvicorn intake_voice_runtime.serve:app_from_env --factory`` is the staging
image's process (``infra/staging/Dockerfile.voice-runtime``). The factory does
two things in order:

1. **hardens the process** (:func:`~intake_voice_runtime.hardening.
   harden_process`) before anything else is allocated, so every page that
   follows is locked and no core can be written (invariant 3);
2. **binds what the environment names, and nothing it does not**
   (:func:`wiring_from_env`). Every binding has a variable and no default; an
   absent or malformed one leaves the binding empty, logs which binding and the
   class of the refusal (never a value), and ``/readyz`` names it. There is no
   guessed address anywhere in this module.

What the staging compose sets, and what each binds:

- ``INTAKE_VOICE_CONTROL_REDIS_URL`` → ``voice_controls`` (the INT-182 kill switch);
- ``INTAKE_SAFETY_INBOX_REDIS_URL`` → ``safety_inbox`` (INT-406, every RED);
- ``INTAKE_LIVEKIT_URL`` + ``LIVEKIT_API_KEY``/``LIVEKIT_API_SECRET`` → ``sfu``
  (the RoomService client) and ``room_token_source`` (the agent's own token,
  INT-090's grant: microphone source, ``canPublishData`` false);
- ``INTAKE_MODEL_LANES_REDIS_URL`` and the rest of INT-428's variables → the
  lane registry (:func:`~intake_voice_runtime.lanes.lane_gate_from_env`).

What it does **not** set yet: a TTS, ASR or extraction lane. INT-095's
self-hosted adapters bind from ``INTAKE_TTS_ENDPOINT``/``INTAKE_ASR_ENDPOINT``/
``INTAKE_EXTRACTION_ENDPOINT`` when a host serves them (a private address
only); the hosted lanes arrive with INT-428/INT-442/INT-443. Until then the
lane checks say why, and the synthetic turn stops at its first stage.
``INTAKE_VOICE_PROBE_VOICE_ID`` names the voice the turn speaks with; it has no
default because a voice id is the lane's vocabulary, not this service's.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

import httpx
from fastapi import FastAPI
from intake_platform.room_tokens import LiveKitCredentials, RoomTokenError, mint_room_token
from intake_platform.safety_inbox import safety_inbox_store_from_env
from intake_platform.voice_control import voice_control_store_from_env

from intake_voice_runtime.adapters.asr import Transcriber, transcriber_from_env
from intake_voice_runtime.adapters.speech import (
    ExternalHostRefused,
    SpeechNotConfigured,
    speech_synthesizer_from_env,
)
from intake_voice_runtime.app import VoiceRuntimeWiring, create_app
from intake_voice_runtime.extraction.errors import ExtractionRefused
from intake_voice_runtime.extraction.gateway import ExtractionGateway, extraction_gateway_from_env
from intake_voice_runtime.hardening import ProcessHardening, harden_process
from intake_voice_runtime.lanes import LaneGate, lane_gate_from_env
from intake_voice_runtime.ports import SpeechSynthesizer
from intake_voice_runtime.sfu import AGENT_IDENTITY, RoomServiceClient

__all__ = [
    "ENV_LIVEKIT_URL",
    "ENV_PROBE_VOICE_ID",
    "AgentRoomTokens",
    "app_from_env",
    "wiring_from_env",
]

logger = logging.getLogger("intake_voice_runtime.serve")

#: The SFU's server API, inside the deployment (``http://livekit:7880`` on staging).
ENV_LIVEKIT_URL: Final = "INTAKE_LIVEKIT_URL"
#: The voice the synthetic turn speaks with, in the TTS lane's own vocabulary.
ENV_PROBE_VOICE_ID: Final = "INTAKE_VOICE_PROBE_VOICE_ID"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AgentRoomTokens:
    """``RoomTokenSource``: the agent's join token for one session room."""

    credentials: LiveKitCredentials
    clock: Callable[[], datetime] = field(default=_utc_now)

    def __call__(self, session_id: str) -> str:
        return mint_room_token(
            session_id, AGENT_IDENTITY, self.clock(), credentials=self.credentials
        )


def _unbound(binding: str, err: Exception) -> None:
    # the binding and the refusal's class: never the value that was refused
    logger.warning("voice binding unbound", extra={"binding": binding, "error": type(err).__name__})


def _internal_url(raw: str) -> str | None:
    url = httpx.URL(raw)
    if (
        url.scheme not in ("http", "https")
        or not url.host
        or url.query
        or url.path not in ("", "/")
    ):
        return None
    return str(url).rstrip("/")


def _sfu(env: Mapping[str, str]) -> tuple[RoomServiceClient, AgentRoomTokens] | None:
    raw = env.get(ENV_LIVEKIT_URL, "").strip()
    if not raw:
        return None
    base = _internal_url(raw)
    if base is None:
        _unbound("sfu", ValueError(ENV_LIVEKIT_URL))
        return None
    try:
        credentials = LiveKitCredentials.from_env(env)
    except RoomTokenError as err:
        _unbound("sfu", err)
        return None
    return RoomServiceClient(base, credentials), AgentRoomTokens(credentials)


def _synthesizer(env: Mapping[str, str]) -> SpeechSynthesizer | None:
    try:
        return speech_synthesizer_from_env(env)
    except (SpeechNotConfigured, ExternalHostRefused) as err:
        _unbound("speech_synthesizer", err)
        return None


def _transcriber(env: Mapping[str, str]) -> Transcriber | None:
    try:
        return transcriber_from_env(env)
    except (SpeechNotConfigured, ExternalHostRefused) as err:
        _unbound("transcriber", err)
        return None


def _extraction(env: Mapping[str, str]) -> ExtractionGateway | None:
    try:
        return extraction_gateway_from_env(env)
    except ExtractionRefused as err:
        _unbound("extraction", err)
        return None


def wiring_from_env(
    env: Mapping[str, str],
    *,
    hardening: ProcessHardening,
    lane_gate: LaneGate | None = None,
) -> VoiceRuntimeWiring:
    """Every binding the environment names; every other one empty and logged."""
    try:
        voice_controls = voice_control_store_from_env(env)
    except ValueError as err:
        _unbound("voice_controls", err)
        voice_controls = None
    try:
        safety_inbox = safety_inbox_store_from_env(env)
    except ValueError as err:
        _unbound("safety_inbox", err)
        safety_inbox = None
    sfu = _sfu(env)
    probe_voice = env.get(ENV_PROBE_VOICE_ID, "").strip() or None
    return VoiceRuntimeWiring(
        # the clip byte store has no reader yet (packages/voice-clips writes
        # clips; nothing fetches them), so the binding stays empty and says so
        clip_store=None,
        synthesizer=_synthesizer(env),
        room_token_source=sfu[1] if sfu else None,
        voice_controls=voice_controls,
        safety_inbox=safety_inbox,
        sfu=sfu[0] if sfu else None,
        lanes=lane_gate if lane_gate is not None else lane_gate_from_env(env),
        hardening=hardening,
        transcriber=_transcriber(env),
        extraction=_extraction(env),
        probe_voice_id=probe_voice,
    )


def app_from_env() -> FastAPI:
    """The uvicorn factory: harden first, then bind, then serve."""
    hardening = harden_process()
    return create_app(wiring_from_env(os.environ, hardening=hardening))
