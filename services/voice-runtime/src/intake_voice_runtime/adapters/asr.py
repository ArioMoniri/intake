"""The ASR adapter behind ``SpeechGateway`` — files/03 §4.9.1 rows 1-2.

The mechanism ships; the PHI-path lane does not, and that is the honest state
of the stack rather than a gap to fill later.

- **Row 1**, ``nvidia/nemotron-3.5-asr-streaming-0.6b`` (OpenMDW-1.1), is the
  primary streaming ASR §4.9.1 pins. It is served nowhere in this project and
  carries no registry row, so :func:`~intake_voice_runtime.adapters.pins.resolve_pin`
  refuses it outright.
- **Row 2**, ``turkmedstt/whisper-large-v3-turkish-medical``, is the shadow /
  whole-session fallback. It *is* served on the dev bridge, and its registry
  row records its licence as ``UNVERIFIED (card tag apache-2.0, no blob)`` —
  a badge, which files/03 §4.9.0 rule 3 refuses.

So :class:`HttpTranscriber` takes ``row`` and ``phi_path``, and a
``phi_path=True`` lane calls ``require_phi_path_pin``, which raises for both
rows today. A dev/synthetic lane (``phi_path=False``, the default) is built and
records the unverified pin it is running — which is what the registry's own
``host`` fields already say in prose, made mechanical.

Everything else mirrors :mod:`intake_voice_runtime.adapters.speech`: one wire
shape (``POST /transcribe``, ``application/octet-stream`` in, ``{"text": …}``
out — the shape ``apps/mobile/src/lib/voice.ts`` already speaks), a recorded
lane addressed by ``sha256(audio)`` for CI, a public-internet refusal before
any transport, and no default for where audio goes.

**Nothing here retains audio.** :meth:`HttpTranscriber.transcribe` takes bytes,
posts them and keeps no reference; :class:`Transcription` carries text and a
model id. CLAUDE.md invariant 3's buffers, mlocking and zeroing live in the
media plane (INT-090's ``audio_retention_guard``), not in an HTTP adapter, and
this module has no attribute an audio buffer could occupy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

import httpx

from intake_voice_runtime.adapters.pins import (
    ModelPin,
    ModelStackRow,
    require_phi_path_pin,
    resolve_pin,
)
from intake_voice_runtime.adapters.speech import (
    DEFAULT_TIMEOUT_S,
    RECORDING_SUFFIX,
    SpeechNotConfigured,
    SpeechUnavailable,
    refuse_external_host,
)

__all__ = [
    "ENV_ASR_ENDPOINT",
    "ENV_ASR_RECORDED_DIR",
    "TRANSCRIBE_PATH",
    "HttpTranscriber",
    "RecordedTranscriber",
    "RecordedTranscriptMismatch",
    "RecordedTranscriptMissing",
    "Transcriber",
    "Transcription",
    "transcriber_from_env",
]

ENV_ASR_ENDPOINT: Final = "INTAKE_ASR_ENDPOINT"
ENV_ASR_RECORDED_DIR: Final = "INTAKE_ASR_RECORDED_DIR"

TRANSCRIBE_PATH: Final = "/transcribe"


class RecordedTranscriptMissing(LookupError):
    """No recorded transcript for this audio under the recording root."""


class RecordedTranscriptMismatch(LookupError):
    """A recording exists and was made for other audio."""


@dataclass(frozen=True, repr=False)
class Transcription:
    """What one ASR call returns: the text, and which model produced it.

    ``__repr__`` shows the digest and the model, never the text — this is the
    one artefact on the ASR seam where the value *is* the patient's narrative
    (CLAUDE.md invariant 6).
    """

    text: str
    model: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return f"Transcription(model={self.model!r}, sha256={self.sha256!r})"

    def __str__(self) -> str:
        return self.__repr__()


@runtime_checkable
class Transcriber(Protocol):
    """The port: audio in, one :class:`Transcription` out.

    :attr:`pin` is part of the port rather than an implementation detail: a
    lane that carries patient speech has to be able to say which files/03
    §4.9.1 row it is, and ``None`` says "this lane names no row and may not
    carry PHI".
    """

    pin: ModelPin | None

    def transcribe(self, audio: bytes) -> Transcription: ...


def _bind_pin(row: ModelStackRow | None, *, phi_path: bool) -> ModelPin | None:
    """Resolve the row's pin, refusing when a PHI lane is not licence-clean."""
    if row is None:
        if phi_path:
            raise SpeechNotConfigured(
                "a PHI-path ASR lane must name its files/03 §4.9.1 row — an unnamed "
                "model is an unpinned model (CLAUDE.md invariant 19)"
            )
        return None
    if phi_path:
        return require_phi_path_pin(row)
    return resolve_pin(row)


