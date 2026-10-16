"""The TTS seam: one adapter interface, three implementations, no guessing.

ADR-006 (provider-agnostic gateways) and CLAUDE.md §How we work: every
external speech call goes through an adapter interface with recorded fixtures
for tests, and CI never dials a live model. This module is that seam for the
compile-time clip path (files/03 §4.9.1 row 10).

**Configuration fails closed.** Exactly one of ``INTAKE_TTS_ENDPOINT`` (a live
self-hosted TTS), ``INTAKE_TTS_RECORDED_DIR`` (recorded responses — the CI and
dev path), or the offline cloud clip-gen pair ``TTS_ELEVENLABS_BASE_URL`` +
``TTS_ELEVENLABS_API_KEY`` (ADR-028) must be set. None has a default, on the
``INTAKE_CLAMD_HOST`` precedent rather than the ``MINIO_ENDPOINT`` one: a
guessed scanner is a scan that did not happen, and a guessed TTS is a clip
nobody synthesised. Two sources at once is refused too — an ambiguous source
for the audio a patient hears is not a preference to resolve quietly.

**The cloud clip-gen path is OFFLINE ONLY (ADR-028).** INT-319 reintroduces a
cloud vendor for exactly one job: pre-synthesising the FIXED set (scripted
questions, red-flag scripts, instruments — all verbatim, non-patient
``text_tr``) into the clip cache at BUILD time. It is never on the runtime or
PHI path — the runtime speech adapter
(``intake_voice_runtime.adapters.speech``) refuses every public host, so a
session physically cannot reach a vendor — and the cache it fills is played
back with zero per-session egress. That is why this reintroduction does not
weaken CLAUDE.md invariant 19: the vendor touches non-patient text offline and
nothing else. The key is read from the environment only, never a source file or
a log (files/10 §2), and the live call is spend-gated on ``EVAL_BUDGET_USD`` so
a test or CI never takes it. Its licence/terms and the KVKK transfer question
are human blockers (see docs/backlog/blockers.md), and the live path is
``blocked`` until the key lands.

**No numeral reaches any model.** :func:`assert_speakable_tr` is the last gate
before the wire, and it *only* rejects — it never normalises. The compiler
already expanded every digit, unit and dose form to Turkish orthography
(CLAUDE.md invariant 22, files/03 §4.9.6); a second normaliser here would be a
second opinion about what a dose says, which is precisely the hazard. Every TTS
this seam speaks to — the pinned self-hosted models and the cloud vendor alike
— has its own normaliser disabled (the cloud request sends
``apply_text_normalization: "off"``), so a digit that got this far would be read
out by the English or the comma-blind branch. Refusing is the only safe answer.

**Every synthesis names its delivery profile** (INT-415,
:mod:`voice_clips.delivery`). The profile says how the scripted text is
delivered and never changes the text. The cloud clip-gen request carries the
profile's ``voice_settings``. The self-hosted ``/synthesize`` contract has no
delivery controls today, so that adapter sends the text and the voice exactly
as before; docs/voice/on-prem-tts-wiring.md maps each profile to the controls
the pinned self-hosted models do have.
"""

from __future__ import annotations

import base64
import json
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

import httpx
from protocols.dsl import clip_text_hash

from voice_clips.audio import SynthesisedSpeech, wav_to_speech
from voice_clips.errors import ClipCacheError

if TYPE_CHECKING:
    from voice_clips.delivery import DeliveryProfile

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "ELEVENLABS_MODEL_ID",
    "ELEVENLABS_PCM_RATE_HZ",
    "ENV_ELEVENLABS_BASE",
    "ENV_ELEVENLABS_KEY",
    "ENV_EVAL_BUDGET_USD",
    "ENV_TTS_ENDPOINT",
    "ENV_TTS_RECORDED_DIR",
    "SYNTHESIS_PATH",
    "CloudClipGenNotBudgetedError",
    "DeliveryProfileMismatchError",
    "ElevenLabsClipGenGateway",
    "HttpTtsGateway",
    "MarkupInScriptError",
    "NumeralInScriptError",
    "RecordedSpeechMismatchError",
    "RecordedSpeechMissingError",
    "RecordedTtsGateway",
    "TtsError",
    "TtsGateway",
    "TtsNotConfiguredError",
    "TtsRefusedError",
    "TtsUnavailableError",
    "UnspeakableScriptError",
    "assert_numeral_free",
    "assert_speakable_tr",
    "tts_gateway_from_env",
    "wire_text",
]

