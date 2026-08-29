"""The TTS seam: one adapter interface, two implementations, no guessing.

ADR-006 (provider-agnostic gateways) and CLAUDE.md §How we work: every
external speech call goes through an adapter interface with recorded fixtures
for tests, and CI never dials a live model. This module is that seam for the
compile-time clip path (files/03 §4.9.1 row 10).

**Configuration fails closed.** Exactly one of ``INTAKE_TTS_ENDPOINT`` (a live
self-hosted TTS) or ``INTAKE_TTS_RECORDED_DIR`` (recorded responses — the CI
and dev path) must be set. Neither has a default, on the ``INTAKE_CLAMD_HOST``
precedent rather than the ``MINIO_ENDPOINT`` one: a guessed scanner is a scan
that did not happen, and a guessed TTS is a clip nobody synthesised. Both set
at once is refused too — an ambiguous source for the audio a patient hears is
not a preference to resolve quietly. Two lanes exist on the team GPU box today
(docs/runbooks/team-gpu-server.md) and neither is load-bearing here: nothing in
this module assumes any endpoint is up.

**No numeral reaches any model.** :func:`assert_speakable_tr` is the last gate
before the wire, and it *only* rejects — it never normalises. The compiler
already expanded every digit, unit and dose form to Turkish orthography
(CLAUDE.md invariant 22, files/03 §4.9.6); a second normaliser here would be a
second opinion about what a dose says, which is precisely the hazard. Both
pinned TTS models ship a Turkish-hostile normaliser and both have theirs
disabled, so a digit that got this far would be read out by the English or the
comma-blind branch. Refusing is the only safe answer.
"""

from __future__ import annotations

import base64
import json
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

import httpx
from protocols.dsl import clip_text_hash

from voice_clips.audio import SynthesisedSpeech, wav_to_speech
from voice_clips.errors import ClipCacheError

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "ENV_TTS_ENDPOINT",
    "ENV_TTS_RECORDED_DIR",
    "SYNTHESIS_PATH",
    "HttpTtsGateway",
    "NumeralInScriptError",
    "RecordedSpeechMismatchError",
    "RecordedSpeechMissingError",
    "RecordedTtsGateway",
    "TtsError",
    "TtsGateway",
    "TtsNotConfiguredError",
    "TtsRefusedError",
    "TtsUnavailableError",
    "assert_speakable_tr",
    "tts_gateway_from_env",
]

ENV_TTS_ENDPOINT: Final = "INTAKE_TTS_ENDPOINT"
ENV_TTS_RECORDED_DIR: Final = "INTAKE_TTS_RECORDED_DIR"

#: The dev bridges expose ``POST /synthesize`` returning a WAV body
#: (docs/runbooks/team-gpu-server.md); the production serving path speaks the
#: same shape so one adapter covers both.
SYNTHESIS_PATH: Final = "/synthesize"
DEFAULT_TIMEOUT_S: Final = 30.0

#: A recorded response is one JSON document per scripted string, named by the
#: compiler's own ``text_hash`` so a recording cannot drift from its text.
RECORDING_SUFFIX: Final = ".json"


class TtsError(ClipCacheError):
    """Base for every refusal at the speech-synthesis boundary."""


class TtsNotConfiguredError(TtsError):
    """No unambiguous source of speech. The build stops rather than guessing."""


class TtsUnavailableError(TtsError):
    """The configured endpoint could not be reached."""


class TtsRefusedError(TtsError):
    """The endpoint answered, and the answer was a refusal."""


class RecordedSpeechMissingError(TtsError):
    """No recorded response exists for this text under the recording root."""


class RecordedSpeechMismatchError(TtsError):
    """A recording exists but was made for other text, or another voice."""


class NumeralInScriptError(TtsError):
    """A manifest string still carries a numeral (CLAUDE.md invariant 22)."""


class TtsGateway(Protocol):
    """One scripted string in, one synthesis out. Nothing streams here."""

    def synthesise(self, *, text_tr: str, voice_id: str) -> SynthesisedSpeech: ...


