"""The service's monitoring contract, and its three honest not-readys.

CLAUDE.md invariant 15: every service exposes ``/healthz``, ``/readyz``,
``/metrics`` and ``/version`` via ``packages/intake_platform/health``, emits
OTel through the shared setup, declares its SLOs in ``docs/slo/<service>.yaml``
and has a synthetic probe. All four endpoints and the shared OTel setup are
wired here; the SLO file and the ``voice-runtime`` registry row are committed
alongside.

The readiness checks are the interesting part. Three bindings the Talker needs
have no implementation on this branch, and each is a named check that reports
**not ready** rather than a stand-in that reports healthy:

- ``clip_store`` — the clip byte store is ``packages/voice-clips`` (INT-060),
  which is not on ``origin/main``. The Talker resolves ``clip_id`` from the
  compiler's manifest today; the bytes behind it have nowhere to come from.
- ``speech_synthesizer`` — the self-hosted streaming TTS adapter is INT-095
  (files/03 §4.9.1 rows 10–12). CI never calls a vendor, and there is no
  in-repo TTS to call instead.
- ``room_token`` — ``intake_platform.room_tokens`` mints the LiveKit JWT
  (INT-090), but no HTTP route serves one to a worker (INT-103's finding).

So an unwired process answers ``/healthz`` 200 and ``/readyz`` 503 naming each
missing binding. That is the shape CLAUDE.md asks for when a dependency is
absent: build the mechanism, wire the gate, make it fail closed, leave the
content empty — never a mock on a serving path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import FastAPI
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.otel import JsonLogFormatter, setup_otel
from intake_platform.security import SecurityHeadersMiddleware

from intake_voice_runtime.ports import ClipStore, RoomTokenSource, SpeechSynthesizer

__all__ = ["VoiceRuntimeWiring", "create_app"]

SERVICE_NAME = "voice-runtime"

logger = logging.getLogger("intake_voice_runtime")

_otel_installed = False


def _setup_observability() -> None:
    """Shared OTel setup + JSON logging, once per process (invariant 15)."""
    global _otel_installed
    if _otel_installed:
        return
    setup_otel(SERVICE_NAME)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    _otel_installed = True


@dataclass
class VoiceRuntimeWiring:
    """Everything the worker needs, injectable for tests.

    Every field defaults to ``None`` and every ``None`` is a readiness
    failure — the process comes up so it can be observed, and refuses to be
    routed traffic until each binding exists.
    """

    clip_store: ClipStore | None = None
    synthesizer: SpeechSynthesizer | None = None
    room_token_source: RoomTokenSource | None = None


def create_app(wiring: VoiceRuntimeWiring | None = None) -> FastAPI:
    """The FastAPI surface. The Talker itself runs in the agent worker."""
    _setup_observability()
    bound = wiring or VoiceRuntimeWiring()

    app = FastAPI(title="intake-voice-runtime")
    app.state.wiring = bound
    app.add_middleware(SecurityHeadersMiddleware)
    mount_http_metrics(app, SERVICE_NAME)

    async def clip_store_ready() -> bool:
        return bound.clip_store is not None

    async def synthesizer_ready() -> bool:
        return bound.synthesizer is not None

    async def room_token_ready() -> bool:
        return bound.room_token_source is not None

    mount_health(
        app,
        readiness=[
            ReadinessCheck("clip_store", clip_store_ready),
            ReadinessCheck("speech_synthesizer", synthesizer_ready),
            ReadinessCheck("room_token", room_token_ready),
        ],
    )
    return app