ENV_TTS_ENDPOINT: Final = "INTAKE_TTS_ENDPOINT"
ENV_TTS_RECORDED_DIR: Final = "INTAKE_TTS_RECORDED_DIR"

#: The offline cloud clip-gen pair (ADR-028). The base URL is env-supplied and
#: never a literal in this tree — ``scripts/ci/assert_no_vendor_calls.sh`` scans
#: for the vendor FQDN everywhere but files/, and a build with no vendor
#: hostname in it is the honest state of "CI never dials a vendor". The key is
#: env-only and never logged (files/10 §2).
ENV_ELEVENLABS_BASE: Final = "TTS_ELEVENLABS_BASE_URL"
ENV_ELEVENLABS_KEY: Final = "TTS_ELEVENLABS_API_KEY"

#: A live paid call is a spend decision, so the offline cloud path refuses
#: unless a budget is set (CLAUDE.md §How we work: live evals run only with
#: ``EVAL_BUDGET_USD``). A test and CI set none of these, so this path is never
#: taken there — the recorded fixture is.
ENV_EVAL_BUDGET_USD: Final = "EVAL_BUDGET_USD"

#: The pinned model id and the raw-PCM sample rate the offline clip-gen
#: requests. Config, not a claim about output. ``eleven_v3`` since INT-449
#: (D20; ADR-034 amended by the owner's pick of the cast take E04, 3 Oct 2026);
#: it was ``eleven_multilingual_v2`` under INT-319/INT-415.
ELEVENLABS_MODEL_ID: Final = "eleven_v3"
ELEVENLABS_PCM_RATE_HZ: Final = 24000

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


class UnspeakableScriptError(TtsError):
    """Scripted text that no TTS may be handed as it stands. Refused, never fixed."""


class NumeralInScriptError(UnspeakableScriptError):
    """A manifest string still carries a numeral (CLAUDE.md invariant 22)."""


class MarkupInScriptError(UnspeakableScriptError):
    """Scripted text carries SSML or an audio tag (INT-424, invariant 10)."""


class CloudClipGenNotBudgetedError(TtsNotConfiguredError):
    """The offline cloud clip-gen path was selected with no ``EVAL_BUDGET_USD``."""


class DeliveryProfileMismatchError(TtsError):
    """A delivery profile tuned for another model than the one this gateway pins."""


class TtsGateway(Protocol):
    """One scripted string in, one synthesis out. Nothing streams here.

    ``profile`` is required, with no default: every caller states how the
    string is delivered (INT-415), so a new call site that forgets is a type
    error rather than a silently routine clip."""

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech: ...


#: The two markup syntaxes the vendor reads inside ``text``: SSML (``<break
#: time=... />`` on eleven_multilingual_v2) and audio tags (``[whispers]`` on
#: eleven_v3 and eleven_v4). Punctuation is not markup: the comma, full stop,
#: semicolon, ellipsis and dash are how text paces itself and stay admitted.
_MARKUP_CHARS: Final = frozenset("<>[]")


def assert_numeral_free(text: str) -> None:
    """Refuse any Unicode number character (invariant 22). Never rewrite one.

    The numeral half of :func:`assert_speakable_tr`, on its own so it can run on
    the exact text a request carries: ``text_tr`` plus a profile's closed-table
    tags (INT-449). The tags are markup by construction, so the whole wire text
    can never pass the markup half; it must still carry no numeral, because the
    wire text is what reaches the model.
    """
    offenders = sorted({char for char in text if unicodedata.category(char).startswith("N")})
    if offenders:
        raise NumeralInScriptError(
            f"scripted text still carries {''.join(offenders)!r} — the compiler expands "
            "every numeral to Turkish orthography and no TTS in any profile may see "
            "one (CLAUDE.md invariant 22; files/03 §4.9.6). The builder refuses; it "
            "does not normalise, because a second normaliser is a second opinion "
            "about a dose"
        )


