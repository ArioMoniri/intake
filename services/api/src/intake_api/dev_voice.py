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

- *Scripted-only* (the "patient words never reach the vendor" guarantee) is
  enforced at the CLIENT boundary, because only the client knows which text was
  composed from the catalog (``speech.ts``) versus derived from a patient. The
  mobile George client accepts a nominal ``ScriptedTr`` produced solely from an
  ``IntakeQuestion`` and refuses any other string
  (``apps/mobile/src/lib/dialogue/georgeClip.ts``). This route is the dev egress
  the client calls; it is dev-gated so nothing else can reach the vendor.
- *Invariant 22* (no numeral crosses into a TTS) is enforced HERE too, before
  the wire, by ``voice_clips.gateway.assert_speakable_tr`` — a patient-shaped
  answer carrying a numeral is refused before any dial.
- *Key handling* mirrors ADR-028: the key is read from the environment only
  (``TTS_ELEVENLABS_API_KEY``), never a source file, never a log, never an
  exception (files/10 §2). The MOBILE DEVICE never holds the key — generation
  goes through this server route, which reads it from the process environment.
- *Fail closed.* No dev flag, or no key/base, or the vendor unreachable/refused
  → a 4xx/5xx the mobile treats as "unavailable" and falls back to the
  self-hosted TTS. Never a crash, never a blocked turn.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from protocols.dsl import clip_text_hash
from pydantic import BaseModel, ConfigDict, Field
from voice_clips.gateway import (
    ENV_ELEVENLABS_BASE,
    ENV_ELEVENLABS_KEY,
    ElevenLabsClipGenGateway,
    NumeralInScriptError,
    TtsError,
    TtsGateway,
    assert_speakable_tr,
)

from intake_api.consent_guard import dev_voice_scripted

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
    "pcm_to_wav",
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


class _Speech(Protocol):
    """The three fields this module reads off a synthesis; avoids importing
    numpy/soundfile-backed ``SynthesisedSpeech`` into the api at runtime.
    Read-only members so a frozen ``SynthesisedSpeech`` satisfies it."""

    @property
    def pcm_s16le(self) -> bytes: ...
    @property
    def sample_rate_hz(self) -> int: ...
    @property
    def channels(self) -> int: ...


def pcm_to_wav(speech: _Speech) -> bytes:
    """Wrap raw signed 16-bit LE PCM in a canonical RIFF/WAVE header.

    ElevenLabs ``pcm_<rate>`` is headerless; expo-av plays a container, so the
    dev route hands back a WAV. This is agent speech (a scripted clip), which
    invariant 3 explicitly permits writing — it governs *patient* audio.
    """
    pcm = speech.pcm_s16le
    rate = int(speech.sample_rate_hz)
    channels = int(speech.channels)
    byte_rate = rate * channels * 2
    block_align = channels * 2
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, byte_rate, block_align, 16)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


@dataclass
class GeorgeClipCache:
    """A ``sha256(text_tr)``-addressed clip cache over an injected gateway.

    The address is ``clip_text_hash`` — the exact function the ADR-028 offline
    manifest keys on — so the same scripted text always maps to the same file
    and the vendor is dialled AT MOST once per distinct text.
    """

    gateway: TtsGateway
    cache_dir: Path
    voice_id: str = GEORGE_VOICE_ID

    def ensure(self, text_tr: str) -> tuple[bytes, bool]:
        """Return ``(wav_bytes, cache_hit)``.

        Raises :class:`NumeralInScriptError` (invariant 22) or another
        :class:`TtsError` (vendor unreachable/refused); the route maps both to a
        refusal that never echoes the key.
        """
        assert_speakable_tr(text_tr)  # invariant 22 — before the vendor, always
        path = self.cache_dir / f"{clip_text_hash(text_tr)}.wav"
        if path.is_file():
            return path.read_bytes(), True
        speech = self.gateway.synthesise(text_tr=text_tr, voice_id=self.voice_id)
        wav = pcm_to_wav(speech)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav)
        return wav, False


@dataclass
class GeorgeWiring:
    """What the route needs; ``None`` on ``app.state.george`` means the surface
    is unconfigured and every request fails closed (503)."""

    cache: GeorgeClipCache


def george_wiring_from_env() -> GeorgeWiring | None:
    """Build the dev George wiring, or ``None`` (fail closed).

    Off unless (1) the opt-in phrase is set AND (2) the ADR-028 ElevenLabs base
    and key are both present in the environment. Any gap → ``None`` → the route
    answers 503 and the mobile falls back to the self-hosted lane. The key is
    read here from the environment only and is never logged (files/10 §2).
    """
    if os.environ.get(ENV_DEV_GEORGE) != _EXPLICIT_YES:
        return None
    base = os.environ.get(ENV_ELEVENLABS_BASE, "").strip()
    key = os.environ.get(ENV_ELEVENLABS_KEY, "").strip()
    if not (base and key):
        return None
    cache_dir = Path(os.environ.get(ENV_GEORGE_CACHE_DIR) or _DEFAULT_CACHE_DIR)
    return GeorgeWiring(
        cache=GeorgeClipCache(
            gateway=ElevenLabsClipGenGateway(base_url=base, api_key=key),
            cache_dir=cache_dir,
        )
    )


class GeorgeClipIn(BaseModel):
    """The wire body: one scripted question ``text_tr``. ``extra='forbid'`` so no
    voice id or model can be smuggled in — George is fixed server-side."""

    model_config = ConfigDict(extra="forbid")

    text_tr: str = Field(min_length=1, max_length=MAX_SCRIPTED_LEN)


@router.post(GEORGE_CLIP_PATH, dependencies=[dev_voice_scripted()])
async def george_clip(payload: GeorgeClipIn, request: Request) -> Response:
    """Synthesise (or serve from cache) one scripted question clip in George's
    voice. Dev-gated, fail-closed, and never echoes the vendor key."""
    wiring: GeorgeWiring | None = getattr(request.app.state, "george", None)
    if wiring is None:
        # No dev flag / no key — the mobile treats this as "unavailable" and
        # falls back to the self-hosted TTS (ADR-028 posture, on demand).
        return JSONResponse({"error": "george_unconfigured"}, status_code=503)
    try:
        wav, hit = wiring.cache.ensure(payload.text_tr)
    except NumeralInScriptError:
        # invariant 22: a numeral reached the boundary — refuse, do not normalise
        return JSONResponse({"error": "not_speakable"}, status_code=422)
    except TtsError:
        # vendor unreachable/refused; the key is never in the message (files/10
        # §2). The turn is never blocked — the mobile falls back.
        return JSONResponse({"error": "george_unavailable"}, status_code=502)
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={"X-George-Cache": "hit" if hit else "miss"},
    )
