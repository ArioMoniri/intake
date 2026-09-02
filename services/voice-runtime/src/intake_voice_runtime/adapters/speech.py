"""The TTS adapter behind ``SpeechGateway`` — files/03 §4.9.1 rows 10-12.

ADR-006: every external speech call goes through an adapter interface with
recorded fixtures for tests, and CI never dials a model. This module is the
**runtime** half of that seam — the dynamic path of §4.9.1 row 11 and the
low-footprint fallback of row 12 — and it implements
:class:`~intake_voice_runtime.ports.SpeechSynthesizer`, which is the port
``SpeechRouter`` already speaks.

Its compile-time sibling is ``packages/voice-clips``' ``TtsGateway`` (row 10,
pre-synthesising every scripted string at ``protocols compile --voice``). The
two are deliberately separate modules on the same wire shape: one builds a
cache offline against a manifest, the other answers a turn. They share the
environment variables so a bridge is configured once, and they share the rule
that matters — **no numeral reaches any model** (CLAUDE.md invariant 22).

Three refusals, all before the wire:

1. **A numeral.** :func:`~intake_voice_runtime.talker.speech.assert_no_numeral`
   runs first, and it only rejects — it never normalises. Both pinned models
   ship a Turkish-hostile normaliser and both have theirs disabled, so a digit
   that got this far would be read out by the English or the comma-blind
   branch. A second normaliser here would be a second opinion about a dose.
2. **Any host on the public internet.** Not a deny-list of vendor names —
   :func:`refuse_external_host` refuses *everything* that is not loopback, a
   private/link-local address, or a cluster-internal name. That is invariant
   19 stated positively: a self-hosted lane is by definition not on the public
   internet, so naming the four vendors files/03 §1 deletes would be a
   blocklist that a fifth vendor walks past. It also means this module spells
   no vendor hostname at all, which is what ``scripts/ci/assert_no_vendor_calls.sh``
   exists to keep true. The egress allow-list (files/10 §4, default deny) is
   the other enforcement point and carries no model or speech destination in
   its ``phi_path`` tier; a test asserts that from the other side.
3. **A guess about where speech comes from.** Exactly one of
   ``INTAKE_TTS_ENDPOINT`` or ``INTAKE_TTS_RECORDED_DIR``. Neither has a
   default, on ``voice_clips.gateway``'s own precedent: a guessed TTS is a
   sentence nobody synthesised, and two sources at once is an ambiguous voice.

**Selecting a tier is not this module's job.** files/03 §4.9.1 row 12 is chosen
*at session start*, never mid-session ("two voices mid-session breaks voice
identity"), and which tier a deployment starts on is the lane-selection
question INT-249 measured and another issue owns. This adapter takes one
endpoint and speaks to it.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from intake_voice_runtime.talker.speech import assert_no_numeral

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "ENV_TTS_ENDPOINT",
    "ENV_TTS_RECORDED_DIR",
    "RECORDING_SUFFIX",
    "SELF_HOSTED_SUFFIXES",
    "SYNTHESIS_PATH",
    "ExternalHostRefused",
    "HttpSpeechSynthesizer",
    "RecordedSpeechMismatch",
    "RecordedSpeechMissing",
    "RecordedSpeechSynthesizer",
    "SpeechNotConfigured",
    "SpeechUnavailable",
    "refuse_external_host",
    "speech_synthesizer_from_env",
]

ENV_TTS_ENDPOINT: Final = "INTAKE_TTS_ENDPOINT"
ENV_TTS_RECORDED_DIR: Final = "INTAKE_TTS_RECORDED_DIR"

#: The dev bridges expose ``POST /synthesize`` returning a WAV body
#: (docs/runbooks/team-gpu-server.md); the production serving path speaks the
#: same shape, so one adapter covers both.
SYNTHESIS_PATH: Final = "/synthesize"
DEFAULT_TIMEOUT_S: Final = 30.0
RECORDING_SUFFIX: Final = ".json"

#: Name suffixes a self-hosted deployment legitimately uses: a Kubernetes
#: service, a docker-compose service name, an mDNS host, or an internal zone.
#: A single-label host (no dot at all) is permitted for the same reason — it
#: cannot be a public FQDN.
SELF_HOSTED_SUFFIXES: Final[tuple[str, ...]] = (
    ".local",
    ".internal",
    ".svc",
    ".svc.cluster.local",
    ".cluster.local",
)


class SpeechNotConfigured(RuntimeError):
    """No unambiguous source of speech. Nothing is guessed."""


class SpeechUnavailable(RuntimeError):
    """The configured endpoint did not answer, or answered a refusal."""


class ExternalHostRefused(RuntimeError):
    """A public-internet host was configured for a speech lane.

    Refused before any transport is consulted, so there is no environment in
    which one is reachable. Reaching a model over the public internet is what
    the all-self-hosted constraint deleted (files/00 §0b; CLAUDE.md invariant
    19), and adding a destination is an egress allow-list row plus a human
    decision (files/10 §4), never an environment variable.
    """


class RecordedSpeechMissing(LookupError):
    """No recorded response for this text under the recording root."""


class RecordedSpeechMismatch(LookupError):
    """A recording exists and was made for other text, or another voice."""


def _is_self_hosted_address(host: str) -> bool:
    """True for an address a self-hosted deployment can legitimately use."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host or host.endswith(SELF_HOSTED_SUFFIXES)
    # ``is_global`` rather than ``not is_private``: it is the one predicate
    # that covers loopback, RFC 1918, link-local, CGNAT and the reserved
    # documentation ranges in a single reading, and its negation is exactly
    # "not reachable from the public internet". files/10 §4 denies IP literals
    # for *egress*; this is the opposite direction — a literal is how a
    # self-hosted lane on a loopback forward is addressed today.
    return not address.is_global