@dataclass(init=False)
class HttpTranscriber:
    """A self-hosted ASR reached over HTTP."""

    endpoint: str
    row: ModelStackRow | None
    phi_path: bool
    timeout_s: float
    transport: httpx.BaseTransport | None
    pin: ModelPin | None

    def __init__(
        self,
        endpoint: str,
        *,
        row: ModelStackRow | None = None,
        phi_path: bool = False,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # The host refusal runs first: an unreachable-by-construction host
        # should be refused whether or not the pin resolves.
        self.endpoint = refuse_external_host(endpoint)
        self.row = row
        self.phi_path = phi_path
        self.timeout_s = timeout_s
        self.transport = transport
        self.pin = _bind_pin(row, phi_path=phi_path)

    def transcribe(self, audio: bytes) -> Transcription:
        try:
            with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
                response = client.post(
                    f"{self.endpoint}{TRANSCRIBE_PATH}",
                    content=audio,
                    headers={"Content-Type": "application/octet-stream"},
                )
        except httpx.HTTPError as exc:
            raise SpeechUnavailable(
                f"the ASR endpoint did not answer ({type(exc).__name__}). The audio is "
                "deliberately not echoed and not retained (CLAUDE.md invariants 3, 6)"
            ) from None
        if response.status_code // 100 != 2:
            raise SpeechUnavailable(f"the ASR endpoint answered HTTP {response.status_code}")
        body = response.json()
        text = body.get("text")
        if not isinstance(text, str):
            raise SpeechUnavailable("the ASR endpoint returned no 'text' string")
        model = body.get("model")
        return Transcription(
            text=text.strip(),
            model=model if isinstance(model, str) else (self.pin.pinned_id if self.pin else ""),
        )


@dataclass(init=False)
class RecordedTranscriber:
    """Replay a committed transcript, addressed by the audio's own digest."""

    root: Path
    pin: ModelPin | None

    def __init__(self, root: Path, *, row: ModelStackRow | None = None) -> None:
        self.root = root
        self.pin = None if row is None else resolve_pin(row)

    @staticmethod
    def key(audio: bytes) -> str:
        return hashlib.sha256(audio).hexdigest()

    def transcribe(self, audio: bytes) -> Transcription:
        digest = self.key(audio)
        path = self.root / f"{digest}{RECORDING_SUFFIX}"
        if not path.is_file():
            raise RecordedTranscriptMissing(
                f"no recorded transcript under {self.root.name} for this audio. Record "
                f"one, or point {ENV_ASR_ENDPOINT} at a self-hosted endpoint — nothing "
                "is invented to fill the gap"
            )
        recorded = json.loads(path.read_text(encoding="utf-8"))
        if recorded.get("audio_sha256") != digest:
            raise RecordedTranscriptMismatch(
                "the recording was made for other audio; a recording that has drifted "
                "from its call is not a recording of it"
            )
        return Transcription(text=str(recorded["text"]), model=str(recorded.get("model", "")))


def transcriber_from_env(
    environ: Mapping[str, str],
    *,
    row: ModelStackRow | None = None,
    phi_path: bool = False,
) -> Transcriber:
    """Resolve the one configured lane, or refuse to choose one."""
    endpoint = environ.get(ENV_ASR_ENDPOINT, "").strip()
    recorded = environ.get(ENV_ASR_RECORDED_DIR, "").strip()
    if bool(endpoint) == bool(recorded):
        raise SpeechNotConfigured(
            f"set exactly one of {ENV_ASR_ENDPOINT} (a self-hosted ASR endpoint) or "
            f"{ENV_ASR_RECORDED_DIR} (recorded transcripts; the CI and no-GPU dev "
            "path). Neither has a default: a guessed ASR endpoint is a transcription "
            "nobody performed"
        )
    if endpoint:
        return HttpTranscriber(endpoint, row=row, phi_path=phi_path)
    return RecordedTranscriber(Path(recorded), row=row)
