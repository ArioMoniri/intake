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
- ``speech_synthesizer`` — the adapter now exists (INT-095,
  :mod:`intake_voice_runtime.adapters.speech`, files/03 §4.9.1 rows 10–12) and
  builds from ``INTAKE_TTS_ENDPOINT`` or ``INTAKE_TTS_RECORDED_DIR``, neither
  of which has a default. What is still absent is a *deployment* that sets
  one, so the check stays and reports not-ready rather than constructing an
  adapter pointed at a guess.
- ``room_token`` — ``intake_platform.room_tokens`` mints the LiveKit JWT
  (INT-090), but no HTTP route serves one to a worker (INT-103's finding).

A fourth check arrived with INT-182: ``voice_controls`` — the per-tenant kill
switch, default profile and canary the session router reads at every session
start. It has no default either: the store is named by
``INTAKE_VOICE_CONTROL_REDIS_URL`` in the deployment, and a speech worker that
cannot read it could not honour the kill switch.

A fifth arrived with INT-406: ``safety_inbox`` — the store every RED's clinic
inbox entry is written to (``INTAKE_SAFETY_INBOX_REDIS_URL``, the store the
console's Safety queue reads). Unlike the speech checks it holds on **both**
profiles: a typed session fires REDs too, and a worker that cannot put a RED
in front of the clinic must not take a session (files/10 §9.1 invariant 49).
The process owns one :class:`~intake_platform.safety_inbox.SafetyInboxOutbox`
(``VoiceRuntimeWiring.outbox``) — every session's clinician route puts there —
and, with a store wired, the app runs the pump that writes it for as long as it
serves, and gives the pump its last pass on the way down.

So an unwired process answers ``/healthz`` 200 and ``/readyz`` 503 naming each
missing binding. That is the shape CLAUDE.md asks for when a dependency is
absent: build the mechanism, wire the gate, make it fail closed, leave the
content empty — never a mock on a serving path.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.otel import JsonLogFormatter, setup_otel
from intake_platform.safety_inbox import PUMP_INTERVAL, SafetyInboxOutbox, SafetyInboxStore
from intake_platform.security import SecurityHeadersMiddleware
from intake_platform.voice_control import VoiceControlReader

from intake_voice_runtime.ports import ClipStore, RoomTokenSource, SpeechSynthesizer
from intake_voice_runtime.profiles import VoiceProfile

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

    ``profile`` decides *which* bindings are required, and INT-096 is why it
    exists. ``typed`` is the kill-switch target, and a target that can never
    report ready is not one: a worker serving keyboards has no clip store, no
    TTS and no LiveKit room to join, so demanding all three would leave the
    safer state permanently un-routable. The three checks stay in the list and
    say why they passed, rather than disappearing — a readiness report that
    silently shrinks is one nobody can compare across deployments.
    """

    clip_store: ClipStore | None = None
    synthesizer: SpeechSynthesizer | None = None
    room_token_source: RoomTokenSource | None = None
    profile: VoiceProfile = VoiceProfile.RESIDENCY_TR
    #: INT-182: where the per-tenant kill switch, default profile and canary
    #: are read at every session start (``INTAKE_VOICE_CONTROL_REDIS_URL``,
    #: the same store the admin console writes). A speech worker without it
    #: could not honour the kill switch, so it is not ready.
    voice_controls: VoiceControlReader | None = None
    #: INT-406: where the clinician route's entries are written. Every
    #: profile needs it — the RED path is the same on a keyboard.
    safety_inbox: SafetyInboxStore | None = None
    #: The process's one outbox: the worker binds every session's
    #: ``SafetyInboxNotifier`` to it, and the app pumps it into ``safety_inbox``.
    outbox: SafetyInboxOutbox = field(default_factory=SafetyInboxOutbox)

    @property
    def needs_speech(self) -> bool:
        """Whether this worker's profile has a speech path at all."""
        return self.profile is not VoiceProfile.TYPED


def create_app(wiring: VoiceRuntimeWiring | None = None) -> FastAPI:
    """The FastAPI surface. The Talker itself runs in the agent worker."""
    _setup_observability()
    bound = wiring or VoiceRuntimeWiring()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # INT-406: the outbox pump. No store, no pump, and /readyz says so.
        pump: threading.Thread | None = None
        if bound.safety_inbox is not None:
            pump = threading.Thread(
                target=bound.outbox.pump,
                args=(bound.safety_inbox,),
                name="safety-inbox-pump",
                daemon=True,
            )
            pump.start()
        try:
            yield
        finally:
            if pump is not None:
                bound.outbox.stop()
                pump.join(timeout=PUMP_INTERVAL.total_seconds() * 5)
                left = len(bound.outbox.pending())
                if left:
                    # a count only (invariant 6); the entries' age already pages
                    logger.error("safety inbox entries unwritten at stop", extra={"count": left})

    app = FastAPI(title="intake-voice-runtime", lifespan=lifespan)
    app.state.wiring = bound
    app.add_middleware(SecurityHeadersMiddleware)
    mount_http_metrics(app, SERVICE_NAME)

    async def clip_store_ready() -> bool:
        return not bound.needs_speech or bound.clip_store is not None

    async def synthesizer_ready() -> bool:
        return not bound.needs_speech or bound.synthesizer is not None

    async def room_token_ready() -> bool:
        # The room token joins a LiveKit *media* room. A typed worker has no
        # media to carry — files/03 §4.4 gives the profile a dash in the
        # turn-taking and TTS columns — so it needs no room and no token.
        return not bound.needs_speech or bound.room_token_source is not None

    async def voice_controls_ready() -> bool:
        # INT-182. A typed worker is already the kill switch's target; a
        # speech worker must be able to read the switch before it may take a
        # session, or "without a deploy" would silently stop being true.
        return not bound.needs_speech or bound.voice_controls is not None

    async def safety_inbox_ready() -> bool:
        # INT-406, invariant 49: no profile is exempt — a typed RED reaches
        # the clinic through the same inbox as a spoken one.
        return bound.safety_inbox is not None

    mount_health(
        app,
        readiness=[
            ReadinessCheck("clip_store", clip_store_ready),
            ReadinessCheck("speech_synthesizer", synthesizer_ready),
            ReadinessCheck("room_token", room_token_ready),
            ReadinessCheck("voice_controls", voice_controls_ready),
            ReadinessCheck("safety_inbox", safety_inbox_ready),
        ],
    )
    return app