def assert_speakable_tr(text_tr: str) -> None:
    """Refuse any Unicode number character, and any markup. Never rewrite either.

    The whole ``N`` category, not just ASCII digits: Arabic-Indic digits and
    vulgar fractions reach a TTS normaliser exactly as a ``5`` does, and the
    compiler's expansion is supposed to have removed all of them.

    Markup is refused for the same reason in the other direction (INT-424). An
    audio tag is words the protocol did not author, and the model may voice it
    or turn it into a sound, so it breaks verbatim delivery (invariant 10). An
    SSML break carries a duration numeral (invariant 22). Pacing lives in the
    profile and in punctuation; an expressive-markup model is an ADR question
    (docs/adr/ADR-034), not a string edit.
    """
    assert_numeral_free(text_tr)
    markup = sorted(_MARKUP_CHARS.intersection(text_tr))
    if markup:
        raise MarkupInScriptError(
            f"scripted text carries markup {''.join(markup)!r} — no SSML and no audio tag "
            "rides inside verbatim text_tr (CLAUDE.md invariants 10 and 22); the gate "
            "refuses and never strips"
        )


def wire_text(text_tr: str, profile: DeliveryProfile) -> str:
    """The exact ``text`` an ElevenLabs request carries (INT-449, D20).

    ``text_tr`` passes the whole :func:`assert_speakable_tr` gate first, so a
    tag, an SSML element or a numeral inside the script is refused before any
    tag exists. Then the profile's closed-table tags (its ``wire_prefix``) go
    in front, and the composed text is checked once more for a numeral, since
    it is what reaches the model (invariant 22). The tags come from the served
    delivery table only: a caller names a context, never a tag. RED and
    instrument rows carry none, so their wire text is the script alone.

    The offline clip-gen gateway (ADR-028, which rendered the bundled set) and
    the hosted lane (INT-443) both compose through here, so the two can never
    send different words for the same row.
    """
    assert_speakable_tr(text_tr)
    text = profile.wire_prefix + text_tr
    assert_numeral_free(text)
    return text


