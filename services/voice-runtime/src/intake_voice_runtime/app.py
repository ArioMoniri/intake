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

INT-515 deploys the worker on the synthetic host (``infra/staging``) and adds
six checks, each named on every profile and passed where the profile has no
use for it:

- ``sfu`` — the LiveKit SFU answers its own liveness path (speech only);
- ``lane_asr``, ``lane_tts``, ``lane_llm`` — each lane the profile needs
  resolves in the lane registry (:mod:`intake_voice_runtime.lanes`); the
  registry's refusal code, or ``lane_registry_absent`` while INT-428's package
  is not in the image, is on ``/metrics`` as ``voice_lane_ready``;
- ``core_dumps_off`` and ``memory_locked`` — invariant 3's process facts
  (:mod:`intake_voice_runtime.hardening`); a typed worker holds no audio, so
  only the first binds it.

It also adds the synthetic probe, ``POST /probe/synthetic-turn``
(:mod:`intake_voice_runtime.synthetic_turn`): one scripted turn on the bound
lanes, answered as ids and timings, at most once per
:data:`~intake_voice_runtime.synthetic_turn.PROBE_MIN_INTERVAL_S`. The worker
publishes no port and no edge routes to it, so only a caller inside the
deployment's networks can ask.

So an unwired process answers ``/healthz`` 200 and ``/readyz`` 503 naming each
missing binding. That is the shape CLAUDE.md asks for when a dependency is
absent: build the mechanism, wire the gate, make it fail closed, leave the
content empty — never a mock on a serving path.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from intake_platform.health import ReadinessCheck, mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.otel import JsonLogFormatter, setup_otel
from intake_platform.safety_inbox import PUMP_INTERVAL, SafetyInboxOutbox, SafetyInboxStore
from intake_platform.security import SecurityHeadersMiddleware
from intake_platform.voice_control import VoiceControlReader

from intake_voice_runtime.adapters.asr import Transcriber
from intake_voice_runtime.extraction.gateway import ExtractionGateway
from intake_voice_runtime.hardening import ProcessHardening
from intake_voice_runtime.lanes import LANES_FOR_PROFILE, LaneGate, SpeechLane
from intake_voice_runtime.metrics import VOICE_SYNTHETIC_TURNS_TOTAL
from intake_voice_runtime.ports import ClipStore, RoomTokenSource, SpeechSynthesizer
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.synthetic_turn import PROBE_MIN_INTERVAL_S, SyntheticTurn

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


class SfuLiveness(Protocol):
    """Whether the SFU answers (``intake_voice_runtime.sfu.RoomServiceClient``)."""

    def ping(self) -> Awaitable[bool]: ...


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
    #: INT-515: the SFU this worker's rooms live on.
    sfu: SfuLiveness | None = None
    #: INT-515: each lane's readiness, keyed on the lane registry.
    lanes: LaneGate | None = None
    #: INT-515: invariant 3's process facts, as the process set them at start.
    hardening: ProcessHardening | None = None
    #: INT-515: the ASR and extraction lanes the synthetic turn runs on (the
    #: TTS lane is ``synthesizer``), and the voice it speaks with.
    transcriber: Transcriber | None = None
    extraction: ExtractionGateway | None = None
    probe_voice_id: str | None = None

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

    async def sfu_ready() -> bool:
        # INT-515: a speech worker's rooms live on the SFU; a typed one has none.
        if not bound.needs_speech:
            return True
        return bound.sfu is not None and await bound.sfu.ping()

    def lane_ready(lane: SpeechLane) -> ReadinessCheck:
        async def check() -> bool:
            if lane not in LANES_FOR_PROFILE[bound.profile]:
                return True
            if bound.lanes is None:
                return False
            # the registry may read its store or ask a lane who it is: off the loop
            status = await asyncio.to_thread(bound.lanes.status, lane)
            return status.ready

        return ReadinessCheck(f"lane_{lane.value}", check)

    async def core_dumps_off() -> bool:
        # every profile holds transcripts in memory; a core would carry them
        hardening = bound.hardening
        return hardening is not None and hardening.core_dumps_off and hardening.not_dumpable

    async def memory_locked() -> bool:
        # invariant 3's audio buffers exist only on a speech worker
        if not bound.needs_speech:
            return True
        return bound.hardening is not None and bound.hardening.memory_locked

    mount_health(
        app,
        readiness=[
            ReadinessCheck("clip_store", clip_store_ready),
            ReadinessCheck("speech_synthesizer", synthesizer_ready),
            ReadinessCheck("room_token", room_token_ready),
            ReadinessCheck("voice_controls", voice_controls_ready),
            ReadinessCheck("safety_inbox", safety_inbox_ready),
            ReadinessCheck("sfu", sfu_ready),
            *(lane_ready(lane) for lane in SpeechLane),
            ReadinessCheck("core_dumps_off", core_dumps_off),
            ReadinessCheck("memory_locked", memory_locked),
        ],
    )
    _mount_synthetic_turn(app, bound)
    return app


def _mount_synthetic_turn(app: FastAPI, bound: VoiceRuntimeWiring) -> None:
    """``POST /probe/synthetic-turn`` — the runtime's synthetic probe (INT-515).

    A plain ``def`` route, so FastAPI runs the turn's blocking lane calls on its
    worker threads, never on the event loop. One turn at a time, and none
    within :data:`PROBE_MIN_INTERVAL_S` of the last one started.
    """
    lock = threading.Lock()
    last_started: list[float] = []

    @app.post("/probe/synthetic-turn")
    def synthetic_turn() -> JSONResponse:
        with lock:
            now = time.monotonic()
            if last_started and now - last_started[-1] < PROBE_MIN_INTERVAL_S:
                VOICE_SYNTHETIC_TURNS_TOTAL.labels(outcome="rate_limited").inc()
                return JSONResponse(status_code=429, content={"code": "probe_rate_limited"})
            last_started[:] = [now]
            report = SyntheticTurn(
                synthesizer=bound.synthesizer,
                transcriber=bound.transcriber,
                extraction=bound.extraction,
                voice_id=bound.probe_voice_id,
            ).run()
        outcome = "completed" if report.completed else "incomplete"
        VOICE_SYNTHETIC_TURNS_TOTAL.labels(outcome=outcome).inc()
        return JSONResponse(status_code=200 if report.completed else 503, content=report.to_json())
