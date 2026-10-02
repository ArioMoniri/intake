"""On-demand cached George (ElevenLabs) clips for SCRIPTED questions — the
ON-DEMAND variant of ADR-028, dev lane only.

ADR-028 pre-synthesises the FIXED scripted set into a clip cache at BUILD time
and the device plays cached clips. This route does the same synthesis on
DEMAND for a scripted question whose ``text_tr`` has no cached George clip yet:
it generates once, caches the result addressed by ``sha256(text_tr)`` (the same
``protocols.dsl.clip_text_hash`` the offline manifest uses), and serves it, so a
second request for the same text is a cache HIT that never dials the vendor a
second time. It gives George's voice to dynamically-selected scripted questions
(e.g. a department pack) without pre-baking every one.

**Why this does not weaken invariant 19 (self-hosted PHI path).** Exactly the
ADR-028 argument, and no more: the vendor is reached only for *scripted,
verbatim, non-patient* ``text_tr`` that is committed to this repository in plain
text (invariant 10), never a patient answer, never patient audio, never a
follow-up phrase quoting patient words. It is the DEV lane (opt-in phrase
``INTAKE_DEV_GEORGE_TTS=explicit-yes``), never the production ``residency_tr``
profile and never the runtime PHI path. The generated clip is agent speech, a
cache of scripts — invariant 3 governs *patient* audio, which this route never
touches.

**Layered guards — what each layer is responsible for.**

- *A patient principal* (INT-326). The route resolves the same principal every
  patient route does (``intake_api.auth``: DPoP/OTP or the dev bearer) and
  refuses anyone else — 401 before the lane even says whether it is configured.
- *Scripted-only* (the "patient words never reach the vendor" guarantee) is
  enforced HERE (INT-326): ``text_tr`` is admitted only when its
  ``clip_text_hash`` is a row of a compiled clip manifest
  (``intake_api.dev_voice_guard``), otherwise 422 and no dial. The mobile
  client's nominal ``ScriptedTr`` (``apps/mobile/src/lib/dialogue/georgeClip.ts``)
  stays as defence in depth; the server no longer trusts it.
- *Delivery context, not delivery settings* (INT-415). The body names one of
  seven contexts (routine by default). The server maps it to its own
  delivery-profile table (``voice_clips.delivery``), so the device never holds
  or sends a voice setting. ``red`` is refused, and so is any compiled rule
  script under any label: RED audio is pre-positioned on the device and never
  fetched on demand (invariant 21). An instrument item is spoken only in the
  instrument profile. The profile id and version are part of the cache key.
- *A per-principal budget* (INT-326) on the INT-012 Redis token bucket; every
  authenticated request costs a token, an empty bucket is 429, an unreachable
  store is 503.
- *Absent in production* (INT-326): with ``INTAKE_ENV`` prod the route is not
  mounted (``intake_api.app``) and no wiring is built, whatever the dev flags say.
- *Invariant 22* (no numeral crosses into a TTS) is enforced HERE too, before
  the wire, by ``voice_clips.gateway.assert_speakable_tr`` — a patient-shaped
  answer carrying a numeral is refused before any dial.
- *Key handling* mirrors ADR-028: the key is read from the environment only
  (``TTS_ELEVENLABS_API_KEY``), never a source file, never a log, never an
  exception (files/10 §2). The MOBILE DEVICE never holds the key — generation
  goes through this server route, which reads it from the process environment.
- *Fail closed.* No dev flag, or no key/base, or no readable compiled catalogue,
  or the vendor unreachable/refused → a 4xx/5xx the mobile treats as
  "unavailable" and falls back to the self-hosted TTS. Never a crash, never a
  blocked turn.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import redis
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from intake_platform.security.rate_limit import RateLimitExceeded, TokenBucketLimiter
from protocols.dsl import clip_text_hash
from pydantic import BaseModel, ConfigDict, Field
from voice_clips.audio import wav_bytes
from voice_clips.delivery import (
    DEFAULT_DELIVERY_CONTEXT,
    DeliveryContext,
    DeliveryProfile,
    delivery_profile,
)
from voice_clips.gateway import (
    ENV_ELEVENLABS_BASE,
    ENV_ELEVENLABS_KEY,
    ElevenLabsClipGenGateway,
    TtsError,
    TtsGateway,
    UnspeakableScriptError,
    assert_speakable_tr,
)

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import dev_voice_scripted
from intake_api.dev_voice_guard import (
    ScriptedCatalogue,
    george_budget,
    intake_env_is_prod,
    scripted_catalogue_from_env,
)
from intake_api.settings import DEFAULT_REDIS_URL

__all__ = [
    "ENV_DEV_GEORGE",
    "ENV_GEORGE_CACHE_DIR",
    "GEORGE_CLIP_PATH",
    "GEORGE_VOICE_ID",
    "MAX_SCRIPTED_LEN",
    "GeorgeClipCache",
    "GeorgeClipIn",
    "GeorgeWiring",
    "george_wiring_from_env",
    "router",
]

#: George — the voice id ADR-028 pins; the model (eleven_multilingual_v2) and
#: the numeral-normaliser-off request are the gateway's, unchanged.
GEORGE_VOICE_ID: Final = "JBFqnCBsd6RMkjVDRZzb"

#: Opt-in dev phrase. Anything but the exact string leaves the route
#: unconfigured (503), on the INT-131 ``explicit-yes`` precedent.
ENV_DEV_GEORGE: Final = "INTAKE_DEV_GEORGE_TTS"
ENV_GEORGE_CACHE_DIR: Final = "INTAKE_DEV_GEORGE_CACHE_DIR"
_EXPLICIT_YES: Final = "explicit-yes"

GEORGE_CLIP_PATH: Final = "/dev/voice/george-clip"

#: Scripted question text is short; a longer body is refused at the boundary —
#: a paragraph is not a scripted question and has no business on this route.
MAX_SCRIPTED_LEN: Final = 600

_DEFAULT_CACHE_DIR: Final = ".cache/george-clips"


router = APIRouter(tags=["dev-voice"])


@dataclass
class GeorgeClipCache:
    """A clip cache addressed by delivery profile and ``sha256(text_tr)``, over
    an injected gateway.

    The address is ``<profile key>/<clip_text_hash(text_tr)>``. The hash is the
    exact function the ADR-028 offline manifest keys on, and the profile key
    (``delivery.<context>@v<version>``, INT-415) keeps one text delivered two
    ways as two clips. The vendor is dialled AT MOST once per distinct (text,
    profile), and a retuned profile is a miss rather than a replay of the old
    tuning.
    """

    gateway: TtsGateway
    cache_dir: Path
    voice_id: str = GEORGE_VOICE_ID

    def ensure(self, text_tr: str, profile: DeliveryProfile) -> tuple[bytes, bool]:
        """Return ``(wav_body, cache_hit)``.

        The WAV framing is the sanctioned :func:`voice_clips.audio.wav_bytes`,
        never assembled here — agent-audio encoding lives in the one module
        invariant 3's guard allows it (files/03 §4.2), not ad hoc in a service.
        The on-disk cache is addressed by the profile key and
        ``clip_text_hash(text_tr)``, with no file extension, so this service
        names no audio artefact.

        Raises :class:`UnspeakableScriptError` (a numeral, invariant 22, or markup) or another
        :class:`TtsError` (vendor unreachable/refused); the route maps both to a
        refusal that never echoes the key.
        """
        assert_speakable_tr(text_tr)  # invariant 22 — before the vendor, always
        folder = self.cache_dir / profile.key
        path = folder / clip_text_hash(text_tr)
        if path.is_file():
            return path.read_bytes(), True
        speech = self.gateway.synthesise(text_tr=text_tr, voice_id=self.voice_id, profile=profile)
        wav = wav_bytes(speech)
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav)
        return wav, False


@dataclass
class GeorgeWiring:
    """What the route needs; ``None`` on ``app.state.george`` means the surface
    is unconfigured and every request fails closed (503).

    ``catalogue`` is the server-side allow-list and ``budget`` the per-principal
    token bucket (INT-326); neither has a default, so a wiring cannot exist
    without both doors."""

    cache: GeorgeClipCache
    catalogue: ScriptedCatalogue
    budget: TokenBucketLimiter


def george_wiring_from_env(redis_url: str = DEFAULT_REDIS_URL) -> GeorgeWiring | None:
    """Build the dev George wiring, or ``None`` (fail closed).

    Never in production (INT-326): checked FIRST, so a prod process does not
    even read the vendor key, whatever the dev flags say. Otherwise off unless
    (1) the opt-in phrase is set AND (2) the ADR-028 ElevenLabs base and key are
    both present in the environment AND (3) a compiled clip catalogue is
    readable and non-empty. Any gap → ``None`` → the route answers 503 and the
    mobile falls back to the self-hosted lane. The key is read here from the
    environment only and is never logged (files/10 §2).
    """
    if intake_env_is_prod():
        return None
    if os.environ.get(ENV_DEV_GEORGE) != _EXPLICIT_YES:
        return None
    base = os.environ.get(ENV_ELEVENLABS_BASE, "").strip()
    key = os.environ.get(ENV_ELEVENLABS_KEY, "").strip()
    if not (base and key):
        return None
    catalogue = scripted_catalogue_from_env()
    if catalogue is None:
        return None
    cache_dir = Path(os.environ.get(ENV_GEORGE_CACHE_DIR) or _DEFAULT_CACHE_DIR)
    return GeorgeWiring(
        cache=GeorgeClipCache(
            gateway=ElevenLabsClipGenGateway(base_url=base, api_key=key),
            cache_dir=cache_dir,
        ),
        catalogue=catalogue,
        budget=george_budget(redis_url),
    )


class GeorgeClipIn(BaseModel):
    """The wire body: one scripted question ``text_tr`` and the delivery
    context it is spoken in. ``extra='forbid'`` so no voice id, model or voice
    setting can be smuggled in: George and the delivery-profile table are fixed
    server-side, and the device names a context, never a setting (INT-415)."""

    model_config = ConfigDict(extra="forbid")

    text_tr: str = Field(min_length=1, max_length=MAX_SCRIPTED_LEN)
    delivery_context: DeliveryContext = Field(
        default=DEFAULT_DELIVERY_CONTEXT,
        description="How the text is delivered (INT-414/INT-415); never changes the words.",
    )


def _delivery_refusal(wiring: GeorgeWiring, payload: GeorgeClipIn) -> JSONResponse | None:
    """INT-415's two delivery doors; ``None`` admits.

    RED is never served on demand. Invariant 21 pre-positions the RED script
    on the device and triggers it over the data channel, so a RED clip fetched
    at RED time would be exactly the media round trip the invariant removes.
    The route refuses the ``red`` label AND any compiled rule script, whatever
    it is labelled. An instrument item is spoken only in the instrument
    profile. The text is never echoed (invariant 6).
    """
    pinned = wiring.catalogue.pinned_context(payload.text_tr)
    if "red" in (payload.delivery_context, pinned):
        return JSONResponse({"error": "red_not_on_demand"}, status_code=422)
    if pinned is not None and pinned != payload.delivery_context:
        return JSONResponse({"error": "delivery_context_mismatch"}, status_code=422)
    return None


async def _refusal(
    wiring: GeorgeWiring, account_id: str, payload: GeorgeClipIn
) -> JSONResponse | None:
    """The INT-326 doors after authentication, in order; ``None`` admits.

    The budget is charged FIRST, so a refused request still costs a token
    (hammering the door with off-catalogue text is not free). No refusal
    echoes the text (invariant 6), and none of them reaches the vendor.
    """
    text_tr = payload.text_tr
    try:
        # sync Redis client, so the call hops off the event loop (INT-131 precedent)
        await asyncio.to_thread(wiring.budget.consume, "user", account_id)
    except RateLimitExceeded as exc:
        return JSONResponse(
            {"error": "george_rate_limited"},
            status_code=429,
            headers={"Retry-After": str(int(exc.retry_after_s) + 1)},
        )
    except redis.RedisError:
        # no budget can be checked, so none is granted (fail closed)
        return JSONResponse({"error": "george_budget_unavailable"}, status_code=503)
    try:
        assert_speakable_tr(text_tr)
    except UnspeakableScriptError:
        # invariant 22 (a numeral) and INT-424 (SSML or an audio tag) keep their
        # own, more specific refusal
        return JSONResponse({"error": "not_speakable"}, status_code=422)
    if not wiring.catalogue.admits(text_tr):
        # not a compiled clip-manifest row: never scripted text, never dialled
        return JSONResponse({"error": "not_in_catalogue"}, status_code=422)
    return _delivery_refusal(wiring, payload)


@router.post(GEORGE_CLIP_PATH, dependencies=[dev_voice_scripted()])
async def george_clip(payload: GeorgeClipIn, request: Request, principal: Principal) -> Response:
    """Synthesise (or serve from cache) one scripted question clip in George's
    voice. Patient-only, catalogue-only, budgeted, dev-gated, fail-closed, and
    never echoes the vendor key."""
    account, _ = require_patient(principal)
    wiring: GeorgeWiring | None = getattr(request.app.state, "george", None)
    if wiring is None:
        # No dev flag / no key / no catalogue — the mobile treats this as
        # "unavailable" and falls back to the self-hosted TTS (ADR-028 posture).
        return JSONResponse({"error": "george_unconfigured"}, status_code=503)
    refusal = await _refusal(wiring, account.account_id, payload)
    if refusal is not None:
        return refusal
    try:
        wav, hit = wiring.cache.ensure(payload.text_tr, delivery_profile(payload.delivery_context))
    except UnspeakableScriptError:
        # a numeral or markup reached the boundary — refuse, do not normalise
        return JSONResponse({"error": "not_speakable"}, status_code=422)
    except TtsError:
        # vendor unreachable/refused; the key is never in the message (files/10
        # §2). The turn is never blocked — the mobile falls back.
        return JSONResponse({"error": "george_unavailable"}, status_code=502)
    # The body is a WAV built by voice_clips (agent speech, invariant 3), but the
    # api service names no audio content type: invariant 3's audio-retention
    # guard keeps `audio/*` literals out of every module but the clip cache, and
    # the allow-list is locked to exactly that grant. The mobile client reads the
    # bytes opaquely and plays them by file URI (apps/mobile georgeClip.ts), so it
    # never inspects this content type — octet-stream is both honest and inert.
    return Response(
        content=wav,
        media_type="application/octet-stream",
        headers={"X-George-Cache": "hit" if hit else "miss"},
    )