@dataclass(frozen=True)
class HttpTtsGateway:
    """A self-hosted TTS reached over HTTP; the endpoint comes from config.

    The ``/synthesize`` contract is ``{text, voice_id}`` and carries no delivery
    control, so the profile shapes nothing on this lane and none of the
    vendor's ``voice_settings`` are sent to it. The pinned self-hosted models
    expose different controls (VoxCPM2: a leading style instruction and
    ``cfg_value``; Freya: none), and docs/voice/on-prem-tts-wiring.md is the
    owner-scoped plan for mapping each profile onto them (INT-415)."""

    endpoint: str
    timeout_s: float = DEFAULT_TIMEOUT_S
    transport: httpx.BaseTransport | None = None

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
        del profile  # no delivery control on this contract (see the class docstring)
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

    A recording may also name the delivery profile it was made under
    (``delivery_profile``, INT-415). If it does, it is replayed only for that
    profile, so a welcome take is never served as a RED clip. A recording that
    names none is profile-free, which is what a self-hosted take is: that lane
    has no delivery controls.
    """

    root: Path

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
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
        made_under = recorded.get("delivery_profile")
        if made_under is not None and made_under != profile.key:
            raise RecordedSpeechMismatchError(
                f"recording {text_hash} was made under delivery profile {made_under!r}, "
                f"not {profile.key!r}"
            )
        return wav_to_speech(base64.b64decode(recorded["body_base64"]))


@dataclass(frozen=True)
class ElevenLabsClipGenGateway:
    """The OFFLINE cloud clip-gen adapter (ADR-028) — never a runtime lane.

    It reaches a public vendor endpoint, which the self-hosted seam refuses on
    purpose; this one is allowed because it runs at BUILD time on non-patient
    scripted text and writes only to the clip cache. The vendor's own text
    normaliser is turned off (``apply_text_normalization: "off"``) so the
    invariant-22 expansion the compiler did is the only one that ran, and the
    API key is carried in a header this module never logs and never puts in an
    exception (files/10 §2). The base URL is supplied by the caller, never a
    literal here, so no vendor hostname enters the tree.

    The request carries the delivery profile's ``voice_settings`` (INT-415). A
    profile tuned for another model is refused before the wire: the settings
    are only meaningful for the model they were tuned on, and changing the
    pinned model is an ADR, not a profile edit.
    """

    base_url: str
    api_key: str
    model_id: str = ELEVENLABS_MODEL_ID
    sample_rate_hz: int = ELEVENLABS_PCM_RATE_HZ
    timeout_s: float = 60.0
    transport: httpx.BaseTransport | None = None

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
        assert_speakable_tr(text_tr)
        if profile.model_id != self.model_id:
            raise DeliveryProfileMismatchError(
                f"delivery profile {profile.key} is tuned for model {profile.model_id!r}, "
                f"and this gateway pins {self.model_id!r}; changing the model needs an ADR"
            )
        url = f"{self.base_url.rstrip('/')}/v1/text-to-speech/{voice_id}"
        try:
            with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
                response = client.post(
                    url,
                    # `output_format` governs the response format — raw signed
                    # 16-bit LE PCM at the requested rate — so no Accept header
                    # naming a media type is needed (and invariant 3's guard
                    # keeps content-type strings out of this package anyway).
                    params={"output_format": f"pcm_{self.sample_rate_hz}"},
                    headers={"xi-api-key": self.api_key},
                    json={
                        # INT-449: the profile's closed-table tags, on the wire
                        # only; text_tr itself is the script, verbatim (inv. 10)
                        "text": wire_text(text_tr, profile),
                        "model_id": self.model_id,
                        # invariant 22: disable the vendor normaliser — the
                        # compiler already expanded every numeral to orthography.
                        "apply_text_normalization": "off",
                        # INT-415: how the words are delivered, never which words
                        "voice_settings": profile.voice_settings.as_request(),
                    },
                )
        except httpx.HTTPError as exc:
            raise TtsUnavailableError(
                f"offline cloud clip-gen endpoint unreachable ({type(exc).__name__}) — the "
                "API key is never echoed (files/10 §2); check the base URL and the network"
            ) from None
        if response.status_code // 100 != 2:
            raise TtsRefusedError(
                f"offline cloud clip-gen endpoint answered HTTP {response.status_code} for "
                f"voice {voice_id!r} (the key is not echoed)"
            )
        pcm = response.content
        if not pcm:
            raise TtsRefusedError("offline cloud clip-gen endpoint returned no audio")
        # ElevenLabs `pcm_<rate>` is raw signed 16-bit LE mono, not a RIFF body,
        # so it is wrapped directly rather than parsed through wav_to_speech.
        return SynthesisedSpeech(pcm_s16le=pcm, sample_rate_hz=self.sample_rate_hz, channels=1)


def tts_gateway_from_env() -> TtsGateway:
    """Select the one configured gateway, or refuse.

    Exactly one of three sources: a self-hosted endpoint, a recorded root, or
    the offline cloud clip-gen pair. The cloud path additionally refuses without
    a spend budget, so a test or CI — which set none of these — never reaches a
    vendor (ADR-028; CLAUDE.md §How we work).
    """
    endpoint = os.environ.get(ENV_TTS_ENDPOINT, "").strip()
    recorded = os.environ.get(ENV_TTS_RECORDED_DIR, "").strip()
    cloud_base = os.environ.get(ENV_ELEVENLABS_BASE, "").strip()
    cloud_key = os.environ.get(ENV_ELEVENLABS_KEY, "").strip()
    cloud = bool(cloud_base and cloud_key)
    chosen = [
        name
        for name, on in (
            ("endpoint", bool(endpoint)),
            ("recorded", bool(recorded)),
            ("cloud", cloud),
        )
        if on
    ]
    if len(chosen) != 1:
        raise TtsNotConfiguredError(
            f"set exactly one of {ENV_TTS_ENDPOINT} (a self-hosted TTS endpoint), "
            f"{ENV_TTS_RECORDED_DIR} (recorded responses; the CI and dev path), or the "
            f"offline cloud clip-gen pair {ENV_ELEVENLABS_BASE}+{ENV_ELEVENLABS_KEY} "
            "(ADR-028). None is guessed and none has a default: a guessed TTS is a clip "
            "nobody synthesised, and two sources is an ambiguous voice"
        )
    if endpoint:
        return HttpTtsGateway(endpoint=endpoint)
    if recorded:
        root = Path(recorded)
        if not root.is_dir():
            raise TtsNotConfiguredError(f"{ENV_TTS_RECORDED_DIR}={recorded!r} is not a directory")
        return RecordedTtsGateway(root=root)
    if not os.environ.get(ENV_EVAL_BUDGET_USD, "").strip():
        raise CloudClipGenNotBudgetedError(
            f"the offline cloud clip-gen path needs {ENV_EVAL_BUDGET_USD} set — a live paid "
            "call is a spend decision (CLAUDE.md §How we work: live evals run only with a "
            "budget), and a test or CI never sets it, so this path is never taken there"
        )
    return ElevenLabsClipGenGateway(base_url=cloud_base, api_key=cloud_key)