def refuse_external_host(endpoint: str) -> str:
    """Return the endpoint, or refuse it. Runs before any client is built.

    Default deny, and deliberately **not** a list of vendor names: a blocklist
    of the four vendors files/03 §1 deletes is a blocklist a fifth vendor walks
    straight past, and it would put those hostnames into the tree that
    ``scripts/ci/assert_no_vendor_calls.sh`` exists to keep them out of.
    """
    host = (httpx.URL(endpoint).host or "").casefold()
    if not host:
        raise SpeechNotConfigured(f"{endpoint!r} names no host")
    if not _is_self_hosted_address(host):
        raise ExternalHostRefused(
            f"host {host!r} is on the public internet. Every model and speech lane is "
            "self-hosted (files/00 §0b; CLAUDE.md invariant 19), so a speech endpoint "
            "is loopback, a private address or a cluster-internal name — never a "
            "public FQDN. Reaching one would be a cross-border transfer nobody "
            "registered and a destination the egress allow-list does not carry "
            "(files/10 §4)"
        )
    return endpoint.rstrip("/")


@dataclass(frozen=True)
class HttpSpeechSynthesizer:
    """A self-hosted TTS reached over HTTP. One endpoint, no ladder."""

    endpoint: str
    timeout_s: float = DEFAULT_TIMEOUT_S
    transport: httpx.BaseTransport | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint", refuse_external_host(self.endpoint))

    def synthesize(self, text_tr: str, voice_id: str) -> bytes:
        assert_no_numeral(text_tr)
        url = f"{self.endpoint}{SYNTHESIS_PATH}"
        try:
            with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
                response = client.post(url, json={"text": text_tr, "voice_id": voice_id})
        except httpx.HTTPError as exc:
            raise SpeechUnavailable(
                f"the TTS endpoint did not answer ({type(exc).__name__}). The request "
                "body is deliberately not echoed (CLAUDE.md invariant 6)"
            ) from None
        if response.status_code // 100 != 2:
            raise SpeechUnavailable(
                f"the TTS endpoint answered HTTP {response.status_code} for voice {voice_id!r}"
            )
        return response.content


@dataclass(frozen=True)
class RecordedSpeechSynthesizer:
    """Replay committed audio. The CI lane, and the dev lane with no GPU.

    A recording carries the text and the voice it was made for, so a recording
    of edited script is a refusal rather than a clip: invariant 10 says the
    scripted turn is spoken verbatim, and a cache is only as verbatim as what
    somebody put in it.
    """

    root: Path

    @staticmethod
    def key(text_tr: str, voice_id: str) -> str:
        """``sha256(text_tr, voice_id)`` — files/03 §4.9.1 row 10's own key."""
        return hashlib.sha256(f"{text_tr}\x00{voice_id}".encode()).hexdigest()

    def synthesize(self, text_tr: str, voice_id: str) -> bytes:
        assert_no_numeral(text_tr)
        path = self.root / f"{self.key(text_tr, voice_id)}{RECORDING_SUFFIX}"
        if not path.is_file():
            raise RecordedSpeechMissing(
                f"no recorded speech under {self.root.name} for this text and voice "
                f"{voice_id!r}. Record one, or point {ENV_TTS_ENDPOINT} at a "
                "self-hosted endpoint — nothing is synthesised to fill the gap"
            )
        recorded = json.loads(path.read_text(encoding="utf-8"))
        if recorded.get("voice_id") != voice_id:
            raise RecordedSpeechMismatch(
                f"the recording was made for voice {recorded.get('voice_id')!r}, not {voice_id!r}"
            )
        if recorded.get("text_tr") != text_tr:
            raise RecordedSpeechMismatch(
                "the recording carries text this call does not — a clip is the script "
                "verbatim (CLAUDE.md invariant 10)"
            )
        return base64.b64decode(recorded["body_base64"])


def speech_synthesizer_from_env(
    environ: Mapping[str, str],
) -> HttpSpeechSynthesizer | RecordedSpeechSynthesizer:
    """Resolve the one configured lane, or refuse to choose one."""
    endpoint = environ.get(ENV_TTS_ENDPOINT, "").strip()
    recorded = environ.get(ENV_TTS_RECORDED_DIR, "").strip()
    if bool(endpoint) == bool(recorded):
        raise SpeechNotConfigured(
            f"set exactly one of {ENV_TTS_ENDPOINT} (a self-hosted TTS endpoint) or "
            f"{ENV_TTS_RECORDED_DIR} (recorded responses; the CI and no-GPU dev path). "
            "Neither has a default: a guessed TTS is a sentence nobody synthesised, "
            "and two sources at once is an ambiguous voice"
        )
    if endpoint:
        return HttpSpeechSynthesizer(endpoint=endpoint)
    return RecordedSpeechSynthesizer(root=Path(recorded))