def assert_speakable_tr(text_tr: str) -> None:
    """Refuse any Unicode number character. Never rewrite one.

    The whole ``N`` category, not just ASCII digits: Arabic-Indic digits and
    vulgar fractions reach a TTS normaliser exactly as a ``5`` does, and the
    compiler's expansion is supposed to have removed all of them.
    """
    offenders = sorted({char for char in text_tr if unicodedata.category(char).startswith("N")})
    if offenders:
        raise NumeralInScriptError(
            f"scripted text still carries {''.join(offenders)!r} — the compiler expands "
            "every numeral to Turkish orthography and no TTS in any profile may see "
            "one (CLAUDE.md invariant 22; files/03 §4.9.6). The builder refuses; it "
            "does not normalise, because a second normaliser is a second opinion "
            "about a dose"
        )


@dataclass(frozen=True)
class HttpTtsGateway:
    """A self-hosted TTS reached over HTTP; the endpoint comes from config."""

    endpoint: str
    timeout_s: float = DEFAULT_TIMEOUT_S
    transport: httpx.BaseTransport | None = None

    def synthesise(self, *, text_tr: str, voice_id: str) -> SynthesisedSpeech:
        assert_speakable_tr(text_tr)
        url = f"{self.endpoint.rstrip('/')}{SYNTHESIS_PATH}"
        try:
            with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
                response = client.post(url, json={"text": text_tr, "voice_id": voice_id})
        except httpx.HTTPError as exc:
            raise TtsUnavailableError(
                f"TTS endpoint unreachable ({type(exc).__name__}) — neither GPU lane "
                "is a dependency of this build; configure a reachable endpoint or "
                f"point {ENV_TTS_RECORDED_DIR} at recorded responses"
            ) from exc
        if response.status_code // 100 != 2:
            raise TtsRefusedError(
                f"TTS endpoint answered HTTP {response.status_code} for voice {voice_id!r}"
            )
        return wav_to_speech(response.content)


@dataclass(frozen=True)
class RecordedTtsGateway:
    """Replays recorded responses. The CI path, and the dev path with no GPU.

    A recording carries the text it was made for, so a recording of paraphrased
    or edited script is a refusal rather than a clip: invariant 10 says the
    scripted turn is spoken verbatim, and a cache is only as verbatim as the
    audio somebody put in it.
    """

    root: Path

    def synthesise(self, *, text_tr: str, voice_id: str) -> SynthesisedSpeech:
        assert_speakable_tr(text_tr)
        text_hash = clip_text_hash(text_tr)
        path = self.root / f"{text_hash}{RECORDING_SUFFIX}"
        if not path.is_file():
            raise RecordedSpeechMissingError(
                f"no recorded response for text_hash {text_hash} under {self.root}"
            )
        recorded = json.loads(path.read_text(encoding="utf-8"))
        if recorded.get("voice_id") != voice_id:
            raise RecordedSpeechMismatchError(
                f"recording {text_hash} was made for voice {recorded.get('voice_id')!r}, "
                f"not {voice_id!r}"
            )
        if recorded.get("text_tr") != text_tr:
            raise RecordedSpeechMismatchError(
                f"recording {text_hash} carries text the manifest does not — a clip is "
                "the script verbatim (CLAUDE.md invariant 10)"
            )
        return wav_to_speech(base64.b64decode(recorded["body_base64"]))


def tts_gateway_from_env() -> TtsGateway:
    """Select the one configured gateway, or refuse."""
    endpoint = os.environ.get(ENV_TTS_ENDPOINT, "").strip()
    recorded = os.environ.get(ENV_TTS_RECORDED_DIR, "").strip()
    if bool(endpoint) == bool(recorded):
        raise TtsNotConfiguredError(
            f"set exactly one of {ENV_TTS_ENDPOINT} (a self-hosted TTS endpoint) or "
            f"{ENV_TTS_RECORDED_DIR} (recorded responses; the CI and dev path). "
            "Neither is guessed and neither has a default: a guessed TTS is a clip "
            "nobody synthesised, and two sources is an ambiguous voice"
        )
    if endpoint:
        return HttpTtsGateway(endpoint=endpoint)
    root = Path(recorded)
    if not root.is_dir():
        raise TtsNotConfiguredError(f"{ENV_TTS_RECORDED_DIR}={recorded!r} is not a directory")
    return RecordedTtsGateway(root=root)
